"""Build a staticvec file from a little-endian fbin (uint32 N,D then float32 rows)."""
import argparse
from pathlib import Path
import struct
import faiss
import numpy as np
from format import build

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('input')
    p.add_argument('output')
    p.add_argument('--buckets', type=int, default=1024)
    p.add_argument('--threads', type=int, default=4)
    a = p.parse_args()
    with open(a.input,'rb') as f:
        n,d = struct.unpack('<II', f.read(8))
    if Path(a.input).stat().st_size != 8+n*d*4:
        p.error('Input is not an fbin with the advertised shape')
    if not 1 <= a.buckets <= n:
        p.error('Buckets must be between 1 and N')
    faiss.omp_set_num_threads(a.threads)
    data = np.memmap(a.input, dtype='<f4', offset=8, shape=(n,d), mode='r')
    print(build(a.output, data, a.buckets))
