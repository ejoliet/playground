import os
from urllib.request import Request, urlopen
with urlopen(Request(os.environ['URL'], headers={'X-Custom': 'value'})) as r:
    print(r.read())
