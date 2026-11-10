#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="$PWD/.uv-cache"
uv pip install --python .venv/bin/python duckdb astropy
uv run --no-project --offline python -c 'import duckdb; print("duckdb", duckdb.__version__)'
