"""Exercise the actual app through the reused bridge, without a browser."""
import asyncio
import base64
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.ns = {}
        source = (ROOT / 'vendor-source/bridge-python.js').read_text().split('String.raw`', 1)[1].split('`;', 1)[0]
        exec(source, self.ns)
        exec((ROOT / 'app.py').read_text(), self.ns)
        self.bridge = self.ns['ASGIBridge'](self.ns['app'])
        await self.bridge.startup()

    async def asyncTearDown(self):
        await self.bridge.shutdown()
        self.ns['DB'].close()

    def message(self, method='tools/list', **params):
        return {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': {
            '_meta': {'io.modelcontextprotocol/protocolVersion': '2026-07-28',
                      'io.modelcontextprotocol/clientCapabilities': {}}, **params}}

    async def post(self, message=None, overrides=None, method='POST', raw=None):
        if message is None:
            message = self.message()
        headers = {'content-type': 'application/json', 'accept': 'application/json, text/event-stream',
                   'mcp-protocol-version': '2026-07-28', 'mcp-method': message.get('method', '') if isinstance(message, dict) else ''}
        if isinstance(message, dict) and isinstance(message.get('params'), dict) and 'name' in message['params']:
            headers['mcp-name'] = message['params']['name']
        headers.update(overrides or {})
        result = await self.bridge.handle(method, '/app/test/mcp', '', list(headers.items()),
                                          raw if raw is not None else json.dumps(message), host='localhost', port=8000)
        return result['status'], json.loads(result['body'])

    async def test_discovery_and_direct_call(self):
        status, result = await self.post(self.message('server/discover'))
        self.assertEqual(status, 200)
        self.assertEqual(result['result']['supportedVersions'], ['2026-07-28'])
        _, result = await self.post(self.message('tools/call', name='note_stats'))
        self.assertEqual(result['result']['structuredContent']['count'], 2)
        self.assertEqual(result['result']['resultType'], 'complete')

    async def test_parameterized_sql_unicode(self):
        text = "'); DROP TABLE notes; -- café 🐍"
        _, result = await self.post(self.message('tools/call', name='add_note', arguments={'text': text}))
        self.assertEqual(result['result']['structuredContent']['text'], text)
        _, result = await self.post(self.message('tools/call', name='list_notes', arguments={'search': text}))
        self.assertEqual(result['result']['structuredContent']['notes'], [{'id': 3, 'text': text}])

    async def test_headers_versions_metadata(self):
        for overrides in [{'mcp-method': 'ping'}, {'mcp-protocol-version': ''}]:
            status, result = await self.post(overrides=overrides)
            self.assertEqual((status, result['error']['code']), (400, -32020))
        msg = self.message()
        msg['params']['_meta']['io.modelcontextprotocol/protocolVersion'] = '1900-01-01'
        status, result = await self.post(msg, {'mcp-protocol-version': '1900-01-01'})
        self.assertEqual((status, result['error']['code']), (400, -32022))
        self.assertEqual(result['error']['data']['supported'], ['2026-07-28'])
        msg = self.message(); msg['params'] = {}
        status, result = await self.post(msg)
        self.assertEqual((status, result['error']['code']), (400, -32602))

    async def test_name_encoding(self):
        msg = self.message('tools/call', name='note_stats')
        encoded = '=?base64?' + base64.b64encode(b'note_stats').decode() + '?='
        status, _ = await self.post(msg, {'mcp-name': encoded})
        self.assertEqual(status, 200)
        status, result = await self.post(msg, {'mcp-name': 'add_note'})
        self.assertEqual((status, result['error']['code']), (400, -32020))

    async def test_origin_and_http_methods(self):
        status, _ = await self.post(overrides={'origin': 'http://evil.invalid'})
        self.assertEqual(status, 403)
        status, _ = await self.post(overrides={'origin': 'http://localhost:8000'})
        self.assertEqual(status, 200)
        for method in ['GET', 'DELETE', 'OPTIONS']:
            status, _ = await self.post(method=method)
            self.assertEqual(status, 405)
        for overrides, expected in [({'accept': 'application/json'}, 406), ({'content-type': 'text/plain'}, 415)]:
            status, _ = await self.post(overrides=overrides)
            self.assertEqual(status, expected)

    async def test_bad_messages(self):
        for message, code in [([], -32600), (self.message(id=None), -32600)]:
            if isinstance(message, dict):
                message['id'] = None
            status, result = await self.post(message)
            self.assertEqual((status, result['error']['code']), (400, code))
        status, result = await self.post(raw=b'{')
        self.assertEqual((status, result['error']['code']), (400, -32700))
        status, result = await self.post(self.message('not/a/method'))
        self.assertEqual((status, result['error']['code']), (404, -32601))
        status, result = await self.post({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}})
        self.assertEqual(status, 400)
        self.assertIn('2026-07-28', result['error']['message'])

    async def test_tool_errors(self):
        for params in [{'name': 'missing'}, {'name': 'add_note', 'arguments': []}]:
            status, result = await self.post(self.message('tools/call', **params))
            self.assertEqual((status, result['error']['code']), (400, -32602))
        for args in [{}, {'text': ''}, {'text': 3}, {'text': 'x', 'extra': True}]:
            _, result = await self.post(self.message('tools/call', name='add_note', arguments=args))
            self.assertTrue(result['result']['isError'])

    async def test_bridge_buffers_sse_and_synthesizes_disconnect(self):
        emitted = asyncio.Event()
        finish = asyncio.Event()
        async def streaming(scope, receive, send):
            await receive()
            self.assertEqual((await receive())['type'], 'http.disconnect')
            await send({'type': 'http.response.start', 'status': 200, 'headers': [(b'content-type', b'text/event-stream')]})
            await send({'type': 'http.response.body', 'body': b'data: first\n\n', 'more_body': True})
            emitted.set()
            await finish.wait()
            await send({'type': 'http.response.body', 'body': b'data: last\n\n'})
        task = asyncio.create_task(self.ns['ASGIBridge'](streaming).handle('POST', '/mcp', '', []))
        await emitted.wait()
        self.assertFalse(task.done(), 'First SSE event remains buffered')
        finish.set()
        self.assertEqual((await task)['body'], b'data: first\n\ndata: last\n\n')


if __name__ == '__main__':
    unittest.main()
