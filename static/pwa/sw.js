// static/pwa/sw.js
self.addEventListener("install", (e) => self.skipWaiting());
self.addEventListener("activate", (e) => self.clients.claim());
self.addEventListener("fetch", () => {}); // بلا كاش — فقط لتفعيل التثبيت
