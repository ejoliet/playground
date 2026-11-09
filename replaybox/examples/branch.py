import os
import time
if os.environ.get('VALUE') == 'before':
    print(time.time())
else:
    print(time.time_ns())
