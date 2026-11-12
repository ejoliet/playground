import sitecustomize
import json,time
from pathlib import Path
import lsdb
import pyarrow.parquet as pq
from astropy.coordinates import SkyCoord
from astropy import units as u
ROOT=Path(__file__).resolve().parent

def main():
    t=pq.read_table(ROOT/'data/cat-1000000.parquet'); t=t.filter(__import__('pyarrow').compute.less(t['id'],10000))
    dest=ROOT/'data/local-hats'
    start=time.perf_counter()
    cat=lsdb.from_dataframe(t.to_pandas(),ra_column='ra',dec_column='dec',catalog_name='synthetic',partition_rows=1000,margin_threshold=None)
    cat.to_hats(dest,as_collection=False,overwrite=True,progress_bar=False)
    selected=lsdb.open_catalog(dest).cone_search(ra=0,dec=0,radius_arcsec=1800).compute()
    truth=t['id'].to_numpy()[SkyCoord(t['ra'].to_numpy()*u.deg,t['dec'].to_numpy()*u.deg).separation(SkyCoord(0*u.deg,0*u.deg)).deg<=.5]
    result={'status':'ok','source':'synthetic local HATS via lsdb.from_dataframe/to_hats','input_rows':len(t),'selected_rows':len(selected),'row_diff_count':len(set(truth)^set(selected.id)),'seconds':time.perf_counter()-start,'partitions':len(list(dest.rglob('Npix=*.parquet')))}
    import duckdb,shim, csv
    from mocpy import MOC
    c=duckdb.connect(config={'threads':4,'extension_directory':str(ROOT/'.cache/extensions')})
    shim.register(c);shim.register_hats(c)
    chosen=c.execute('SELECT * FROM hats_partitions(?,moc_from_cone(0.,0.,.5,12))',[str(dest)]).fetchall()
    coverage=MOC.from_cone(lon=0*u.deg,lat=0*u.deg,radius=.5*u.deg,max_depth=12)
    ranges=coverage.to_depth29_ranges
    expected_parts=[]
    with (dest/'partition_info.csv').open() as f:
        for row in csv.DictReader(f):
            o,p=int(row['Norder']),int(row['Npix']);lo=p << (2*(29-o));hi=(p+1) << (2*(29-o))
            if any(int(a)<hi and int(b)>lo for a,b in ranges):expected_parts.append((o,p))
    actual_parts=[(int(o),int(p)) for o,p,_ in chosen]
    paths=[path for _,_,path in chosen]
    got=c.execute('SELECT id FROM read_parquet(?) WHERE sky_in_cone(ra,"dec",0.,0.,.5)',[paths]).fetchnumpy()['id']
    lsdb_parts=[(p.order,p.pixel) for p in lsdb.open_catalog(dest).cone_search(ra=0,dec=0,radius_arcsec=1800).hc_structure.get_healpix_pixels()]
    result['shim_hats']={'selected_files':len(paths),'partition_diff_vs_client':len(set(expected_parts)^set(actual_parts)),'partition_diff_vs_lsdb':len(set(lsdb_parts)^set(actual_parts)),'row_diff_count':len(set(truth)^set(got)),'partitions':actual_parts}
    c.execute('LOAD geography')
    allpaths=[str(p) for p in dest.rglob('Npix=*.parquet')]
    start=time.perf_counter()
    ids=c.execute("SELECT id FROM read_parquet(?) WHERE \"dec\" BETWEEN -.5 AND .5 AND s2_dwithin(s2_geogfromtext('POINT (' || ra || ' ' || \"dec\" || ')'),s2_geogfromtext('POINT (0 0)'),radians(.5)*6371010)",[allpaths]).fetchnumpy()['id']
    result['geography_hats']={'input_files':len(allpaths),'row_diff_count':len(set(truth)^set(ids)),'seconds':time.perf_counter()-start}
    (ROOT/'logs/hats.json').write_text(json.dumps(result,indent=2));print(result)
if __name__=='__main__':main()
