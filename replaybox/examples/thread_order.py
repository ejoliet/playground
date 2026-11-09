import os
import threading
import time
# Force opposite schedules with unwrapped synchronization (bounded waits).
event = threading.Event()
first = os.environ.get('VALUE') == 'before'
def worker():
    if not first:
        event.wait(1)
    time.sleep(0.001)
    event.set()
t = threading.Thread(target=worker)
t.start()
try:
    if first:
        event.wait(1)
    time.sleep(0.002)
finally:
    event.set()
    t.join()
print('done')
