import sitecustomize
from pathlib import Path
import json,time,hashlib,sys,importlib.util,re
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import duckdb
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy_healpix import HEALPix
from mocpy import MOC
from scipy.spatial import cKDTree
import shim
ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
SLUGS=['xmatch','moc-column','per-row-cones','adql-literal','sql-only','browser','ingest','density','lightcurves','lake-partition','map-analysis','distributed','s2-h3']
MACRO='''CREATE MACRO sep(a,b,c,d) AS degrees(atan2(sqrt(pow(cos(radians(d))*sin(radians(c-a)),2)+pow(cos(radians(b))*sin(radians(d))-sin(radians(b))*cos(radians(d))*cos(radians(c-a)),2)),sin(radians(b))*sin(radians(d))+cos(radians(b))*cos(radians(d))*cos(radians(c-a))));'''

def conn(n,with_shim=True):
    c=duckdb.connect(config={'threads':4,'memory_limit':'6GB','max_temp_directory_size':'64MB','temp_directory':str(ROOT/'tmp'),'extension_directory':str(ROOT/'.cache/extensions')})
    c.execute("SET disabled_optimizers='cte_filter_pusher'")
    c.execute(MACRO)
    if with_shim:shim.register(c)
    c.execute((ROOT/'plain_healpix.sql').read_text())
    c.execute(f"create view cat as select * from read_parquet('{DATA}/cat-{n}.parquet')")
    if (DATA/f'other-{n}.parquet').exists():c.execute(f"create view other as select * from read_parquet('{DATA}/other-{n}.parquet')")
    c.execute(f"create view watch as select * from read_parquet('{DATA}/watch.parquet')")
    return c

def xyz(t):
    a=np.deg2rad(t['ra'].to_numpy());b=np.deg2rad(t['dec'].to_numpy())
    return np.column_stack((np.cos(b)*np.cos(a),np.cos(b)*np.sin(a),np.sin(b)))
def sorted_rows(t):
    a=np.column_stack([t[x].to_numpy() for x in t.column_names])
    return a[np.lexsort(tuple(a[:,i] for i in reversed(range(a.shape[1]))))]
def digest(a):
    a=np.asarray(a)
    if a.ndim==1:a=a[:,None]
    if len(a):a=a[np.lexsort(tuple(a[:,i] for i in reversed(range(a.shape[1]))))]
    return {'rows':len(a),'sha256':hashlib.sha256(a.astype('<i8').tobytes()).hexdigest(),'edge_rows':[x.tolist() for x in a if int(x[0])<8][:100]} if len(a)<200000 else {'rows':len(a),'sha256':hashlib.sha256(a.astype('<i8').tobytes()).hexdigest(),'edge_rows':a[a[:,0]<8][:100].tolist()}
def quote(s):return re.sub(r'\bdec\b', '"dec"',s)
def query(c,s):return c.execute(quote(s)).fetch_arrow_table()
def read(n,name='cat'):return pq.read_table(DATA/f'{name}-{n}.parquet')
def cone_ranges(ra=0.,dec=0.,r=.5):return MOC.from_cone(lon=ra*u.deg,lat=dec*u.deg,radius=r*u.deg,max_depth=12).to_depth29_ranges
def literal_filter():return ' OR '.join(f'_healpix_29 BETWEEN {lo} AND {int(hi)-1}' for lo,hi in cone_ranges())
def watch_ranges():
    w=pq.read_table(DATA/'watch.parquet').to_pydict(); rows=[]
    mocs=MOC.from_cones(lon=np.array(w['ra'])*u.deg,lat=np.array(w['dec'])*u.deg,radius=np.array(w['radius'])*u.deg,max_depth=12,n_threads=4)
    for i,a,b,r,m in zip(w['wid'],w['ra'],w['dec'],w['radius'],mocs):
        for lo,hi in m.to_depth29_ranges:rows.append((i,int(lo),int(hi),a,b,r))
    return pa.table(dict(zip(['wid','lo','hi','ra','dec','radius'],zip(*rows))))

def neighbour_reader(n):
    import cdshealpix as hp
    schema=pa.schema([('other_id',pa.int64()),('bucket',pa.int64()),('bra',pa.float64()),('bdec',pa.float64())])
    def batches():
        for batch in pq.ParquetFile(DATA/f'other-{n}.parquet').iter_batches(batch_size=65536):
            cols={name:batch.column(i).to_numpy() for i,name in enumerate(batch.schema.names)}
            neighbours=hp.neighbours((cols['_healpix_29'] >> 34).astype('uint64'),12,num_threads=4).ravel()
            valid=neighbours>=0
            arrays=[np.repeat(cols['id'],9)[valid],neighbours[valid],np.repeat(cols['ra'],9)[valid],np.repeat(cols['dec'],9)[valid]]
            yield pa.RecordBatch.from_arrays([pa.array(x) for x in arrays],schema=schema)
    return pa.RecordBatchReader.from_batches(schema,batches())

def oracle(case,n):
    t=read(n)
    if case in [4,9,13]:
        s=SkyCoord(t['ra'].to_numpy()*u.deg,t['dec'].to_numpy()*u.deg)
        ids=t['id'].to_numpy()[s.separation(SkyCoord(0*u.deg,0*u.deg)).deg<=.5]
        if case==9:return np.column_stack((np.repeat(ids,3),np.tile(np.arange(3),len(ids)),np.repeat((ids%17)*3,3)+np.tile(np.arange(3),len(ids))))
        return ids
    if case in [5,7,10]:
        p=HEALPix(nside=2**12,order='nested').lonlat_to_healpix(t['ra'].to_numpy()*u.deg,t['dec'].to_numpy()*u.deg)
        return np.column_stack((t['id'].to_numpy(),p))
    if case==8:
        p=HEALPix(nside=2**6,order='nested').lonlat_to_healpix(t['ra'].to_numpy()*u.deg,t['dec'].to_numpy()*u.deg)
        a,b=np.unique(p,return_counts=True);return np.column_stack((a,b))
    if case==3:
        w=pq.read_table(DATA/'watch.parquet');tree=cKDTree(xyz(t)); out=[]
        for row,point in zip(w.to_pylist(),xyz(w)):
            idx=tree.query_ball_point(point,2*np.sin(np.deg2rad(row['radius'])/2))
            if idx:
                sc=SkyCoord(t['ra'].to_numpy()[idx]*u.deg,t['dec'].to_numpy()[idx]*u.deg)
                good=sc.separation(SkyCoord(row['ra']*u.deg,row['dec']*u.deg)).deg<=row['radius']
                out.extend((row['wid'],int(i)) for i in t['id'].to_numpy()[idx][good])
        return np.array(out,dtype='int64').reshape(-1,2)
    if case==1:
        b=read(n,'other'); acoord=SkyCoord(t['ra'].to_numpy()*u.deg,t['dec'].to_numpy()*u.deg);bcoord=SkyCoord(b['ra'].to_numpy()*u.deg,b['dec'].to_numpy()*u.deg)
        from astropy.coordinates import search_around_sky
        i,j,_,_=search_around_sky(acoord,bcoord,1*u.arcsec)
        return np.column_stack((t['id'].to_numpy()[i],b['id'].to_numpy()[j]))
    if case==2:
        # Independent astropy HEALPix assignment to a non-overlapping multi-order probability map.
        sm=pq.read_table(DATA/'skymap.parquet').to_pydict()
        p=HEALPix(nside=2,order='nested').lonlat_to_healpix(t['ra'].to_numpy()*u.deg,t['dec'].to_numpy()*u.deg)
        return np.column_stack((np.arange(15),[np.count_nonzero(p//(4 if o==0 else 1)==pix) for o,pix in zip(sm['order'],sm['ipix'])]))
    raise ValueError(case)

def execute(case,n,arm):
    c=conn(n,with_shim=arm.startswith('shim'))
    if arm=='oracle':return oracle(case,n)
    pred='sky_in_cone' if arm=='shim' else None
    if arm=='geography':
        c.execute('LOAD geography')
        c.execute('CREATE MACRO point(a,b) AS s2_geogfromtext(\'POINT (\' || a || \' \' || b || \')\')')
    if case in [4,9,13]:
        cols='id'
        if arm=='python':sql=f'SELECT {cols} FROM cat WHERE ({literal_filter()}) AND sep(ra,dec,0,0)<=0.5'
        elif arm=='shim':sql=f'''WITH intervals AS (SELECT unnest(moc_ranges(moc_from_cone(0.,0.,.5,12))) AS x),
        pixels AS (SELECT unnest(range(x.lo >> 34,x.hi >> 34)) AS bucket FROM intervals),
        candidates AS MATERIALIZED (SELECT cat.* FROM cat SEMI JOIN pixels ON (_healpix_29 >> 34)=bucket)
        SELECT {cols} FROM candidates WHERE sky_in_cone(ra,dec,0.,0.,.5)'''
        elif arm=='geography':sql=f'SELECT {cols} FROM cat WHERE dec BETWEEN -.5 AND .5 AND s2_dwithin(point(ra,dec),point(0,0),radians(0.5)*6371010)'
        else:sql=f'SELECT {cols} FROM cat WHERE dec BETWEEN -.5 AND .5 AND sep(ra,dec,0,0)<=.5'
        if case==9:
            sql=f"WITH selected AS ({sql}) SELECT p.id,p.epoch,p.flux FROM read_parquet('{DATA}/phot-{n}.parquet') p JOIN selected USING(id)"
        return sorted_rows(query(c,sql))
    if case in [5,7,10]:
        if arm=='shim' and case==10:sql='SELECT id,hpx_parent(29,_healpix_29,12) AS pix FROM cat'
        elif arm=='shim':sql='SELECT id,hpx_ang2pix(12,ra,dec) AS pix FROM cat'
        elif arm=='sql' and case in [5,7]:sql="SELECT * FROM plain_pixels('cat',12)"
        elif arm=='sql' and case==10:sql='SELECT id, _healpix_29 >> 34 AS pix FROM cat'
        else:
            t=query(c,'SELECT id,ra,dec FROM cat'); import cdshealpix as hp
            p=hp.lonlat_to_healpix(t['ra'].to_numpy()*u.deg,t['dec'].to_numpy()*u.deg,12,num_threads=4).astype('int64')
            columns={'id':t['id'],'pix':p}
            if case==7:columns.update(ra=t['ra'],dec=t['dec'])
            c.register('indexed',pa.table(columns));sql='SELECT * FROM indexed'
        if case==7:
            if arm=='shim':sql='SELECT id,ra,dec,hpx_ang2pix(12,ra,dec) AS pix FROM cat'
            elif arm=='sql':sql="SELECT p.*,c.ra,c.dec FROM plain_pixels('cat',12) p JOIN cat c USING(id)"
            dest=ROOT/'tmp'/f'ingest-{arm}.parquet'
            c.execute(f"COPY ({quote(sql)} ORDER BY pix) TO '{dest}' (FORMAT PARQUET, COMPRESSION ZSTD)")
            result=sorted_rows(pq.read_table(dest,columns=['id','pix']));dest.unlink();return result
        return sorted_rows(query(c,sql))
    if case==8:
        pixel='hpx_parent(29,_healpix_29,6)' if arm=='shim' else '_healpix_29 >> 46'
        return sorted_rows(query(c,f'SELECT {pixel} AS pixel,count(*) FROM cat GROUP BY 1'))
    if case==2:
        sm=pq.read_table(DATA/'skymap.parquet'); d=sm.to_pydict()
        lo=[int(p)<<int(2*(29-o)) for o,p in zip(d['order'],d['ipix'])]; hi=[int(p+1)<<int(2*(29-o)) for o,p in zip(d['order'],d['ipix'])]
        columns={'rid':np.arange(15),'lo':lo,'hi':hi}
        if arm=='shim':columns['moc']=[shim.encode(MOC.from_depth29_ranges(int(o),np.array([[l,h]],dtype='uint64'))) for o,l,h in zip(d['order'],lo,hi)]
        c.register('regions',pa.table(columns))
        # Range join prevents scalar moc_contains from penalizing the shim with 150M Python calls.
        sql='SELECT rid,count(*) FROM cat JOIN regions ON _healpix_29>=lo AND _healpix_29<hi GROUP BY rid'
        if arm=='shim':sql='WITH r AS (SELECT rid,unnest(moc_ranges(moc)) AS x FROM regions) SELECT rid,count(*) FROM cat JOIN r ON _healpix_29>=x.lo AND _healpix_29<x.hi GROUP BY rid'
        return sorted_rows(query(c,sql))
    if case==3:
        if arm=='python':
            w=pq.read_table(DATA/'watch.parquet'); t=read(n);tree=cKDTree(xyz(t));ids=t['id'].to_numpy();out=[]
            for row,point in zip(w.to_pylist(),xyz(w)):
                out.extend((row['wid'],int(ids[i])) for i in tree.query_ball_point(point,2*np.sin(np.deg2rad(row['radius'])/2)))
            return np.asarray(out,dtype='int64').reshape(-1,2)
        if arm=='ranges':
            c.register('ranges',watch_ranges());sql='WITH r AS (SELECT *,unnest(range(lo >> 34,hi >> 34)) AS bucket FROM ranges) SELECT wid,id FROM cat c JOIN r ON (c._healpix_29 >> 34)=r.bucket WHERE sep(c.ra,c.dec,r.ra,r.dec)<=radius'
        elif arm=='shim':sql='''WITH intervals AS MATERIALIZED (SELECT wid,ra,dec,radius,unnest(moc_ranges(moc_from_cone(ra,dec,radius,12))) AS x FROM watch),
        r AS (SELECT wid,ra,dec,radius,unnest(range(x.lo >> 34,x.hi >> 34)) AS bucket FROM intervals),
        candidates AS MATERIALIZED (SELECT wid,id,c.ra AS ara,c.dec AS adec,r.ra AS bra,r.dec AS bdec,r.radius FROM cat c JOIN r ON (c._healpix_29 >> 34)=r.bucket)
        SELECT wid,id FROM candidates WHERE sky_in_cone(ara,adec,bra,bdec,radius)'''
        else:
            exact='s2_dwithin(point(c.ra,c.dec),point(w.ra,w.dec),radians(w.radius)*6371010)' if arm=='geography' else 'sep(c.ra,c.dec,w.ra,w.dec)<=w.radius'
            sql=f'''WITH c AS MATERIALIZED (SELECT *,cos(radians(dec))*cos(radians(ra)) AS x,cos(radians(dec))*sin(radians(ra)) AS y FROM cat),
            w0 AS MATERIALIZED (SELECT *,cos(radians(dec))*cos(radians(ra)) AS x,cos(radians(dec))*sin(radians(ra)) AS y,2*sin(radians(radius)/2)+1e-14 AS chord FROM watch),
            w AS (SELECT *,unnest(range(floor((dec-radius)*1000)::BIGINT,floor((dec+radius)*1000)::BIGINT+1)) AS bucket FROM w0)
            SELECT wid,id FROM c JOIN w ON floor(c.dec*1000)::BIGINT=w.bucket AND c.dec BETWEEN w.dec-w.radius AND w.dec+w.radius
            AND abs(c.x-w.x)<=w.chord AND abs(c.y-w.y)<=w.chord WHERE {exact}'''
            prefix,tail=sql.rsplit('SELECT wid,id FROM c JOIN w',1)
            bounds=tail.split(' WHERE ',1)[0]
            mapped=exact.replace('c.ra','cra').replace('c.dec','cdec').replace('w.ra','wra').replace('w.dec','wdec').replace('w.radius','radius')
            # Replace radius before ra to avoid a prefix substitution inside w.radius.
            mapped=exact.replace('w.radius','radius').replace('c.ra','cra').replace('c.dec','cdec').replace('w.ra','wra').replace('w.dec','wdec')
            sql=prefix+', candidates AS MATERIALIZED (SELECT wid,id,c.ra AS cra,c.dec AS cdec,w.ra AS wra,w.dec AS wdec,w.radius AS radius FROM c JOIN w'+bounds+') SELECT wid,id FROM candidates WHERE '+mapped
        return sorted_rows(query(c,sql))
    if case==1:
        if arm=='neighbours':
            c.register('neighbours',neighbour_reader(n))
            sql='''WITH candidates AS MATERIALIZED (
            SELECT a.id,b.other_id,a.ra AS ara,a.dec AS adec,b.bra,b.bdec FROM cat a JOIN neighbours b ON (a._healpix_29 >> 34)=b.bucket)
            SELECT id,other_id FROM candidates WHERE sep(ara,adec,bra,bdec)<=1./3600'''
            return sorted_rows(query(c,sql))
        if arm=='shim_healpix':
            sql='''WITH intervals AS MATERIALIZED (
            SELECT id AS other_id,ra,dec,unnest(moc_ranges(moc_from_cone(ra,dec,1./3600,12))) AS x FROM other),
            r AS (SELECT other_id,ra,dec,unnest(range(x.lo >> 34,x.hi >> 34)) AS bucket FROM intervals),
            candidates AS MATERIALIZED (
            SELECT a.id,r.other_id,a.ra AS ara,a.dec AS adec,r.ra AS bra,r.dec AS bdec
            FROM cat a JOIN r ON (a._healpix_29 >> 34)=r.bucket)
            SELECT id,other_id FROM candidates WHERE sky_in_cone(ara,adec,bra,bdec,1./3600)'''
            return sorted_rows(query(c,sql))
        if arm=='python':
            a=read(n);b=read(n,'other');tree=cKDTree(xyz(b));bid=b['id'].to_numpy();out=[]
            av=xyz(a);aid=a['id'].to_numpy();radius=2*np.sin(np.deg2rad(1/3600)/2)
            for start in range(0,len(a),100000):
                idx=tree.query_ball_point(av[start:start+100000],radius)
                out.extend((int(aid[start+i]),int(bid[j])) for i,js in enumerate(idx) for j in js)
            return np.asarray(out,dtype='int64').reshape(-1,2)
        exact='sky_in_cone(a.ra,a.dec,b.ra,b.dec,1./3600)' if arm=='shim' else 'sep(a.ra,a.dec,b.ra,b.dec)<=1./3600'
        if arm=='geography':exact='s2_dwithin(point(a.ra,a.dec),point(b.ra,b.dec),radians(1./3600)*6371010)'
        sql=f'''WITH a AS MATERIALIZED (SELECT *,cos(radians(dec))*cos(radians(ra)) AS x,cos(radians(dec))*sin(radians(ra)) AS y,sin(radians(dec)) AS z FROM cat),
        b0 AS MATERIALIZED (SELECT *,cos(radians(dec))*cos(radians(ra)) AS x,cos(radians(dec))*sin(radians(ra)) AS y,sin(radians(dec)) AS z FROM other),
        b AS (SELECT *,unnest([floor(dec*3600)::BIGINT-1,floor(dec*3600)::BIGINT,floor(dec*3600)::BIGINT+1]) AS bucket FROM b0)
        SELECT a.id,b.id AS other_id FROM a JOIN b ON floor(a.dec*3600)::BIGINT=b.bucket
        AND abs(a.x-b.x)<=2*sin(radians(1./3600)/2)+1e-14
        AND abs(a.y-b.y)<=2*sin(radians(1./3600)/2)+1e-14
        AND abs(a.z-b.z)<=2*sin(radians(1./3600)/2)+1e-14 WHERE {exact}'''
        prefix,tail=sql.rsplit('SELECT a.id,b.id AS other_id',1)
        bounds=tail.split(' WHERE ',1)[0]
        mapped=exact.replace('a.ra','ara').replace('a.dec','adec').replace('b.ra','bra').replace('b.dec','bdec')
        sql=prefix+', candidates AS MATERIALIZED (SELECT a.id,b.id AS other_id,a.ra AS ara,a.dec AS adec,b.ra AS bra,b.dec AS bdec'+bounds+') SELECT id,other_id FROM candidates WHERE '+mapped
        return sorted_rows(query(c,sql))
    raise ValueError(case)

def worker(case,n,arm,out):
    # Keep the ingest output within the disk budget; rebuild counterparts before S2 reruns.
    # Resource staging is outside the timed region, symmetric across arms.
    if case==7:
        for size in [1000000,10000000]:(DATA/f'other-{size}.parquet').unlink(missing_ok=True)
    if case==13:
        import make_data
        for size in [1000000,10000000]:
            if not (DATA/f'other-{size}.parquet').exists():make_data.write(size)
    start=time.perf_counter()
    try:
        arr=execute(case,n,arm); seconds=time.perf_counter()-start
        result={'status':'ok','seconds':seconds,**digest(arr)}
        if case in [5,7] and arm=='sql':
            expected=oracle(case,n);expected=expected[np.argsort(expected[:,0])]
            actual=arr[np.argsort(arr[:,0])]; bad=np.any(actual!=expected,axis=1)
            result['diagnostic_row_diff_count']=int(2*np.count_nonzero(bad))
            result['diagnostic_differing_ids']=actual[bad,0].tolist()
            result['diagnostic_expected_rows']=expected[bad].tolist()
            result['diagnostic_actual_rows']=actual[bad].tolist()
    except Exception as e:result={'status':'error','error':repr(e),'seconds':time.perf_counter()-start}
    Path(out).write_text(json.dumps(result))
if __name__=='__main__':worker(int(sys.argv[1]),int(sys.argv[2]),sys.argv[3],sys.argv[4])
