import sitecustomize
from pathlib import Path
import json
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from astropy import units as u
from astropy.coordinates import SkyCoord
import cdshealpix as hp
ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
SEED=20261111

def ensure_polar_footprints():
    """Keep several deliberately polar regions, including both poles."""
    path=DATA/'obs.parquet'
    table=pq.read_table(path);cols=table.to_pydict()
    changed=False
    for i,latitude in [(1,89.5),(2,-89.5),(3,89.8)]:
        longitude=[0.,90.,180.,270.];latitudes=[latitude]*4
        if cols['lon'][i]!=longitude or cols['lat'][i]!=latitudes:changed=True
        cols['lon'][i]=longitude;cols['lat'][i]=latitudes
        cols['s_region'][i]='POLYGON ICRS '+' '.join(f'{a:.9f} {b:.9f}' for a,b in zip(longitude,latitudes))
    if changed:
        pq.write_table(pa.table(cols),path)
        manifest=DATA/'manifest.json'
        if manifest.exists():
            metadata=json.loads(manifest.read_text())
            metadata['bytes']=sum(p.stat().st_size for p in DATA.rglob('*') if p.is_file() and p!=manifest)
            manifest.write_text(json.dumps(metadata,indent=2))
    return changed

def write(n):
    rng=np.random.default_rng(SEED)
    ra=rng.uniform(0,360,n); dec=np.rad2deg(np.arcsin(rng.uniform(-1,1,n)))
    ra[:8]=[0,90,0,359.9999,180,270,0,359.9999]
    dec[:8]=[90,-90,89.9999,-89.9999,89.9999,-89.9999,0,0]
    # Dense clump is small enough to permit all-pairs truth, but present at both scales.
    ra[8:1008]=rng.normal(0,0.01,1000)%360; dec[8:1008]=rng.normal(0,0.01,1000)
    pix=hp.lonlat_to_healpix(ra*u.deg,dec*u.deg,29).astype('int64')
    sort=np.argsort(pix)
    table=pa.table({'id':np.arange(n,dtype='int64'),'ra':ra,'dec':dec,'_healpix_29':pix})
    pq.write_table(table.take(pa.array(sort)),DATA/f'cat-{n}.parquet',compression='zstd',row_group_size=65536)
    del table,sort,pix
    # Tangent-plane isotropic Gaussian scatter, valid at poles.
    xy=rng.normal(0,0.3,(2,n))
    sc=SkyCoord(ra*u.deg,dec*u.deg).directional_offset_by(np.arctan2(xy[0],xy[1])*u.rad,np.hypot(*xy)*u.arcsec)
    keep=rng.random(n)>=0.05; keep[:8]=True
    r=sc.ra.deg[keep]; d=sc.dec.deg[keep]
    p=hp.lonlat_to_healpix(r*u.deg,d*u.deg,29).astype('int64')
    t=pa.table({'id':np.arange(n,dtype='int64')[keep],'ra':r,'dec':d,'_healpix_29':p})
    pq.write_table(t.take(pa.array(np.argsort(p))),DATA/f'other-{n}.parquet',compression='zstd',row_group_size=65536)

def main():
    DATA.mkdir(exist_ok=True)
    for n in [1_000_000,10_000_000]:
        print('generate',n,flush=True); write(n)
    import duckdb
    c=duckdb.connect(config={'threads':4,'temp_directory':str(ROOT/'tmp')})
    for n in [1_000_000,10_000_000]:
        c.execute(f"COPY (SELECT i AS id,e AS epoch,(i%17)*3+e AS flux FROM range({n}) t(i),range(3) v(e) ORDER BY id,epoch) TO '{DATA}/phot-{n}.parquet' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 65536)")
    c.close()
    rng=np.random.default_rng(SEED+1)
    ra=rng.uniform(0,360,10000); dec=np.rad2deg(np.arcsin(rng.uniform(-1,1,10000)))
    ra[:4]=[0,359.9999,0,0]; dec[:4]=[0,0,90,-90]
    pq.write_table(pa.table({'wid':np.arange(10000),'ra':ra,'dec':dec,'radius':rng.uniform(.001,.05,10000)}),DATA/'watch.parquet')
    r=rng.uniform(0,360,100000); d=rng.uniform(-85,85,100000); w=rng.uniform(.1,1,100000)
    lon=np.stack([(r-w/2)%360,(r+w/2)%360,(r+w/2)%360,(r-w/2)%360],1)
    lat=np.stack([d-w/2,d-w/2,d+w/2,d+w/2],1)
    lon[:2]=[[359.8,.2,.2,359.8],[0,90,180,270]]; lat[:2]=[[-.2,-.2,.2,.2],[89.5]*4]
    stcs=['POLYGON ICRS '+' '.join(f'{a:.9f} {b:.9f}' for a,b in zip(x,y)) for x,y in zip(lon,lat)]
    pq.write_table(pa.table({'id':np.arange(100000),'lon':lon.tolist(),'lat':lat.tolist(),'s_region':stcs}),DATA/'obs.parquet')
    ensure_polar_footprints()
    # Non-overlapping complete sphere, refine first base cell once: 11 order-0 + 4 order-1.
    orders=np.array([0]*11+[1]*4); pixels=np.array(list(range(1,12))+list(range(4)))
    mass=rng.random(15); mass/=mass.sum()
    pq.write_table(pa.table({'order':orders,'ipix':pixels,'probability':mass}),DATA/'skymap.parquet')
    (DATA/'manifest.json').write_text(json.dumps({'seed':SEED,'edge_ids':list(range(8)),'clump_ids':[8,1007],'bytes':sum(p.stat().st_size for p in DATA.rglob('*') if p.is_file())},indent=2))
if __name__=='__main__':main()
