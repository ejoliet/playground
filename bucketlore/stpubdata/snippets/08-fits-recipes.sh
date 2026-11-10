#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="$PWD/.uv-cache"
uv run --no-project --offline python - <<'PY'
import subprocess,json,tempfile,pathlib,os
import numpy as np
from astropy.io import fits
os.environ.update(AWS_CONFIG_FILE='/dev/null',AWS_SHARED_CREDENTIALS_FILE='/dev/null',AWS_EC2_METADATA_DISABLED='true',AWS_MAX_ATTEMPTS='1')
received=0
def aws(*args):
    return json.loads(subprocess.check_output(['aws','s3api',*args,'--bucket','stpubdata','--no-sign-request','--region','us-east-1']))
with tempfile.TemporaryDirectory(dir='.') as temp:
    tmp=pathlib.Path(temp)
    keys=['jwst/public/O2022030903/O2022030903-NRCA3_FULL-1.fits','galex/GR6/pipe/01-vsn/03000-MISDR1_24278_0266/d/00-visits/0001-img/07-try/MISDR1_24278_0266_0001-asp.fits.gz']
    for key in keys:
        meta=aws('head-object','--key',key); size=meta['ContentLength']; assert 0<size<5_000_000
        print('HEAD',key,meta)
        preview=tmp/'preview'
        m=aws('get-object','--key',key,'--range',f'bytes=0-{min(2879,size-1)}',str(preview)); received+=m['ContentLength']
        raw=preview.read_bytes(); print('MAGIC',raw[:30])
        if key.endswith('.fits'):
            assert raw.startswith(b'SIMPLE'); print('PRIMARY_HEADER',fits.Header.fromstring(raw.decode('ascii'),sep=''))
        else:
            assert raw.startswith(b'\x1f\x8b')
        path=tmp/pathlib.Path(key).name
        m=aws('get-object','--key',key,'--range',f'bytes=0-{size-1}',str(path)); received+=m['ContentLength']; assert m['ContentLength']==size
        with fits.open(path,memmap=False) as hdus:
            hdus.info()
            for hdu in hdus:
                print('HDU',hdu.name,'TELESCOP',hdu.header.get('TELESCOP'),'INSTRUME',hdu.header.get('INSTRUME'))
                if hdu.data is None: continue
                if isinstance(hdu,fits.BinTableHDU):
                    print('TABLE_SCHEMA',[(c.name,c.format,c.unit) for c in hdu.columns])
                    print('TABLE_ROWS',len(hdu.data)); assert len(hdu.data)>0
                    print('FIRST_ROW',repr(hdu.data[0]))
                    for name in hdu.columns.names[:6]:
                        a=np.asarray(hdu.data[name])
                        if a.dtype.kind in 'fiu':
                            print('COLUMN_RANGE',name,'min',np.nanmin(a),'max',np.nanmax(a))
                elif np.issubdtype(hdu.data.dtype,np.number):
                    a=hdu.data; print('IMAGE',a.shape,str(a.dtype),'finite',int(np.isfinite(a).sum()),'min',float(np.nanmin(a)),'max',float(np.nanmax(a)),'mean',float(np.nanmean(a)))
                    assert a.size>0
    print('TOTAL_OBJECT_PAYLOAD_BYTES',received)
PY
