import {rpc, selfTest} from './client.js';
const status = document.querySelector('#status');
const output = document.querySelector('#output');
let endpoint;
window.rpc = (method, params) => rpc(endpoint, method, params);
window.selfTest = () => selfTest(endpoint);
const pending = new Map();
let workerPort;
navigator.serviceWorker.addEventListener('message', event => {
  if (event.data?.type !== 'asgi-request') return;
  const id = crypto.randomUUID();
  const port = event.ports[0];
  const timer = setTimeout(() => { pending.delete(id); port.close(); }, 5000);
  pending.set(id, response => {
    clearTimeout(timer);
    port.postMessage(response, [response.body]);
    port.close();
  });
  workerPort.postMessage({type: 'request', id, ...event.data.request});
});
async function main() {
  await navigator.serviceWorker.register('sw.js');
  await navigator.serviceWorker.ready;
  if (!navigator.serviceWorker.controller) {
    await new Promise(resolve => navigator.serviceWorker.addEventListener('controllerchange', resolve, {once: true}));
  }
  const identity = new MessageChannel();
  const owner = await new Promise(resolve => {
    identity.port1.onmessage = event => resolve(event.data);
    navigator.serviceWorker.controller.postMessage({type: 'identify'}, [identity.port2]);
  });
  identity.port1.close();
  endpoint = new URL('app/' + owner + '/mcp', location.href).href;
  window.endpoint = endpoint;
  const worker = new Worker('worker.js');
  const channel = new MessageChannel();
  workerPort = channel.port1;
  workerPort.onmessage = event => {
    pending.get(event.data.id)?.(event.data);
    pending.delete(event.data.id);
  };
  await new Promise((resolve, reject) => {
    worker.onmessage = event => {
      const data = event.data;
      if (data.type === 'ready') resolve();
      else if (data.type === 'error') reject(new Error(data.message));
      else if (data.type === 'status') status.textContent = data.message;
    };
    worker.onerror = reject;
    // worker.js fetches app.py before installing its init handler; wait for the
    // runtime's first status message before transferring this channel.
    const listener = event => {
      if (event.data.type === 'status') {
        worker.postMessage({type: 'init', port: channel.port2}, [channel.port2]);
        worker.removeEventListener('message', listener);
      }
    };
    worker.addEventListener('message', listener);
  });
  status.textContent = 'ready';
  document.querySelector('#endpoint').textContent = endpoint;
  document.querySelector('#external').href = 'client.html?endpoint=' + encodeURIComponent(endpoint);
  document.querySelectorAll('button').forEach(button => button.disabled = false);
}
async function display(fn) {
  try { output.textContent = JSON.stringify(await fn(), null, 2); }
  catch (error) { output.textContent = String(error); }
}
document.querySelector('#test').onclick = () => display(window.selfTest);
document.querySelector('#list').onclick = () => display(() => window.rpc('tools/call', {name: 'list_notes'}));
document.querySelector('#add').onsubmit = event => {
  event.preventDefault();
  display(() => window.rpc('tools/call', {name: 'add_note', arguments: {text: document.querySelector('#text').value}}));
};
main().catch(error => { status.textContent = 'error: ' + error.message; });
