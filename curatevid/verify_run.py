"""Check every exported clip, coverage, manifest consistency and duplicate targets."""
import argparse
import json
from pathlib import Path

import pyarrow.parquet as pq

from curatevid import probe


def verify(folder):
    rows = pq.read_table(folder/'manifest.parquet').to_pylist()
    kept = pq.read_table(folder/'survivors.parquet').to_pylist()
    assert kept == [r for r in rows if r['status']=='kept']
    ids = {r['clip_id'] for r in kept}
    assert len({r['clip_id'] for r in rows}) == len(rows)
    maximum_error = 0
    for r in rows:
        assert r['end'] > r['start']
        if r['status']=='kept':
            duration, _ = probe(folder/r['clip_path'])
            error = abs(duration-r['duration'])
            assert error < .25, (r['clip_id'],error)
            maximum_error = max(maximum_error, error)
        else:
            assert r['clip_path'] is None
        if r['duplicate_of']:
            assert r['duplicate_of'] in ids
        for s in r['segments']:
            assert 0 <= s['start'] < s['end'] <= r['duration']+1e-6
    metrics = json.loads((folder/'metrics.json').read_text())
    for source in metrics['sources']:
        group = [r for r in rows if r['source']==source['path']]
        assert abs(group[0]['start']) < 1e-6
        assert abs(group[-1]['end']-source['seconds']) < 1e-6
        assert all(abs(a['end']-b['start'])<1e-6 for a,b in zip(group,group[1:]))
    result = dict(rows=len(rows),kept=len(kept),exports_probed=len(kept),
                  maximum_duration_error_seconds=maximum_error,
                  transcript_segments=sum(len(r['segments']) for r in rows),status='passed')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path)
    verify(p.parse_args().folder)
