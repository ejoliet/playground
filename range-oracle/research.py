import urllib.request, pathlib, json, re
sources = {
'http': 'https://www.rfc-editor.org/rfc/rfc9111.html',
'nginx': 'https://nginx.org/en/docs/http/ngx_http_slice_module.html',
'fsspec': 'https://filesystem-spec.readthedocs.io/en/latest/_modules/fsspec/caching.html',
'arrow': 'https://arrow.apache.org/docs/python/generated/pyarrow.parquet.ParquetFile.html',
'duckdb': 'https://raw.githubusercontent.com/duckdb/duckdb-web/main/docs/2.0/guides/performance/how_to_tune_workloads.md',
'duckdb-http': 'https://raw.githubusercontent.com/duckdb/duckdb-web/main/docs/2.0/core_extensions/httpfs/https.md',
'linux': 'https://raw.githubusercontent.com/torvalds/linux/master/mm/readahead.c',
}
out=[]
for name,url in sources.items():
 try:
  raw=urllib.request.urlopen(url, timeout=30).read().decode()
  text=re.sub('<[^>]+>', ' ', raw)
  text=re.sub(r'\s+', ' ',text)
  pathlib.Path('results/source-'+name+'.txt').write_text(text)
  out.append(dict(name=name,url=url,status='retrieved',length=len(raw)))
 except Exception as e:
  record=dict(name=name,url=url,error=str(e))
  if name=='fsspec':
   import inspect, fsspec.caching, importlib.metadata
   pathlib.Path('results/source-fsspec.txt').write_text(inspect.getsource(fsspec.caching))
   record.update(fallback='installed fsspec.caching source',version=importlib.metadata.version('fsspec'))
  out.append(record)
pathlib.Path('results/sources.json').write_text(json.dumps(out,indent=2))
print(out)
