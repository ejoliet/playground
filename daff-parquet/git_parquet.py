#!/usr/bin/env python3
"""Run Git with Parquet drivers enabled, without editing repository config."""
from pathlib import Path
import shlex
import subprocess
import sys

root = Path(__file__).resolve().parent
command = shlex.join([sys.executable, str(root / 'parquet_git.py'), '--key', 'id'])
sys.exit(subprocess.call([
    'git', '-c', 'merge.parquet.name=Keyed Parquet three-way merge',
    '-c', 'merge.parquet.driver=' + command + ' merge %O %A %B',
    '-c', 'merge.parquet.recursive=binary',
    '-c', 'diff.parquet.command=' + command + ' diff',
    *sys.argv[1:],
]))
