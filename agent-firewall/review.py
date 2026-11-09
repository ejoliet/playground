#!/usr/bin/env python3
"""Human terminal review client. Keep its token out of the agent environment."""
import argparse
import json
import os
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('decision', choices=['list', 'approve', 'deny'])
parser.add_argument('id', nargs='?')
args = parser.parse_args()
client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
headers = {'Authorization': 'Bearer ' + os.environ['REVIEWER_TOKEN']}
with client.open(urllib.request.Request('http://127.0.0.1:8080/review', headers=headers)) as response:
    proposals = json.load(response)
for proposal in proposals:
    if args.id and proposal['id'] != args.id:
        continue
    print(f"{proposal['id']} [{proposal['state']}] {proposal['risk']}: {proposal['method']} {proposal['path']}")
    print('\n'.join(proposal['reasons'] + proposal['diff']))
    if args.decision != 'list':
        if not args.id:
            parser.error('Specify the exact proposal ID.')
        if input(f"Type {args.decision} to confirm: ") != args.decision:
            raise SystemExit('Cancelled')
        request = urllib.request.Request(f"http://127.0.0.1:8080/review/{args.id}/{args.decision}",
                                         data=b'{}', headers=headers, method='POST')
        with client.open(request) as response:
            print(response.read().decode())
