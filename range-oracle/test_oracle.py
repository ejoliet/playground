import random
import pytest
from oracle import Oracle, RangeFile, POLICIES, merge_ranges
from benchmark import server, HTTPSource
from workloads import fixtures, WORKLOADS, consume

@pytest.mark.parametrize('policy', POLICIES)
@pytest.mark.parametrize('budget',[31,256,65536])
def test_bytes_budget_and_accounting(policy,budget):
    blob=random.Random(13).randbytes(4096)
    o=Oracle(lambda a,b:blob[a:b],len(blob),policy,budget,window=128)
    rng=random.Random(5)
    requests=[(0,10),(10,10),(20,10),(100,5),(180,5),(260,5)]
    requests += [(rng.randrange(4200),rng.randrange(600)) for _ in range(200)]
    for a,n in requests:
        assert o.read(a,n)==blob[a:a+n]
        assert o.resident <= budget
    s=o.stats()
    assert 0 <= s['unused_bytes'] <= s['bytes']
    assert s['cache_peak_bytes'] <= budget


def test_unused_incarnations_and_eviction():
    o=Oracle(lambda a,b:bytes(b-a),100,'fixed',budget=10,window=10)
    o.read(0,2); o.read(2,2); o.read(20,2); o.read(0,2)
    assert o.stats()['unused_bytes']==22
    assert o.stats()['bytes']==30


def test_prediction_is_not_use():
    o=Oracle(lambda a,b:bytes(b-a),1000,'stride',budget=100)
    for a in [0,100,200]: o.read(a,10)
    assert o.stats()['unused_bytes']==10
    assert o.stats()['requests']==4


def test_file_semantics():
    f=RangeFile(Oracle(lambda a,b:b'abcdef'[a:b],6))
    assert f.seek(-2,2)==4
    assert f.read()==b'ef'
    assert f.read()==b''
    f.seek(1); buf=bytearray(3); assert f.readinto(buf)==3
    assert buf==b'bcd'
    with pytest.raises(ValueError): f.seek(-1)


def test_merging():
    assert merge_ranges([(8,12),(0,10),(20,24)],gap=8,limit=24)==[(0,24)]
    assert merge_ranges([(0,10),(11,20)],gap=1,limit=10)==[(0,10),(11,20)]


@pytest.mark.parametrize('name',WORKLOADS)
def test_readers(name):
    paths=fixtures(); blob=paths[WORKLOADS[name]].read_bytes()
    expected=consume(name,Oracle(lambda a,b:blob[a:b],len(blob),'none'))
    for policy in POLICIES:
        assert consume(name,Oracle(lambda a,b:blob[a:b],len(blob),policy))==expected


def test_real_http():
    blob=bytes(range(256))*100
    with server({'blob':blob}) as addr:
        src=HTTPSource(addr,'blob',len(blob))
        try:
            assert src(7,91)==blob[7:91]
            assert src(100,25600)==blob[100:]
        finally: src.close()
