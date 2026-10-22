/* Public application files only. Auth, APIs, uploads and images always use the network. */
const VERSION = 'daff3a153bdce007';
const CACHE = 'xyz-public-' + VERSION;
const SHELL = '/__xyz_public_shell__';
let refresh;

async function notifyUpdate() {
  for (const client of await self.clients.matchAll({type:'window'})) client.postMessage({type:'xyz:update-ready'});
}

async function updateShell() {
  if (refresh) return refresh;
  refresh = (async () => {
    const response = await fetch('/index.html?__xyz_shell=' + VERSION, {cache:'no-store', credentials:'omit'});
    if (!response.ok || !response.headers.get('content-type')?.includes('text/html')) throw new Error('Public shell unavailable');
    const html = await response.clone().text();
    // Never retain a proxy error/challenge as the application.
    if (!html.includes('id="xyz-auth-config"') || !html.includes('id="root"')) throw new Error('Invalid app shell');
    const cache = await caches.open(CACHE);
    const previous = await cache.match(SHELL);
    // Make the entry and its static dependencies available before updating HTML.
    const assets = [...new Set([...html.matchAll(/(?:src|href)="(\/assets\/[^"<>]+\.(?:js|css))"/g)].map(match => match[1]))];
    for (const url of assets) {
      if (!await cache.match(url)) {
        const asset = await fetch(url, {credentials:'omit'});
        if (!asset.ok || asset.headers.get('content-type')?.includes('text/html')) throw new Error('Application asset unavailable');
        await cache.put(url, asset);
      }
    }
    await cache.put(SHELL, response);
    if (previous && await previous.text() !== html) await notifyUpdate();
  })().finally(() => { refresh = null; });
  return refresh;
}

self.addEventListener('install', event => event.waitUntil((async () => {
  try { await updateShell(); await self.skipWaiting(); }
  catch (error) { await caches.delete(CACHE); throw error; }
})()));

self.addEventListener('activate', event => event.waitUntil((async () => {
  const versions = (await caches.keys()).filter(key => key.startsWith('xyz-public-') && key !== CACHE);
  await Promise.all(versions.slice(0, -1).map(key => caches.delete(key)));
  await self.clients.claim();
})()));

self.addEventListener('message', event => {
  if (event.data?.type === 'xyz:version') event.ports[0]?.postMessage(VERSION);
});

self.addEventListener('fetch', event => {
  const request = event.request, url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (/^\/(api|data)(\/|$)/.test(url.pathname)) return;
  if (request.mode === 'navigate') {
    // Error recovery always has a way to bypass a cached document.
    if (url.searchParams.has('__xyz_boot')) return;
    event.respondWith((async () => {
      const cached = await (await caches.open(CACHE)).match(SHELL);
      if (!cached) return fetch(request);
      event.waitUntil(updateShell().catch(() => {}));
      return cached;
    })());
  } else if (/^\/assets\/[A-Za-z0-9_.-]+\.(js|css|woff2?)$/.test(url.pathname)) {
    event.respondWith((async () => {
      // Exact hashed paths only; keep the preceding release usable for open tabs.
      const cached = await caches.match(request);
      if (cached) return cached;
      const response = await fetch(request);
      if (response.ok && !response.headers.get('content-type')?.includes('text/html')) {
        const cache = await caches.open(CACHE);
        const keys = await cache.keys();
        if (keys.length < 160) await cache.put(request, response.clone());
      }
      return response;
    })());
  }
});
