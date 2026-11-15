/* Luminest closed-beta service worker.
 * Caches the app shell so an installed PWA opens on an iPad even with a flaky
 * connection. API calls are NEVER cached: they carry bearer tokens and live data.
 */
const CACHE = 'luminest-shell-1.4.0';
const SHELL = ['/app/', '/app/index.html'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET') return;
  if (url.pathname.startsWith('/api/')) return;          // never cache live data
  if (url.origin !== self.location.origin) return;       // no third-party requests
  event.respondWith(
    fetch(event.request).then((response) => {
      if (response.ok && url.pathname.startsWith('/app/')) {
        const copy = response.clone();
        caches.open(CACHE).then((c) => c.put(event.request, copy));
      }
      return response;
    }).catch(() => caches.match(event.request).then((hit) => hit || caches.match('/app/index.html')))
  );
});
