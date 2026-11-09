"""Audit retained IDs, recall calculations and byte accounting independently of HTTP."""
import gzip
import json
from pathlib import Path
import numpy as np
from benchmark import vectors, recall, tie_recall

ROOT = Path(__file__).resolve().parent

def main():
    path = ROOT/'results/queries.jsonl'
    text = path.read_text() if path.exists() else gzip.decompress(path.with_suffix('.jsonl.gz').read_bytes()).decode()
    rows = [json.loads(line) for line in text.splitlines()]
    env = json.loads((ROOT/'results/environment.json').read_text())
    x = vectors(ROOT/'data/base.1B.fbin')
    q = vectors(ROOT/'data/query.public.10K.fbin')
    query_position = {q:i for i,q in enumerate(env['query_ids'])}
    truth = {n:np.load(ROOT/f'results/truth-{n}.npy') for n in env['sizes']}
    radius = {n:np.load(ROOT/f'results/radius-{n}.npy') for n in env['sizes']}
    checked = 0
    outliers = []
    for row in rows:
        if row['kind']=='delay':
            continue
        ids = row['ids']
        n, query = row['n'],row['query']
        i = query_position[query]
        assert len(ids)==len(set(ids))==10
        assert min(ids)>=0 and max(ids)<n
        assert recall(ids,truth[n][i])==row['recall']
        assert tie_recall(ids,q[query],x,radius[n][i])==row['tie_recall']
        if row['kind']=='static':
            assert row['bytes']==row['vectors']*388
            assert 1<=row['requests']<=row['probes']
            assert row['startup_bytes']==64+row['buckets']*96*4+(row['buckets']+1)*8
        if row['tie_recall']!=row['recall']:
            outliers.append({k:row[k] for k in ['kind','n','query','recall','tie_recall','probes','buckets','ef'] if k in row})
        checked+=1
    result=dict(checked_queries=checked, tie_differences=outliers,
                assertions='10 unique in-range IDs; recalls recomputed; query bytes equal visited rows × 388; request bounds; exact metadata bytes')
    (ROOT/'results/audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Audited {checked} HNSW/static queries; {len(outliers)} ID-recall/tie-aware differences')

if __name__=='__main__':
    main()
