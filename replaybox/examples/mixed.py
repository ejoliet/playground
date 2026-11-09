import json
import os
import random
import time
from pathlib import Path
from urllib.request import urlopen

with urlopen(os.environ['URL']) as response:
    http = [response.status, response.headers['X-Test'], response.read().decode()]
with open('input.txt') as f:
    first = f.readline()
    f.seek(0)
    text = f.read()
with Path('output.txt').open('w') as f:
    count = f.write(text.upper())
with open('output.txt') as f:
    written = f.read()
try:
    open('absent.txt')
except FileNotFoundError as exc:
    missing = [type(exc).__name__, exc.errno, exc.filename]
print(json.dumps([time.time_ns(), time.monotonic(), random.random(),
                  random.randint(1, 1000), os.urandom(8).hex(), http,
                  first, text, written, count, missing, sorted(os.listdir('listing'))]))
