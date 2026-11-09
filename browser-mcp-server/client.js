export const VERSION = '2026-07-28';
export function request(method, params = {}) {
  return {jsonrpc: '2.0', id: crypto.randomUUID(), method, params: {...params, _meta: {
    'io.modelcontextprotocol/protocolVersion': VERSION,
    'io.modelcontextprotocol/clientInfo': {name: 'browser-demo', version: '0.1.0'},
    'io.modelcontextprotocol/clientCapabilities': {},
  }}};
}
export async function rpc(endpoint, method, params = {}) {
  const message = request(method, params);
  const headers = {'Content-Type': 'application/json', Accept: 'application/json, text/event-stream',
    'MCP-Protocol-Version': VERSION, 'Mcp-Method': method};
  if (method === 'tools/call') headers['Mcp-Name'] = params.name;
  const response = await fetch(endpoint, {method: 'POST', headers,
    body: JSON.stringify(message), signal: AbortSignal.timeout(10000)});
  const text = await response.text();
  if (!response.ok && !response.headers.get('content-type')?.includes('application/json')) throw new Error('HTTP ' + response.status + ': ' + text);
  const body = JSON.parse(text);
  if (!response.ok || body.error) throw new Error(JSON.stringify(body));
  return body.result;
}
export async function selfTest(endpoint) {
  const results = [];
  const check = (name, ok) => { if (!ok) throw new Error(name); results.push(name); };
  check('discovery', (await rpc(endpoint, 'server/discover')).supportedVersions.includes(VERSION));
  check('three tools', (await rpc(endpoint, 'tools/list')).tools.length === 3);
  const before = (await rpc(endpoint, 'tools/call', {name: 'note_stats'})).structuredContent.count;
  const text = 'Browser test ' + crypto.randomUUID() + " — SQLite ' works";
  const added = await rpc(endpoint, 'tools/call', {name: 'add_note', arguments: {text}});
  check('insert', added.structuredContent.text === text);
  const found = await rpc(endpoint, 'tools/call', {name: 'list_notes', arguments: {search: text}});
  check('query', found.structuredContent.notes.length === 1);
  check('aggregate', (await rpc(endpoint, 'tools/call', {name: 'note_stats'})).structuredContent.count === before + 1);
  return results;
}
