// v3
const CACHE_NAME = "bassam-cache-v3";
const CORE_ASSETS = [
  "/",                      // الصفحة الرئيسية
  "/static/style.css",
  "/static/pwa/manifest.json",
  "/static/pwa/icons/icon-192.png",
  "/static/pwa/icons/icon-512.png"
];

self.addEventListener("install", (event) => {
  console.log("SW install");
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  console.log("SW activate");
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((k) => (k !== CACHE_NAME ? caches.delete(k) : null)))
    ).then(() => self.clients.claim())
  );
});

// سياسة جلب:
// - صفحات HTML: network-first (لمنع بقاء الصفحة قديمة)
// - ملفات ثابتة (css, js, icons): cache-first
// - مجلد /uploads/ والصور الخارجية: bypass (من الشبكة مباشرة)
self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // تخطَّ أي أصل خارجي أو مجلد الرفع
  if (url.origin !== self.location.origin || url.pathname.startsWith("/uploads/")) {
    return; // دع المتصفح يتعامل مباشرة (network)
  }

  // HTML → network first
  if (req.mode === "navigate" || (req.headers.get("accept") || "").includes("text/html")) {
    event.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE_NAME).then((c) => c.put(req, copy));
        return res;
      }).catch(() => caches.match(req))
    );
    return;
  }

  // ثابتات → cache first
  if (/\.(css|js|png|jpg|jpeg|webp|svg|ico)$/i.test(url.pathname) ||
      CORE_ASSETS.includes(url.pathname)) {
    event.respondWith(
      caches.match(req).then((cached) =>
        cached || fetch(req).then((res) => {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((c) => c.put(req, copy));
          return res;
        })
      )
    );
  }
});
