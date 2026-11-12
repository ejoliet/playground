"""Size evidence is mechanical, not an astronomical row-selection claim."""
from pathlib import Path
import json

def expected():
    root=Path(__file__).resolve().parents[2]
    return json.loads((root/'logs/external.json').read_text())['js']
