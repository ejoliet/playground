"""No benchmark, by request; expose the measured single-node join evidence."""
from pathlib import Path
import json

def expected():
    return json.loads((Path(__file__).resolve().parents[1]/'01-xmatch/result.json').read_text())
