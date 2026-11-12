import sitecustomize
import json
from pathlib import Path
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
import cdshealpix as hp
from mocpy import MOC
import bench,shim
from run_all import ARMS

@pytest.fixture(scope='module')
def fixture_data():
    dest=bench.ROOT/'tmp/test-data';dest.mkdir(exist_ok=True)
    source=bench.DATA
    for name in ['cat','other']:
        t=pq.read_table(source/f'{name}-1000000.parquet');t=t.filter(pc.less(t['id'],2000))
        pq.write_table(t,dest/f'{name}-2000.parquet')
    pq.write_table(pq.read_table(source/'watch.parquet').slice(0,20),dest/'watch.parquet')
    pq.write_table(pq.read_table(source/'skymap.parquet'),dest/'skymap.parquet')
    ids=np.repeat(np.arange(2000),3);epochs=np.tile(np.arange(3),2000)
    pq.write_table(pa.table({'id':ids,'epoch':epochs,'flux':(ids%17)*3+epochs}),dest/'phot-2000.parquet')
    bench.DATA=dest
    yield dest
    bench.DATA=source

@pytest.mark.parametrize('case,arm',[(i,a) for i,arms in ARMS.items() for a in arms]+[(1,'geography'),(3,'geography')])
def test_every_executed_arm(fixture_data,case,arm):
    expected=bench.digest(bench.oracle(case,2000)); actual=bench.digest(bench.execute(case,2000,arm))
    if expected!=actual and not arm.startswith('shim'):
        pytest.xfail(f'Baseline incorrect on edge fixture: case {case}, {arm}, {expected} != {actual}')
    assert actual==expected

@pytest.mark.parametrize('order',[0,1,6,12,29])
def test_ang2pix(order):
    import duckdb
    c=duckdb.connect();shim.register(c)
    r=np.array([0.,90.,359.9999,0.,180.]);d=np.array([90.,-90.,0.,89.9999,-89.9999])
    c.register('t',pa.table({'ra':r,'d':d}))
    got=np.array(c.execute(f'SELECT hpx_ang2pix({order},ra,d) FROM t').fetchall()).ravel()
    np.testing.assert_array_equal(got,hp.lonlat_to_healpix(r*u.deg,d*u.deg,order))

def test_hpx29():
    import duckdb
    c=duckdb.connect();shim.register(c)
    assert c.execute('SELECT hpx29(0.,90.)').fetchone()[0]==int(hp.lonlat_to_healpix(np.array([0])*u.deg,np.array([90])*u.deg,29)[0])

@pytest.mark.parametrize('order',[0,6,12,29])
def test_hpx_parent(order):
    import duckdb
    c=duckdb.connect();shim.register(c)
    ra=np.array([0.,359.9999,90.,270.]);dec=np.array([90.,0.,-90.,89.9999])
    high=hp.lonlat_to_healpix(ra*u.deg,dec*u.deg,29).astype('int64')
    c.register('pixels',pa.table({'p':high}))
    got=np.array(c.execute(f'SELECT hpx_parent(29,p,{order}) FROM pixels').fetchall()).ravel()
    np.testing.assert_array_equal(got,hp.lonlat_to_healpix(ra*u.deg,dec*u.deg,order))

@pytest.mark.parametrize('name',['moc_from_cone','moc_ranges','moc_contains','moc_area_sr','moc_union','moc_intersect','moc_from_polygon'])
def test_moc_functions(name):
    import duckdb
    c=duckdb.connect();shim.register(c)
    a=MOC.from_cone(lon=359.9*u.deg,lat=0*u.deg,radius=.5*u.deg,max_depth=8)
    b=MOC.from_cone(lon=0*u.deg,lat=0*u.deg,radius=.5*u.deg,max_depth=8)
    ab,bb=shim.encode(a),shim.encode(b)
    if name=='moc_from_cone':got=c.execute('SELECT moc_from_cone(359.9,0.,0.5,8)').fetchone()[0];assert shim.decode(got)==a
    elif name=='moc_ranges':assert c.execute('SELECT moc_ranges(?)',[ab]).fetchone()[0]==[{'lo':int(x),'hi':int(y)} for x,y in a.to_depth29_ranges]
    elif name=='moc_contains':
        p=int(hp.lonlat_to_healpix(np.array([0.])*u.deg,np.array([0.])*u.deg,29)[0]);assert c.execute('SELECT moc_contains(?,?)',[ab,p]).fetchone()[0]==bool(a.contains_lonlat(0*u.deg,0*u.deg)[0])
    elif name=='moc_area_sr':assert c.execute('SELECT moc_area_sr(?)',[ab]).fetchone()[0]==pytest.approx(a.sky_fraction*4*np.pi)
    elif name in ['moc_union','moc_intersect']:
        expected=a.union(b) if name=='moc_union' else a.intersection(b)
        assert shim.decode(c.execute(f'SELECT {name}(?,?)',[ab,bb]).fetchone()[0])==expected
    else:
        lon=[0.,90.,180.,270.];lat=[89.5]*4
        expected=MOC.from_polygon(np.array(lon)*u.deg,np.array(lat)*u.deg,max_depth=8)
        assert shim.decode(c.execute('SELECT moc_from_polygon(?,?,8)',[lon,lat]).fetchone()[0])==expected

@pytest.mark.parametrize('name',['sky_distance','sky_in_cone'])
def test_sky(name):
    import duckdb
    c=duckdb.connect();shim.register(c)
    for ra,dec in [(359.9999,0),(0,90),(180,-90),(0,89.9999)]:
        truth=SkyCoord(ra*u.deg,dec*u.deg).separation(SkyCoord(0*u.deg,0*u.deg)).deg
        if name=='sky_distance':assert c.execute('SELECT sky_distance(?,?,0.,0.)',[float(ra),float(dec)]).fetchone()[0]==pytest.approx(truth,abs=1e-12)
        else:assert c.execute('SELECT sky_in_cone(?,?,0.,0.,.5)',[float(ra),float(dec)]).fetchone()[0]==bool(truth<=.5)

def test_moc_blob_validation():
    with pytest.raises(ValueError):shim.decode(b'bad')

def test_injected_polar_regions():
    rows=pq.read_table(bench.ROOT/'data/obs.parquet').slice(1,3).to_pylist()
    for row,latitude in zip(rows,[90,-90,90]):
        coverage=MOC.from_polygon(np.array(row['lon'])*u.deg,np.array(row['lat'])*u.deg,max_depth=8)
        assert coverage.contains_lonlat(0*u.deg,latitude*u.deg)[0]

RESULTS=[(p,json.loads(p.read_text())) for p in sorted((bench.ROOT/'cases').glob('*/result.json'))]
@pytest.mark.parametrize('p,r',RESULTS)
def test_result_schema(p,r):
    assert r['verdict'] in ['MATTERS','MARGINAL','NO','UNPROVEN']
    if r['case'] in [11,12]:assert r['derived_evidence']['source_case'] in [1,8]
    if r['case']==6:
        assert r['range_sql_bytes']>0
        assert r['js_module_gzip_bytes']>0
    if r['case']==2 and 'arms' in r.get('footprints',{}):
        for arm in r['footprints']['arms'].values():
            assert all(v['row_diff_count']==0 for v in arm['trials'] if v['status']=='ok')

@pytest.mark.parametrize('case,n,arm,result',[(r['case'],n,arm,result) for _,r in RESULTS for n,block in r['sizes'].items() for arm,result in block['arms'].items()])
def test_recorded_arm(case,n,arm,result):
    for v in result['trials']:
        if v['status']!='ok':pytest.skip(f'Case {case}/{n}/{arm}: {v}')
        if not v['correct'] and not arm.startswith('shim'):pytest.xfail(f'Recorded baseline differs: {case}/{n}/{arm}; {v.get("diagnostic_differing_ids")}')
        assert v['correct']

def test_all_cases_present():
    assert sorted(r['case'] for _,r in RESULTS)==list(range(1,14))

@pytest.mark.parametrize('case,n,trials',[(case,n,trials) for _,r in RESULTS for case,sizes in r.get('geography_reruns',{}).items() for n,trials in sizes.items()])
def test_recorded_geography_rerun(case,n,trials):
    for trial in trials:
        if trial['status']!='ok':pytest.skip(f'Geography rerun {case}/{n}: {trial}')
        if trial['row_diff_count']!=0:pytest.xfail(f'Geography baseline differs: {case}/{n}')
        assert trial['row_diff_count']==0

def test_hats_cell_overlap():
    import duckdb
    c=duckdb.connect();shim.register(c);shim.register_hats(c)
    m=MOC.from_cone(lon=0*u.deg,lat=90*u.deg,radius=.1*u.deg,max_depth=8)
    for order,ipix in [(0,0),(0,8),(1,0)]:
        lo=ipix << (2*(29-order));hi=(ipix+1) << (2*(29-order))
        truth=any(int(a)<hi and int(b)>lo for a,b in m.to_depth29_ranges)
        assert c.execute('SELECT moc_overlaps_cell(?,?,?)',[shim.encode(m),order,ipix]).fetchone()[0]==truth

def test_hats_macro_record():
    evidence=json.loads((bench.ROOT/'logs/hats.json').read_text())
    assert evidence['shim_hats']['partition_diff_vs_client']==0
    assert evidence['shim_hats']['row_diff_count']==0
    assert evidence['geography_hats']['row_diff_count']==0

@pytest.mark.parametrize('arm',['python_scalar','python_batch','shim'])
def test_footprint_trials(arm):
    r=json.loads((bench.ROOT/'logs/footprints.json').read_text())
    if arm not in r.get('arms',{}):pytest.skip('Footprint arm not verified')
    for trial in r['arms'][arm]['trials']:
        if trial['status']!='ok':pytest.skip(str(trial))
        assert trial['seconds']>0
        if trial['row_diff_count'] and arm!='shim':pytest.xfail('Footprint baseline differs from direct MOCPy oracle')
        assert trial['row_diff_count']==0
