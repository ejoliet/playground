"""Real Chromium experiment, including an HTTP client outside the browser."""
import functools
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent


class BrowserExperiment(unittest.TestCase):
    def test_experiment(self):
        handler = functools.partial(SimpleHTTPRequestHandler, directory=str(ROOT.parent))
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}/{ROOT.name}/'
        evidence = {'tested_at': '2026-11-09', 'pyodide': '0.27.7', 'protocol': '2026-07-28'}
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
                evidence['chromium'] = browser.version
                context = browser.new_context()
                page = context.new_page()
                page.on('console', lambda msg: print('BROWSER:', msg.text))
                page.on('pageerror', lambda error: print('PAGE ERROR:', error))
                page.goto(base)
                page.wait_for_function("document.querySelector('#status').textContent === 'ready' || document.querySelector('#status').textContent.startsWith('error:')", timeout=120000)
                self.assertEqual(page.locator('#status').inner_text(), 'ready')
                evidence['in_page'] = page.evaluate('selfTest()')
                self.assertEqual(len(evidence['in_page']), 5)
                endpoint = page.evaluate('endpoint')
                # Exercise actual UI too.
                page.locator('#text').fill('UI note')
                page.locator('#add button').click()
                page.wait_for_function("document.querySelector('#output').textContent.includes('UI note')")
                other = context.new_page()
                other.goto(base + 'client.html?endpoint=' + endpoint)
                other.wait_for_function('navigator.serviceWorker.controller !== null && !!window.run')
                evidence['separate_tab'] = other.evaluate('run()')
                self.assertEqual(len(evidence['separate_tab']), 5)
                # HTTP outside the browser never reaches the service worker.
                body = page.evaluate("async () => (await import('./client.js')).request('server/discover')")
                headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
                           'MCP-Protocol-Version': '2026-07-28', 'Mcp-Method': 'server/discover'}
                try:
                    urlopen(Request(endpoint, json.dumps(body).encode(), headers), timeout=10)
                    self.fail('Static server unexpectedly accepted POST')
                except HTTPError as exc:
                    evidence['external_http_post'] = exc.code
                    self.assertEqual(exc.code, 501)
                fresh = browser.new_context(service_workers='block')
                outsider = fresh.new_page()
                outsider.goto(base + 'client.html?endpoint=' + endpoint)
                evidence['fresh_context_post'] = outsider.evaluate("async () => (await fetch(endpoint, {method:'POST', body:'{}'})).status")
                self.assertEqual(evidence['fresh_context_post'], 501)
                fresh.close()
                # A second host gets an independent in-memory DB and endpoint.
                second = context.new_page()
                second.goto(base)
                second.wait_for_function("document.querySelector('#status').textContent === 'ready'", timeout=120000)
                count = second.evaluate("async () => (await rpc('tools/call', {name:'note_stats'})).structuredContent.count")
                self.assertEqual(count, 2)
                evidence['second_host_count'] = count
                self.assertNotEqual(second.evaluate('endpoint'), endpoint)
                # Native-browser external automation works by entering the page,
                # but is not a remote MCP HTTP transport.
                evidence['automation_call'] = page.evaluate("async () => (await rpc('tools/call', {name:'note_stats'})).structuredContent")
                page.reload()
                page.wait_for_function("document.querySelector('#status').textContent === 'ready'", timeout=120000)
                evidence['reload_count'] = page.evaluate("async () => (await rpc('tools/call', {name:'note_stats'})).structuredContent.count")
                self.assertEqual(evidence['reload_count'], 2)
                # Previous endpoint no longer has an owner, even with other hosts open.
                evidence['old_endpoint_after_reload'] = other.evaluate("async () => (await fetch(endpoint, {method:'POST', body:'{}'})).status")
                self.assertEqual(evidence['old_endpoint_after_reload'], 503)
                new_endpoint = page.evaluate('endpoint')
                page.close()
                evidence['closed_host'] = other.evaluate("async endpoint => (await fetch(endpoint, {method:'POST', body:'{}'})).status", new_endpoint)
                self.assertEqual(evidence['closed_host'], 503)
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
        (ROOT / 'browser-results.json').write_text(json.dumps(evidence, indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
