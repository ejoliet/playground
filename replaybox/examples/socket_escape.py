import socket
import os
from urllib.parse import urlsplit
url = urlsplit(os.environ['URL'])
with socket.create_connection((url.hostname, url.port)) as s:
    s.sendall(b'GET / HTTP/1.0\r\nHost: localhost\r\n\r\n')
    print(bool(s.recv(1024)))
