import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
# Independent numerical path lives centrally to avoid divergent test fixtures.
from bench import oracle
def expected(n):
    return oracle(1,n)
