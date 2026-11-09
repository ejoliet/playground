"""Synchronous, content-blind range wrapper; byte-bounded interval LRU."""
import io
import time
from collections import OrderedDict

POLICIES = ('none', 'cache', 'fixed', 'adaptive', 'stride')


def union_length(intervals):
    end = total = 0
    for a, b in sorted(intervals):
        total += max(0, b - max(a, end))
        end = max(end, b)
    return total


class Oracle:
    def __init__(self, fetch, size, policy='cache', budget=262144, window=65536):
        assert policy in POLICIES and budget > 0 and window > 0
        self.fetch, self.size, self.policy = fetch, size, policy
        self.budget, self.window = budget, min(window, budget)
        self.cache = OrderedDict()
        self.resident = self.peak = self.hits = self.calls = 0
        self.history, self.trace, self.transfers = [], [], []

    def _get(self, a, b, mark=True):
        for key, value in list(self.cache.items()):
            if key[0] <= a and b <= key[1]:
                self.cache.move_to_end(key)
                # Track use per fetched incarnation, including after eviction.
                if mark: value[1].append((a, b))
                return value[0][a-key[0]:b-key[0]]
        return None

    def _fetch(self, a, b, used):
        start = time.perf_counter()
        data = self.fetch(a, b)
        if len(data) != b-a:
            raise IOError('short range response')
        record = dict(offset=a, length=b-a, seconds=time.perf_counter()-start, used=list(used))
        self.transfers.append(record)
        if self.policy != 'none' and len(data) <= self.budget:
            while self.resident + len(data) > self.budget:
                _, old = self.cache.popitem(last=False)
                self.resident -= len(old[0])
            key = (a, b)
            if key in self.cache:
                self.resident -= len(self.cache.pop(key)[0])
            self.cache[key] = (data, record['used'])
            self.resident += len(data)
            self.peak = max(self.peak, self.resident)
        return data

    def read(self, a, n):
        if a < 0 or n < 0:
            raise ValueError('negative range')
        b = min(self.size, a+n)
        if a >= b:
            return b''
        start = time.perf_counter()
        self.calls += 1
        data = self._get(a, b)
        hit = data is not None
        self.hits += hit
        contiguous = len(self.history) >= 2 and self.history[-1][1] == a and self.history[-2][1] == self.history[-1][0]
        if data is None:
            end = b
            if self.policy == 'fixed' or (self.policy in ('adaptive', 'stride') and contiguous):
                end = min(self.size, max(b, a+self.window))
            data = self._fetch(a, end, [(a, b)])[:b-a]
        if self.policy == 'stride' and len(self.history) >= 2:
            delta = a-self.history[-1][0]
            if delta > 0 and delta == self.history[-1][0]-self.history[-2][0] and not contiguous:
                p, q = a+delta, min(self.size, a+delta+(b-a))
                if p < q and q-p <= self.budget and self._get(p, q, mark=False) is None:
                    self._fetch(p, q, [])
        self.history = (self.history + [(a,b)])[-2:]
        self.trace.append(dict(sequence=len(self.trace), offset=a, length=b-a,
                               start=start, seconds=time.perf_counter()-start, hit=hit))
        return data

    def stats(self):
        return dict(requests=len(self.transfers), bytes=sum(t['length'] for t in self.transfers),
                    unused_bytes=sum(t['length']-union_length(t['used']) for t in self.transfers),
                    calls=self.calls, hit_rate=self.hits/max(1,self.calls), cache_peak_bytes=self.peak)


class RangeFile(io.RawIOBase):
    def __init__(self, oracle):
        super().__init__()
        self.oracle, self.pos = oracle, 0
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos
    def seek(self, offset, whence=0):
        pos = offset + (self.pos if whence == 1 else self.oracle.size if whence == 2 else 0)
        if whence not in (0,1,2) or pos < 0: raise ValueError('invalid seek')
        self.pos = pos
        return pos
    def read(self, size=-1):
        data = self.oracle.read(self.pos, max(0,self.oracle.size-self.pos) if size is None or size < 0 else size)
        self.pos += len(data)
        return data
    def readinto(self, buf):
        data = self.read(len(buf)); buf[:len(data)] = data
        return len(data)


def merge_ranges(ranges, gap=4096, limit=262144):
    """Requires an explicit batch; never infer future calls from a trace online."""
    out = []
    for a,b in sorted(ranges):
        if out and a <= out[-1][1]+gap and max(b,out[-1][1])-out[-1][0] <= limit:
            out[-1] = (out[-1][0], max(b,out[-1][1]))
        else: out.append((a,b))
    return out
