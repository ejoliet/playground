#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="$PWD/.uv-cache"
uv --version
aws --version
if [[ ! -d .venv ]]; then
  uv venv --no-python-downloads .venv
fi
uv run --no-project --offline python -c 'import sys; print("Local environment:", sys.prefix); assert sys.prefix.endswith("/.venv")'
