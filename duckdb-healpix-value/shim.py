"""Research shim of the published API; timings are Python/Arrow, not native.
MOC storage follows upstream's version/depth + little endian int64 intervals.
Optional SQL arguments are supplied explicitly in this harness.
"""
import sitecustomize
from functools import lru_cache
import numpy as np
import pyarrow as pa
import cdshealpix as hp
from astropy import units as u
from mocpy import MOC

def encode(m):
    return bytes([1,int(m.max_order)])+np.asarray(m.to_depth29_ranges,dtype='<i8').tobytes()
@lru_cache(maxsize=4096)
def decode(b):
    if len(b)<2 or b[0]!=1 or b[1]>29 or (len(b)-2)%16:
        raise ValueError('healpix: not a MOC v1 blob')
    return MOC.from_depth29_ranges(b[1],np.frombuffer(b[2:],dtype='<i8').astype(np.uint64).reshape(-1,2))
def cone(ra,dec,radius,order):
    return encode(MOC.from_cone(lon=ra*u.deg,lat=dec*u.deg,radius=radius*u.deg,max_depth=order))
def ranges(b):
    if len(b)<2 or b[0]!=1 or b[1]>29 or (len(b)-2)%16:
        raise ValueError('healpix: not a MOC v1 blob')
    return [{'lo':int(a),'hi':int(z)} for a,z in np.frombuffer(b[2:],dtype='<i8').reshape(-1,2)]
def cone_arrow(ra,dec,radius,order):
    a,b,r,o=map(np.asarray,(ra,dec,radius,order));out=[None]*len(a)
    for depth in np.unique(o):
        idx=np.flatnonzero(o==depth)
        values=MOC.from_cones(lon=a[idx]*u.deg,lat=b[idx]*u.deg,radius=r[idx]*u.deg,max_depth=int(depth),n_threads=1)
        for i,m in zip(idx,values):out[i]=encode(m)
    return pa.array(out,type=pa.binary())

def polygon_arrow(lon,lat,order):
    lon,lat,o=lon.to_pylist(),lat.to_pylist(),np.asarray(order);out=[None]*len(lon)
    groups={}
    for i,(a,b,depth) in enumerate(zip(lon,lat,o)):
        if len(a)!=len(b) or len(a)<3:raise ValueError('healpix: invalid polygon')
        groups.setdefault((int(depth),len(a)),[]).append(i)
    for (depth,_),idx in groups.items():
        vertices=[v for i in idx for v in (lon[i],lat[i])]
        values=MOC.from_polygons(vertices,max_depth=depth,n_threads=1)
        for i,m in zip(idx,values):out[i]=encode(m)
    return pa.array(out,type=pa.binary())

def arrow_map(fn):
    # DuckDB inspects callable arity; do not register a variadic wrapper.
    import inspect
    def convert(columns):
        return pa.array([fn(*args) for args in zip(*(c.to_pylist() for c in columns))])
    wrappers={1:lambda a:convert((a,)),2:lambda a,b:convert((a,b)),3:lambda a,b,c:convert((a,b,c))}
    return wrappers[len(inspect.signature(fn).parameters)]

def ang(order,ra,dec):
    o=np.asarray(order); r=np.asarray(ra); d=np.asarray(dec)
    if np.any((o<0)|(o>29)|(r<0)|(r>=360)|(d < -90)|(d>90)):
        raise ValueError('healpix: invalid order or coordinates')
    out=np.empty(len(r),dtype=np.int64)
    for depth in np.unique(o):
        mask=o==depth
        out[mask]=hp.lonlat_to_healpix(r[mask]*u.deg,d[mask]*u.deg,int(depth),num_threads=1)
    return pa.array(out)
def distance(a,b,c,d):
    a,b,c,d=map(np.deg2rad,map(np.asarray,(a,b,c,d)))
    x=np.cos(d)*np.sin(c-a)
    y=np.cos(b)*np.sin(d)-np.sin(b)*np.cos(d)*np.cos(c-a)
    z=np.sin(b)*np.sin(d)+np.cos(b)*np.cos(d)*np.cos(c-a)
    return np.rad2deg(np.arctan2(np.hypot(x,y),z))
def register(c):
    c.create_function('hpx_ang2pix',ang,['INTEGER','DOUBLE','DOUBLE'],'BIGINT',type='arrow')
    c.create_function('sky_distance',lambda a,b,x,y:pa.array(distance(a,b,x,y)),['DOUBLE']*4,'DOUBLE',type='arrow')
    c.create_function('sky_in_cone',lambda a,b,x,y,r:pa.array(distance(a,b,x,y)<=np.asarray(r)),['DOUBLE']*5,'BOOLEAN',type='arrow')
    c.create_function('moc_from_cone',cone_arrow,['DOUBLE','DOUBLE','DOUBLE','INTEGER'],'BLOB',type='arrow')
    c.create_function('moc_from_polygon',polygon_arrow,['DOUBLE[]','DOUBLE[]','INTEGER'],'BLOB',type='arrow')
    c.create_function('moc_ranges',arrow_map(ranges),['BLOB'],'STRUCT(lo BIGINT, hi BIGINT)[]',type='arrow')
    c.create_function('moc_intersect',arrow_map(lambda a,b:encode(decode(a).intersection(decode(b)))),['BLOB','BLOB'],'BLOB',type='arrow')
    c.create_function('moc_union',arrow_map(lambda a,b:encode(decode(a).union(decode(b)))),['BLOB','BLOB'],'BLOB',type='arrow')
    c.create_function('moc_area_sr',arrow_map(lambda a:float(decode(a).sky_fraction*4*np.pi)),['BLOB'],'DOUBLE',type='arrow')
    c.create_function('moc_contains',arrow_map(lambda a,p:any(lo<=p<hi for lo,hi in decode(a).to_depth29_ranges)),['BLOB','BIGINT'],'BOOLEAN',type='arrow')
    c.execute('CREATE MACRO hpx29(a,b) AS hpx_ang2pix(29,a,b)')
    c.execute('CREATE MACRO hpx_parent(source_order,ipix,to_order) AS (ipix::BIGINT >> (2*(source_order-to_order)))')

def register_hats(c):
    """Optional HATS macro family, kept separate from timed scalar benchmarks."""
    def overlaps(blob,order,ipix):
        lo=int(ipix) << (2*(29-order));hi=(int(ipix)+1) << (2*(29-order))
        return any(int(a)<hi and int(b)>lo for a,b in decode(blob).to_depth29_ranges)
    c.create_function('moc_overlaps_cell',arrow_map(overlaps),['BLOB','INTEGER','BIGINT'],'BOOLEAN',type='arrow')
    c.execute('''CREATE MACRO hats_partitions(root,coverage) AS TABLE
    SELECT "Norder" AS norder,"Npix" AS npix,
    root || '/dataset/Norder=' || "Norder" || '/Dir=' || ("Npix" // 10000 * 10000) || '/Npix=' || "Npix" || '.parquet' AS path
    FROM read_csv(root || '/partition_info.csv')
    WHERE moc_overlaps_cell(coverage,"Norder"::INTEGER,"Npix"::BIGINT)''')
