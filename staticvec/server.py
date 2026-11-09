"""Local static-file server with strict single byte ranges; no vector-search code."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import socket
import time

class RangeHandler(SimpleHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    delay_ms = 0

    def setup(self):
        super().setup()
        self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def log_message(self, *args):
        pass

    def do_GET(self):
        path = Path(self.translate_path(self.path))
        if not path.is_file():
            self.send_error(404)
            return
        size = path.stat().st_size
        value = self.headers.get('Range')
        start, end = 0, size-1
        status = 200
        if value:
            match = re.fullmatch(r'bytes=(\d+)-(\d+)', value)
            if not match or not (0 <= int(match[1]) <= int(match[2]) < size):
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            start, end = map(int, match.groups())
            status = 206
        if self.delay_ms:
            time.sleep(self.delay_ms/1000)
        self.send_response(status)
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(end-start+1))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Expose-Headers', 'Content-Range, Accept-Ranges')
        if status == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        with path.open('rb') as f:
            f.seek(start)
            left = end-start+1
            while left:
                block = f.read(min(left, 1024*1024))
                if not block:
                    raise IOError('File changed during request')
                self.wfile.write(block)
                left -= len(block)


def make_server(directory, port=0, delay_ms=0):
    handler = type('ConfiguredRangeHandler', (RangeHandler,), {'delay_ms': delay_ms})
    return ThreadingHTTPServer(('127.0.0.1', port), partial(handler, directory=str(directory)))

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('directory', nargs='?', default='indexes')
    p.add_argument('--port', type=int, default=8000)
    p.add_argument('--delay-ms', type=float, default=0)
    a = p.parse_args()
    server = make_server(a.directory, a.port, a.delay_ms)
    print(f'Serving {a.directory} at http://127.0.0.1:{server.server_port}', flush=True)
    server.serve_forever()
