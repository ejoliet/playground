"""Fetch the two public-domain benchmark films with reproducible checksums."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import time
import urllib.request

SOURCES = [
    ('HisGirlFriday', 'MoviePowderPresentsHisGirlFriday_512kb.mp4',
     'Internet Archive item carries a public-domain dedication.'),
    ('NightOfTheLivingDead-MPEG', 'NightOfTheLivingDead_512kb.mp4',
     'Original 1968 US film entered public domain on release without required copyright notice; not a later restoration.'),
]


def download(source):
    item, filename, rights = source
    start = time.perf_counter()
    url = f'https://archive.org/download/{item}/{filename}'
    target = Path('data')/filename
    with urllib.request.urlopen(f'https://archive.org/metadata/{item}', timeout=60) as response:
        metadata = json.load(response)
    if not target.exists():
        temporary = target.with_suffix('.partial')
        urllib.request.urlretrieve(url, temporary)
        temporary.rename(target)
    h = hashlib.sha256()
    md5 = hashlib.md5()
    with target.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
            md5.update(block)
    entry = next(f for f in metadata['files'] if f['name']==filename)
    if entry.get('md5') != md5.hexdigest():
        raise ValueError(f'Archive checksum mismatch: {target}')
    return dict(item=item, filename=filename, url=url, rights=rights,
                metadata_url=f'https://archive.org/metadata/{item}',
                license_url=metadata['metadata'].get('licenseurl'),
                sha256=h.hexdigest(), md5=md5.hexdigest(), bytes=target.stat().st_size,
                fetch_verify_seconds=time.perf_counter()-start)


if __name__ == '__main__':
    Path('data').mkdir(exist_ok=True)
    Path('reports').mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        sources = list(pool.map(download, SOURCES))
    Path('reports/sources.json').write_text(json.dumps(sources, indent=2)+'\n')
    print(json.dumps(sources, indent=2))
