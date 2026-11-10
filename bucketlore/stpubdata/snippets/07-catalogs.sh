#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="$PWD/.uv-cache"
uv run --no-project --offline python - <<'PY'
import subprocess,json,tempfile,pathlib,os,struct,duckdb
os.environ.update(AWS_CONFIG_FILE='/dev/null',AWS_SHARED_CREDENTIALS_FILE='/dev/null',AWS_EC2_METADATA_DISABLED='true',AWS_MAX_ATTEMPTS='1')
received=0
def aws(*args):
    return json.loads(subprocess.check_output(['aws','s3api',*args,'--bucket','stpubdata','--no-sign-request','--region','us-east-1']))
def read(key,start,end,path):
    global received
    meta=aws('get-object','--key',key,'--range',f'bytes={start}-{end}',str(path))
    assert meta['ContentLength']==end-start+1
    received+=meta['ContentLength']; assert received<5_000_000
    return path.read_bytes()
with tempfile.TemporaryDirectory(dir='.') as temp:
    tmp=pathlib.Path(temp)
    for key in ['gaia/gaia_dr3/public/hats/collection.properties','panstarrs/ps1/public/hats/detection/collection.properties']:
        meta=aws('head-object','--key',key); size=meta['ContentLength']; assert size<10000
        print('METADATA',key,meta)
        print(read(key,0,size-1,tmp/'properties').decode())
    for label,key in [('gaia','gaia/gaia_dr3/public/hats/gaia/dataset/Norder=2/Dir=0/Npix=0.parquet'),('ps1','panstarrs/ps1/public/hats/detection/detection/dataset/Norder=10/Dir=8760000/Npix=8765439.parquet')]:
        meta=aws('head-object','--key',key); size=meta['ContentLength']; print('HEAD',key,meta)
        tail=read(key,size-8,size-1,tmp/'tail'); assert tail[-4:]==b'PAR1'
        footer=struct.unpack('<I',tail[:4])[0]; assert 0<footer<2_000_000
        print('FOOTER',label,'object_bytes',size,'footer_bytes',footer)
        body=read(key,size-footer-8,size-1,tmp/'footer')
        sparse=tmp/(label+'.parquet')
        with sparse.open('wb') as f:
            f.write(b'PAR1'); f.seek(size-len(body)); f.write(body)
        con=duckdb.connect()
        print('SCHEMA',label)
        print(con.execute('select name, type, repetition_type, converted_type, logical_type from parquet_schema(?)',[str(sparse)]).fetchall())
        print('ROW_GROUPS',label,con.execute('select row_group_id,max(row_group_num_rows) rows from parquet_metadata(?) group by 1 order by 1',[str(sparse)]).fetchall())
        if label=='ps1':
            assert size<100_000
            read(key,0,size-1,sparse)
            con.read_parquet(str(sparse)).create_view('detections')
            print('DETECTION_COLUMNS',con.execute('describe detections').fetchall())
            print('DETECTION_ROWS',con.execute('select objID, detectID, ra, dec, obsTime, filterID, psfFlux from detections where psfFlux > 0 limit 5').fetchall())
            print('DETECTION_COUNT',con.execute('select count(*) from detections').fetchone())
    print('TOTAL_OBJECT_PAYLOAD_BYTES',received)
PY
