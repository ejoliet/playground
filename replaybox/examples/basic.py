import os
import random
import time
with open('input.txt') as f:
    text = f.read()
with open('output.txt', 'w') as f:
    f.write(text.upper())
print(time.time_ns(), random.random(), os.urandom(8).hex(), text.strip())
