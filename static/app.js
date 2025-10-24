// ==========================
// Bassam Brain – app.js (Merged Final)
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

// ==========================
// واجهة المحادثة: عرض السؤال + الإجابة
// ==========================

// أمان بسيط ضد إدخال HTML
function escapeHTML(s) {
  return String(s || "").replace(/[&<>"']/g, m => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
  }[m]));
}

function pushCard(role, html) {
  const conv = document.getElementById("conversation");
  if (!conv) return; // إن لم توجد الحاوية نتجاهل بدون كسر الواجهة

  const box = document.createElement("div");
  box.style.padding = "14px";
  box.style.borderRadius = "14px";
  box.style.background = role === "user" ? "#1d2a44" : "#162237";
  box.style.border = "1px solid #273654";
  box.style.lineHeight = "1.9";
  box.style.direction = "rtl";
  box.innerHTML = html;
  conv.prepend(box); // أحدث سؤال/جواب بالأعلى
}

// استدعِ هذه لإرسال السؤال وعرض البطاقات
async function askQuestion(q, askBtn) {
  if (!q || !q.trim()) return;

  // اعرض السؤال فورًا
  pushCard("user", `<b>سؤالك:</b><br>${escapeHTML(q)}`);

  // تعطيل الزر مؤقتًا إن وُجد
  const btnRef = askBtn || document.getElementById("askBtn");
  if (btnRef) { btnRef.disabled = true; btnRef.textContent = "⏳ جاري البحث..."; }

  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ q })
    });

    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();

    // دعم {question, answer, links} أو {answer, links} فقط
    const links = (data.links || []).map(u =>
      `<li><a href="${u}" target="_blank" rel="noopener">${escapeHTML(u)}</a></li>`
    ).join("");
    const linksBlock = links ? `<hr><b>روابط للاستزادة:</b><ul style="margin:6px 0 0 18px">${links}</ul>` : "";

    // عرض الإجابة
    pushCard("bot", `<b>الإجابة:</b><br>${(data.answer || "")}${linksBlock}`);
  } catch (e) {
    console.error(e);
    pushCard("bot", `❗ حدث خطأ أثناء جلب الإجابة. حاول لاحقًا.`);
  } finally {
    if (btnRef) { btnRef.disabled = false; btnRef.textContent = "اسأل"; }
  }
}

// ==========================
// تفعيل أزرار "عرض المزيد/إخفاء" + إدارة النماذج
// ==========================
document.addEventListener("DOMContentLoaded", () => {
  // ====== تفعيل أزرار "عرض المزيد/إخفاء" للملخّص والنتائج ======
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

  // يطابق IDs الموجودة في index.html (اختياري)
  setupToggle("toggleSummary", "summaryBox");
  setupToggle("toggleResults", "resultsBox");

  // ====== إدارة نموذج السؤال (submit) ======
  const searchForm = document.getElementById("searchForm");
  if (searchForm) {
    const askBtn = document.getElementById("askBtn");
    searchForm.addEventListener("submit", (ev) => {
      ev.preventDefault();

      // ابحث عن حقل الإدخال داخل الفورم (مرن مع عدة أسماء)
      const input = searchForm.querySelector("textarea, input[type='text'], input[type='search']");
      const q = input ? input.value : "";

      // احفظ آخر قيمة (اختياري)
      try { localStorage.setItem("last_q", q); } catch (_) {}

      // نفّذ الطلب واعرض الكروت
      askQuestion(q, askBtn);
    });
  }

  // ====== UX: تعطيل زر رفع الملفات أثناء التنفيذ ======
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
