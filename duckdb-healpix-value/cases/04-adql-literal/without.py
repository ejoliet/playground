import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
# See bench.py:execute for the full Python and SQL baseline implementations.
from bench import execute
def run(n,arm=None):
    if arm is None:
        import json
        result=Path(__file__).with_name("result.json")
        arm=json.loads(result.read_text()).get("best_baseline","python") if result.exists() else "python"
    return execute(4,n,arm)
