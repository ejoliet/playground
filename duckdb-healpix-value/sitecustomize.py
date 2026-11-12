"""Keep library caches and temporary files inside the authorized folder."""
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parent
for key, rel in {'TMPDIR':'tmp','MPLCONFIGDIR':'.cache/matplotlib','XDG_CACHE_HOME':'.cache','NUMBA_CACHE_DIR':'.cache/numba','ASTROPY_CACHE_DIR':'.cache/astropy'}.items():
    p = ROOT / rel
    p.mkdir(parents=True, exist_ok=True)
    os.environ[key] = str(p)
