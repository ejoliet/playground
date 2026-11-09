import hashlib
import pathlib
import random
import sqlite3
import zipfile
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from astropy.io import fits
import apsw
from oracle import RangeFile

DATA = pathlib.Path('data')

def fixtures():
    DATA.mkdir(exist_ok=True)
    rng=np.random.default_rng(20261109)
    if not (DATA/'sample.parquet').exists():
        pq.write_table(pa.table({f'c{i}':rng.integers(0,2**31,262144,dtype=np.int64) for i in range(8)}), DATA/'sample.parquet', row_group_size=8192, compression=None, use_dictionary=False)
        with zipfile.ZipFile(DATA/'sample.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
            for i in range(128): z.writestr(f'{i}.bin',rng.bytes(65536))
        fits.PrimaryHDU(rng.normal(size=(2048,2048)).astype('float32')).writeto(DATA/'sample.fits',overwrite=True)
        c=sqlite3.connect(DATA/'sample.sqlite')
        c.execute('create table items(id integer primary key, payload blob)')
        c.executemany('insert into items values (?,?)', ((i,rng.bytes(1000)) for i in range(16384)))
        c.commit(); c.close()
    return {p.suffix[1:]:p for p in DATA.glob('sample.*')}


class RemoteVFS(apsw.VFS):
    def __init__(self, oracle):
        self.oracle=oracle
        super().__init__('range_oracle', '')
    def xOpen(self, name, flags): return RemoteSQLite(self.oracle)
    def xAccess(self, name, flags): return False
    def xFullPathname(self, name): return name


class RemoteSQLite:
    def __init__(self, oracle): self.oracle=oracle
    def xRead(self, amount, offset): return self.oracle.read(offset,amount)
    def xFileSize(self): return self.oracle.size
    def xClose(self): pass
    def xLock(self, level): pass
    def xUnlock(self, level): pass
    def xCheckReservedLock(self): return False
    def xFileControl(self, op, pointer): return False
    def xSectorSize(self): return 4096
    def xDeviceCharacteristics(self): return apsw.SQLITE_IOCAP_IMMUTABLE


WORKLOADS = {
'parquet_columns':'parquet', 'parquet_prebuffer':'parquet',
'zip_cluster':'zip', 'zip_random':'zip', 'zip_metadata':'zip',
'fits_rows':'fits','fits_random':'fits',
'sqlite_random':'sqlite','sqlite_scan':'sqlite',
'sequential':'fits','random':'fits','phase_change':'fits','stride':'fits',
}

def consume(name, oracle):
    f=RangeFile(oracle)
    h=hashlib.sha256()
    def add(x): h.update(x)
    rng=random.Random(42)
    if name.startswith('parquet'):
        p=pq.ParquetFile(f,pre_buffer=name=='parquet_prebuffer')
        t=p.read_row_groups([0,1,2,3],columns=['c0','c1'],use_threads=False)
        for col in t.columns: add(col.to_numpy().tobytes())
    elif name.startswith('zip'):
        if name=='zip_metadata':
            for _ in range(8):
                f.seek(0)
                with zipfile.ZipFile(f) as z: add('\n'.join(z.namelist()).encode())
        else:
            with zipfile.ZipFile(f) as z:
                for i in (range(8) if name=='zip_cluster' else rng.sample(range(128),8)):
                    add(z.read(f'{i}.bin'))
    elif name.startswith('fits'):
        with fits.open(f,memmap=False,lazy_load_hdus=True) as hdus:
            for i in (range(16) if name=='fits_rows' else rng.sample(range(2048),16)):
                add(hdus[0].section[i:i+1,:].tobytes())
    elif name.startswith('sqlite'):
        vfs=RemoteVFS(oracle)
        try:
            c=apsw.Connection('remote',vfs='range_oracle',flags=apsw.SQLITE_OPEN_READONLY)
            c.execute('pragma cache_size=8')
            ids= rng.sample(range(16384),16) if name=='sqlite_random' else range(64)
            for i in ids:
                add(c.execute('select payload from items where id=?',(i,)).fetchone()[0])
            c.close()
        finally: vfs.unregister()
    else:
        seq=list(range(0,32*4096,4096))
        rand=[rng.randrange(oracle.size//4096)*4096 for _ in range(32)]
        offsets={'sequential':seq,'random':rand,'phase_change':seq[:16]+rand[16:], 'stride':[i*131072 for i in range(32)]}[name]
        for a in offsets: add(oracle.read(a,4096))
    return h.hexdigest()
