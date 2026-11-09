"""Small modern MCP (2026-07-28) server: JSON-only Streamable HTTP subset."""
import base64
import json
import sqlite3

VERSION = '2026-07-28'
META = 'io.modelcontextprotocol/'
INFO = {'name': 'browser-sqlite', 'version': '0.1.0'}
DB = sqlite3.connect(':memory:')
DB.row_factory = sqlite3.Row
DB.execute('CREATE TABLE notes (id INTEGER PRIMARY KEY, text TEXT NOT NULL)')
DB.executemany('INSERT INTO notes(text) VALUES (?)', [('Python lives in this tab.',), ('SQLite needs no backend.',)])
DB.commit()


def tool(name, description, properties, required=()):
    return {'name': name, 'description': description,
            'inputSchema': {'type': 'object', 'properties': properties,
                            'required': list(required), 'additionalProperties': False},
            'annotations': {'readOnlyHint': name != 'add_note',
                            'destructiveHint': False, 'openWorldHint': False}}


TOOLS = [
    tool('add_note', 'Insert a note into this tab’s SQLite database.',
         {'text': {'type': 'string', 'minLength': 1, 'maxLength': 1000}}, ['text']),
    tool('list_notes', 'Search notes by literal substring; returns at most 100 rows.',
         {'search': {'type': 'string', 'maxLength': 1000}}),
    tool('note_stats', 'Count notes and their total text length.', {}),
]


class RPCError(Exception):
    def __init__(self, code, message, status=400, data=None):
        self.code, self.message, self.status, self.data = code, message, status, data


def call_tool(params):
    name, args = params.get('name'), params.get('arguments', {})
    definition = next((t for t in TOOLS if t['name'] == name), None)
    if definition is None:
        raise RPCError(-32602, 'Unknown tool')
    schema = definition['inputSchema']
    if not isinstance(args, dict):
        raise RPCError(-32602, 'arguments must be an object')
    def invalid(text):
        return {'content': [{'type': 'text', 'text': text}], 'isError': True}
    if set(args) - set(schema['properties']):
        return invalid('Unexpected tool arguments')
    if any(k not in args for k in schema['required']):
        return invalid('Missing required tool argument')
    for key, value in args.items():
        rule = schema['properties'][key]
        if not isinstance(value, str) or not rule.get('minLength', 0) <= len(value) <= rule['maxLength']:
            return invalid('Invalid string argument: ' + key)
    try:
        if name == 'add_note':
            with DB:
                cursor = DB.execute('INSERT INTO notes(text) VALUES (?)', (args['text'],))
            data = {'id': cursor.lastrowid, 'text': args['text']}
        elif name == 'list_notes':
            data = {'notes': [dict(r) for r in DB.execute(
                'SELECT id, text FROM notes WHERE instr(text, ?) > 0 ORDER BY id LIMIT 100',
                (args.get('search', ''),))]}
        else:
            data = dict(DB.execute('SELECT count(*) AS count, coalesce(sum(length(text)), 0) AS characters FROM notes').fetchone())
        return {'content': [{'type': 'text', 'text': json.dumps(data, ensure_ascii=False)}],
                'structuredContent': data, 'isError': False}
    except sqlite3.Error as exc:
        return {'content': [{'type': 'text', 'text': str(exc)}], 'isError': True}


def dispatch(message, headers):
    if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or not isinstance(message.get('method'), str):
        raise RPCError(-32600, 'Expected a single JSON-RPC request')
    if 'id' not in message:
        # No client-to-server notifications are defined by this HTTP revision.
        raise RPCError(-32600, 'No HTTP notifications supported')
    if type(message['id']) not in (str, int):
        raise RPCError(-32600, 'Request id must be a string or integer')
    params = message.get('params', {})
    if not isinstance(params, dict) or not isinstance(params.get('_meta'), dict):
        raise RPCError(-32602, 'Required per-request metadata missing; supported version: ' + VERSION)
    meta = params['_meta']
    version = meta.get(META + 'protocolVersion')
    if not isinstance(version, str) or not isinstance(meta.get(META + 'clientCapabilities'), dict):
        raise RPCError(-32602, 'protocolVersion and clientCapabilities are required')
    expected = {'mcp-protocol-version': version, 'mcp-method': message['method']}
    if message['method'] in ('tools/call', 'prompts/get', 'resources/read'):
        expected['mcp-name'] = params.get('uri' if message['method'] == 'resources/read' else 'name')
    for key, value in expected.items():
        actual = headers.get(key)
        if key == 'mcp-name' and actual and actual.startswith('=?base64?') and actual.endswith('?='):
            try:
                actual = base64.b64decode(actual[9:-2], validate=True).decode('utf-8')
            except (ValueError, UnicodeError):
                raise RPCError(-32020, 'Malformed encoded Mcp-Name')
        if actual is None or actual != value:
            raise RPCError(-32020, 'Header mismatch: ' + key)
    if version != VERSION:
        raise RPCError(-32022, 'Unsupported protocol version', data={'supported': [VERSION], 'requested': version})
    method = message['method']
    if method == 'server/discover':
        result = {'supportedVersions': [VERSION], 'capabilities': {'tools': {}},
                  'instructions': 'Notes are volatile and scoped to this browser tab.'}
    elif method == 'tools/list':
        if params.get('cursor') is not None:
            raise RPCError(-32602, 'This small tool list has no pagination cursor')
        result = {'tools': TOOLS}
    elif method == 'tools/call':
        result = call_tool(params)
    elif method == 'ping':
        result = {}
    else:
        raise RPCError(-32601, 'Method not found; supported version: ' + VERSION, 404)
    return dict(result, resultType='complete', _meta={META + 'serverInfo': INFO})


async def app(scope, receive, send):
    if scope['type'] == 'lifespan':
        while True:
            event = await receive()
            if event['type'] == 'lifespan.startup':
                await send({'type': 'lifespan.startup.complete'})
            elif event['type'] == 'lifespan.shutdown':
                await send({'type': 'lifespan.shutdown.complete'})
                return
    headers = {k.decode('latin-1'): v.decode('latin-1') for k, v in scope['headers']}
    status, response, extra = 200, None, []
    request_id = None
    try:
        origin = scope['scheme'] + '://' + headers['host']
        if 'origin' in headers and headers['origin'] != origin:
            raise RPCError(-32600, 'Origin forbidden', 403)
        if not scope['path'].endswith('/mcp'):
            raise RPCError(-32600, 'Endpoint not found', 404)
        if scope['method'] != 'POST':
            extra = [(b'allow', b'POST')]
            raise RPCError(-32600, 'Use POST', 405)
        if headers.get('content-type', '').split(';')[0].strip() != 'application/json':
            raise RPCError(-32600, 'Use application/json', 415)
        accepted = {x.split(';')[0].strip() for x in headers.get('accept', '').split(',')}
        if not {'application/json', 'text/event-stream'} <= accepted:
            raise RPCError(-32600, 'Accept must include application/json and text/event-stream', 406)
        body = bytearray()
        while True:
            event = await receive()
            if event['type'] == 'http.disconnect':
                return
            body.extend(event.get('body', b''))
            if len(body) > 65536:
                raise RPCError(-32600, 'Request too large', 413)
            if not event.get('more_body'):
                break
        try:
            message = json.loads(body)
        except (ValueError, UnicodeError):
            raise RPCError(-32700, 'Parse error')
        if isinstance(message, dict) and type(message.get('id')) in (str, int):
            request_id = message['id']
        response = {'jsonrpc': '2.0', 'id': request_id, 'result': dispatch(message, headers)}
    except RPCError as exc:
        status = exc.status
        error = {'code': exc.code, 'message': exc.message}
        if exc.data is not None:
            error['data'] = exc.data
        response = {'jsonrpc': '2.0', 'error': error}
        if request_id is not None:
            response['id'] = request_id
    await send({'type': 'http.response.start', 'status': status,
                'headers': [(b'content-type', b'application/json'), (b'cache-control', b'no-store')] + extra})
    await send({'type': 'http.response.body', 'body': json.dumps(response, ensure_ascii=False).encode()})
