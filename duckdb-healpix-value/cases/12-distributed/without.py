import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
# See bench.py:execute for the full Python and SQL baseline implementations.
from bench import execute
def run(n,arm="sql"):
    return execute(12,n,arm)
