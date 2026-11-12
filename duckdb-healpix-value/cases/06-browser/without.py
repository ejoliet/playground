import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
"""No browser: measure one ESM module, not both package module formats."""
import gzip,tarfile
from pathlib import Path
from bench import literal_filter

def measure():
    root=Path(__file__).resolve().parents[2]
    with tarfile.open(root/'vendor/healpix-ts.tgz') as archive:
        module=archive.extractfile('package/dist/index.mjs').read()
    return {'js_gzip_bytes':len(gzip.compress(module,mtime=0)),
            'generated_range_sql_bytes':len(literal_filter().encode())}
if __name__=='__main__':print(measure())
