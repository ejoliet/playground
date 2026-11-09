import os
import random
import time
from urllib.request import urlopen

kind = os.environ.get('WORKLOAD', 'calls')
if kind == 'calls':
    for _ in range(10000):
        time.time_ns()
        random.random()
elif kind == 'files':
    for _ in range(100):
        with open('input.txt', 'rb') as f:
            f.read()
elif kind == 'http':
    for _ in range(10):
        with urlopen(os.environ['URL']) as response:
            response.read()
elif kind == 'sleep':
    time.sleep(0.05)
print('done')
