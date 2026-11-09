"""Cross-check full reader execution under latency, not just trace replay."""
import json
import pathlib
import time
from benchmark import server, HTTPSource
from workloads import fixtures, WORKLOADS, consume
from oracle import Oracle

blobs={k:p.read_bytes() for k,p in fixtures().items()}
rows=[]
with server(blobs,.1) as address:
    for name in ['parquet_columns','parquet_prebuffer','zip_metadata','fits_rows','sqlite_random']:
        expected=None
        for policy in ['none','cache','fixed','adaptive']:
            blob=blobs[WORKLOADS[name]]
            src=HTTPSource(address,WORKLOADS[name],len(blob))
            o=Oracle(src,len(blob),policy)
            start=time.perf_counter(); digest=consume(name,o); wall=time.perf_counter()-start
            src.close()
            if expected is None: expected=digest
            assert expected==digest
            rows.append(dict(workload=name,policy=policy,rtt_ms=100,wall_seconds=wall,digest=digest,**o.stats()))
pathlib.Path('results/live_100ms.json').write_text(json.dumps(rows,indent=2))
print('Verified',len(rows),'full reader executions at 100 ms RTT')
