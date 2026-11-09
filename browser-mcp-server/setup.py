"""Download static runtime assets. All writes stay inside this folder."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
REF = 'aa4e39edad154dad649a1804e32a943cf670a6e4'
PYODIDE = '0.27.7'


def download(url, path, digest=None):
    if path.exists() and (digest is None or hashlib.sha256(path.read_bytes()).hexdigest() == digest):
        return
    print('Downloading', url, flush=True)
    data = urlopen(url, timeout=90).read()
    if digest and hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('Checksum mismatch: ' + url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def main():
    bridge_files = {
        'bridge-python.js': '44e81f41124c1481aadb86d43e62f161e311d4243d92697e482397ac1e22f664',
        'worker-runtime.js': '041f65bb16db23974763adc8954fa0da8a65c3f735c916e42f3e194185ec4a2e',
    }
    for name, digest in bridge_files.items():
        download(f'https://raw.githubusercontent.com/simonw/research/{REF}/pyodide-asgi-browser/{name}', ROOT / 'vendor-source' / name, digest)
    base = f'https://cdn.jsdelivr.net/pyodide/v{PYODIDE}/full/'
    vendor = ROOT / 'vendor'
    for name in ['pyodide.js', 'pyodide.asm.js', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json']:
        download(base + name, vendor / name)
    lock = json.loads((vendor / 'pyodide-lock.json').read_text())['packages']
    seen = set()
    def package(name):
        if name in seen:
            return
        seen.add(name)
        item = lock[name]
        for dep in item['depends']:
            package(dep)
        download(base + item['file_name'], vendor / item['file_name'], item['sha256'])
    for name in ['micropip', 'sqlite3']:
        package(name)
    (vendor / 'install.json').write_text('{"wheels": []}\n')


if __name__ == '__main__':
    main()
