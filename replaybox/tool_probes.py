"""Optional real-tool probes: run with .venv/bin/python tool_probes.py."""
import ctypes
from datetime import datetime
import importlib.metadata
import json
from pathlib import Path
import tempfile
import threading
import time
from urllib.request import urlopen
from http.server import BaseHTTPRequestHandler, HTTPServer

from freezegun import freeze_time
from pyfakefs.fake_filesystem_unittest import Patcher
import vcr

ROOT = Path(__file__).resolve().parent

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'vcr probe')
    def log_message(self, *args):
        pass


def main():
    results = {'versions': {name: importlib.metadata.version(name) for name in ('vcrpy','freezegun','pyfakefs')}}
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        server = HTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{server.server_port}/'
        cassette = str(Path(tmp)/'http.yaml')
        with vcr.use_cassette(cassette, record_mode='once'):
            first = urlopen(url).read()
        server.shutdown()
        server.server_close()
        with vcr.use_cassette(cassette, record_mode='none'):
            second = urlopen(url).read()
            t1, t2 = time.time_ns(), time.time_ns()
        results['vcr_http_server_stopped'] = first == second
        results['vcr_time_still_live'] = t1 != t2
        with freeze_time('2020-01-01'):
            results['freezegun_datetime'] = datetime.now().isoformat()
            native_time = ctypes.CDLL(None).time
            native_time.argtypes = [ctypes.c_void_p]
            native_time.restype = ctypes.c_long
            results['freezegun_native_time_escapes'] = native_time(None) != int(time.time())
        real = Path(tmp)/'real.txt'
        real.write_text('real file')
        native_open = ctypes.CDLL(None).open
        native_open.argtypes = [ctypes.c_char_p, ctypes.c_int]
        with Patcher():
            results['pyfakefs_python_cannot_see_real_file'] = not real.exists()
            fd = native_open(str(real).encode(), 0)
            results['pyfakefs_native_can_open_real_file'] = fd >= 0
            if fd >= 0:
                ctypes.CDLL(None).close(fd)
    assert all(v for k,v in results.items() if isinstance(v, bool)), results
    (ROOT/'results'/'tool_probes.json').write_text(json.dumps(results, indent=2)+'\n')
    print(json.dumps(results, indent=2))

if __name__ == '__main__':
    main()
