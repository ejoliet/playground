// Reuse the original bridge and worker runtime without modification.
importScripts('vendor-source/bridge-python.js', 'vendor-source/worker-runtime.js');
const glue = String.raw`
import json
from js import Object
from pyodide.ffi import to_js
bridge = ASGIBridge(app)
async def handle_request(method, path, query, headers_json, body_buf, scheme, host, port):
    response = await bridge.handle(method, path, query, json.loads(headers_json),
        body_buf.to_py().tobytes(), scheme=scheme, host=host, port=int(port))
    return to_js(response, dict_converter=Object.fromEntries)
`;
fetch('app.py').then(r => {
  if (!r.ok) throw new Error('Cannot load app.py');
  return r.text();
}).then(source => startAsgiWorker({
  pyodideUrl: new URL('vendor/', self.location.href).href,
  installManifest: 'install.json', loadPackages: ['sqlite3'],
  pythonSources: [ASGI_BRIDGE_PY, source, glue],
  setupExpr: 'await bridge.startup()',
})).catch(error => self.postMessage({type: 'error', message: String(error)}));
