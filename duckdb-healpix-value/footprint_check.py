"""Fixed 100k ObsCore supplement, with a hard timeout for each individual query."""
import sitecustomize
import argparse,json,time,statistics,subprocess,sys
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq
import duckdb
from astropy import units as u
from mocpy import MOC
import shim
ROOT=Path(__file__).resolve().parent
SQL='''WITH m AS MATERIALIZED (SELECT id,moc_from_polygon(lon,lat,8) AS region FROM obs)
SELECT id,moc_area_sr(moc_intersect(region,survey.m)),moc_area_sr(moc_union(region,survey.m)) FROM m,survey ORDER BY id'''

def worker(arm,out):
    t=pq.read_table(ROOT/'data/obs.parquet');rows=t.to_pylist()
    survey=MOC.from_cone(lon=0*u.deg,lat=0*u.deg,radius=1*u.deg,max_depth=8)
    def areas(m,row):
        return [row['id'],float(m.intersection(survey).sky_fraction*4*np.pi),float(m.union(survey).sky_fraction*4*np.pi)]
    c=None
    if arm=='shim':
        c=duckdb.connect(config={'threads':4,'memory_limit':'6GB','temp_directory':str(ROOT/'tmp'),'max_temp_directory_size':'64MB'})
        shim.register(c);c.register('obs',t);c.execute('CREATE TABLE survey AS SELECT ?::BLOB AS m',[shim.encode(survey)])
    started_at=time.perf_counter()
    if arm in ['oracle','python_scalar']:
        actual=np.array([areas(MOC.from_polygon(np.array(row['lon'])*u.deg,np.array(row['lat'])*u.deg,max_depth=8),row) for row in rows])
    elif arm=='python_batch':
        output=[]
        for start in range(0,len(rows),2048):
            batch=rows[start:start+2048]
            vertices=[v for row in batch for v in (row['lon'],row['lat'])]
            mocs=MOC.from_polygons(vertices,max_depth=8,n_threads=4)
            output.extend(areas(m,row) for row,m in zip(batch,mocs))
        actual=np.array(output)
    else:actual=np.array(c.execute(SQL).fetchall())
    elapsed=time.perf_counter()-started_at
    result={'status':'ok','seconds':elapsed,'rows':len(actual)}
    if arm=='oracle':np.save(ROOT/'tmp/footprint-oracle.npy',actual)
    else:
        expected=np.load(ROOT/'tmp/footprint-oracle.npy')
        bad=~np.isclose(actual,expected,rtol=0,atol=1e-15).all(axis=1)
        result.update(row_diff_count=int(bad.sum()),edge_rows_differ=actual[bad & (actual[:,0]<4)].tolist())
    Path(out).write_text(json.dumps(result))

def main():
    result={'rows':100000,'order':8,'edge_ids':[0,1,2,3],'sql':SQL,'arms':{},'note':'Fixed footprint workload, separate from catalog scales. MOC areas, not exact polygon areas. Each query is independently bounded at 300 seconds. Four-thread DuckDB and batch baseline. Timers exclude input loading and connection setup for this supplement.'}
    def attempt(arm,rep):
        out=ROOT/'tmp'/f'footprint-{arm}-{rep}.json';out.unlink(missing_ok=True)
        with (ROOT/'logs'/f'footprint-{arm}-{rep}.log').open('w') as f:
            try:
                p=subprocess.run([sys.executable,__file__,'--arm',arm,'--out',str(out)],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=300)
                value=json.loads(out.read_text()) if out.exists() else {'status':'error','exit_code':p.returncode,'row_diff_count':None}
            except subprocess.TimeoutExpired:value={'status':'timeout','limit_seconds':300,'row_diff_count':None}
        print(arm,rep,value,flush=True);return value
    result['oracle']=attempt('oracle',0)
    if result['oracle']['status']=='ok':
        for arm in ['python_scalar','python_batch','shim']:
            trials=[attempt(arm,i) for i in range(3)]
            good=[x for x in trials if x['status']=='ok']
            result['arms'][arm]={'trials':trials,'median_seconds':statistics.median(x['seconds'] for x in good) if len(good)==3 else None}
            (ROOT/'logs/footprints.json').write_text(json.dumps(result,indent=2))
    result['complete']=True
    (ROOT/'logs/footprints.json').write_text(json.dumps(result,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--arm');p.add_argument('--out');args=p.parse_args()
    if args.arm:worker(args.arm,args.out)
    else:main()
