const CACHE_NAME = 'fiszki-v6';

const STATIC_ASSETS = [
  '/static/css/style.css',
  '/static/css/dashboard.css',
  '/static/css/learn.css',
  '/static/css/sets.css',
  '/static/css/auth.css',
  '/favicon.ico',
  '/icons/icon-16x16.png',
  '/icons/icon-32x32.png',
  '/icons/icon-192x192.png',
  '/icons/icon-512x512.png'
];

const PAGES_TO_CACHE = [
  '/offline'
];

// Install: cache all assets, then skip waiting
self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll([...STATIC_ASSETS, ...PAGES_TO_CACHE]))
      .catch(err => console.log('Cache install failed:', err))
  );
});

// Activate: clean old caches and claim clients
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            console.log('Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Helper: is this a static asset URL?
function isStaticAsset(url) {
  return url.includes('/static/') || url.includes('/icons/') || url.includes('favicon.ico');
}

// Fetch: cache-first for static assets, network-first for pages
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  if (!event.request.url.startsWith('http')) return;

  if (isStaticAsset(event.request.url)) {
    // Cache-first strategy for static assets
    event.respondWith(
      caches.match(event.request).then(cached => {
        if (cached) return cached;
        return fetch(event.request).then(response => {
          if (!response || response.status !== 200 || response.type === 'error') {
            return response;
          }
          const responseToCache = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, responseToCache));
          return response;
        });
      })
    );
  } else {
    // Network-first strategy for pages
    event.respondWith(
      fetch(event.request)
        .then(response => {
          if (!response || response.status !== 200 || response.type === 'error') {
            return response;
          }
          const responseToCache = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, responseToCache));
          return response;
        })
        .catch(() => {
          return caches.match(event.request).then(cached => {
            if (cached) return cached;
            if (event.request.mode === 'navigate') {
              return caches.match('/offline');
            }
            return new Response('Offline', {
              status: 503,
              statusText: 'Service Unavailable',
              headers: new Headers({ 'Content-Type': 'text/plain' })
            });
          });
        })
    );
  }
});

// Handle messages from clients
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

self.addEventListener('push', event => {
  let data = { title: 'Mądra Nauka 📚', body: 'Czas na powtórkę!' };
  if (event.data) {
    try { data = JSON.parse(event.data.text()); } catch(e) {}
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/icons/icon-192x192.png',
      badge: '/icons/icon-32x32.png',
      tag: 'daily-review',
      renotify: true,
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      for (const client of list) {
        if (client.url.includes('/dashboard') && 'focus' in client) return client.focus();
      }
      if (clients.openWindow) return clients.openWindow('/dashboard');
    })
  );
});
