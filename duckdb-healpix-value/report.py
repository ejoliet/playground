import sitecustomize
from pathlib import Path
import json,html,statistics
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
CLAIMS={1:'A cone predicate does not by itself supply an efficient cross-match join.',2:'Persisted multi-order cells can be joined using ordinary integer ranges.',3:'Per-row cones can be turned into SQL range joins without client orchestration.',4:'Literal cone ranges can be computed by a client before DuckDB runs.',5:'The intended API simplifies SQL clients, but a Python shim does not validate delivery.',6:'The no-extension browser path has a measurable JS and generated-SQL cost.',7:'Ingest can move pixel computation into COPY, but Python already offers a vectorized route.',8:'An existing level-29 key already contains every coarser density-map key.',9:'Position lookup is only one part of a light-curve lake.',10:'A materialized HEALPix key already supplies partition columns.',11:'The v1 API does not perform spherical harmonic analysis.',12:'The v1 API does not turn DuckDB into a distributed join engine.',13:'S2 already provides spherical distances; HEALPix/MOC interoperability is a separate claim.'}
OBJECTIONS={1:'A Python KD-tree or a proper neighbour-bucket join can beat these SQL joins.',2:'SQL integer ranges already perform set operations; why add another coverage type?',3:'A client can generate the same ranges, and KD-trees support variable radii.',4:'A dynamic UDF range relation may prune less effectively than literal BETWEEN filters.',5:'HEALPix is computable in SQL; lack of an implementation here is not impossibility.',6:'Applications tree-shake JS; compressed source size is not load latency.',7:'Arrow already avoids per-row Python overhead, and the native extension may behave differently.',8:'Raw ra/dec still needs a pixel computation.',9:'Three deterministic epochs do not represent a production time-series workload.',10:'This does not test Iceberg or DuckLake metadata or write paths.',11:'Map aggregation might still be useful even when transforms live elsewhere.',12:'A distributed system might embed DuckDB on each worker.',13:'S2 coverings and indexes could accelerate joins; this harness uses declination pruning.'}
ANSWERS={
1:'The KD-tree is measured alongside SQL. The tested shim replaces the exact predicate, not the join operator. A separate HEALPix cone-to-bucket candidate arm is also measured, against a streamed CDS-neighbour baseline as well as KD-tree and pure SQL. Python MOC construction and native join performance are distinct; timed-out variants remain unverified and do not supply a speed ratio.',
2:'The footprint supplement constructs all polygons and compares per-row intersection and union areas with direct MOCPy. Integer-range catalog joins are already SQL. Native column semantics and a portable SQL constructor remain unverified; no capability win is awarded.',
3:'Both a KD-tree and client-generated HEALPix ranges are timed, including setup. The range algorithm is available without an extension; the comparison measures where its construction and execution occur.',
4:'The client-generated literal filters are included, as is geography. Constant Parquet predicates can expose pruning opportunities that a UDF-produced range relation does not. The real Gaia check failed twice; the local HATS fallback is explicitly separate.',
5:'The macro demonstrates pure-SQL feasibility but disagrees at the exact RA=0, Dec=0 boundary. That arm is preserved as xfail; a correct Python baseline prevents turning this into a win over the best baseline. Native CLI delivery remains unverified.',
6:'Objection stands. The measurement is one shipped ESM module, not application load latency; no browser or extension WASM measurement was performed.',
7:'The COPY arms preserve coordinates, compute pixels, sort and write Parquet. The Arrow baseline calls CDS on whole arrays; the shim processes DuckDB chunks. Without native calibration these are shim results only.',
8:'For indexed input, the strongest with arm is hpx_parent, shimmed as the same bit shift as SQL and checked against independent ang2pix output. Raw-coordinate pixel generation is measured in cases 5 and 7; it must not be charged again to an indexed density query.',
9:'A separate Parquet table with repeated epochs is joined by object id. The extension changes position selection, not the ordinary photometry join. Production temporal layout and varying epoch counts remain outside this small shortcut.',
10:'Both the plain SQL shortcut and the hpx_parent shim derive the sort/partition key from the existing level-29 key. Iceberg or DuckLake metadata is not involved in that calculation; actual storage-service integration was not tested.',
11:'Case 8 measures aggregation, which is useful but is not a spherical harmonic transform. No harmonic API exists in the proposed v1 function table; no transform benchmark was requested.',
12:'Case 1 is a single-node join measurement, not a scaling study. Case 4 checks only a small LSDB HATS selection. Neither supports claims about Rubin-scale distributed execution.',
13:'The spherical predicate reruns test the existing S2 capability. Missing HEALPix/MOC functions establish an API boundary, not mathematical impossibility. S2-covering index joins remain unmeasured.'}
def fmt(x):return '—' if x is None else f'{x:.6g}' if isinstance(x,(int,float)) else str(x)
def main():
 results=[json.loads(p.read_text()) for p in sorted((ROOT/'cases').glob('*/result.json'))]
 if not results:return
 by_case={r['case']:r for r in results}
 # Case 13 runs these baselines later in the requested order. Include them
 # in the original cases' final competition rather than hiding a faster S2 arm.
 for target,sizes in by_case.get(13,{}).get('geography_reruns',{}).items():
  r=by_case[int(target)]
  for n,trials in sizes.items():
   truth=r['sizes'][n]['oracle']
   trials=[dict(v,correct=v.get('status')=='ok' and v.get('row_diff_count')==0,edge_rows_differ=[] if v.get('edge_rows')==truth.get('edge_rows') else {'actual':v.get('edge_rows'),'expected':truth.get('edge_rows')}) for v in trials]
   sizes[n]=trials
   good=[v for v in trials if v['status']=='ok']
   r['sizes'][n]['arms']['geography']={'trials':trials,'median_seconds':statistics.median(v['seconds'] for v in good) if len(good)==len(trials) else None,'correct':all(v['correct'] for v in trials),'source_case':13}
  r['install']['per_arm']['geography']=['duckdb','geography community extension']
  arms=r['sizes']['10000000']['arms']
  baselines=[(v['median_seconds'],a) for a,v in arms.items() if not a.startswith('shim') and v['correct']]
  variants=[(v['median_seconds'],a) for a,v in arms.items() if a.startswith('shim') and v['correct']]
  if baselines and variants:
   seconds,base=min(baselines);with_seconds,with_arm=min(variants);ratio=seconds/with_seconds
   r.update(best_baseline=base,best_with=with_arm,speed_ratio=ratio,number=ratio,verdict='UNPROVEN',axis=None)
   if ratio>=3:r.update(verdict='MATTERS',axis='speed')
   elif ratio>=1.5:r.update(verdict='MARGINAL',axis='speed')
   elif any(a in ['sql','geography'] and v['correct'] and v['median_seconds']/with_seconds<1.5 for a,v in arms.items()):r.update(verdict='NO',axis='speed')
   if r['verdict']=='NO' and (r.get('query_line_reduction') or 0)>=.5:r.update(verdict='MARGINAL',axis='code',number=r['query_line_reduction'])
 for target in [11,12]:
  if target in by_case:
   evidence=by_case[target]['derived_evidence']
   evidence['sizes']=by_case[evidence['source_case']]['sizes']
 for r in results:
  hats_path=ROOT/'logs/hats.json'
  if hats_path.exists():
   hats=json.loads(hats_path.read_text())
   if r['case']==4:r['fallback']=hats
   if r['case']==13 and 'geography_hats' in hats:r['geography_hats']=hats['geography_hats']
  if r['case']==2:
   if (ROOT/'logs/footprints.json').exists():r['footprints']=json.loads((ROOT/'logs/footprints.json').read_text())
   r['limitations']=[x.replace('ObsCore polygon construction, overlap and union are tested separately; 100k footprint performance is not measured.','Fixed 100k ObsCore construction, intersection and union are measured in the supplement. Pure-SQL polygon-to-MOC construction and a native MOC type remain unverified.') for x in r['limitations']]
  if r['case'] in [11,12]:
   source=r['derived_evidence']['source_case']
   arms=r['derived_evidence']['sizes']['10000000']['arms']
   valid=[(v['median_seconds'],a) for a,v in arms.items() if not a.startswith('shim') and v['correct']]
   if valid:
    seconds,arm=min(valid)
    r['number']=f'case {source}: {seconds:.6g}s ({arm}; scope evidence)'
  if r['case']==5:
   limitation='Python execution does not validate native CLI, dbt, R or Java delivery; the measured SQL macro has a boundary mismatch.'
   if limitation not in r['limitations']:r['limitations'].append(limitation)
  if r['pure_sql_possible']=='unproven' or (r['case'] in [5,7] and not r.get('sizes',{}).get('10000000',{}).get('arms',{}).get('sql',{}).get('correct',False)):
   r['pure_sql_possible']='no'
   r['pure_sql_note']='No oracle-correct pure-SQL route was established for the full stated use case; this is not a proof of mathematical impossibility.'
  if r['verdict']=='UNPROVEN' and r['case'] not in [2,5,7] and 'speed_ratio' in r:
   arms=r['sizes']['10000000']['arms'];with_seconds=arms[r['best_with']]['median_seconds']
   sql_ratios=[v['median_seconds']/with_seconds for a,v in arms.items() if a in ['sql','geography'] and v['correct']]
   if sql_ratios:
    r['closest_sql_to_shim_ratio']=min(sql_ratios)
    reason=f"Rubric gap: the best correct baseline is faster than the shim, but the closest correct SQL/S2 arm is {min(sql_ratios):.6g} times the shim time, outside the 1.5 band. No speed/code threshold is met. UNPROVEN is not a demonstrated extension win; native performance remains unmeasured."
    r['limitations']=[x for x in r['limitations'] if not x.startswith('Rubric gap:')]+[reason]
  r['timing_scope']={'sql_returning_arms':'connection, registration, reads, computation, materialization, canonical sort','direct_kdtree_cases_1_3':'connection, reads, tree build, query, result collection; validation ordering excluded','excluded':'process/module startup and final fingerprinting'}
  r['baseline_outcomes']={}
  for arm,v in r.get('sizes',{}).get('10000000',{}).get('arms',{}).items():
   if arm.startswith('shim'):continue
   r['baseline_outcomes'][arm]='selected fastest correct baseline' if arm==r.get('best_baseline') else ('slower than selected baseline' if v['correct'] else 'oracle mismatch, error or timeout; see trials')
  folder=ROOT/'cases'/f"{r['case']:02}-{r['slug']}"
  with_path=folder/('with-chord.sql' if r['case']==1 and r.get('best_with')=='shim' else 'with.sql')
  r['displayed_queries']={'without':(folder/'without.sql').read_text(),'with':with_path.read_text()}
  (folder/'result.json').write_text(json.dumps(r,indent=2))
 charts=ROOT/'charts';charts.mkdir(exist_ok=True)
 passes=[r for r in results if r['verdict']=='MATTERS' and r['axis'] in ['capability','correctness']]
 verdict_counts={v:sum(r['verdict']==v for r in results) for v in ['MATTERS','MARGINAL','NO','UNPROVEN']}
 verdict_summary=', '.join(f'{n} {v}' for v,n in verdict_counts.items() if n)
 pass_met=len(passes)>=3 and any(r.get('beyond_geography',False) for r in passes)
 text=['# Does a HEALPix/MOC extension matter for DuckDB?', '',f'This run yields {verdict_summary}. The project pass line is {"met" if pass_met else "not met"}: {len(passes)} cases are MATTERS on capability or correctness (required: 3, including one beyond geography). Existing pixel keys and client-computed ranges provide strong baselines. Shim timings describe this Python implementation, not native extension speed. Several broad workloads remain UNPROVEN because the measured subcase does not establish the full claim; these are explicitly listed below. Scope down to validating the remaining MOC/HATS and native SQL-client claims before committing through Gate 5.','', '| Case | Verdict | Winning axis | Carrying number (baseline/shim at 10M unless noted) |','|---|---|---|---|']
 for r in results:text.append(f"| {r['case']:02} {r['slug']} | {r['verdict']} | {r['axis'] or '—'} | {fmt(r['number']) + (' bytes of generated SQL' if r['case']==6 else '')} |")
 text+=['','Timing includes connection/UDF registration, input reads, candidate computation and result materialization. SQL-returning arms include the harness canonical sort; direct KD-tree baselines in cases 1 and 3 canonicalize only during validation outside the timer, a concession to those baselines. Python module startup and final fingerprinting are excluded. Each normal arm has three fresh-process trials; small cases have one trial per scale. Warm OS page cache is possible. Input catalogs are physically sorted by the level-29 key as requested; ingest ignores that key but inherits the spatial ordering. DuckDB uses four threads and disables `cte_filter_pusher` consistently for all main arms. Fixed-order cone coverage is expanded into order-12 buckets for hash joins; it is not left as a quadratic point-in-interval merge join. Orders/seed/versions are recorded in data/manifest.json, logs/setup.json and the lockfile. Exact integer row-set fingerprints are compared against independently computed Astropy/astropy-healpix oracles. Zero diff means equal row count and SHA-256; mismatches retain null diff count rather than an invented count. No native calibration was obtained.','']
 text+=['![Measured baseline/shim ratios](charts/summary.png)','']
 ratios=[]
 for r in results:
  i=r['case'];folder=ROOT/'cases'/f"{i:02}-{r['slug']}"
  text += [f"## {i:02} — {r['slug']}",'',CLAIMS[i],'','| Without | With (shim) |','|---|---|']
  snippets=[html.escape(r['displayed_queries'][arm]).replace('\n','<br>') for arm in ['without','with']]
  text += [f'| <code>{snippets[0]}</code> | <code>{snippets[1]}</code> |','','These are short SQL forms; the without cell can be a losing SQL arm. The fastest measured baseline and shim variant are named below. `bench.py:execute` is the executed source, including Python range construction and COPY setup. Shared `sep`/`point` macros and registration costs are not counted in these displayed query-line counts.','',f"Evidence: [{folder.name}/result.json](cases/{folder.name}/result.json).",'', '| Scale | Arm | Median seconds | Oracle row diff | Status |','|---|---|---|---|---|']
  for n,b in r['sizes'].items():
   for arm,a in b['arms'].items():
    text.append(f"| {n} | {arm} | {fmt(a['median_seconds'])} | {'0' if a['correct'] else '/'.join(str(v.get('row_diff_count','unverified')) for v in a['trials'])} | {','.join(v['status'] for v in a['trials'])} |")
  if not r['sizes']:text.append('| — | Not benchmarked | — | — | '+r['verdict']+' |')
  if 'js_module_gzip_bytes' in r:text += ['',f"Shipped ESM gzip: {r['js_module_gzip_bytes']} bytes; generated range predicate: {r['range_sql_bytes']} bytes. Version and provenance in result.json."]
  if 'fallback' in r:text+=['',f"Local HATS fallback: `{json.dumps(r['fallback'])}`. Public attempts: `{json.dumps(r['real_check'])}`."]
  if 'geography_hats' in r:text+=['','Local HATS geography-only scan (input file-list length, not a physical I/O profile): `'+json.dumps(r['geography_hats'])+'`.']
  if 'geography_reruns' in r:
   text+=['','Geography-only reruns (individual seconds; each compared to the original oracle):']
   for target,sizes in r['geography_reruns'].items():
    for n,trials in sizes.items():text.append(f"- Case {target}, {n}: "+', '.join(fmt(v.get('seconds'))+' / diff '+str(v.get('row_diff_count')) for v in trials))
   text+=['','Exact API boundary:']+[f"```text\n{sql}\n{err}\n```" for sql,err in r['missing_api'].items()]
  if 'derived_evidence' in r:
   evidence=r['derived_evidence'];text+=['',f"Evidence drawn from case {evidence['source_case']}:"]
   for n,b in evidence['sizes'].items():
    text += [f"- {n}: "+', '.join(arm+' '+fmt(v['median_seconds'])+' seconds' for arm,v in b['arms'].items())]
   text+=['',evidence['scope']]
  if 'footprints' in r:
   fp=r['footprints'];text+=['',f"Fixed {fp.get('rows','unverified')} ObsCore polygon supplement at order {fp.get('order','unverified')}:",'', '| Arm | Median seconds | Trial row differences |','|---|---|---|']
   for arm,v in fp.get('arms',{}).items():text.append('| '+arm+' | '+fmt(v.get('median_seconds'))+' | '+', '.join(str(t.get('row_diff_count',t.get('status'))) for t in v['trials'])+' |')
   if not fp.get('arms'):text.append('| Bundle | — | '+fp.get('status','unverified')+' |')
   text+=['',fp.get('note','No per-query result preserved; do not interpret a bundle timeout as a query timing.')]

  text+=['',f"Pure SQL possible: **{r['pure_sql_possible']}**. {r.get('pure_sql_note','')} Displayed query lines: `{r.get('query_lines',{})}`. Install: `{r['install']}`.",'',f"**Skeptical objection:** {OBJECTIONS[i]}",'','**Answer:** '+ANSWERS[i]]
  if 'best_baseline' in r:text += ['',f"Best measured baseline: `{r['best_baseline']}`; best measured with arm: `{r.get('best_with','shim')}`; baseline/shim ratio {fmt(r['speed_ratio'])}. Subcase verdict: {r.get('measured_subcase_verdict',r['verdict'])}. Native calibration could change speed rankings; no factor was measured, so no verdict is flipped."]
  text+=['','Baseline outcomes: `'+json.dumps(r['baseline_outcomes'])+'`.','']+['- '+x for x in r['limitations']]+['']
  if r['sizes']:
   text += [f"[Benchmark chart](charts/{i:02}-{r['slug']}.png)",'']
   fig,ax=plt.subplots(figsize=(7,4));x=np.arange(2);base=r.get('best_baseline',next(iter(next(iter(r['sizes'].values()))['arms'])))
   for offset,arm in [(-.18,base),(.18,r.get('best_with','shim'))]:
    vals=[r['sizes'][str(n)]['arms'].get(arm,{}).get('median_seconds') for n in [1000000,10000000]]
    ax.bar(x+offset,[v if v is not None else np.nan for v in vals],width=.35,label=arm)
   ax.set_xticks(x,['1M','10M']);ax.set_ylabel('seconds');ax.set_title(f"{i:02} {r['slug']} — {r['verdict']}");ax.legend();fig.tight_layout();fig.savefig(charts/f'{i:02}-{r["slug"]}.png',dpi=150);plt.close(fig)
   if 'speed_ratio' in r:ratios.append((f'{i:02}',r['speed_ratio']))
 text += ['## What the cross-match non-goal costs','','No verdict can honestly be changed for a hypothetical join operator. Case 1 measures a declination bucket join and KD-tree; it also measures per-row HEALPix cone ranges, but does not measure a native HEALPix neighbour join. The published function table also lacks a neighbour primitive: the shim bucket arm constructs per-row cones while the CDS baseline streams neighbours directly. A dedicated operator or neighbour primitive could reduce candidate generation and UDF overhead in cases 1 and 3, but both correctness and speed require a new benchmark. Case 12 still needs distributed orchestration.','','## What geography already covers','','The measured S2 distance predicates cover cones and cross-match distances, including wrap and polar inputs when oracle checks pass. Geography-only case 13 reruns identify the concrete API boundary: HEALPix conversion and MOC construction are absent from the installed function catalog. This does not prove no equivalent SQL/library composition exists. HATS partitions and IVOA MOC use a different cell encoding from S2. S2 covering joins, polygons and MOC interoperability were not exhaustively benchmarked.','','## Public pitch','','The three defensible topics to demonstrate next are MOC-valued coverage (case 2), per-row cone ranges (case 3), and HATS interoperability (case 4). These are proposed demonstrations, not three established wins. Drop claims that spherical predicates are unavailable in DuckDB, that density maps need an extension when a pixel key exists, that a shim proves WASM delivery, or that these measurements establish distributed/CMB capability.','','## Reproduction and limitations','','```bash\ncd duckdb-healpix-value\nuv sync --locked\nuv cache clean --cache-dir .cache/uv  # keep the complete run below the disk cap\nuv run python external_checks.py  # network checks, at most two Gaia attempts\nuv run python run_all.py         # regenerate both scales, all arms, report/charts\nuv run python verify.py         # full pytest, counts, and report refresh\nuv run python run_all.py --report-only\n```','','One native build was attempted and stopped on a missing submodule; it did not test compilability. No second build or native load was attempted. To perform a proper recursive build (requires Rust and the exact DuckDB CLI):','','```bash\ngit clone --recursive https://github.com/ejoliet/healpix-duckdb vendor/healpix-native\ncd vendor/healpix-native\ngit checkout 9154587498af20e0e41279fb749f1651829cbe94\ngit submodule update --init --recursive\ntimeout 600 make\nduckdb -unsigned -c "LOAD \'build/release/extension/healpix/healpix.duckdb_extension\'; SELECT hpx_ang2pix(12,0.,0.);"\ncd ../..\n```','','After locating the built artifact, calibration can be run with `uv run python calibrate.py --extension vendor/healpix-native/build/release/extension/healpix/healpix.duckdb_extension`. The artifact path must be checked against the build output. The optional script is supplied but unexecuted; no native build succeeded here.', '', 'The CLI must be v1.5.6. Full failed build log: logs/native-build.log. Upstream README snapshot: logs/upstream-README.md. No native-versus-shim calibration exists.','','Unverified: native load, native calibration, browser/WASM, production ObsCore and time-series integration, Iceberg/DuckLake integration, native HEALPix-neighbour and S2-covering joins, pyacid performance, public Gaia query, spherical harmonics and distributed scaling. No skipped item is counted as a capability win. No test asserts correctness for an unexecuted arm.']
 validation=ROOT/'logs/validation.json'
 if validation.exists():text+=['','Test evidence: `'+json.dumps(json.loads(validation.read_text()))+'`.']
 aggregate={'cases':results,'setup':json.loads((ROOT/'logs/setup.json').read_text()),'validation':json.loads(validation.read_text()) if validation.exists() else None,'threads':4,'project_pass_count':len(passes),'project_pass_required':3,'project_pass_met':pass_met,'verdict_counts':verdict_counts}
 (ROOT/'result.json').write_text(json.dumps(aggregate,indent=2))
 (ROOT/'README.md').write_text('\n'.join(text)+'\n')
 if ratios:
  fig,ax=plt.subplots(figsize=(8,4));ax.bar([x[0] for x in ratios],[x[1] for x in ratios]);ax.axhline(1,color='black');ax.axhline(3,color='green',linestyle='--');ax.set_ylabel('best baseline / shim seconds');ax.set_xlabel('case');ax.set_title('Measured subcases only; not native speed');fig.tight_layout();fig.savefig(charts/'summary.png',dpi=150);plt.close(fig)
if __name__=='__main__':main()
