// static/app.js — واجهة الرد الفوري + تحسينات بسيطة

// SW + PWA
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

// تعامل مع إرسال النموذج: استخدم /api/ask إن أمكن، وإلا دع المتصفح يذهب لـ /search
const form = document.getElementById("searchForm");
const askBtn = document.getElementById("askBtn");
const qInput = document.getElementById("q");
const aiCard = document.getElementById("aiCard");
const aiAnswer = document.getElementById("aiAnswer");

if (form && askBtn && qInput) {
  form.addEventListener("submit", async (e) => {
    // جرّب الطلب عبر API أولًا (AJAX)
    e.preventDefault();

    const q = qInput.value.trim();
    if (!q) return;

    askBtn.disabled = true;
    askBtn.textContent = "جاري الإجابة...";

    try {
      const r = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ q })
      });

      if (!r.ok) throw new Error("HTTP " + r.status);
      const data = await r.json();

      if (data.ok) {
        // اعرض الإجابة
        aiCard.style.display = "block";
        aiAnswer.innerHTML = `
          <div class="results">
            <p style="white-space:pre-wrap;line-height:1.9">${escapeHtml(data.answer || "")}</p>
            ${renderBullets(data.bullets)}
            ${renderSources(data.sources)}
          </div>
        `;
        window.scrollTo({ top: aiCard.offsetTop - 20, behavior: "smooth" });
      } else {
        // fallback للبحث العادي
        form.submit();
      }
    } catch (err) {
      // fallback للبحث العادي عند أي خطأ
      form.submit();
    } finally {
      askBtn.disabled = false;
      askBtn.textContent = "اسأل";
    }
  });
}

// أزرار "عرض المزيد" للملخص والنتائج (fallback)
(function () {
  const box = document.getElementById('summaryBox');
  const btn = document.getElementById('toggleSummary');
  if (box && btn) {
    btn.addEventListener('click', () => {
      const expanded = box.classList.toggle('expanded');
      box.classList.toggle('collapsed', !expanded);
      btn.textContent = expanded ? 'إخفاء' : 'عرض المزيد';
    });
  }
})();
(function () {
  const box = document.getElementById('resultsBox');
  const btn = document.getElementById('toggleResults');
  if (box && btn) {
    btn.addEventListener('click', () => {
      const expanded = box.classList.toggle('expanded');
      box.classList.toggle('collapsed', !expanded);
      btn.textContent = expanded ? 'إخفاء' : 'عرض المزيد';
    });
  }
})();

function renderBullets(bullets) {
  if (!bullets || !bullets.length) return "";
  const items = bullets.map(b => `<li>${escapeHtml(b)}</li>`).join("");
  return `<h4>نِقَاط موجزة</h4><ul class="sumText">${items}</ul>`;
}
function renderSources(srcs) {
  if (!srcs || !srcs.length) return "";
  const lis = srcs.map(s => `
    <li>
      <a href="${s.link}" target="_blank">${escapeHtml(s.title || s.link || "مصدر")}</a>
      <small>${escapeHtml(s.snippet || "")}</small>
      <em>${escapeHtml(s.source || "")}</em>
    </li>
  `).join("");
  return `<h4 style="margin-top:12px">المصادر</h4><ul class="results">${lis}</ul>`;
}
function escapeHtml(t) {
  return (t || "").replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}
