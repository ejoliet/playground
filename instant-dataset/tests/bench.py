"""End-to-end browser benchmark. Run from any directory. Large files stay in .work."""
import argparse
import functools
import json
import os
import platform
import shutil
import sqlite3
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PAGE = "/instant-dataset/"
SAMPLE = ROOT / "examples/observations.csv"


def large_fixture(path):
    """One million fixed-pattern records, exactly 100 decimal MB including header."""
    header = b"id,target,kind,site,note\n"
    with path.open("wb") as out:
        out.write(header)
        for n in range(1_000_000):
            site = ("Palomar", "Paranal", "Maunakea", "LaSilla")[n % 4]
            prefix = f"{n:07d},T{n:07d},field,{site},".encode()
            width = 100 - (len(header) if n == 999_999 else 0)
            out.write(prefix + b"x" * (width - len(prefix) - 1) + b"\n")
    assert path.stat().st_size == 100_000_000


def elapsed(start):
    return round((time.perf_counter() - start) * 1000)


def view(page, selector="#api"):
    page.locator(selector).wait_for(state="visible")
    return page.locator(selector).evaluate("(a) => fetch(a.href).then(r => r.json())")


def upload(page, path):
    start = time.perf_counter()
    page.locator("#file").set_input_files(path)
    page.wait_for_function("name => document.querySelector('#filename').textContent === name && document.querySelector('#grid tbody')", arg=path.name)
    return elapsed(start)


def sql(page, query):
    page.locator("#sqlTab").click()
    page.locator("#sql").fill(query)
    start = time.perf_counter()
    page.locator("#sqlForm button").click()
    page.wait_for_function("q => !document.querySelector('#api').hidden && document.querySelector('#sql').value === q", arg=query)
    ms = elapsed(start)
    data = view(page)
    assert data["view"]["sql"] == query, data
    return data, ms


def benchmark(page, path, big):
    page.evaluate("""() => {let last=performance.now();window.maxTick=0;
        window.timer=setInterval(()=>{const now=performance.now();window.maxTick=Math.max(window.maxTick,now-last);last=now;},50);}""")
    measurements = {"bytes": path.stat().st_size, "open_ms": upload(page, path)}
    measurements["max_timer_gap_ms"] = page.evaluate("() => {clearInterval(window.timer);return Math.round(window.maxTick);}")
    measurements.update(page.locator('#stats').evaluate("el => ({heap_bytes:+el.dataset.heapBytes, db_bytes:+el.dataset.databaseBytes})"))
    first = view(page)
    assert len(first["rows"]) == (50 if big else 12), first
    assert first["rows"][0][0] == ("0000000" if big else "001")
    if big:
        page.locator("#next").click()
        assert view(page)["rows"][0][0] == "0000050"
        override = page.locator("#api").evaluate("(a) => fetch(a.href+'?offset=999999').then(r=>r.json())")
        assert override["rows"][0][0] == "0999999" and not override["hasMore"]
        page.locator("#prev").click()
        assert view(page)["offset"] == 0
    start = time.perf_counter()
    page.locator("#facet").select_option("site")
    page.locator(".bucket").first.wait_for()
    measurements["facet_ms"] = elapsed(start)
    facet = view(page, "#facetApi")
    counts = {row[0]: row[2] for row in facet["rows"]}
    assert counts["Palomar"] == (250000 if big else 5), counts
    page.locator(".bucket").filter(has_text="Palomar").click()
    assert all(row[3] == "Palomar" for row in view(page)["rows"])
    page.locator(".chip").click()
    page.locator("#facet").select_option("")
    view(page)
    page.locator("#search").fill("T0999999" if big else "m51")
    start = time.perf_counter()
    page.locator("#searchForm button").click()
    result = view(page)
    measurements["search_and_json_ms"] = elapsed(start)
    assert len(result["rows"]) == 1 and result["rows"][0][0] == ("0999999" if big else "004")
    result, measurements["group_sql_ms"] = sql(page, "SELECT site, count(*) FROM data GROUP BY site ORDER BY site")
    assert sum(row[1] for row in result["rows"]) == (1000000 if big else 12)
    return measurements


def edge_cases(page, tmp):
    data = tmp / "mixed.json"
    data.write_text('[{"id":1,"k":null},{"id":2,"late":{"a":1}},{"id":3,"k":"two"}]')
    upload(page, data)
    initial = view(page)
    assert initial["rows"] == [[1,None,None],[2,None,'{"a":1}'],[3,"two",None]], initial
    page.locator("#facet").select_option("k")
    page.locator(".bucket").filter(has_text="NULL").click()
    assert len(view(page)["rows"]) == 2
    old = page.locator("#api").get_attribute("href")
    path = tmp / "native.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript("""CREATE TABLE "deep sky"(id INTEGER, bytes BLOB);
            INSERT INTO "deep sky" VALUES(9223372036854775807,x'cafe');
            CREATE VIEW v AS SELECT * FROM "deep sky";""")
    upload(page,path)
    page.locator("#tables").select_option("v")
    assert view(page)["rows"] == [["9223372036854775807",{"hex":"CAFE"}]]
    assert page.evaluate("u=>fetch(u).then(r=>r.status)",old) == 410
    bad = tmp / "bad.csv"
    bad.write_text('id,target\n1,"broken')
    page.locator("#file").set_input_files(bad)
    page.get_by_role("status").filter(has_text="Unclosed quote").wait_for()
    assert page.locator("#filename").inner_text() == path.name
    result, _ = sql(page,'SELECT count(*) FROM "deep sky"')
    assert result["rows"] == [[1]]
    page.locator("#sql").fill('DELETE FROM "deep sky"')
    page.locator("#sqlForm button").click()
    page.get_by_text("Query failed",exact=True).wait_for()
    # Split a UTF-8 character across the 256 KiB decoder boundary.
    path = tmp / "quoted.csv"
    prefix = b'k,v\r\n1,"'
    path.write_bytes(prefix + b'x'*(262143-len(prefix)) + 'é,""q""\r\nline"\r\n'.encode())
    upload(page,path)
    assert view(page)["rows"][0][1].endswith('é,"q"\r\nline')
    # Exercise the drop handler itself through DataTransfer.
    page.evaluate("""() => {const d=new DataTransfer();d.items.add(new File(['n\\n001\\n'],'drop.csv'));
        window.dispatchEvent(new DragEvent('drop',{dataTransfer:d,bubbles:true}));}""")
    page.wait_for_function("document.querySelector('#filename').textContent === 'drop.csv'")
    assert view(page)["rows"] == [["001"]]
    # A second tab can navigate directly to the synthetic API.
    api_tab = page.context.new_page()
    response = api_tab.goto(page.locator("#api").get_attribute("href"))
    assert response.json()["rows"] == [["001"]]
    assert response.from_service_worker
    # A reload releases the data and expires the URL even in the other tab.
    page.reload()
    assert api_tab.reload().status == 410
    api_tab.close()
    bulky = tmp / "bulky.json"
    with bulky.open("wb") as out:
        out.truncate(16 * 1024 ** 2 + 1)
    page.locator("#file").set_input_files(bulky)
    page.get_by_role("status").filter(has_text="JSON import limit").wait_for()
    upload(page, SAMPLE)
    page.locator("#sqlTab").click()
    page.locator("#sql").fill("SELECT zeroblob(3000000)")
    page.locator("#sqlForm button").click()
    page.get_by_role("status").filter(has_text="Result page exceeds").wait_for()
    page.locator("#sql").fill("WITH RECURSIVE seq(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM seq) SELECT sum(x) FROM seq")
    page.locator("#sqlForm button").click()
    page.get_by_role("status").filter(has_text="15-second budget").wait_for()
    assert sql(page, "SELECT 42")[0]["rows"] == [[42]]
    page.context.set_offline(True)
    try:
        assert sql(page, "SELECT count(*) FROM data")[0]["rows"] == [[12]]
    finally:
        page.context.set_offline(False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int,default=1)
    parser.add_argument("--small-only",action="store_true")
    args = parser.parse_args()
    work = ROOT / ".work"
    work.mkdir(exist_ok=True)
    requests = []

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args): requests.append(self.path)

    handler = functools.partial(Handler,directory=str(ROOT.parent))
    server = ThreadingHTTPServer(("127.0.0.1",0),handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with TemporaryDirectory(dir=work) as directory, sync_playwright() as pw:
            tmp = Path(directory)
            big = tmp / "million.csv"
            if not args.small_only: large_fixture(big)
            browser = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM") or shutil.which("chromium"),headless=True)
            print(json.dumps({"chromium":browser.version,"platform":platform.platform(),"runs":args.runs}),flush=True)
            files = [SAMPLE] if args.small_only else [SAMPLE,big]
            for path in files:
                for i in range(args.runs):
                    context = browser.new_context()
                    page = context.new_page()
                    page.on("pageerror", lambda exc: print("PAGE ERROR", exc,flush=True))
                    page.set_default_timeout(90000)
                    page.goto(f"http://127.0.0.1:{server.server_port}{PAGE}")
                    print(json.dumps({"file":path.name,"run":i+1,**benchmark(page,path,path==big)}),flush=True)
                    if path == SAMPLE and i == 0: edge_cases(page,tmp)
                    context.close()
            browser.close()
        assert not any(p.startswith(PAGE+"api/") for p in requests), requests
        print("PASS · UI, JSON endpoints, expected values, endpoint isolation",flush=True)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
