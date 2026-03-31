const CACHE_NAME      = 'dashboard-shell-v1';
const DATA_CACHE_NAME = 'dashboard-data-v1';
const FILES_TO_CACHE  = [
  '/',
  '/static/js/app.js',
  '/static/videos/video.mp4'
];

self.addEventListener('install', evt => {
  evt.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(FILES_TO_CACHE))
  );
  self.skipWaiting();
});

self.addEventListener('activate', evt => {
  evt.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.map(key => {
        if (![CACHE_NAME, DATA_CACHE_NAME].includes(key)) {
          return caches.delete(key);
        }
      }))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Datos: network first, fallback cache
  if (url.pathname === '/data') {
    event.respondWith((async () => {
      try {
        const response = await fetch(event.request);
        const cache = await caches.open(DATA_CACHE_NAME);
        cache.put(event.request, response.clone());
        return response;
      } catch {
        const cached = await caches.match(event.request);
        return cached || new Response(null, { status: 503 });
      }
    })());
    return;
  }

  // Vídeo: cache first
  if (url.pathname.endsWith('video.mp4')) {
    event.respondWith(
      caches.match(event.request).then(cached =>
        cached ||
        fetch(event.request).then(res => {
          caches.open(CACHE_NAME).then(c => c.put(event.request, res.clone()));
          return res;
        })
      )
    );
    return;
  }

  // Shell: cache first
  event.respondWith(
    caches.match(event.request).then(cached =>
      cached || fetch(event.request)
    )
  );
});
