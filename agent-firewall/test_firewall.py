import copy
import json
import tempfile
import unittest
import urllib.parse
from firewall import Firewall

DEPLOY = '/apis/apps/v1/namespaces/shop/deployments/web'
CM = '/api/v1/namespaces/shop/configmaps/settings'
NS = '/api/v1/namespaces/shop'
ROLE = '/apis/rbac.authorization.k8s.io/v1/namespaces/shop/roles/reader'


class FakeAPI:
    """Small API double: records dry-run and enforces update/delete versions."""
    def __init__(self):
        self.objects = {
            DEPLOY: {'metadata': {'name': 'web', 'uid': 'd1', 'resourceVersion': '1'}, 'spec': {'replicas': 2}},
            CM: {'metadata': {'name': 'settings', 'uid': 'c1', 'resourceVersion': '1'}, 'data': {'mode': 'safe'}},
            NS: {'metadata': {'name': 'shop', 'uid': 'n1', 'resourceVersion': '1'}},
            ROLE: {'metadata': {'name': 'reader', 'uid': 'r1', 'resourceVersion': '1'}, 'rules': []}}
        self.calls = []
        self.fail_dry = False

    def __call__(self, method, target, body=None, content_type=None):
        parsed = urllib.parse.urlsplit(target)
        path = parsed.path
        dry = 'dryRun=All' in parsed.query
        self.calls.append((method, target, copy.deepcopy(body)))
        old = copy.deepcopy(self.objects.get(path, {}))
        if method == 'GET':
            return (200, old) if old else (404, {})
        if dry and self.fail_dry:
            return 422, {'message': 'invalid'}
        if method == 'PATCH':
            new = copy.deepcopy(old)
            for key, value in body.items():
                if isinstance(value, dict):
                    new.setdefault(key, {}).update(value)
                else:
                    new[key] = value
        else:
            new = copy.deepcopy(body)
        if dry:
            return 200, old if method == 'DELETE' else new
        if method == 'DELETE':
            if body['preconditions']['resourceVersion'] != old['metadata']['resourceVersion']:
                return 409, {}
            del self.objects[path]
            return 200, {'status': 'Success'}
        if method == 'PUT' and new['metadata']['resourceVersion'] != old['metadata']['resourceVersion']:
            return 409, {}
        self.objects[path] = new
        return 200, new


class Tests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.fw = Firewall('http://unused', self.directory.name + '/journal.sqlite')
        self.api = FakeAPI()
        self.fw.upstream_call = self.api

    def tearDown(self):
        self.fw.db.close()
        self.directory.cleanup()

    def request(self, method, path, body=None):
        return self.fw.handle(method, path, body or {}, 'application/merge-patch+json')

    def approve(self, proposal):
        return self.fw.handle('POST', '/review/' + proposal['proposal_id'] + '/approve', {}, 'application/json', True)

    def test_three_attacks_are_dry_run_but_not_applied(self):
        before = copy.deepcopy(self.api.objects)
        for method, path, body in [('DELETE', NS, {}), ('PATCH', DEPLOY, {'spec': {'replicas': 0}}),
                                   ('PATCH', ROLE, {'rules': [{'verbs': ['*'], 'resources': ['*'], 'apiGroups': ['*']}]})]:
            code, result = self.request(method, path, body)
            self.assertEqual(code, 403)
            self.assertIn('proposal_id', result)
        self.assertEqual(before, self.api.objects)
        self.assertEqual(3, sum('dryRun=All' in call[1] for call in self.api.calls))

    def test_approval_materializes_patch_and_is_single_use(self):
        _, proposal = self.request('PATCH', DEPLOY, {'spec': {'replicas': 0}})
        self.assertEqual(self.approve(proposal)[0], 200)
        self.assertEqual(self.api.objects[DEPLOY]['spec']['replicas'], 0)
        self.assertEqual(self.api.calls[-1][0], 'PUT')
        self.assertEqual(self.approve(proposal)[0], 409)

    def test_stale_approval_and_delete_cannot_clobber_new_state(self):
        for method, path, body in [('PATCH', DEPLOY, {'spec': {'replicas': 0}}), ('DELETE', NS, {})]:
            _, proposal = self.request(method, path, body)
            self.api.objects[path]['metadata']['resourceVersion'] = '2'
            self.assertEqual(self.approve(proposal)[0], 409)
            self.assertIn(path, self.api.objects)

    def test_configmap_semantic_harm_is_known_miss(self):
        code, _ = self.request('PATCH', CM, {'data': {'mode': 'disable-auth'}})
        self.assertEqual(code, 200)
        self.assertEqual(self.api.objects[CM]['data']['mode'], 'disable-auth')

    def test_benign_scale_up_is_false_positive(self):
        self.assertEqual(self.request('PATCH', DEPLOY, {'spec': {'replicas': 3}})[0], 403)

    def test_invalid_dry_run_fails_closed(self):
        self.api.fail_dry = True
        self.assertEqual(self.request('PATCH', CM, {'data': {'mode': 'bad'}})[0], 422)
        self.assertEqual(self.api.objects[CM]['data']['mode'], 'safe')

    def test_client_dry_run_never_commits(self):
        self.assertEqual(self.request('PATCH', CM + '?dryRun=All', {'data': {'mode': 'changed'}})[0], 200)
        self.assertEqual(self.api.objects[CM]['data']['mode'], 'safe')

    def test_alternate_paths_and_agent_approval_denied(self):
        for method, path in [('GET', DEPLOY + '/proxy'), ('POST', '/api/v1/namespaces/shop/pods/p/exec'),
                             ('DELETE', '/api/v1/namespaces'), ('PATCH', CM + '?watch=true'),
                             ('GET', '/api/v1/namespaces/shop/secrets'), ('GET', '/api/v1/namespaces/%73hop'),
                             ('POST', '/review/' + 'a' * 32 + '/approve')]:
            self.assertEqual(self.request(method, path)[0], 403, path)
        self.assertEqual(self.api.calls, [])

    def test_pending_survives_restart_and_denial_is_final(self):
        _, proposal = self.request('PATCH', DEPLOY, {'spec': {'replicas': 0}})
        self.fw.db.close()
        self.fw = Firewall('http://unused', self.directory.name + '/journal.sqlite')
        result = self.fw.handle('POST', '/review/' + proposal['proposal_id'] + '/deny', {}, '', True)
        self.assertEqual(result[0], 200)
        self.assertEqual(self.approve(proposal)[0], 409)
        events = [json.loads(row[0]) for row in self.fw.db.execute('SELECT event FROM events')]
        self.assertIn('denied', [event['type'] for event in events])

    def test_expired_approval(self):
        _, proposal = self.request('PATCH', DEPLOY, {'spec': {'replicas': 0}})
        row = self.fw.db.execute('SELECT payload FROM proposals WHERE id=?', (proposal['proposal_id'],)).fetchone()
        payload = json.loads(row[0])
        payload['created'] = 0
        self.fw.db.execute('UPDATE proposals SET payload=? WHERE id=?', (json.dumps(payload), proposal['proposal_id']))
        self.assertEqual(self.approve(proposal)[0], 409)

class HTTPTests(unittest.TestCase):
    def test_agent_cannot_use_review_credentials_or_bypass_proxy(self):
        import threading
        import urllib.error
        import urllib.request
        from http.server import ThreadingHTTPServer
        from firewall import Handler
        with tempfile.TemporaryDirectory() as directory:
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            server.agent_token, server.reviewer_token = 'agent-test', 'human-test'
            server.firewall = Firewall('http://unused', directory + '/journal.sqlite')
            server.firewall.upstream_call = FakeAPI()
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

            def call(path, token, method='GET', body=None):
                request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}' + path,
                    data=json.dumps(body).encode() if body is not None else None, method=method,
                    headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/merge-patch+json'})
                try:
                    with client.open(request) as response:
                        return response.status, json.load(response)
                except urllib.error.HTTPError as error:
                    return error.code, json.load(error)
            try:
                self.assertEqual(call('/review', 'invalid')[0], 401)
                self.assertEqual(call('/review', 'agent-test')[0], 403)
                code, proposal = call(DEPLOY, 'agent-test', 'PATCH', {'spec': {'replicas': 0}})
                self.assertEqual(code, 403)
                approval_path = '/review/' + proposal['proposal_id'] + '/approve'
                self.assertEqual(call(approval_path, 'agent-test', 'POST', {})[0], 403)
                self.assertEqual(call('/review', 'human-test')[0], 200)
                self.assertEqual(call(approval_path, 'human-test', 'POST', {})[0], 200)
                self.assertEqual(call(approval_path, 'human-test', 'POST', {})[0], 409)
                self.assertEqual(call('/apis/evil.example/v1/configmaps', 'agent-test', 'POST', {'metadata': {'name': 'x'}})[0], 403)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
                server.firewall.db.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
