import sitecustomize
import json, gzip, urllib.request, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def get(url):
    with urllib.request.urlopen(url,timeout=40) as r:return r.read()
def main():
    (ROOT/'vendor').mkdir(exist_ok=True)
    (ROOT/'logs').mkdir(exist_ok=True)
    evidence={}
    # Published LSDB tutorial endpoint, verify metadata and perform an actual LSDB cone.
    path='https://data.lsdb.io/hats/gaia_dr3/gaia'
    attempts=[]
    for i in range(2):
        try:
            raw=get(path+'/properties')
            import lsdb
            start=time.perf_counter()
            cat=lsdb.open_catalog(path,columns=['ra','dec'],search_filter=lsdb.ConeSearch(ra=56.75,dec=24.12,radius_arcsec=30))
            df=cat.compute()
            attempts.append({'status':'ok','rows':len(df),'seconds':time.perf_counter()-start,'properties':raw.decode()})
            break
        except Exception as e:attempts.append({'status':'error','error':repr(e)})
    evidence['gaia']={'path':path,'attempts':attempts}
    try:
        meta=json.loads(get('https://registry.npmjs.org/healpix-ts/1.1.0'))
        raw=get(meta['dist']['tarball'])
        (ROOT/'vendor/healpix-ts.tgz').write_bytes(raw)
        import tarfile,io
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tar:
            files={m.name:tar.extractfile(m).read() for m in tar.getmembers() if m.isfile() and m.name.endswith(('.js','.mjs'))}
        evidence['js']={'package':'healpix-ts','version':meta['version'],'tarball':meta['dist']['tarball'],'js_files':list(files),'gzip_all_js_bytes':len(gzip.compress(b'\n'.join(files.values()),mtime=0)),'status':'ok','note':'All shipped JS concatenated; not a tree-shaken application bundle.'}
    except Exception as e:evidence['js']={'status':'error','error':repr(e)}
    (ROOT/'logs/external.json').write_text(json.dumps(evidence,indent=2))
    print(json.dumps(evidence,indent=2))
if __name__=='__main__':main()
