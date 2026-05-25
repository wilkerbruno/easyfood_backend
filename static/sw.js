// EasyFood Service Worker
const CACHE = "easyfood-v1";
self.addEventListener("install", e => e.waitUntil(caches.open(CACHE)));
self.addEventListener("fetch", e => {
  if (e.request.url.includes("/api/")) return;
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
