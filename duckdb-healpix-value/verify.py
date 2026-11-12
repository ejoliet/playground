"""Run the final suite, persist its counts, then rebuild the report from JSON."""
import sitecustomize
import subprocess,sys,json,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parent
hats_path=ROOT/'logs/hats.json'
if not hats_path.exists() or 'input_files' not in json.loads(hats_path.read_text()).get('geography_hats',{}):
    import hats_check
    hats_check.main()
footprint_path=ROOT/'logs/footprints.json'
from make_data import ensure_polar_footprints
polar_changed=ensure_polar_footprints()
footprints=json.loads(footprint_path.read_text()) if footprint_path.exists() else {}
invalid_timer=any(t.get('seconds',1)<=0 for a in footprints.get('arms',{}).values() for t in a['trials'])
if not footprints.get('complete',False) or invalid_timer or polar_changed:
    subprocess.run([sys.executable,'footprint_check.py'],cwd=ROOT,check=True)
p=subprocess.run([sys.executable,'-m','pytest','-q','--junitxml=logs/pytest.xml'],cwd=ROOT,text=True,capture_output=True)
(ROOT/'logs/pytest-final.log').write_text(p.stdout+p.stderr)
x=ET.parse(ROOT/'logs/pytest.xml').getroot()
cases=x.findall('.//testcase');xfail=sum(c.find('skipped') is not None and c.find('skipped').get('type')=='pytest.xfail' for c in cases)
r={'total':len(cases),'passed':sum(not any(c.find(k) is not None for k in ['failure','error','skipped']) for c in cases),'xfailed':xfail,'skipped':sum(c.find('skipped') is not None for c in cases)-xfail,'failed':sum(c.find('failure') is not None or c.find('error') is not None for c in cases),'exit_code':p.returncode}
(ROOT/'logs/validation.json').write_text(json.dumps(r,indent=2))
import report;report.main()
print(p.stdout);print(r)
sys.exit(p.returncode)
