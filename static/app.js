// ====== PWA: Service Worker ======
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js")
    .then(() => console.log("SW ✅"))
    .catch(err => console.error("SW ❌", err));
}

// ====== PWA: Install Button ======
let deferredPrompt;
const installBtn = document.getElementById("installBtn");

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

// iOS hint (Safari doesn’t support beforeinstallprompt)
(function () {
  const ua = navigator.userAgent.toLowerCase();
  const isiOS = /iphone|ipad|ipod/.test(ua);
  const inStandalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;
  if (isiOS && !inStandalone) {
    installBtn.style.display = "block";
    installBtn.textContent = "📱 تثبيت على الشاشة الرئيسية (iOS)";
    installBtn.onclick = () => {
      alert("على iPhone/iPad: افتح زر المشاركة في Safari → Add to Home Screen → Add");
    };
  }
})();

// ====== UI: expand/collapse for summary/results ======
(function () {
  const sumBox = document.getElementById("summaryBox");
  const sumBtn = document.getElementById("toggleSummary");
  if (sumBox && sumBtn) {
    sumBtn.addEventListener("click", () => {
      const expanded = sumBox.classList.toggle("expanded");
      sumBox.classList.toggle("collapsed", !expanded);
      sumBtn.textContent = expanded ? "إخفاء" : "عرض المزيد";
    });
  }
})();
(function () {
  const resBox = document.getElementById("resultsBox");
  const resBtn = document.getElementById("toggleResults");
  if (resBox && resBtn) {
    resBtn.addEventListener("click", () => {
      const expanded = resBox.classList.toggle("expanded");
      resBox.classList.toggle("collapsed", !expanded);
      resBtn.textContent = expanded ? "إخفاء" : "عرض المزيد";
    });
  }
})();

// ====== AI Ask via /api/ask (بدون تغيير الشكل العام) ======
const qInput = document.getElementById("q");
const askBtn  = document.getElementById("askBtn");
const aiCard  = document.getElementById("aiCard");
const aiAnswer= document.getElementById("aiAnswer");
const aiSources = document.getElementById("aiSources");
const form = document.getElementById("searchForm");

// إذا أراد المستخدم إرسال السؤال إلى الذكاء بدل /search (نفعّل هنا)
form.addEventListener("submit", async (e) => {
  // نرسل للسيرفرين؟ اختر: الذكاء فقط أو كلاهما.
  // هنا نجعلها الذكاء أولا (يمكنك حذف هذا المانع لو تريد سلوك /search التقليدي)
  e.preventDefault();
  const q = (qInput.value || "").trim();
  if (!q) return;

  aiCard.style.display = "block";
  aiAnswer.innerHTML = `<div class="ok">⏳ جاري توليد الإجابة...</div>`;
  aiSources.innerHTML = "";

  try {
    const resp = await fetch("/api/ask", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ q })
    });
    const data = await resp.json();

    if (!data.ok) {
      aiAnswer.innerHTML = `<div class="err">⚠️ تعذر توليد الإجابة: ${data.error || "مشكلة غير معروفة"}</div>`;
      return;
    }

    // نص الإجابة
    aiAnswer.innerHTML = "";
    const p = document.createElement("div");
    p.style.whiteSpace = "pre-wrap";
    p.textContent = data.answer || "";
    aiAnswer.appendChild(p);

    // نقاط الملخص (اختياري)
    if (Array.isArray(data.bullets) && data.bullets.length) {
      const ul = document.createElement("ul");
      ul.className = "sumText";
      data.bullets.forEach(b => {
        const li = document.createElement("li");
        li.textContent = b;
        ul.appendChild(li);
      });
      aiAnswer.appendChild(ul);
    }

    // المصادر (روابط)
    if (Array.isArray(data.sources) && data.sources.length) {
      const list = document.createElement("ul");
      list.className = "results";
      data.sources.forEach(s => {
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = s.link;
        a.target = "_blank";
        a.textContent = s.title || s.link;
        const sm = document.createElement("small");
        sm.textContent = s.snippet || "";
        li.appendChild(a);
        li.appendChild(document.createElement("br"));
        li.appendChild(sm);
        list.appendChild(li);
      });
      aiSources.innerHTML = "<h4>المصادر:</h4>";
      aiSources.appendChild(list);
    }
  } catch (err) {
    aiAnswer.innerHTML = `<div class="err">⚠️ خطأ في الاتصال بالخادم.</div>`;
    console.error(err);
  }
});
