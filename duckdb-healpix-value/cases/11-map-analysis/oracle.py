"""No benchmark, by request; expose the measured aggregation evidence."""
from pathlib import Path
import json

def expected():
    return json.loads((Path(__file__).resolve().parents[1]/'08-density/result.json').read_text())
