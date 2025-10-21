// ==========================
// Bassam Brain – app.js (Final)
// ==========================

// ====== تسجيل Service Worker لتفعيل PWA ======
if ("serviceWorker" in navigator) {
  navigator.serviceWorker
    .register("/sw.js")
    .then(() => console.log("SW ✅ Registered"))
    .catch(err => console.error("SW ❌", err));
}

// ====== زر تثبيت التطبيق (PWA install) ======
let deferredPrompt;
const installBtn = document.getElementById("installBtn");

if (installBtn) {
  // متصفح يدعم beforeinstallprompt (أندرويد/كروم)
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredPrompt = e;
    installBtn.style.display = "block";
  });

  installBtn.addEventListener("click", async () => {
    // مسار أندرويد/كروم
    if (deferredPrompt) {
      installBtn.style.display = "none";
      deferredPrompt.prompt();
      try { await deferredPrompt.userChoice; } catch (_) {}
      deferredPrompt = null;
      return;
    }
    // مسار iOS (يوضح للمستخدم كيف يثبت يدويًا)
    const ua = navigator.userAgent.toLowerCase();
    const isiOS = /iphone|ipad|ipod/.test(ua);
    const inStandalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;
    if (isiOS && !inStandalone) {
      alert("على iPhone/iPad: افتح زر المشاركة في Safari → Add to Home Screen → Add");
    } else {
      alert("التثبيت غير مدعوم على هذا المتصفح.");
    }
  });

  // إظهار زر خاص لـ iOS إذا لم يكن مثبّت كـ PWA
  (function () {
    const ua = navigator.userAgent.toLowerCase();
    const isiOS = /iphone|ipad|ipod/.test(ua);
    const inStandalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;
    if (isiOS && !inStandalone) {
      installBtn.style.display = "block";
      installBtn.textContent = "📱 أضِف إلى الشاشة الرئيسية (iOS)";
    }
  })();
}

// ====== تفعيل أزرار "عرض المزيد/إخفاء" للملخّص والنتائج ======
document.addEventListener("DOMContentLoaded", () => {
  function setupToggle(btnId, boxId) {
    const btn = document.getElementById(btnId);
    const box = document.getElementById(boxId);
    if (!btn || !box) return;

    const setLabel = () => {
      const expanded = !box.classList.contains("collapsed");
      btn.textContent = expanded ? "إخفاء" : "عرض المزيد";
    };

    btn.addEventListener("click", () => {
      box.classList.toggle("collapsed");
      setLabel();
    });

    // اجعل الحالة الابتدائية مطوية
    if (!box.classList.contains("collapsed")) box.classList.add("collapsed");
    setLabel();
  }

  // يطابق IDs الموجودة في index.html
  setupToggle("toggleSummary", "summaryBox");
  setupToggle("toggleResults", "resultsBox");

  // ====== UX: تعطيل أزرار الإرسال أثناء التنفيذ ======
  const searchForm = document.getElementById("searchForm");
  if (searchForm) {
    const askBtn = document.getElementById("askBtn");
    searchForm.addEventListener("submit", () => {
      if (askBtn) {
        askBtn.disabled = true;
        askBtn.textContent = "⏳ جاري البحث...";
      }
    });
  }

  const uploadForm = document.getElementById("uploadForm");
  if (uploadForm) {
    const uploadBtn = uploadForm.querySelector("button[type='submit']");
    uploadForm.addEventListener("submit", () => {
      if (uploadBtn) {
        uploadBtn.disabled = true;
        uploadBtn.textContent = "⏳ جاري المعالجة...";
      }
    });
  }
});
