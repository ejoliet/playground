#!/usr/bin/env python3
"""Serve a dashboard of HTTP endpoints discovered on this machine."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import csv
from http import HTTPStatus
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import re
import socket
import ssl
import struct
import subprocess
import sys
import threading
from urllib.parse import quote


WEB = Path(__file__).resolve().parent / "web"
REQUEST_TIMEOUT = 0.6
TLS = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
TLS.check_hostname = False
TLS.verify_mode = ssl.CERT_NONE


def command(*args, allowed=(0,)):
    result = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=5)
    if result.returncode not in allowed:
        raise RuntimeError(result.stderr.strip() or f"{args[0]} exited with {result.returncode}")
    return result.stdout


def linux_listeners():
    try:
        output = [
            (family, command("ss", "-H", "-ltnp", flag))
            for flag, family in (("-4", socket.AF_INET), ("-6", socket.AF_INET6))
        ]
    except (FileNotFoundError, RuntimeError):
        yield from proc_listeners()
        return
    for family, lines in output:
        for line in lines.splitlines():
            fields = line.split(maxsplit=5)
            if len(fields) < 5:
                continue
            process = re.search(r'\("([^"]+)",pid=', fields[5]) if len(fields) == 6 else None
            yield family, fields[3], process[1] if process else ""


def proc_listeners():
    for table, family in (("tcp", socket.AF_INET), ("tcp6", socket.AF_INET6)):
        path = Path("/proc/net") / table
        if table == "tcp6" and not path.exists():
            continue
        for line in path.read_text().splitlines()[1:]:
            fields = line.split()
            if fields[3] != "0A":  # TCP_LISTEN
                continue
            encoded, port = fields[1].split(":")
            words = [int(encoded[i:i + 8], 16) for i in range(0, len(encoded), 8)]
            address = socket.inet_ntop(family, struct.pack(f"={len(words)}I", *words))
            yield family, f"[{address}]:{int(port, 16)}", ""


def mac_listeners():
    process, family = "", socket.AF_INET
    listing = command("lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-Fctn", allowed=(0, 1))
    for line in listing.splitlines():
        value = line[1:]
        if line.startswith("c"):
            process = value
        elif line.startswith("t"):
            family = socket.AF_INET6 if value == "IPv6" else socket.AF_INET
        elif line.startswith("n"):
            yield family, value, process


def windows_listeners():
    try:
        listing = command("tasklist", "/FO", "CSV", "/NH")
        processes = {row[1]: row[0] for row in csv.reader(listing.splitlines()) if len(row) >= 2}
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        processes = {}
    for line in command("netstat", "-ano").splitlines():
        fields = line.split()
        if len(fields) == 5 and fields[0] == "TCP" and fields[2] in ("0.0.0.0:0", "[::]:0"):
            family = socket.AF_INET6 if fields[1].startswith("[") else socket.AF_INET
            yield family, fields[1], processes.get(fields[4], "")


def endpoints(listeners):
    targets = {}
    for family, endpoint, process in listeners:
        address, _, port_text = endpoint.rpartition(":")
        address = address.strip("[]")
        if address == "*":
            address = "::" if family == socket.AF_INET6 else "0.0.0.0"
        try:
            ip = ipaddress.ip_address(address)
            port = int(port_text)
        except ValueError:
            continue
        if ip.is_unspecified:
            host = "::1" if ip.version == 6 else "127.0.0.1"
        else:
            host = str(ip)
        matches = targets.setdefault((host, port), {"binds": set(), "process": ""})
        matches["binds"].add(str(ip))
        matches["process"] = matches["process"] or process
    return targets


def probe(host, port, protocol):
    if protocol == "https":
        connection = HTTPSConnection(host, port, timeout=REQUEST_TIMEOUT, context=TLS)
    else:
        connection = HTTPConnection(host, port, timeout=REQUEST_TIMEOUT)
    try:
        connection.request("HEAD", "/", headers={"Connection": "close"})
        response = connection.getresponse()
        return response.status, response.getheader("Server", "")[:150]
    except (OSError, HTTPException, ValueError):
        return None
    finally:
        connection.close()


def detect(target):
    (host, port), details = target
    # HTTPS first avoids mistaking a TLS server's plaintext error page for HTTP.
    for protocol in ("https", "http"):
        result = probe(host, port, protocol)
        if result:
            status, server = result
            url_host = f"[{quote(host, safe=':')}]" if ":" in host else host
            return dict(port=port, protocol=protocol, address=host, binds=sorted(details["binds"]),
                        process=details["process"], server=server, status=status,
                        url=f"{protocol}://{url_host}:{port}/")
    return None


def discover():
    if sys.platform.startswith("linux"):
        listeners = linux_listeners()
    elif sys.platform == "darwin":
        listeners = mac_listeners()
    elif sys.platform == "win32":
        listeners = windows_listeners()
    else:
        raise RuntimeError(f"Listener discovery is unavailable on {sys.platform}")
    targets = endpoints(listeners)
    with ThreadPoolExecutor(max_workers=24) as pool:
        services = [service for service in pool.map(detect, targets.items()) if service]
    services.sort(key=lambda item: (item["port"], item["address"], item["protocol"]))
    return dict(services=services, checked=len(targets), scannedAt=datetime.now(timezone.utc).isoformat())


class Dashboard(BaseHTTPRequestHandler):
    server_version = "Local Services"

    def version_string(self):
        return self.server_version

    def do_HEAD(self):
        self.serve(head_only=True)

    def do_GET(self):
        self.serve(head_only=False)

    def serve(self, head_only):
        port = self.server.server_port
        hosts = {"127.0.0.1", "localhost", f"127.0.0.1:{port}", f"localhost:{port}"}
        # The Host check blocks DNS rebinding; it cannot apply when remote clients use arbitrary names.
        if self.server.local_only and self.headers.get("Host", "").lower() not in hosts:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        path = self.path.partition("?")[0]
        assets = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                  "/style.css": ("style.css", "text/css")}
        if path == "/api/services":
            if head_only:
                self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)
                return
            try:
                with self.server.scan_lock:
                    payload = discover()
                self.respond(HTTPStatus.OK, "application/json", json.dumps(payload).encode())
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                body = json.dumps({"error": f"Could not read listeners. {error}"})
                self.respond(HTTPStatus.SERVICE_UNAVAILABLE, "application/json", body.encode())
        elif path in assets:
            filename, content_type = assets[path]
            self.respond(HTTPStatus.OK, content_type, (WEB / filename).read_bytes(), head_only)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def respond(self, status, content_type, body, head_only=False):
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8787, help="dashboard port (default: 8787)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="address to bind; 0.0.0.0 accepts other machines (default: 127.0.0.1)")
    options = parser.parse_args()
    if not 0 <= options.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    try:
        server = ThreadingHTTPServer((options.host, options.port), Dashboard)
    except OSError as error:
        parser.exit(1, f"Could not start the dashboard. {error}\n")
    with server:
        server.scan_lock = threading.Lock()
        server.local_only = options.host in ("127.0.0.1", "localhost")
        print(f"Local Services is running at http://{options.host}:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
