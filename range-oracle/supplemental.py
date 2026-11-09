"""Existing fsspec background read-ahead and honest batched coalescing."""
import json
import pathlib
import time
import tracemalloc
import threading
from fsspec.caching import BlockCache, BackgroundBlockCache
from benchmark import server, HTTPSource
from oracle import union_length, merge_ranges
from workloads import fixtures, WORKLOADS


def main():
    blobs={k:p.read_bytes() for k,p in fixtures().items()}
    traces=json.loads(pathlib.Path('results/traces.json').read_text())
    with open('results/fsspec.jsonl','w') as output:
        for repeat in range(3):
            with server(blobs,.1) as address:
                for name in ['sequential','random','fits_rows','zip_cluster','sqlite_random']:
                    blob=blobs[WORKLOADS[name]]
                    for think in (0,.02):
                        for cls in (BlockCache,BackgroundBlockCache):
                            records=[]; lock=threading.Lock()
                            def fetch(a,b):
                                b=min(b,len(blob))
                                if a>=b: return b''
                                # One connection per call; thread-safe, equal for both baselines.
                                src=HTTPSource(address,WORKLOADS[name],len(blob))
                                try: data=src(a,b)
                                finally: src.close()
                                with lock: records.append((a,b))
                                return data
                            # Reserve one block for background/in-flight results in BOTH policies.
                            c=cls(65536,fetch,len(blob),maxblocks=3)
                            tracemalloc.start(); start=time.perf_counter()
                            for t in traces[name]:
                                a=t['offset']; b=a+t['length']
                                assert c._fetch(a,b)==blob[a:b]
                                if think: time.sleep(think)
                            foreground=time.perf_counter()-start
                            info=c.cache_info()._asdict()
                            if hasattr(c,'close'): c.close()
                            wall=time.perf_counter()-start
                            _,peak=tracemalloc.get_traced_memory(); tracemalloc.stop()
                            used=[(t['offset'],t['offset']+t['length']) for t in traces[name]]
                            waste=sum(b-a-union_length([(max(a,u),min(b,v)) for u,v in used if max(a,u)<min(b,v)]) for a,b in records)
                            row=dict(workload=name,policy=cls.__name__,repeat=repeat,rtt_ms=100,think_seconds=think,
                                foreground_seconds=foreground,wall_including_drain_seconds=wall,requests=len(records),
                                bytes=sum(b-a for a,b in records),unused_global_lower_bound=waste,
                                python_peak_bytes=peak,cache_info=info,transfers=records)
                            output.write(json.dumps(row)+'\n'); output.flush()
                    print('fsspec',repeat,name,flush=True)
    # Explicit concurrent/batch caller: offsets provided together, same input for both.
    blob=blobs['fits']
    batches=[[(i*131072+j*8192,i*131072+j*8192+12288) for j in range(4)] for i in range(8)]
    out=[]
    with server(blobs,.1) as address:
        for merged in (False,True):
            src=HTTPSource(address,'fits',len(blob)); count=total=0; start=time.perf_counter()
            for batch in batches:
                fetched=[(a,b,src(a,b)) for a,b in (merge_ranges(batch) if merged else batch)]
                for a,b in batch:
                    candidate=next(d[a-u:b-u] for u,v,d in fetched if u<=a and b<=v)
                    assert candidate==blob[a:b]
                count+=len(fetched); total+=sum(b-a for a,b,d in fetched)
            out.append(dict(merged=merged,wall_seconds=time.perf_counter()-start,requests=count,bytes=total,
                            max_batch_bytes=4*12288,budget=262144))
            src.close()
    pathlib.Path('results/batch.json').write_text(json.dumps(out,indent=2))

if __name__=='__main__':main()
