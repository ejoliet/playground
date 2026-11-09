#!/usr/bin/env python3
"""Repeat the bounded edge/caching experiment; writes a new file by default."""
import argparse
import json
import time
from measure import ROOT, query

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',default='evidence/edge-cases-rerun.json')
args=p.parse_args()
path=ROOT/args.output
if not path.resolve().is_relative_to((ROOT/'evidence').resolve()):
    raise SystemExit('Output must stay in evidence/')
names=['nonexistent-website-in-dns.invalid','dnssec-failed.org','rs.dns-oarc.net','a'*63+'.example.com','a'*64+'.example.com']
rows=[]
for resolver in ['google','cloudflare','quad9']:
    for name in names:
        rows.append(query(resolver,name,'edge-case',wire=resolver=='quad9'))
for resolver in ['google','cloudflare','quad9']:
    for _ in range(3):
        rows.append(query(resolver,'example.com','spaced-cache-repeat',wire=resolver=='quad9'))
        time.sleep(2)
path.write_text(json.dumps({'method':'Bounded public edge cases and 2-second-spaced repeats; no control of authoritative zone or cache instance','rows':rows},indent=2)+'\n')
print(path)
