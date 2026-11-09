"""NumPy + standard-library Range client; no FAISS or local index access."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import threading
import time
from urllib.parse import urlsplit
import numpy as np
from format import HEADER_SIZE, parse_header, row_type

class RangeReader:
    def __init__(self, url, workers=8):
        self.url = urlsplit(url)
        if self.url.scheme not in ('http', 'https') or not self.url.hostname:
            raise ValueError('Expected an HTTP(S) URL')
        self.pool = ThreadPoolExecutor(max_workers=workers)
        self.local = threading.local()
        self.lock = threading.Lock()
        self.connections = []
        self.total_size = None
        self.reset()

    def reset(self):
        self.bytes = self.requests = self.header_bytes = 0

    def get(self, start, end):
        if not hasattr(self.local, 'conn'):
            cls = http.client.HTTPSConnection if self.url.scheme == 'https' else http.client.HTTPConnection
            self.local.conn = cls(self.url.hostname, self.url.port, timeout=60)
            with self.lock:
                self.connections.append(self.local.conn)
        conn = self.local.conn
        path = self.url.path + ('?'+self.url.query if self.url.query else '')
        conn.request('GET', path, headers={'Range': f'bytes={start}-{end}', 'Accept-Encoding': 'identity'})
        response = conn.getresponse()
        cr = response.getheader('Content-Range', '')
        expected = f'bytes {start}-{end}/'
        if response.status != 206 or not cr.startswith(expected):
            conn.close()
            raise ValueError(f'Range not honored: status={response.status}, Content-Range={cr!r}')
        size = int(cr[len(expected):])
        if self.total_size is not None and size != self.total_size:
            conn.close()
            raise ValueError('Object size changed')
        if response.getheader('Content-Encoding', 'identity') != 'identity':
            conn.close()
            raise ValueError('Compressed range response')
        body = response.read(end-start+2)
        if len(body) != end-start+1:
            raise ValueError('Truncated or overlong range')
        with self.lock:
            self.bytes += len(body)
            self.requests += 1
            # Response header fields only; excludes status line, request headers, TCP/TLS.
            self.header_bytes += sum(len(k)+len(v)+4 for k, v in response.getheaders())+2
        return body

    def close(self):
        self.pool.shutdown()
        for conn in self.connections:
            conn.close()

class StaticIndex:
    def __init__(self, url, workers=8):
        start = time.perf_counter()
        self.reader = RangeReader(url, workers)
        try:
            self.info = h = parse_header(self.reader.get(0, HEADER_SIZE-1))
            self.reader.total_size = h['size']
            raw = self.reader.get(HEADER_SIZE, h['payload']-1)
            length = h['buckets']*h['dim']*4
            self.centers = np.frombuffer(raw[:length], dtype='<f4').reshape(h['buckets'], h['dim'])
            self.offsets = np.frombuffer(raw[length:], dtype='<u8')
            if (self.offsets[0] != h['payload'] or self.offsets[-1] != h['size'] or
                    np.any(self.offsets[1:] < self.offsets[:-1]) or
                    np.any((self.offsets-h['payload']) % row_type(h['dim']).itemsize)):
                raise ValueError('Invalid bucket directory')
        except Exception:
            self.reader.close()
            raise
        self.startup = dict(bytes=self.reader.bytes, requests=self.reader.requests,
                            milliseconds=(time.perf_counter()-start)*1000)

    def search(self, query, k=10, probes=16):
        q = np.asarray(query, dtype=np.float32)
        if q.shape != (self.info['dim'],) or not np.isfinite(q).all():
            raise ValueError('Invalid query')
        if not 1 <= k <= self.info['n'] or not 1 <= probes <= self.info['buckets']:
            raise ValueError('Invalid k/probes')
        self.reader.reset()
        start = time.perf_counter()
        distances = np.sum((self.centers-q)**2, axis=1)
        selected = np.argpartition(distances, probes-1)[:probes]
        # Merge physically adjacent buckets without fetching gaps.
        spans = []
        for bucket in sorted(selected):
            lo, hi = map(int, self.offsets[bucket:bucket+2])
            if hi == lo:
                continue
            if spans and spans[-1][1] == lo:
                spans[-1] = (spans[-1][0], hi)
            else:
                spans.append((lo, hi))
        route_ms = (time.perf_counter()-start)*1000
        candidates, scores, visited = [], [], 0
        for body in self.reader.pool.map(lambda s: self.reader.get(s[0], s[1]-1), spans):
            rows = np.frombuffer(body, dtype=row_type(self.info['dim']))
            d = np.sum((rows['vector']-q)**2, axis=1)
            take = np.argpartition(d, min(k, len(d))-1)[:k]
            candidates.extend(rows['id'][take].tolist())
            scores.extend(d[take].tolist())
            visited += len(rows)
        order = np.lexsort((candidates, scores))[:k]
        result = np.asarray(candidates, dtype=np.uint32)[order]
        stats = dict(bytes=self.reader.bytes, requests=self.reader.requests,
                     response_header_bytes=self.reader.header_bytes, vectors=visited,
                     route_ms=route_ms, milliseconds=(time.perf_counter()-start)*1000)
        return result, stats

    def close(self):
        self.reader.close()

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('url')
    p.add_argument('query', help='JSON array of float coordinates')
    p.add_argument('--probes', type=int, default=16)
    p.add_argument('--workers', type=int, default=8)
    a = p.parse_args()
    index = StaticIndex(a.url, a.workers)
    try:
        ids, stats = index.search(json.loads(a.query), probes=a.probes)
        print(json.dumps(dict(ids=ids.tolist(), startup=index.startup, query=stats), indent=2))
    finally:
        index.close()
