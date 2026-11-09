"""Regenerate report figures and aggregate tables from per-query measurements."""
import json
import gzip
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'figures'
OUT.mkdir(exist_ok=True)
plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                     'svg.fonttype': 'none', 'savefig.dpi': 180})
COLORS = ['#0072B2', '#E69F00', '#009E73', '#CC79A7']

def ci(values):
    values = np.asarray(values)
    rng = np.random.default_rng(42)
    means = values[rng.integers(0, len(values), size=(2000,len(values)))].mean(axis=1)
    return np.percentile(means, [2.5,97.5])

def aggregate(rows):
    result = {'queries': len(rows)}
    for key in ['recall','tie_recall','hnsw_overlap','bytes','requests','vectors','milliseconds','route_ms','response_header_bytes']:
        if key not in rows[0]:
            continue
        values = [r[key] for r in rows]
        result[key] = dict(mean=float(np.mean(values)), p50=float(np.median(values)),
                           p95=float(np.percentile(values,95)), ci95=ci(values).tolist())
    return result

def save(fig, name):
    fig.savefig(OUT/f'{name}.svg', bbox_inches='tight')
    fig.savefig(OUT/f'{name}.png', bbox_inches='tight')
    plt.close(fig)

def main():
    path = ROOT/'results/queries.jsonl'
    raw = path.read_text() if path.exists() else gzip.decompress(path.with_suffix('.jsonl.gz').read_bytes()).decode()
    rows = [json.loads(s) for s in raw.splitlines()]
    groups = {}
    for row in rows:
        key = tuple((k,row[k]) for k in ['kind','n','buckets','probes','ef','workers','delay_ms'] if k in row)
        groups.setdefault(key, []).append(row)
    summary = [dict(key, **aggregate(group)) for key,group in groups.items()]
    (ROOT/'results/aggregate.json').write_text(json.dumps(summary,indent=2)+'\n')
    static = [r for r in summary if r['kind']=='static']
    configs = sorted(set((r['n'],r['buckets']) for r in static))
    fig, axes = plt.subplots(1,2,figsize=(11,4.2),layout='constrained')
    for color, (n,buckets) in zip(COLORS, configs):
        rs = sorted([r for r in static if (r['n'],r['buckets'])==(n,buckets)],key=lambda r:r['probes'])
        xs = np.array([r['bytes']['mean']/2**20 for r in rs])
        ys = np.array([r['tie_recall']['mean'] for r in rs])
        limits = np.array([r['tie_recall']['ci95'] for r in rs]).T
        label=f'{n/1e6:g}M / {buckets:,} buckets'
        axes[0].errorbar(xs,ys,yerr=[ys-limits[0],limits[1]-ys], marker='o', capsize=3, color=color,label=label)
        axes[1].plot([r['milliseconds']['p50'] for r in rs],ys,marker='o',color=color,label=label)
        for x,y,r in zip(xs,ys,rs):
            if n==max(c[0] for c in configs) and buckets==4096:
                axes[0].annotate(str(r['probes']), (x,y),xytext=(4,-12),textcoords='offset points',fontsize=8)
    for ax in axes:
        ax.set_ylim(0,1.03)
        ax.set_ylabel('Tie-aware recall@10')
        ax.set_xscale('log')
        ax.grid(alpha=.2)
    axes[0].set_xlabel('Mean query response body (MiB; log scale)')
    axes[1].set_xlabel('Median local HTTP query latency (ms; log scale)')
    axes[0].set_title('A  Recall costs bytes')
    axes[1].set_title('B  Recall costs latency')
    axes[1].legend(fontsize=8,loc='lower right')
    save(fig,'tradeoff')
    fig, axes = plt.subplots(1,3,figsize=(12,3.8),layout='constrained')
    for color, probes in zip(COLORS,[4,16,64,256]):
        rs=sorted([r for r in static if r['buckets']==1024 and r['probes']==probes],key=lambda r:r['n'])
        x=[r['n']/1e6 for r in rs]
        for ax,key,scale in zip(axes,['bytes','milliseconds','tie_recall'],[2**20,1,1]):
            ys=np.array([r[key]['mean'] / scale for r in rs])
            bounds=np.array([r[key]['ci95'] for r in rs]).T / scale
            ax.errorbar(x,ys,yerr=[ys-bounds[0],bounds[1]-ys],marker='o',capsize=3,color=color,label=f'{probes} probes')
            ax.set_xlabel('Indexed vectors (millions)')
            ax.grid(alpha=.2)
    axes[0].set_ylabel('Mean response body (MiB)')
    axes[1].set_ylabel('Mean query latency (ms)')
    axes[2].set_ylabel('Mean tie-aware recall@10')
    axes[2].set_ylim(0,1.03)
    axes[0].legend(fontsize=8)
    fig.suptitle('Fixed 1,024-bucket directory: growth makes each bucket larger')
    save(fig,'scaling')
    fig,axes=plt.subplots(1,2,figsize=(10,4),layout='constrained')
    largest=max(r['n'] for r in static)
    for color,ef in zip(COLORS,[16,64,256]):
        rs=sorted([r for r in summary if r['kind']=='hnsw' and r['ef']==ef],key=lambda r:r['n'])
        axes[0].plot([r['milliseconds']['p50'] for r in rs],[r['tie_recall']['mean'] for r in rs],marker='s',color=color,label=f'HNSW ef={ef}')
    for color,buckets in zip(COLORS,[1024,4096]):
        rs=sorted([r for r in static if r['n']==largest and r['buckets']==buckets],key=lambda r:r['probes'])
        axes[0].plot([r['milliseconds']['p50'] for r in rs],[r['tie_recall']['mean'] for r in rs],marker='o',linestyle='--',color=color,label=f'Static 3M, {buckets} buckets')
    axes[0].set_xscale('log')
    axes[0].set_ylim(0,1.03)
    axes[0].set_xlabel('Median query latency (ms; log scale)')
    axes[0].set_ylabel('Tie-aware recall@10')
    axes[0].set_title('A  Native HNSW versus HTTP IVF')
    axes[0].legend(fontsize=7)
    for color,(delay,workers) in zip(COLORS,[(0,1),(0,8),(20,1),(20,8)]):
        rs=sorted([r for r in summary if r['kind']=='delay' and r['delay_ms']==delay and r['workers']==workers],key=lambda r:r['probes'])
        if not rs:
            continue
        ys=np.array([r['milliseconds']['mean'] for r in rs])
        limits=np.array([r['milliseconds']['ci95'] for r in rs]).T
        axes[1].errorbar([r['probes'] for r in rs],ys,yerr=[ys-limits[0],limits[1]-ys],marker='o',capsize=3,color=color,label=f'{delay} ms delay, {workers} connections')
    axes[1].set_yscale('log')
    axes[1].set_xscale('log',base=4)
    axes[1].set_xticks([16,64,256],[16,64,256])
    axes[1].set_xlabel('Buckets probed (3M / 4,096 buckets)')
    axes[1].set_ylabel('Mean query latency (ms; log scale)')
    axes[1].set_title('B  Injected request delay')
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.grid(alpha=.2)
    save(fig,'latency')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    main()
