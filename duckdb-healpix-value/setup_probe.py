import sitecustomize
import importlib.metadata as md
import json, pathlib, subprocess, time, urllib.request, gzip
import duckdb
root=pathlib.Path(__file__).resolve().parent
p=root/'pyproject.toml'
s=p.read_text()
import re
for name in ['pyarrow','cdshealpix','mocpy','astropy','astropy-healpix','numpy','matplotlib','pytest','scipy','lsdb','pyacid']:
    s=re.sub(r'"'+name+r'(?:[>=0-9.]+)?"','"'+name+'=='+md.version(name)+'"',s)
p.write_text(s)
c=duckdb.connect(config={'extension_directory':str(root/'.cache/extensions')})
r={'duckdb':duckdb.__version__,'native':{'status':'setup_failure','calibration':None,'error':(root/'logs/native-build.log').read_text()},'versions':{n:md.version(n) for n in ['duckdb','pyarrow','cdshealpix','mocpy','astropy','astropy-healpix','numpy','matplotlib','pytest','scipy','lsdb','pyacid']}}
try:
    c.execute('INSTALL geography FROM community; LOAD geography')
    r['geography']={'status':'installed','functions':c.execute("select function_name,parameters,parameter_types,return_type from duckdb_functions() where function_name like 's2_%'").fetchall()}
except Exception as e:r['geography']={'status':'failed','error':str(e)}
(root/'logs/setup.json').write_text(json.dumps(r,indent=2))
print(json.dumps(r,indent=2))
