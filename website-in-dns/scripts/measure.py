#!/usr/bin/env python3
"""Bounded real DoH measurements; JSON and RFC 8484 DNS-wire queries.

Each urllib request opens its own HTTPS connection through the environment's
proxy, if present. These are end-to-end harness timings, not pure DNS latency.
"""
import argparse
import base64
import concurrent.futures
import datetime
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import struct
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RESOLVERS = {'google':'https://dns.google/resolve', 'cloudflare':'https://cloudflare-dns.com/dns-query', 'quad9':'https://dns.quad9.net/dns-query'}


def skip_name(data, offset):
    while True:
        n = data[offset]
        if n & 0xc0 == 0xc0:
            return offset+2
        if n & 0xc0:
            raise ValueError('Invalid DNS label')
        offset += 1
        if not n:
            return offset
        offset += n


def wire_query(name):
    labels = name.rstrip('.').encode('ascii').split(b'.')
    if any(len(label)>63 or not label for label in labels):
        raise ValueError('Invalid DNS name')
    qname = b''.join(bytes([len(label)])+label for label in labels) + b'\0'
    if len(qname)>255:
        raise ValueError('DNS name exceeds 255 wire octets')
    return struct.pack('!6H',0,0x100,1,0,0,0) + qname + struct.pack('!2H',16,1)


def wire_answer(data):
    _, flags, nq, na, ns, ne = struct.unpack_from('!6H',data)
    pos=12
    for _ in range(nq):
        pos=skip_name(data,pos)+4
    answers=[]
    for i in range(na+ns+ne):
        pos=skip_name(data,pos)
        kind,cl,ttl,length=struct.unpack_from('!HHIH',data,pos)
        pos+=10
        end=pos+length
        if end>len(data):
            raise ValueError('Truncated RDATA')
        if kind==16 and i<na:
            parts=[]
            while pos<end:
                n=data[pos];pos+=1
                if pos+n>end:
                    raise ValueError('Truncated TXT string')
                parts.append(data[pos:pos+n]);pos+=n
            answers.append({'TTL':ttl,'type':16,'data':b''.join(parts).decode('ascii'),'strings':len(parts)})
        pos=end
    return {'Status':flags & 15,'TC':bool(flags&512),'AD':bool(flags&32),'Answer':answers,'authorityRecords':ns}


def txt(value):
    if not value.startswith('"'):
        return value
    # Only ASCII protocol records are decoded here; JSON unescapes its layer first.
    import re
    parts=re.findall(r'"((?:\\.|[^"\\])*)"',value)
    return ''.join(re.sub(r'\\(\d{3}|.)',lambda m: chr(int(m[1])) if len(m[1])==3 and m[1].isdigit() else m[1],p) for p in parts)


def query(resolver,name,phase='repeat',wire=False):
    start=time.perf_counter()
    row={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'resolver':resolver,'name':name,'phase':phase,'format':'wire' if wire else 'json'}
    endpoint=RESOLVERS[resolver]
    try:
        if wire:
            endpoint=endpoint.replace('/resolve','/dns-query')
            url=endpoint+'?dns='+base64.urlsafe_b64encode(wire_query(name)).decode().rstrip('=')
        else:
            url=endpoint+'?'+urllib.parse.urlencode({'name':name,'type':'TXT'})
        req=urllib.request.Request(url,headers={'Accept':'application/dns-message' if wire else 'application/dns-json','Cache-Control':'no-cache'})
        with urllib.request.urlopen(req,timeout=20) as response:
            body=response.read()
            row.update(http=response.status,responseBytes=len(body),cacheControl=response.headers.get('Cache-Control'),age=response.headers.get('Age'),cors=response.headers.get('Access-Control-Allow-Origin'))
        parsed=wire_answer(body) if wire else json.loads(body)
        row.update(dnsStatus=parsed['Status'],truncated=parsed.get('TC',False),authenticated=parsed.get('AD',False),answerCount=len(parsed.get('Answer',[])),ttls=[a['TTL'] for a in parsed.get('Answer',[]) if a['type']==16])
        values=[txt(a['data']) for a in parsed.get('Answer',[]) if a['type']==16]
        row.update(txtBytes=sum(len(v.encode()) for v in values),answerSha256=hashlib.sha256('\n'.join(sorted(values)).encode()).hexdigest(),strings=[a.get('strings') for a in parsed.get('Answer',[]) if a['type']==16],answer=parsed)
    except Exception as error:
        row['error']=str(error)
        if isinstance(error,urllib.error.HTTPError):
            row['http']=error.code
            row['errorBody']=error.read(1000).decode(errors='replace')
    row['ms']=round((time.perf_counter()-start)*1000,2)
    return row


def load_app(resolver,parallel):
    build=json.loads((ROOT/'dist/build.json').read_text());domain=build['domain']
    start=time.perf_counter();rows=[]
    try:
        row=query(resolver,'_site.'+domain,'app-manifest');rows.append(row)
        if row.get('dnsStatus')!=0:
            raise ValueError('Manifest DNS failure')
        values=[txt(a['data']) for a in row['answer'].get('Answer',[]) if a['type']==16]
        values=[v for v in values if v.startswith('wd1:m:')]
        if len(values)!=1:
            raise ValueError('Missing or ambiguous manifest')
        raw=base64.b64decode(values[0][6:],validate=True)
        if hashlib.sha256(raw).hexdigest()!=build['manifestSha256']:
            raise ValueError('Manifest pin mismatch')
        manifest=json.loads(raw)
        names=[f'c{i}.{manifest["release"]}.{domain}' for i in range(manifest['chunks'])]
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as pool:
            chunks=list(pool.map(lambda n:query(resolver,n,'app-chunk'),names))
        rows.extend(chunks);parts=[]
        for i,row in enumerate(chunks):
            if row.get('dnsStatus')!=0 or row.get('truncated'):
                raise ValueError('Chunk DNS failure')
            prefix=f'wd1:{i}:'
            values=[txt(a['data']) for a in row['answer'].get('Answer',[]) if a['type']==16]
            values=[v[len(prefix):] for v in values if v.startswith(prefix)]
            if len(values)!=1:
                raise ValueError('Missing or ambiguous chunk')
            parts.append(values[0])
        compressed=base64.b64decode(''.join(parts),validate=True)
        if len(compressed)!=manifest['bytes'] or hashlib.sha256(compressed).hexdigest()!=manifest['sha256']:
            raise ValueError('Content integrity mismatch')
        html=gzip.decompress(compressed)
        if html!=(ROOT/'dist/app.html').read_bytes():
            raise ValueError('Reconstructed bytes differ from build')
        result={'verified':True,'htmlBytes':len(html),'gzipBytes':len(compressed)}
    except Exception as error:
        result={'verified':False,'error':str(error)}
    return {**result,'resolver':resolver,'parallel':parallel,'ms':round((time.perf_counter()-start)*1000,2),'queries':rows}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['public','app','limits'],default='public')
    p.add_argument('--repeats',type=int,default=5)
    p.add_argument('--output',default='evidence/measurements.json')
    args=p.parse_args()
    if not 1<=args.repeats<=20:
        p.error('Use 1..20 repeats')
    out={'startedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'mode':args.mode,'method':'urllib fresh HTTPS connections; no HTTP cache; proxy may participate; repeat is not guaranteed warm or cold','rows':[]}
    domain=json.loads((ROOT/'dist/build.json').read_text())['domain']
    if args.mode=='app':
        for resolver in ['google','cloudflare']:
            for parallel in [1,2,4,8]:
                for _ in range(args.repeats):
                    out['rows'].append(load_app(resolver,parallel))
    else:
        names=['example.com','google.com','microsoft.com', 'no-such-name-widns-20261109.example.com'] if args.mode=='public' else [f's{s}.limits.{domain}' for s in [254,255,256,512,1024,1800,2000,2048,2049,4096,8192,16384,32768,60000]]+[f'r{n}.limits.{domain}' for n in [2,4,8,16,32]]
        for resolver in RESOLVERS:
            for name in names:
                for i in range(args.repeats):
                    row=query(resolver,name,'first-observed' if i==0 else 'repeat',wire=resolver=='quad9')
                    out['rows'].append(row)
                if resolver!='quad9':
                    out['rows'].append(query(resolver,name,'wire-cross-check',wire=True))
    path=ROOT/args.output
    if not path.resolve().is_relative_to((ROOT/'evidence').resolve()):
        raise SystemExit('Output must stay in evidence/')
    path.write_text(json.dumps(out,indent=2)+'\n')
    for resolver in RESOLVERS:
        rows=[r for r in out['rows'] if r['resolver']==resolver]
        if rows:
            print(resolver,len(rows),'observations; median',round(statistics.median(r['ms'] for r in rows),2),'ms; failures',sum('error' in r for r in rows))


if __name__=='__main__':
    main()
