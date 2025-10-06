// static/pwa/sw.js — كاش بسيط لملفات الواجهة
const CACHE = "bassam-cache-v1";
const CORE = [
  "/",
  "/static/style.css",
  "/static/pwa/manifest.json"
];

// تثبيت: حفظ الملفات الأساسية
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(CORE)));
  self.skipWaiting();
});

// تفعيل: حذف الكاشات القديمة
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((k) => (k !== CACHE ? caches.delete(k) : null)))
    )
  );
  self.clients.claim();
});

// جلب: أولوية للكاش ثم الشبكة
self.addEventListener("fetch", (e) => {
  e.respondWith(
    caches.match(e.request).then((res) => res || fetch(e.request))
  );
});
