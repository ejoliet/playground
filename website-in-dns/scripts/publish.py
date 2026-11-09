#!/usr/bin/env python3
"""Publish only the selected research namespace. No changes without --apply.

CF_API_TOKEN and CF_ZONE_ID are supplied through the environment, never browser
code. Existing equal records are reused; only the manifest may be updated.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def api(method, path, body=None):
    req = urllib.request.Request('https://api.cloudflare.com/client/v4' + path,
        data=None if body is None else json.dumps(body).encode(), method=method,
        headers={'Authorization': 'Bearer ' + os.environ['CF_API_TOKEN'], 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def quoted(text):
    return ' '.join('"' + text[i:i+255].replace('\\', '\\\\').replace('"', '\\"') + '"' for i in range(0, len(text), 255))


def probes(domain):
    # Small, bounded experiment. No query-rate saturation or zone-quota filling.
    out = []
    for size in [254, 255, 256, 512, 1024, 1800, 2000, 2048, 2049, 4096, 8192, 16384, 32768, 60000]:
        value = ''.join(hashlib.sha256(str(i).encode()).hexdigest() for i in range((size+63)//64))[:size]
        out.append(dict(name=f's{size}.limits.{domain}', type='TXT', ttl=60, content=value))
    # RRset growth is different from a single TXT RDATA growing.
    for count in [2, 4, 8, 16, 32]:
        for i in range(count):
            out.append(dict(name=f'r{count}.limits.{domain}', type='TXT', ttl=60, content=f'{i:03d}:' + 'x'*996))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--probes', action='store_true')
    p.add_argument('--output', default='evidence/publication.json')
    args = p.parse_args()
    build = json.loads((ROOT/'dist/build.json').read_text())
    domain = build['domain']
    records = probes(domain) if args.probes else json.loads((ROOT/'dist/records.json').read_text())
    if not args.apply:
        print(json.dumps({'dryRun': True, 'namespace': domain, 'records': records}, indent=2))
        return
    zone = os.environ['CF_ZONE_ID']
    code, z = api('GET', '/zones/' + zone)
    if not z.get('success') or not domain.endswith('.' + z['result']['name']):
        raise SystemExit('Namespace must be a subdomain of the selected zone')
    results = []
    output = ROOT / args.output
    if not output.resolve().is_relative_to((ROOT/'evidence').resolve()):
        raise SystemExit('Output must stay in evidence/')
    output.parent.mkdir(exist_ok=True)
    for record in records:
        name = record['name']
        if not name.endswith('.' + domain):
            raise SystemExit('Refusing record outside experiment namespace')
        code, existing = api('GET', f'/zones/{zone}/dns_records?' + urllib.parse.urlencode({'name': name, 'type':'TXT', 'per_page':100}))
        if not existing.get('success'):
            raise SystemExit('Cannot inspect existing records; refusing to write')
        matches = existing['result']
        # Cloudflare may normalize quotes and character-string splitting.
        def normalize(value):
            return value.replace('" "', '').strip('"')
        equal = [r for r in matches if normalize(r['content']) == record['content']]
        body = {**record, 'content':quoted(record['content']), 'comment':'website-in-dns research; ejoliet/playground'}
        if equal:
            result = {'success':True, 'result':{'id':equal[0]['id']}, 'reused':True}
            code = 200
        elif matches and name.startswith('_site.') and len(matches) == 1:
            code, result = api('PUT', f'/zones/{zone}/dns_records/' + matches[0]['id'], body)
        elif matches and not args.probes:
            raise SystemExit(f'Refusing to overwrite immutable record {name}')
        else:
            code, result = api('POST', f'/zones/{zone}/dns_records', body)
        row = dict(name=name, textBytes=len(record['content'].encode()), http=code,
                   success=result.get('success',False), id=result.get('result',{}).get('id'),
                   errors=result.get('errors',[]), reused=result.get('reused',False))
        results.append(row)
        output.write_text(json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'namespace':domain, 'probes':args.probes, 'results':results}, indent=2)+'\n')
        print(json.dumps(row))
        if not row['success'] and (not args.probes or code in [401,403,429]):
            raise SystemExit('Publication stopped; manifest is not advanced after failed chunks')


if __name__ == '__main__':
    main()
