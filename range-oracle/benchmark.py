"""Run deterministic trace replay and real socket HTTP experiments."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import contextlib
import csv
import hashlib
import http.client
import http.server
import json
import pathlib
import platform
import random
import socket
import threading
import time
import tracemalloc
import importlib.metadata
from oracle import Oracle, POLICIES, union_length, merge_ranges
from workloads import fixtures, consume, WORKLOADS

RESULTS=pathlib.Path('results')

@contextlib.contextmanager
def server(blobs, rtt=0, bandwidth=50*1024**2):
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def setup(self):
            super().setup()
            self.connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        def log_message(self,*args): pass
        def do_GET(self):
            data=blobs[self.path.lstrip('/')]
            a,b=map(int,self.headers['Range'].removeprefix('bytes=').split('-'))
            if not 0 <= a <= b < len(data):
                self.send_error(416); return
            time.sleep(rtt+(b-a+1)/bandwidth)
            self.send_response(206)
            self.send_header('Content-Range',f'bytes {a}-{b}/{len(data)}')
            self.send_header('Content-Length',str(b-a+1))
            self.end_headers(); self.wfile.write(data[a:b+1])
    s=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=s.serve_forever,daemon=True); thread.start()
    try: yield s.server_address
    finally: s.shutdown(); s.server_close(); thread.join()


class HTTPSource:
    def __init__(self,address,name,size):
        self.conn=http.client.HTTPConnection(*address,timeout=30)
        self.name,self.size=name,size
    def __call__(self,a,b):
        self.conn.request('GET','/'+self.name,headers={'Range':f'bytes={a}-{b-1}','Accept-Encoding':'identity'})
        r=self.conn.getresponse(); data=r.read()
        if r.status!=206 or r.getheader('Content-Range')!=f'bytes {a}-{b-1}/{self.size}' or len(data)!=b-a:
            raise IOError('server did not honor exact byte range')
        return data
    def close(self): self.conn.close()


def replay(o,trace,blob):
    for t in trace:
        a,n=t['offset'],t['length']
        assert o.read(a,n)==blob[a:a+n]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--http',action='store_true')
    parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    RESULTS.mkdir(exist_ok=True)
    paths=fixtures(); blobs={k:p.read_bytes() for k,p in paths.items()}
    traces={}; digests={}; live=[]
    # Live integration uses actual Range HTTP, unmodified parser code.
    with server(blobs) as address:
        for name,kind in WORKLOADS.items():
            for policy in POLICIES:
                src=HTTPSource(address,kind,len(blobs[kind]))
                o=Oracle(src,len(blobs[kind]),policy)
                start=time.perf_counter(); digest=consume(name,o); wall=time.perf_counter()-start
                src.close()
                if policy=='none':
                    traces[name]=o.trace; digests[name]=digest
                assert digest==digests[name], (name,policy)
                assert [(x['offset'],x['length']) for x in o.trace]==[(x['offset'],x['length']) for x in traces[name]], (name,policy,'trace changed')
                live.append(dict(workload=name,policy=policy,wall_seconds=wall,digest=digest,**o.stats()))
            print('captured',name,len(traces[name]),flush=True)
    (RESULTS/'traces.json').write_text(json.dumps(traces,indent=2))
    (RESULTS/'live_readers.json').write_text(json.dumps(live,indent=2))
    rows=[]
    for budget in (65536,262144,1048576):
        for name,trace in traces.items():
            blob=blobs[WORKLOADS[name]]
            useful=union_length([(t['offset'],t['offset']+t['length']) for t in trace])
            for policy in POLICIES:
                o=Oracle(lambda a,b:blob[a:b],len(blob),policy,budget=budget)
                tracemalloc.start(); start=time.perf_counter(); replay(o,trace,blob)
                wall=time.perf_counter()-start; _,peak=tracemalloc.get_traced_memory(); tracemalloc.stop()
                stats=o.stats()
                for rtt in (.02,.1,.2):
                    for bandwidth in (1,50):
                        rows.append(dict(workload=name,policy=policy,budget=budget,rtt_ms=int(rtt*1000),bandwidth_mib=bandwidth,
                                         modeled_seconds=stats['requests']*rtt+stats['bytes']/(bandwidth*1024**2),
                                         replay_cpu_wall_seconds=wall,python_peak_bytes=peak,useful_unique_bytes=useful,**stats))
            # Explicit offline batch bound, not an online policy or fair cache comparison.
            intervals=merge_ranges([(t['offset'],t['offset']+t['length']) for t in trace],limit=budget)
            rows.append(dict(workload=name,policy='offline_batch_bound',budget=budget,rtt_ms=100,bandwidth_mib=50,
                             modeled_seconds=len(intervals)*.1+sum(b-a for a,b in intervals)/(50*1024**2),
                             requests=len(intervals),bytes=sum(b-a for a,b in intervals), useful_unique_bytes=useful))
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with (RESULTS/'model.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=keys); w.writeheader(); w.writerows(rows)
    meta=dict(python=platform.python_version(),platform=platform.platform(),versions={n:importlib.metadata.version(n) for n in ['numpy','pyarrow','astropy','apsw','fsspec','duckdb']},files={k:dict(bytes=len(v),sha256=hashlib.sha256(v).hexdigest()) for k,v in blobs.items()},seed=20261109)
    (RESULTS/'environment.json').write_text(json.dumps(meta,indent=2))
    if args.http:
        out=[]
        with (RESULTS/'http.jsonl').open('w') as f:
            for repeat in range(args.repeats):
                for rtt in (.02,.1,.2):
                    with server(blobs,rtt) as address:
                        jobs=[(n,p) for n in WORKLOADS for p in POLICIES]
                        random.Random(42+repeat).shuffle(jobs)
                        def run_job(job):
                            name,policy=job
                            blob=blobs[WORKLOADS[name]]
                            src=HTTPSource(address,WORKLOADS[name],len(blob))
                            o=Oracle(src,len(blob),policy)
                            start=time.perf_counter(); replay(o,traces[name],blob); wall=time.perf_counter()-start
                            src.close()
                            row=dict(workload=name,policy=policy,rtt_ms=int(rtt*1000),repeat=repeat,wall_seconds=wall,**o.stats())
                            return row
                        with ThreadPoolExecutor(max_workers=6) as pool:
                            for future in as_completed([pool.submit(run_job,job) for job in jobs]):
                                row=future.result()
                                f.write(json.dumps(row)+'\n'); f.flush(); out.append(row)
                    print('HTTP completed',repeat,rtt,flush=True)
        print('HTTP rows',len(out))

if __name__=='__main__': main()
