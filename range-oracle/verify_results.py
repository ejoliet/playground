"""Fail if the published experiment is incomplete or internally inconsistent."""
import csv
import json
from collections import Counter
from pathlib import Path

p=Path('results')
http=[json.loads(l) for l in (p/'http.jsonl').read_text().splitlines()]
assert len(http)==585
keys=Counter((r['workload'],r['policy'],r['rtt_ms']) for r in http)
assert len(keys)==195 and set(keys.values())=={3}
for r in http:
    assert 0 <= r['unused_bytes'] <= r['bytes']
    assert r['cache_peak_bytes'] <= 262144
    same=[x for x in http if (x['workload'],x['policy'])==(r['workload'],r['policy'])]
    for k in ['bytes','requests','unused_bytes','hit_rate']:
        assert len({x[k] for x in same})==1, (r['workload'],r['policy'],k)
model=list(csv.DictReader((p/'model.csv').open()))
assert len(model)==1209
for r in model:
    if r['policy']!='offline_batch_bound':
        assert int(r['cache_peak_bytes'])<=int(r['budget'])
        measured=next(x for x in http if (x['workload'],x['policy'])==(r['workload'],r['policy']))
        if r['budget']=='262144':
            for key in ['bytes','requests','unused_bytes']:
                assert int(r[key])==measured[key]
fs=[json.loads(l) for l in (p/'fsspec.jsonl').read_text().splitlines()]
assert len(fs)==60
assert set(Counter((r['workload'],r['policy'],r['think_seconds']) for r in fs).values())=={3}
assert len(json.loads((p/'live_100ms.json').read_text()))==20
live=json.loads((p/'live_readers.json').read_text())
assert len(live)==65
for name in {r['workload'] for r in live}:
    assert len({r['digest'] for r in live if r['workload']==name})==1
assert len({r['digest'] for r in live if r['workload'].startswith('parquet')})==1
print('Verified 585 HTTP trials, 1209 model rows, 60 fsspec trials, 85 full-reader runs, equal outputs and bounded caches.')
