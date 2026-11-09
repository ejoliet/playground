#!/usr/bin/env python3
"""Local Kubernetes change-review proxy. Python standard library only."""
import argparse
import copy
import hmac
import json
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def clean(obj):
    obj = copy.deepcopy(obj)
    obj.pop('status', None)
    for key in ('managedFields', 'creationTimestamp'):
        obj.get('metadata', {}).pop(key, None)
    return obj


def changes(before, after, path=''):
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(before.keys() | after.keys()):
            if key in ('resourceVersion', 'uid'):
                continue
            result += changes(before.get(key), after.get(key), f'{path}/{key}')
        return result
    if before == after:
        return []
    label = {'/spec/replicas': 'Desired replica count', '/rules': 'Permission rules', '/subjects': 'Permission recipients', '/roleRef': 'Granted role'}.get(path, path or 'Object')
    return [f'{label} changes from {json.dumps(before, sort_keys=True)} to {json.dumps(after, sort_keys=True)}']


def classify(method, resource, before, after):
    if method == 'DELETE':
        return 'destructive', ['Deletes this object; deleting a namespace also removes its contents.']
    if resource in ('roles', 'clusterroles', 'rolebindings', 'clusterrolebindings'):
        return 'dangerous', ['Changes Kubernetes permissions or who receives them.']
    if after.get('spec', {}).get('replicas') == 0:
        return 'destructive', ['Sets desired replicas to zero; the workload stops serving traffic.']
    if resource == 'configmaps':
        return 'low', ['Changes application configuration; semantic effects are not understood.']
    if clean(before) == clean(after):
        return 'harmless', ['No effective object change.']
    return 'dangerous', ['Changes workload or infrastructure state; human review required.']


class Firewall:
    def __init__(self, upstream, database):
        self.upstream = upstream.rstrip('/')
        self.db = sqlite3.connect(database, check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, time REAL, event TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, state TEXT, payload TEXT)')
        self.db.commit()
        self.lock = threading.RLock()
        self.client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def journal(self, event):
        self.db.execute('INSERT INTO events(time,event) VALUES (?,?)', (time.time(), json.dumps(event)))
        self.db.commit()  # Durable intent before any live write.

    def upstream_call(self, method, path, body=None, content_type='application/json'):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.upstream + path, data=data, method=method,
                                     headers={'Content-Type': content_type, 'Accept': 'application/json'})
        try:
            with self.client.open(req, timeout=20) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def handle(self, method, target, body, content_type, reviewer=False):
        with self.lock:
            self.journal({'type': 'request', 'method': method, 'path': target, 'actor': 'reviewer' if reviewer else 'agent'})
            if reviewer:
                return self.review(method, target, body)
            parsed = urllib.parse.urlsplit(target)
            path = parsed.path
            # Canonical paths only: no encoded slash, traversal, connect or streaming APIs.
            match = re.fullmatch(r'/(api/v1|apis/[a-z0-9.-]+/v[0-9][a-z0-9]*)(?:/namespaces/([a-z0-9.-]+))?/([a-z][a-z0-9]*)(?:/([a-z0-9.-]+))?(?:/(scale))?', path)
            if method == 'GET' and path in ('/api', '/apis', '/version', '/api/v1', '/apis/apps/v1', '/apis/rbac.authorization.k8s.io/v1') and not parsed.query:
                return self.upstream_call(method, path)
            if not match or '%' in target or '..' in target:
                return 403, {'error': 'Unsupported path; connect, exec, proxy, logs and arbitrary subresources are denied.'}
            group, namespace, resource, name, subresource = match.groups()
            expected = ('apis/apps/v1' if resource in ('deployments', 'statefulsets', 'daemonsets') else
                        'apis/rbac.authorization.k8s.io/v1' if resource in ('roles', 'rolebindings', 'clusterroles', 'clusterrolebindings') else 'api/v1')
            if group != expected or (subresource and resource not in ('deployments', 'statefulsets')):
                return 403, {'error': 'Unsupported API group or subresource.'}
            if resource not in ('namespaces', 'configmaps', 'deployments', 'statefulsets', 'daemonsets', 'services', 'pods', 'roles', 'rolebindings', 'clusterroles', 'clusterrolebindings'):
                return 403, {'error': 'Resource not allowlisted.'}
            query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            if set(query) - {'fieldManager', 'fieldValidation', 'force', 'dryRun', 'labelSelector', 'fieldSelector', 'limit', 'resourceVersion'}:
                return 403, {'error': 'Unsupported query parameter (including watch).'}
            if method == 'GET':
                return self.upstream_call(method, target)
            if method not in ('POST', 'PUT', 'PATCH', 'DELETE') or (method != 'POST' and not name) or (method == 'POST' and name):
                return 403, {'error': 'Unsupported operation; collection deletes are denied.'}
            if not isinstance(body, (dict, list)):
                return 400, {'error': 'A JSON body is required.'}
            object_path = path
            if method == 'POST':
                object_name = body.get('metadata', {}).get('name', '')
                if not re.fullmatch('[a-z0-9][a-z0-9.-]*', object_name):
                    return 400, {'error': 'Explicit metadata.name required.'}
                object_path += '/' + object_name
            code, before = self.upstream_call('GET', object_path)
            if code == 404 and method == 'POST':
                before = {}
            elif code != 200:
                return code, before
            query['dryRun'] = ['All']
            dry_path = path + '?' + urllib.parse.urlencode(query, doseq=True)
            code, after = self.upstream_call(method, dry_path, body, content_type)
            if code >= 300:
                self.journal({'type': 'dry-run-failed', 'path': path, 'status': code})
                return code, after
            risk, reasons = classify(method, resource, before, after)
            diff = changes(clean(before), {} if method == 'DELETE' else clean(after))
            proposal = {'id': uuid.uuid4().hex, 'method': method, 'path': path,
                        'object_path': object_path, 'before': before, 'after': after,
                        'risk': risk, 'reasons': reasons, 'diff': diff, 'created': time.time()}
            if method == 'DELETE':
                proposal['commit_body'] = {'apiVersion': 'v1', 'kind': 'DeleteOptions',
                    **body, 'dryRun': [], 'preconditions': {'uid': before['metadata']['uid'], 'resourceVersion': before['metadata']['resourceVersion']}}
            else:
                proposal['commit_body'] = clean(after)
                if method == 'POST':
                    for key in ('uid', 'resourceVersion'):
                        proposal['commit_body'].get('metadata', {}).pop(key, None)
                if method != 'POST':
                    proposal['commit_body']['metadata']['resourceVersion'] = before['metadata']['resourceVersion']
            self.db.execute('INSERT INTO proposals VALUES (?,?,?)', (proposal['id'], 'pending', json.dumps(proposal)))
            self.journal({'type': 'proposal', **proposal})
            if 'dryRun' in urllib.parse.parse_qs(parsed.query) or (isinstance(body, dict) and body.get('dryRun')):
                self.set_state(proposal['id'], 'dry-run-only')
                return code, after
            if risk in ('harmless', 'low'):
                return self.commit(proposal)
            return 403, {'apiVersion': 'v1', 'kind': 'Status', 'status': 'Failure', 'reason': 'Forbidden', 'code': 403,
                         'message': f"Approval required: {proposal['id']} ({risk}). " + ' '.join(reasons) + '\n' + '\n'.join(diff),
                         'proposal_id': proposal['id']}

    def set_state(self, proposal_id, state):
        self.db.execute('UPDATE proposals SET state=? WHERE id=?', (state, proposal_id))
        self.journal({'type': state, 'id': proposal_id})

    def commit(self, proposal):
        if time.time() - proposal['created'] > 300:
            self.set_state(proposal['id'], 'expired')
            return 409, {'error': 'Proposal expired; submit again.'}
        self.set_state(proposal['id'], 'committing')
        method = proposal['method']
        # Commit the materialized dry-run object, not a patch evaluated a second time.
        commit_method = method if method in ('POST', 'DELETE') else 'PUT'
        code, result = self.upstream_call(commit_method, proposal['path'], proposal['commit_body'])
        self.set_state(proposal['id'], 'applied' if code < 300 else 'failed')
        self.journal({'type': 'result', 'id': proposal['id'], 'status': code, 'object': result})
        return code, result

    def review(self, method, path, body):
        if method == 'GET' and path == '/review':
            return 200, [{'state': row[0], **json.loads(row[1])} for row in self.db.execute('SELECT state,payload FROM proposals')]
        match = re.fullmatch('/review/([a-f0-9]{32})/(approve|deny)', path)
        if method != 'POST' or not match:
            return 404, {'error': 'Unknown reviewer endpoint.'}
        proposal_id, decision = match.groups()
        row = self.db.execute('SELECT state,payload FROM proposals WHERE id=?', (proposal_id,)).fetchone()
        if not row or row[0] != 'pending':
            return 409, {'error': 'Proposal is missing or already resolved.'}
        self.journal({'type': 'human-decision', 'id': proposal_id, 'decision': decision})
        if decision == 'deny':
            self.set_state(proposal_id, 'denied')
            return 200, {'state': 'denied'}
        return self.commit(json.loads(row[1]))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def dispatch(self):
        token = self.headers.get('Authorization', '').removeprefix('Bearer ')
        reviewer = hmac.compare_digest(token, self.server.reviewer_token)
        if not reviewer and not hmac.compare_digest(token, self.server.agent_token):
            code, result = 401, {'error': 'Invalid credential.'}
        else:
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 <= length <= 1024 * 1024 or self.headers.get('Transfer-Encoding'):
                    raise ValueError('Body too large or unsupported transfer encoding.')
                body = json.loads(self.rfile.read(length)) if length else {}
                code, result = self.server.firewall.handle(self.command, self.path, body,
                    self.headers.get('Content-Type', 'application/json'), reviewer)
            except (ValueError, KeyError, TypeError) as error:
                code, result = 400, {'error': str(error)}
            except Exception:
                code, result = 503, {'error': 'Firewall/upstream unavailable; no retry authorization granted.'}
        try:
            with self.server.firewall.lock:
                self.server.firewall.journal({'type': 'response', 'method': self.command, 'path': self.path, 'status': code})
        except Exception:
            code, result = 503, {'error': 'Journal unavailable; outcome may be uncertain. Inspect cluster before retrying.'}
        data = json.dumps(result).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = dispatch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', default='http://127.0.0.1:8001')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--database', default='.local/journal.sqlite')
    parser.add_argument('--replay', action='store_true', help='Print journal; never reapply writes')
    args = parser.parse_args()
    if args.replay:
        db = sqlite3.connect(f'file:{args.database}?mode=ro', uri=True)
        for seq, stamp, event in db.execute('SELECT * FROM events ORDER BY seq'):
            print(json.dumps({'seq': seq, 'time': stamp, **json.loads(event)}))
        return
    agent, reviewer = os.environ['AGENT_TOKEN'], os.environ['REVIEWER_TOKEN']
    if not agent or not reviewer or agent == reviewer:
        parser.error('Separate nonempty agent/reviewer tokens required.')
    os.umask(0o077)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.agent_token, server.reviewer_token = agent, reviewer
    server.firewall = Firewall(args.upstream, args.database)
    print(f'Firewall listening on 127.0.0.1:{args.port}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
