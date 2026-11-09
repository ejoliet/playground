#!/usr/bin/env python3
"""Deterministic, standard-library-only DNS document builder."""
import argparse
import base64
import gzip
import hashlib
import json
import math
from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]


def png(size=240):
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    pixels = bytearray()
    palette = [(25, 61, 53), (69, 102, 76), (119, 147, 103), (184, 199, 145), (218, 228, 184), (245, 242, 233)]
    for y in range(size):
        pixels.append(0)
        for x in range(size):
            z = complex((x / size - .5) * 3.2, (y / size - .5) * 3.2)
            n = 0
            while abs(z) < 4 and n < 60:
                z = z*z + complex(-.745, .186)
                n += 1
            pixels.extend(palette[min(n // 3, 5)] if n < 60 else palette[0])
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', size, size, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(pixels, 9)) + chunk(b'IEND', b'')


def build(domain, chunk_size=1800):
    if not 64 <= chunk_size <= 60000:
        raise ValueError('Chunk size must be 64..60000 base64 characters')
    if len(domain) > 180 or any(not p or len(p) > 63 or not all(c.isalnum() or c == '-' for c in p) for p in domain.split('.')):
        raise ValueError('Invalid or overly long DNS suffix')
    wave = ' '.join(('M' if i == 0 else 'L') + f'{300+245*math.sin(3*i*math.pi/250):.1f},{300+245*math.sin(4*i*math.pi/250):.1f}' for i in range(501))
    picture = png()
    html = (ROOT / 'src/app.html').read_text().replace('{{FRACTAL}}', 'data:image/png;base64,' + base64.b64encode(picture).decode()).replace('{{WAVE}}', wave).encode()
    compressed = gzip.compress(html, compresslevel=9, mtime=0)
    sha = hashlib.sha256(compressed).hexdigest()
    version = 'v' + sha[:20]
    encoded = base64.b64encode(compressed).decode()
    chunks = [encoded[i:i+chunk_size] for i in range(0, len(encoded), chunk_size)]
    manifest = dict(v=1, encoding='gzip+base64', release=version, chunks=len(chunks), bytes=len(compressed), decodedBytes=len(html), sha256=sha)
    raw = json.dumps(manifest, separators=(',', ':')).encode()
    records = [dict(name=f'c{i}.{version}.{domain}', type='TXT', content=f'wd1:{i}:{data}', ttl=300) for i, data in enumerate(chunks)]
    records.append(dict(name=f'_site.{domain}', type='TXT', content='wd1:m:' + base64.b64encode(raw).decode(), ttl=60))
    out = ROOT / 'dist'
    out.mkdir(exist_ok=True)
    (out / 'app.html').write_bytes(html)
    (out / 'records.json').write_text(json.dumps(records, indent=2) + '\n')
    (out / 'zone.txt').write_text('; Import only into the intended zone; chunks first, manifest last.\n' + '\n'.join(f'{r["name"]}. {r["ttl"]} IN TXT ' + ' '.join('"'+r['content'][i:i+255]+'"' for i in range(0, len(r['content']), 255)) for r in records) + '\n')
    summary = dict(domain=domain, htmlBytes=len(html), pngBytes=len(picture), gzipBytes=len(compressed), base64Bytes=len(encoded), chunkSize=chunk_size, chunkCount=len(chunks), recordCount=len(records), manifestSha256=hashlib.sha256(raw).hexdigest(), manifest=manifest)
    (out / 'build.json').write_text(json.dumps(summary, indent=2) + '\n')
    loader = (ROOT / 'src/loader.html').read_text().replace('{{DOMAIN}}', domain).replace('{{PIN}}', summary['manifestSha256'])
    loader = loader.replace('/* TRANSPORT */', (ROOT / 'src/transport.js').read_text())
    (ROOT / 'index.html').write_text(loader)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--domain', default='website-in-dns.626733.xyz')
    parser.add_argument('--chunk-size', type=int, default=1800)
    args = parser.parse_args()
    build(args.domain, args.chunk_size)
