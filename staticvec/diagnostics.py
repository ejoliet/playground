"""Explain routing misses and isolate HTTP overhead with the identical Python search."""
import json
import os
from pathlib import Path
import threading
import time
import numpy as np
from benchmark import vectors, recall, tie_recall
from client import StaticIndex
from format import HEADER_SIZE, parse_header, row_type
from server import make_server

ROOT = Path(__file__).resolve().parent

def run():
    env = json.loads((ROOT/'results/environment.json').read_text())
    qids = env['query_ids']
    q = np.asarray(vectors(ROOT/'data/query.public.10K.fbin')[qids])
    server = make_server(ROOT/'indexes')
    threading.Thread(target=server.serve_forever, daemon=True).start()
    diagnostics = []
    try:
        # End-to-end exhaustive test using real data, with a separate exact oracle.
        small = min(env['sizes'])
        index = StaticIndex(f'http://127.0.0.1:{server.server_port}/deep-{small}-k1024.svx')
        truth = np.load(ROOT/f'results/truth-{small}.npy')
        ids, stats = index.search(q[0], probes=1024)
        assert recall(ids, truth[0]) == 1.0
        exhaustive = dict(n=small, query=qids[0], recall=1.0, **stats)
        index.close()
        for n, buckets in [(n,1024) for n in env['sizes']] + [(max(env['sizes']),4096)]:
            path = ROOT/f'indexes/deep-{n}-k{buckets}.svx'
            with path.open('rb') as f:
                h = parse_header(f.read(HEADER_SIZE))
            centers = np.memmap(path, offset=h['centers'], dtype='<f4', shape=(buckets,h['dim']), mode='r')
            offsets = np.memmap(path, offset=h['directory'], dtype='<u8', shape=(buckets+1,), mode='r')
            rows = np.memmap(path, offset=h['payload'], dtype=row_type(h['dim']), shape=(n,), mode='r')
            counts = np.diff(offsets)//row_type(h['dim']).itemsize
            # Original vector ID -> containing bucket. Each vector occurs exactly once.
            owner = np.empty(n,dtype=np.int32)
            owner[rows['id']] = np.repeat(np.arange(buckets), counts.astype(np.int64))
            assert np.unique(rows['id']).size == n
            truth = np.load(ROOT/f'results/truth-{n}.npy')
            ranks = []
            for query, nearest in zip(q,truth):
                rank = np.empty(buckets,dtype=int)
                rank[np.argsort(np.sum((centers-query)**2,axis=1))] = np.arange(1,buckets+1)
                ranks.append(rank[owner[nearest]])
            ranks = np.asarray(ranks)
            predicted = {str(p):float(np.mean(ranks<=p)) for p in env['probes']}
            diagnostics.append(dict(n=n,buckets=buckets,kind='routing',
                recall_from_true_neighbor_bucket_rank=predicted,
                bucket_rank_p50=float(np.median(ranks)), bucket_rank_p95=float(np.percentile(ranks,95)),
                bucket_rank_max=int(ranks.max())))
            del rows, centers, offsets, owner
        # Identical selection, distance code, thread pool and copying; replace only HTTP GET.
        n = max(env['sizes'])
        path = ROOT/f'indexes/deep-{n}-k4096.svx'
        index = StaticIndex(f'http://127.0.0.1:{server.server_port}/{path.name}')
        fd = os.open(path,os.O_RDONLY)
        def local_get(start,end):
            body = os.pread(fd,end-start+1,start)
            assert len(body)==end-start+1
            with index.reader.lock:
                index.reader.bytes += len(body)
                index.reader.requests += 1
            return body
        index.reader.get = local_get
        truth = np.load(ROOT/f'results/truth-{n}.npy')
        radius = np.load(ROOT/f'results/radius-{n}.npy')
        data = vectors(ROOT/'data/base.1B.fbin')
        try:
            for p in env['probes']:
                for i,query in enumerate(q):
                    ids,stats = index.search(query,probes=p)
                    diagnostics.append(dict(kind='local_pread',n=n,buckets=4096,probes=p,
                        query=qids[i],recall=recall(ids,truth[i]),
                        tie_recall=tie_recall(ids,query,data,radius[i]),ids=ids.tolist(),**stats))
        finally:
            index.close()
            os.close(fd)
        # Count exact copies of the observed duplicate-query outlier in the base prefix.
        duplicate_query = 449
        duplicate_q = vectors(ROOT/'data/query.public.10K.fbin')[duplicate_query]
        exact_copies = 0
        for lo in range(0,n,65536):
            exact_copies += int(np.count_nonzero(np.all(data[lo:min(n,lo+65536)] == duplicate_q,axis=1)))
        diagnostics.append(dict(kind='duplicate_audit',query=duplicate_query,n=n,exact_copies=exact_copies))
        # Cold object startup + first query; no cached centroid directory or connections.
        for i,query in enumerate(q[:10]):
            start = time.perf_counter()
            index = StaticIndex(f'http://127.0.0.1:{server.server_port}/{path.name}')
            ids,stats = index.search(query,probes=64)
            diagnostics.append(dict(kind='cold',n=n,buckets=4096,probes=64,query=qids[i],
                total_ms=(time.perf_counter()-start)*1000,total_bytes=index.startup['bytes']+stats['bytes'],
                startup=index.startup,**stats))
            index.close()
        (ROOT/'results/diagnostics.json').write_text(json.dumps(dict(exhaustive_test=exhaustive, measurements=diagnostics),indent=2)+'\n')
    finally:
        server.shutdown()
        server.server_close()
    print('Exhaustive real-data check, routing attribution, local pread and cold-start checks complete.')

if __name__=='__main__':
    run()
