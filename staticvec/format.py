"""Staticvec v1: immutable float32 IVF file, little endian, squared L2."""
import struct
from pathlib import Path
import numpy as np

MAGIC = b'SVECIVF1'
HEADER = struct.Struct('<8sIIIIQQQQ8x')
HEADER_SIZE = HEADER.size

def row_type(dim):
    return np.dtype([('id', '<u4'), ('vector', '<f4', (dim,))])

def parse_header(raw):
    magic, version, n, dim, buckets, centers, directory, payload, size = HEADER.unpack(raw)
    if magic != MAGIC or version != 1:
        raise ValueError('Unsupported staticvec format')
    if not (0 < n < 2**32 and 0 < dim <= 65536 and 0 < buckets <= n):
        raise ValueError('Invalid dimensions/counts')
    if centers != HEADER_SIZE or directory != centers + buckets*dim*4 or payload != directory+(buckets+1)*8:
        raise ValueError('Invalid metadata offsets')
    if size != payload+n*row_type(dim).itemsize:
        raise ValueError('Invalid file size')
    return dict(n=n, dim=dim, buckets=buckets, centers=centers, directory=directory, payload=payload, size=size)

def build(path, vectors, buckets=1024, seed=42):
    import faiss
    import time
    start = time.perf_counter()
    n, dim = vectors.shape
    if not (0 < n < 2**32 and 0 < dim <= 65536 and 1 <= buckets <= n):
        raise ValueError('Invalid dimensions/counts')
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.partial')
    rng = np.random.default_rng(seed)
    train = np.asarray(vectors[rng.choice(n, min(n, max(65536, buckets*32)), replace=False)], dtype='float32')
    km = faiss.Kmeans(dim, buckets, niter=15, seed=seed, verbose=False)
    km.train(train)
    labels = np.empty(n, dtype='int32')
    for lo in range(0, n, 65536):
        labels[lo:lo+65536] = km.index.search(np.asarray(vectors[lo:lo+65536]), 1)[1][:, 0]
    order = np.argsort(labels, kind='stable')
    counts = np.bincount(labels, minlength=buckets)
    directory = HEADER_SIZE + buckets*dim*4
    payload = directory + (buckets+1)*8
    offsets = payload + np.r_[0, counts.cumsum()].astype('<u8') * row_type(dim).itemsize
    with temporary.open('wb') as f:
        f.write(HEADER.pack(MAGIC, 1, n, dim, buckets, HEADER_SIZE, directory, payload, int(offsets[-1])))
        f.write(km.centroids.astype('<f4').tobytes())
        f.write(offsets.tobytes())
        for lo in range(0, n, 65536):
            ids = order[lo:lo+65536]
            rows = np.empty(len(ids), dtype=row_type(dim))
            rows['id'], rows['vector'] = ids, vectors[ids]
            f.write(rows.tobytes())
    temporary.replace(path)
    return dict(n=n, dim=dim, buckets=buckets, seconds=time.perf_counter()-start,
                bytes=int(offsets[-1]), metadata_bytes=payload,
                bucket_min=int(counts.min()), bucket_p50=float(np.median(counts)),
                bucket_p95=float(np.percentile(counts, 95)), bucket_max=int(counts.max()))
