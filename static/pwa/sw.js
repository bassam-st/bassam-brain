/* Bassam SW v2 — cache + network timeout */
const CACHE_STATIC = "bassam-static-v2";
const ASSETS = [
  "/", "/static/style.css", "/static/icons/icon-192.png", "/static/icons/icon-512.png", "/static/app.js"
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE_STATIC).then(c => c.addAll(ASSETS)));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_STATIC).map(k => caches.delete(k)))
    )
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/search") || url.pathname.startsWith("/api/")) {
    e.respondWith(networkFirst(e.request));
    return;
  }
  e.respondWith(caches.match(e.request).then(cached => cached || fetch(e.request)));
});

async function networkFirst(req){
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 12000);
  try{
    const fresh = await fetch(req, { signal: ctrl.signal });
    clearTimeout(timer); return fresh;
  }catch(err){
    clearTimeout(timer);
    if (req.headers.get("accept")?.includes("application/json")) {
      return new Response(JSON.stringify({ ok:false, error:"offline_or_timeout" }), {
        headers: { "Content-Type": "application/json" }, status: 503
      });
    }
    return caches.match(req) || new Response("⚠️ لا يوجد اتصال بالإنترنت.", { status: 503 });
  }
}
