// بسيط وفعال: cache-first للأصول الثابتة + تحديث نسخة الكاش
const CACHE = "bassam-cache-v2";
const ASSETS = ["/", "/static/style.css", "/static/pwa/manifest.json"];

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  e.respondWith(
    caches.match(req).then((cached) => {
      return (
        cached ||
        fetch(req)
          .then((res) => {
            // خزّن CSS/JS/صور فقط
            const url = new URL(req.url);
            if (
              [".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"].some((x) =>
                url.pathname.endsWith(x)
              )
            ) {
              const clone = res.clone();
              caches.open(CACHE).then((c) => c.put(req, clone));
            }
            return res;
          })
          .catch(() => cached)
      );
    })
  );
});
