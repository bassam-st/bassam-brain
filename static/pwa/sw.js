// static/pwa/sw.js
self.addEventListener("install", (e) => self.skipWaiting());
self.addEventListener("activate", (e) => self.clients.claim());
self.addEventListener("fetch", () => {}); // بلا كاش ثقيل — يكفي للتثبيت كتطبيق
