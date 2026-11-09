"""Download a prefix of DEEP1B without transferring the full 384 GB dataset."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import struct
import urllib.request

ROOT = 'https://storage.yandexcloud.net/yandex-research/ann-datasets/DEEP/'

def fetch(url, start, end):
    req = urllib.request.Request(url, headers={'Range': f'bytes={start}-{end}', 'Accept-Encoding': 'identity'})
    with urllib.request.urlopen(req, timeout=180) as r:
        if r.status != 206 or not r.headers.get('Content-Range', '').startswith(f'bytes {start}-{end}/'):
            raise ValueError(f'Server did not honor Range: {r.status}, {r.headers}')
        body = r.read()
    if len(body) != end-start+1:
        raise ValueError('Truncated range')
    return body

def download(name, count, dest):
    url = ROOT + name
    total, dim = struct.unpack('<II', fetch(url, 0, 7))
    assert count <= total
    size = count * dim * 4
    path = dest / name
    if not path.exists() or path.stat().st_size != size + 8:
        tmp = path.with_suffix('.partial')
        with tmp.open('wb') as f:
            f.write(struct.pack('<II', count, dim))
            ranges = [(i, min(i+8*1024**2, size)) for i in range(0, size, 8*1024**2)]
            with ThreadPoolExecutor(max_workers=4) as pool:
                for i, chunk in enumerate(pool.map(lambda p: fetch(url, p[0]+8, p[1]+7), ranges)):
                    f.write(chunk)
                    if i % 16 == 0:
                        print(f'{name}: {i+1}/{len(ranges)} chunks', flush=True)
        tmp.rename(path)
    h = hashlib.sha256()
    with path.open('rb') as f:
        while b := f.read(8*1024**2):
            h.update(b)
    return dict(url=url, source_count=total, count=count, dimensions=dim, sha256=h.hexdigest(), file=str(path))

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--count', type=int, default=3_000_000)
    p.add_argument('--queries', type=int, default=1000)
    a = p.parse_args()
    dest = Path(__file__).resolve().parent / 'data'
    dest.mkdir(exist_ok=True)
    results = [download('base.1B.fbin', a.count, dest), download('query.public.10K.fbin', a.queries, dest)]
    (dest.parent / 'results').mkdir(exist_ok=True)
    (dest.parent / 'results/dataset.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))
