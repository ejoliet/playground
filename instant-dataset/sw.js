// Only synthetic API routes are intercepted. Static assets use ordinary HTTP.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
self.addEventListener('message', (event) => {
  if (event.data === 'identify') event.ports[0].postMessage(event.source.id);
});
const json = (data, status) =>
  Response.json(data, {
    status,
    headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' },
  });
self.addEventListener('fetch', (event) => {
  const prefix = self.registration.scope + 'api/';
  if (!event.request.url.startsWith(prefix)) return;
  event.respondWith(
    (async () => {
      if (event.request.method !== 'GET') return json({ error: 'Use GET.' }, 405);
      const [clientId, datasetId, viewId] = event.request.url
        .slice(prefix.length)
        .split('?')[0]
        .split('/');
      const owner = await self.clients.get(clientId);
      if (!owner) return json({ error: 'Dataset tab closed or reloaded.' }, 410);
      const channel = new MessageChannel();
      return new Promise((resolve) => {
        function finish(data, status) {
          clearTimeout(timer);
          channel.port1.close();
          resolve(json(data, status));
        }
        const timer = setTimeout(
          () => finish({ error: 'Dataset tab did not respond.' }, 504),
          20000,
        );
        channel.port1.onmessage = ({ data }) => finish(data.body, data.status);
        owner.postMessage(
          {
            type: 'view',
            datasetId,
            viewId,
            offset: new URL(event.request.url).searchParams.get('offset'),
          },
          [channel.port2],
        );
      });
    })(),
  );
});
