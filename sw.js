/* Computer Search: cache only TCGdex artwork; leave JSON, API and application assets untouched. */
const CARD_CACHE = 'computersearch-tcgdex-art-v1';
const MAX_CARDS = 300;
const IMAGE_HOST = 'assets.tcgdex.net';

self.addEventListener('install', event => event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));

function isCardArtwork(request) {
  if (request.method !== 'GET' || request.destination !== 'image') return false;
  const url = new URL(request.url);
  return url.protocol === 'https:' && url.hostname === IMAGE_HOST;
}

async function trimCache(cache) {
  const keys = await cache.keys();
  if (keys.length > MAX_CARDS) {
    await Promise.all(keys.slice(0, keys.length - MAX_CARDS).map(key => cache.delete(key)));
  }
}

async function artworkResponse(request) {
  const cache = await caches.open(CARD_CACHE);
  const saved = await cache.match(request);
  if (saved) return saved;
  const response = await fetch(request);
  // Opaque cross-origin image responses are valid cache entries (status 0).
  if (response.ok || response.type === 'opaque') {
    try {
      await cache.put(request, response.clone());
      await trimCache(cache);
    } catch (error) {
      // Storage may be disabled or full; still display the network image.
      console.warn('Unable to cache TCGdex artwork:', error);
    }
  }
  return response;
}

self.addEventListener('fetch', event => {
  if (isCardArtwork(event.request)) event.respondWith(artworkResponse(event.request));
});
