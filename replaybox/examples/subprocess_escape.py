import subprocess
import sys
subprocess.run([sys.executable, '-c', 'import time; print(time.time_ns())'], check=True)
