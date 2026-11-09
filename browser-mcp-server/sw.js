// Same bridge architecture as pyodide-asgi-browser/sw.js: fresh client lookup
// and a one-shot reply channel per fetch. No Pyodide state lives in the SW.
const base = new URL('./', self.location.href);
const prefix = base.pathname + 'app/';
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.origin === base.origin && url.pathname.startsWith(prefix)) {
    event.respondWith(forward(event.request, url.pathname.slice(prefix.length).split('/')[0]));
  }
});
async function forward(request, owner) {
  const candidate = await self.clients.get(owner);
  const path = candidate && new URL(candidate.url).pathname;
  const host = candidate && [base.pathname, base.pathname + 'index.html'].includes(path) ? candidate : null;
  if (!host) return new Response('Hosting tab is closed or unavailable', {status: 503});
  const body = ['GET', 'HEAD'].includes(request.method) ? null : await request.arrayBuffer();
  const channel = new MessageChannel();
  const reply = new Promise(resolve => {
    const timer = setTimeout(() => resolve(null), 5000);
    channel.port1.onmessage = event => { clearTimeout(timer); resolve(event.data); };
  });
  host.postMessage({type: 'asgi-request', request: {
    method: request.method, url: request.url, headers: [...request.headers], body,
  }}, [channel.port2]);
  const result = await reply;
  channel.port1.close();
  if (!result) return new Response('Hosting tab did not reply within 5 seconds', {status: 504});
  return new Response(request.method === 'HEAD' || [204, 205, 304].includes(result.status) ? null : result.body,
    {status: result.status, headers: result.headers});
}

self.addEventListener('message', event => {
  if (event.data?.type === 'identify') event.ports[0].postMessage(event.source.id);
});
