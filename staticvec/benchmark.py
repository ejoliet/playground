"""Reproducible measured experiments. Run from staticvec; all output stays here."""
import argparse
import gc
import json
import os
from pathlib import Path
import platform
import struct
import threading
import time
import faiss
import numpy as np
from client import StaticIndex
from format import build
from server import make_server

ROOT = Path(__file__).resolve().parent

def vectors(path):
    with open(path, 'rb') as f:
        n, dim = struct.unpack('<II', f.read(8))
    assert Path(path).stat().st_size == 8+n*dim*4
    return np.memmap(path, dtype='<f4', offset=8, shape=(n, dim), mode='r')

def recall(ids, truth):
    return len(set(map(int, ids)) & set(map(int, truth)))/len(truth)

def tie_recall(ids, query, data, radius):
    """Fraction within exact kth distance; float64 recomputation, 1e-7 tolerance."""
    distances = np.sum((np.asarray(data[ids], dtype=np.float64)-query.astype(np.float64))**2, axis=1)
    return float(np.count_nonzero(distances <= radius+1e-7)/10)

def write_json(name, obj):
    (ROOT / 'results' / name).write_text(json.dumps(obj, indent=2)+'\n')

def run(a):
    faiss.omp_set_num_threads(a.threads)
    (ROOT/'indexes').mkdir(exist_ok=True)
    (ROOT/'results').mkdir(exist_ok=True)
    x = vectors(ROOT/'data/base.1B.fbin')
    all_q = vectors(ROOT/'data/query.public.10K.fbin')
    qids = np.random.default_rng(2026).choice(len(all_q), a.queries, replace=False)
    q = np.asarray(all_q[qids], dtype=np.float32)
    write_json('environment.json', dict(platform=platform.platform(), python=platform.python_version(),
        numpy=np.__version__, faiss=faiss.__version__, threads=a.threads, cpu_count=os.cpu_count(),
        query_ids=qids.tolist(), k=10, seed=42, hnsw_m=16, ef_construction=100,
        ef_search=[16,64,256], sizes=a.sizes, probes=a.probes, queries=a.queries,
        date_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())))
    server = make_server(ROOT/'indexes')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    hnsw = faiss.IndexHNSWFlat(x.shape[1], 16)
    hnsw.hnsw.efConstruction = 100
    builds, truths, baseline, radii = [], {}, {}, {}
    records = (ROOT/'results/queries.jsonl').open('w', buffering=1)
    cumulative_build = 0
    try:
        for n in a.sizes:
            print(f'{n}: exact ground truth', flush=True)
            flat = faiss.IndexFlatL2(x.shape[1])
            flat.add(x[:n])
            start = time.perf_counter()
            _, truth = flat.search(q, 10)
            exact_seconds = time.perf_counter()-start
            del flat
            gc.collect()
            np.save(ROOT/f'results/truth-{n}.npy', truth)
            truths[n] = truth
            radii[n] = np.array([np.max(np.sum((np.asarray(x[t], dtype=np.float64)-query.astype(np.float64))**2, axis=1))
                                for query, t in zip(q, truth)])
            np.save(ROOT/f'results/radius-{n}.npy', radii[n])
            print(f'{n}: HNSW construction', flush=True)
            start = time.perf_counter()
            for lo in range(hnsw.ntotal, n, 100000):
                hnsw.add(x[lo:min(n, lo+100000)])
                print(f'  HNSW: {hnsw.ntotal}', flush=True)
            cumulative_build += time.perf_counter()-start
            # FAISS search is explicitly single-threaded, one query at a time.
            faiss.omp_set_num_threads(1)
            for ef in [16, 64, 256]:
                hnsw.hnsw.efSearch = ef
                hnsw.search(q[:1], 10)
                all_ids = []
                for i, query in enumerate(q):
                    start = time.perf_counter()
                    _, ids = hnsw.search(query[None], 10)
                    elapsed = (time.perf_counter()-start)*1000
                    all_ids.append(ids[0])
                    records.write(json.dumps(dict(kind='hnsw', n=n, ef=ef, query=int(qids[i]),
                        recall=recall(ids[0], truth[i]), tie_recall=tie_recall(ids[0],query,x,radii[n][i]),
                        ids=ids[0].tolist(), milliseconds=elapsed, bytes=0, requests=0))+'\n')
                if ef == 256:
                    baseline[n] = np.asarray(all_ids)
            faiss.omp_set_num_threads(a.threads)
            if n == max(a.sizes):
                faiss.write_index(hnsw, str(ROOT/f'indexes/hnsw-{n}.faiss'))
            hnsw_bytes = (n*x.shape[1]*4 + hnsw.hnsw.neighbors.size()*4 +
                           hnsw.hnsw.offsets.size()*8 + hnsw.hnsw.levels.size()*4)
            for buckets in ([1024,4096] if n == max(a.sizes) else [1024]):
                name = f'deep-{n}-k{buckets}.svx'
                path = ROOT/'indexes'/name
                print(f'{n}: build static IVF {buckets}', flush=True)
                meta = build(path, x[:n], buckets)
                meta.update(hnsw_build_seconds=cumulative_build, hnsw_array_bytes=hnsw_bytes,
                            exact_seconds=exact_seconds)
                builds.append(meta)
                write_json('builds.json', builds)
                index = StaticIndex(f'http://127.0.0.1:{port}/{name}')
                print(f'{n}: HTTP benchmark {buckets}; startup={index.startup}', flush=True)
                for probes in a.probes:
                    for i, query in enumerate(q):
                        ids, stats = index.search(query, probes=probes)
                        records.write(json.dumps(dict(kind='static', n=n, buckets=buckets, probes=probes,
                            query=int(qids[i]), recall=recall(ids, truth[i]),
                            tie_recall=tie_recall(ids,query,x,radii[n][i]), ids=ids.tolist(),
                            hnsw_overlap=recall(ids, baseline[n][i]), **stats,
                            startup_bytes=index.startup['bytes'], startup_ms=index.startup['milliseconds']))+'\n')
                    print(f'  probes={probes} complete', flush=True)
                index.close()
        print('delay/concurrency experiments', flush=True)
        n = max(a.sizes)
        for delay in [0,20]:
            delayed = make_server(ROOT/'indexes', delay_ms=delay)
            threading.Thread(target=delayed.serve_forever, daemon=True).start()
            try:
                for workers in [1,8]:
                    index = StaticIndex(f'http://127.0.0.1:{delayed.server_port}/deep-{n}-k4096.svx', workers)
                    for probes in [16,64,256]:
                        for i, query in enumerate(q[:10]):
                            ids, stats = index.search(query, probes=probes)
                            records.write(json.dumps(dict(kind='delay', n=n, buckets=4096,
                                probes=probes, workers=workers, delay_ms=delay, query=int(qids[i]),
                                recall=recall(ids, truths[n][i]), **stats))+'\n')
                    index.close()
            finally:
                delayed.shutdown()
                delayed.server_close()
    finally:
        records.close()
        server.shutdown()
        server.server_close()
    print('complete', flush=True)

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--sizes', nargs='+', type=int, default=[100000,1000000,3000000])
    p.add_argument('--queries', type=int, default=100)
    p.add_argument('--probes', nargs='+', type=int, default=[1,4,16,64,256])
    p.add_argument('--threads', type=int, default=4)
    run(p.parse_args())
