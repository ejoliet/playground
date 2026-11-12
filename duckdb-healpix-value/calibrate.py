"""Optional native/shim calibration after a successful v1.5.6 build.
Not executed automatically: the authorized native build attempt already failed.
This measures only pixel conversion; never scales whole-query timings blindly.
"""
import sitecustomize
import argparse,json,time,statistics
from pathlib import Path
import duckdb
import shim
ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--extension',type=Path,required=True);a=p.parse_args()
    if duckdb.__version__!='1.5.6':raise RuntimeError('Requires DuckDB 1.5.6 exactly')
    extension=a.extension.resolve()
    if not extension.is_file():raise FileNotFoundError(extension)
    result={'status':'measured','rows':10000000,'order':12,'native':[],'shim':[],'scope':'conversion only, not end-to-end query calibration'}
    sql=f'''SELECT sum(hpx_ang2pix(12,ra,"dec")) FROM read_parquet('{ROOT}/data/cat-10000000.parquet')'''
    for arm in ['native','shim']:
        for _ in range(3):
            c=duckdb.connect(config={'allow_unsigned_extensions':True,'threads':4})
            if arm=='native':c.execute("LOAD '"+str(extension).replace("'","''")+"'")
            else:shim.register(c)
            start=time.perf_counter();value=c.execute(sql).fetchone()[0];elapsed=time.perf_counter()-start
            result[arm].append({'seconds':elapsed,'pixel_sum':value});c.close()
    assert len({v['pixel_sum'] for arm in ['native','shim'] for v in result[arm]})==1
    result['native_median_seconds']=statistics.median(v['seconds'] for v in result['native'])
    result['shim_median_seconds']=statistics.median(v['seconds'] for v in result['shim'])
    result['shim_over_native_factor']=result['shim_median_seconds']/result['native_median_seconds']
    (ROOT/'logs/native-calibration.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
