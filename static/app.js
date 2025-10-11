// ====== زر تثبيت التطبيق ======
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js")
    .then(() => console.log("SW ✅"))
    .catch(err => console.error("SW ❌", err));
}

let deferredPrompt;
const installBtn = document.getElementById("installBtn");
if (installBtn) {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredPrompt = e;
    installBtn.style.display = "block";
  });

  installBtn.addEventListener("click", async () => {
    installBtn.style.display = "none";
    if (!deferredPrompt) {
      alert("التثبيت غير مدعوم على هذا المتصفح.");
      return;
    }
    deferredPrompt.prompt();
    await deferredPrompt.userChoice;
    deferredPrompt = null;
  });

  // دعم iOS (زر يشرح للمستخدم)
  (function () {
    const ua = navigator.userAgent.toLowerCase();
    const isiOS = /iphone|ipad|ipod/.test(ua);
    const inStandalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;
    if (isiOS && !inStandalone) {
      installBtn.style.display = "block";
      installBtn.textContent = "📱 أضِف إلى الشاشة الرئيسية (iOS)";
      installBtn.onclick = () => {
        alert("على iPhone/iPad: افتح زر المشاركة في Safari → Add to Home Screen → Add");
      };
    }
  })();
}
