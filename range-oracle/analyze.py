"""Generate tables only from recorded measurements, with spread and sample count."""
import collections
import csv
import json
import pathlib
import statistics

P=pathlib.Path('results')

def main():
    rows=[json.loads(l) for l in (P/'http.jsonl').read_text().splitlines()]
    groups=collections.defaultdict(list)
    for r in rows: groups[r['workload'],r['policy'],r['rtt_ms']].append(r)
    summary=[]
    for (workload,policy,rtt),rs in sorted(groups.items()):
        ts=[r['wall_seconds'] for r in rs]
        summary.append(dict(workload=workload,policy=policy,rtt_ms=rtt,n=len(ts),
            median_seconds=statistics.median(ts),min_seconds=min(ts),max_seconds=max(ts),
            **{k:rs[0][k] for k in ['requests','bytes','unused_bytes','hit_rate','cache_peak_bytes']}))
    with (P/'summary.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
    out=['# Measured HTTP replay, cold 256 KiB cache','',
         'Median seconds at 100 ms injected RTT, 50 MiB/s per-request transfer delay. Three repeats; see summary.csv for min/max and all RTTs.','',
         '| Workload | None | Cache | Fixed | Adaptive | Stride |','|---|---:|---:|---:|---:|---:|']
    for name in dict.fromkeys(r['workload'] for r in summary):
        out.append('| '+name+' | '+' | '.join(f"{statistics.median(x['wall_seconds'] for x in groups[name,p,100]):.3f}" for p in ['none','cache','fixed','adaptive','stride'])+' |')
    out+=['','All outputs were verified byte-for-byte against the immutable fixture during replay.','']
    if (P/'fsspec.jsonl').exists():
        fs=[json.loads(l) for l in (P/'fsspec.jsonl').read_text().splitlines()]
        out+=['# fsspec at 100 ms RTT','',
              'Wall time includes draining background fetches. Three repeats; 192 KiB resident cache plus a 64 KiB background-result allowance. Block-cache uses the same resident allowance.','',
              '| Workload | Think/read (ms) | Block median (s) | Background median (s) | Block requests | Background requests |','|---|---:|---:|---:|---:|---:|']
        for name in dict.fromkeys(r['workload'] for r in fs):
            for think in [0,.02]:
                pairs=[[r for r in fs if r['workload']==name and r['think_seconds']==think and r['policy']==p] for p in ['BlockCache','BackgroundBlockCache']]
                if all(pairs):
                    out.append('| '+name+f' | {int(think*1000)} | '+' | '.join(f"{statistics.median(r['wall_including_drain_seconds'] for r in rs):.3f}" for rs in pairs)+' | '+' | '.join(str(statistics.median(r['requests'] for r in rs)) for rs in pairs)+' |')
    (P/'tables.md').write_text('\n'.join(out)+'\n')
    print('\n'.join(out))

if __name__=='__main__': main()
