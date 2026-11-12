"""Rebuild data, execute bounded arms, and regenerate the evidence report."""
import sitecustomize
from pathlib import Path
import argparse,json,subprocess,sys,time,statistics,os
ROOT=Path(__file__).resolve().parent
SLUGS=['xmatch','moc-column','per-row-cones','adql-literal','sql-only','browser','ingest','density','lightcurves','lake-partition','map-analysis','distributed','s2-h3']
ARMS={1:['sql','python','neighbours','shim','shim_healpix'],2:['sql','shim'],3:['sql','python','ranges','shim'],4:['sql','python','geography','shim'],5:['sql','python','shim'],7:['sql','python','shim'],8:['sql','shim'],9:['sql','python','shim'],10:['sql','python','shim'],13:['geography','shim']}
SIZES=[1000000,10000000]

def attempt(case,n,arm,rep):
    path=ROOT/'tmp'/f'result-{case}-{n}-{arm}-{rep}.json'
    path.unlink(missing_ok=True)
    start=time.perf_counter()
    log=ROOT/'logs'/f'case-{case:02}-{n}-{arm}-{rep}.log'
    with log.open('w') as f:
        try:
            p=subprocess.run([sys.executable,str(ROOT/'bench.py'),str(case),str(n),arm,str(path)],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=300)
            result=json.loads(path.read_text()) if path.exists() else {'status':'error','error':f'worker exit {p.returncode}; see {log.relative_to(ROOT)}'}
        except subprocess.TimeoutExpired:result={'status':'timeout','limit_seconds':300}
    print(case,n,arm,rep,result.get('status'),result.get('seconds'),flush=True)
    return result

def run_case(case):
    folder=ROOT/'cases'/f'{case:02}-{SLUGS[case-1]}'
    folder.mkdir(parents=True,exist_ok=True)
    r={'case':case,'slug':SLUGS[case-1],'verdict':'UNPROVEN','axis':None,'number':None,'pure_sql_possible': 'yes' if case in [1,2,3,4,5,7,8,9,10,13] else 'unproven','sizes':{},'install':{'without':['duckdb'],'shim':['duckdb','pyarrow','cdshealpix','mocpy','astropy','numpy']},'timing_label':'shim','limitations':[]}
    if case in ARMS:
        for n in SIZES:
            truth=attempt(case,n,'oracle',0)
            block={'oracle':truth,'arms':{}}
            for arm in ARMS[case]:
                trials=[attempt(case,n,arm,rep) for rep in range(1 if case in [8,9,10] else 3)]
                good=[v for v in trials if v['status']=='ok']
                for v in good:
                    same=truth.get('status')=='ok' and v['sha256']==truth['sha256'] and v['rows']==truth['rows']
                    v['row_diff_count']=0 if same else v.get('diagnostic_row_diff_count')
                    v['correct']=same
                    v['edge_rows_differ']=[] if v.get('edge_rows')==truth.get('edge_rows') else {'actual':v.get('edge_rows'),'expected':truth.get('edge_rows')}
                block['arms'][arm]={'trials':trials,'median_seconds':statistics.median(x['seconds'] for x in good) if len(good)==len(trials) else None,'correct':len(good)==len(trials) and all(x['correct'] for x in good)}
            r['sizes'][str(n)]=block
        b=r['sizes']['10000000']['arms']; options=[(x['median_seconds'],a) for a,x in b.items() if not a.startswith('shim') and x['correct']]
        with_options=[(x['median_seconds'],a) for a,x in b.items() if a.startswith('shim') and x['correct']]
        if options and with_options:
            with_seconds,with_arm=min(with_options)
            seconds,base=min(options);ratio=seconds/with_seconds;r.update(best_baseline=base,best_with=with_arm,speed_ratio=ratio,number=ratio)
            if ratio>=3:r.update(verdict='MATTERS',axis='speed')
            elif ratio>=1.5:r.update(verdict='MARGINAL',axis='speed')
            elif any(a in ['sql','geography'] and x['correct'] and x['median_seconds']/with_seconds<1.5 for a,x in b.items()):r.update(verdict='NO',axis='speed')
        if case==1:r['limitations']+=['Both materialized declination/chord candidates and per-row HEALPix cone-range candidates are tested. Python MOC construction is not native performance; no native join or calibration exists. pyacid is installed; the Python comparator uses SciPy directly.']
        if case==2:r['limitations']+=['Benchmark covers multi-order probability cells × catalog counts. Fixed 100k ObsCore construction, intersection and union are measured in the supplement. Pure-SQL polygon-to-MOC construction and a native MOC type remain unverified.']
        if case==7:r['limitations']+=['Raw coordinate ingest tested via Arrow Python and shim COPY; pure-SQL ang2pix included. Native speed and calibration unverified.']
        if case==9:r['limitations']+=['Separate sorted Parquet photometry with three deterministic epochs per object; no production lake metadata or variable-length light curves.']
        if case==10:r['limitations']+=['Materialized pixel column only; no Iceberg or DuckLake service tested.']
        if case in [2]:
            r['measured_subcase_verdict']=r['verdict'];r['verdict']='UNPROVEN';r['axis']=None
    elif case==5:
        r['limitations']=['Python shim cannot validate CLI, dbt, R or Java extension availability. No claim that pure SQL HEALPix is impossible; native build was not completed.']
    elif case==6:
        import gzip,tarfile
        from bench import literal_filter
        ext=json.loads((ROOT/'logs/external.json').read_text())
        r['external']=ext.get('js');r['js_module_gzip_bytes']=ext.get('js',{}).get('esm_gzip_bytes');r['range_sql_bytes']=len(literal_filter().encode());r['number']=r['range_sql_bytes']
        tarpath=ROOT/'vendor/healpix-ts.tgz'
        if tarpath.exists():
            with tarfile.open(tarpath) as tar:raw=tar.extractfile('package/dist/index.mjs').read()
            r['js_module_gzip_bytes']=len(gzip.compress(raw,mtime=0))
        r['limitations']=['No browser requested or used. Shipped ESM gzip size is not tree-shaken bundle cost; generated SQL uses MOCPy, not execution of JS library. WASM size/load time unverified.']
    elif case in [11,12]:
        source=8 if case==11 else 1
        evidence=json.loads((ROOT/'cases'/f'{source:02}-{SLUGS[source-1]}'/'result.json').read_text())
        r['derived_evidence']={'source_case':source,'sizes':evidence['sizes'],'scope':'Local aggregation/join timings do not establish transforms or distributed execution.'}
        r['verdict']='NO';r['limitations']=['Scope conclusion, not a benchmark-derived speed verdict. No harmonics or distributed execution implemented by the v1 API.']
    if case==4:
        r['real_check']=json.loads((ROOT/'logs/external.json').read_text())['gaia']
        r['fallback']=json.loads((ROOT/'logs/hats.json').read_text()) if (ROOT/'logs/hats.json').exists() else {'status':'failed','log':'logs/hats.log'}
    if case==13:
        r['geography_reruns']={}
        for target in [1,3]:
            r['geography_reruns'][str(target)]={}
            original=json.loads((ROOT/'cases'/f'{target:02}-{SLUGS[target-1]}'/'result.json').read_text())
            for n in SIZES:
                trials=[attempt(target,n,'geography',i) for i in range(3)]
                truth=original['sizes'][str(n)]['oracle']
                for v in trials:
                    v['row_diff_count']=0 if v.get('sha256')==truth.get('sha256') and v.get('status')=='ok' else None
                r['geography_reruns'][str(target)][str(n)]=trials
        import duckdb
        c=duckdb.connect(config={'extension_directory':str(ROOT/'.cache/extensions')});c.execute('LOAD geography')
        r['missing_api']={}
        for sql in ['SELECT hpx_ang2pix(12,0.,0.)','SELECT moc_from_cone(0.,0.,0.5,12)']:
            try:c.execute(sql)
            except Exception as e:r['missing_api'][sql]=str(e)
        r['limitations']+=['S2-only spherical predicates rerun with SQL declination pruning; S2 covering-index join not benchmarked. Missing HEALPix/MOC API is not proof no SQL implementation can be written.']
    if case==2:
        fp=ROOT/'logs/footprints.json'
        r['footprints']=json.loads(fp.read_text()) if fp.exists() else {'status':'unverified','log':'logs/footprints.log'}
    r['query_lines']={arm:len([x for x in (folder/f'{arm}.sql').read_text().splitlines() if x.strip() and not x.lstrip().startswith('--')]) for arm in ['without','with'] if (folder/f'{arm}.sql').exists()}
    q=r['query_lines']
    r['query_line_reduction']=1-q['with']/q['without'] if q.get('without',0)>0 else None
    if r['verdict']=='NO' and r['query_line_reduction'] is not None and r['query_line_reduction']>=.5:
        r.update(verdict='MARGINAL',axis='code',number=r['query_line_reduction'])
    r['install']['per_arm']={}
    for arm in ARMS.get(case,[]):
        if arm.startswith('shim'):deps=r['install']['shim']
        elif arm=='neighbours':deps=['duckdb','cdshealpix','numpy','pyarrow']
        elif arm=='geography':deps=['duckdb','geography community extension']
        elif arm=='sql':deps=['duckdb']
        elif arm=='ranges' or case==4:deps=['duckdb','mocpy','astropy','pyarrow','numpy']
        elif case in [1,3]:deps=['duckdb','scipy','numpy','pyarrow']
        else:deps=['duckdb','cdshealpix','astropy','numpy','pyarrow']
        r['install']['per_arm'][arm]=deps
    r['shared_sql_macro_lines']=len((ROOT/'plain_healpix.sql').read_text().splitlines()) if case in [5,7] else len(__import__('bench').MACRO.splitlines())
    r['install']['all_tested_arms']=['duckdb','pyarrow','numpy','scipy','astropy','astropy-healpix','cdshealpix','mocpy']
    (folder/'result.json').write_text(json.dumps(r,indent=2))
    with (ROOT/'notes.md').open('a') as f:f.write(f"\n- Case {case:02}: {r['verdict']}; measured result written. Limitations: {' '.join(r['limitations'])}\n")
    return r

def main():
    p=argparse.ArgumentParser();p.add_argument('--case',type=int);p.add_argument('--reuse-data',action='store_true');p.add_argument('--report-only',action='store_true');p.add_argument('--commit',action='store_true');args=p.parse_args()
    if not args.report_only:
        import duckdb
        c=duckdb.connect(config={'extension_directory':str(ROOT/'.cache/extensions')})
        try:c.execute('LOAD geography')
        except Exception:c.execute('INSTALL geography FROM community; LOAD geography')
        c.close()
        if not (ROOT/'vendor/healpix-ts.tgz').exists():
            subprocess.run([sys.executable,'external_checks.py'],cwd=ROOT,check=True,timeout=180)
        if not args.reuse_data:
            import shutil
            for folder in ['data','tmp']:
                shutil.rmtree(ROOT/folder,ignore_errors=True)
                (ROOT/folder).mkdir()
            import make_data;make_data.main()
            import hats_check;hats_check.main()
            with (ROOT/'logs/footprints.log').open('w') as f:
                try:subprocess.run([sys.executable,'footprint_check.py'],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=3600)
                except subprocess.TimeoutExpired:(ROOT/'logs/footprints.json').write_text(json.dumps({'status':'timeout','limit_seconds':300}))
        for case in ([args.case] if args.case else range(1,14)):
            r=run_case(case)
            if args.commit or os.environ.get("HPX_COMMIT_CASES")=="1":
                subprocess.run(['git','add','--','.'],cwd=ROOT,check=True)
                subprocess.run(['git','commit','-m',f"duckdb-healpix-value: case {case:02} {r['verdict']}"],cwd=ROOT,check=True)
    import report;report.main()
if __name__=='__main__':main()
