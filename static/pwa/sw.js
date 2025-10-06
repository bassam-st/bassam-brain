self.addEventListener("install", e => {
  console.log("بسام الذكي - Service Worker تم تثبيته");
  e.waitUntil(
    caches.open("bassam-cache").then(cache => {
      return cache.addAll(["/", "/static/style.css"]);
    })
  );
});

self.addEventListener("fetch", e => {
  e.respondWith(
    caches.match(e.request).then(response => response || fetch(e.request))
  );
});
