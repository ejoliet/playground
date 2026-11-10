#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="$PWD/.uv-cache"
uv run --no-project --offline python - <<'PY'
import subprocess,json
n=total=0
for prefix in ['gaia','galex','hst','jwst','k2','kepler','mast','panstarrs','roman','sdss','tess']:
    raw=subprocess.check_output(['aws','s3api','list-objects-v2','--bucket','stpubdata','--prefix',prefix+'/','--max-keys','1000','--no-paginate','--no-sign-request','--region','us-east-1'],env=__import__('os').environ | {'AWS_CONFIG_FILE':'/dev/null','AWS_SHARED_CREDENTIALS_FILE':'/dev/null','AWS_EC2_METADATA_DISABLED':'true','AWS_MAX_ATTEMPTS':'1'})
    d=json.loads(raw); objects=d.get('Contents',[]); size=sum(x['Size'] for x in objects)
    print(prefix,'objects=',len(objects),'bytes=',size,'truncated=',d['IsTruncated'],'listing_json_bytes=',len(raw))
    assert objects
    n+=len(objects); total+=size
print('LOWER_BOUND objects=',n,'bytes=',total,'decimal_TB=',total/10**12)
print('First lexical page per prefix: NOT a random sample, NOT an estimate of the complete bucket.')
PY
