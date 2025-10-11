/* PWA Service Worker for Bassam AI */
const CACHE_NAME = "bassam-ai-v1";
const CORE_ASSETS = [
  "/",                           // الصفحة الرئيسية
  "/static/style.css",
  "/static/app.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/manifest.json",              // سيُعاد كتابته تلقائياً إلى /static/pwa/manifest.json عبر السيرفر
];

// تثبيت: تنزيل الأصول الأساسية
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS))
  );
  self.skipWaiting();
});

// تفعيل: تنظيف الكاشات القديمة
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((k) => (k !== CACHE_NAME ? caches.delete(k) : null)))
    )
  );
  self.clients.claim();
});

// إستراتيجية "Cache, falling back to Network"
self.addEventListener("fetch", (event) => {
  const req = event.request;

  // لا نتعامل مع طلبات غير GET
  if (req.method !== "GET") return;

  event.respondWith(
    caches.match(req).then((cached) => {
      const fetchPromise = fetch(req)
        .then((networkRes) => {
          // تخزين نسخة في الكاش (مع تجاهل طلبات chrome-extension/onesignal إلخ)
          if (networkRes && networkRes.status === 200 && req.url.startsWith(self.location.origin)) {
            const resClone = networkRes.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, resClone));
          }
          return networkRes;
        })
        .catch(() => cached || offlineFallback(req));
      // لو فيه نسخة بالكاش نرجعها فورًا، وإلا ننتظر الشبكة
      return cached || fetchPromise;
    })
  );
});

// صفحة/استجابة بديلة في وضع الأوفلاين (اختياري)
async function offlineFallback(req) {
  // لو الصفحة الرئيسية أو صفحات HTML عامة — ارجع النسخة المخبأة من "/"
  if (req.headers.get("accept")?.includes("text/html")) {
    const cache = await caches.open(CACHE_NAME);
    const home = await cache.match("/");
    if (home) return home;
  }
  // fallback فارغ
  return new Response("", { status: 504, statusText: "Offline" });
}
