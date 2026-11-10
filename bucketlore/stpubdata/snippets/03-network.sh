#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="$PWD/.uv-cache"
uv run --no-project --offline python - <<'PY'
import socket, urllib.request
host = 'stpubdata.s3.amazonaws.com'
print('DNS lookup:', host, flush=True)
print(socket.getaddrinfo(host, 443))
with urllib.request.urlopen('https://' + host + '/?list-type=2&max-keys=1', timeout=10) as r:
    print('HTTP status:', r.status)
    print(r.read(16384).decode())
PY
