# app.py — Bassam Brain (واجهة مع وضع "بحث السوشيال" اليدوي)
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
import json, time

# نستورد دوال العقل
from core.brain import (
    smart_answer,             # يقرر أوتوماتيك: ويب عام أو سوشيال حسب السؤال
    is_social_query,          # كاشف أسئلة السوشيال
    search_social,            # بحث سوشيال مباشر
    compose_social_answer,    # تركيب جواب السوشيال
    web_search_pipeline,      # خط بحث الويب العام
    compose_web_answer        # تركيب جواب الويب العام
)

app = FastAPI(title="Bassam Brain — Web + Social")

# ================== الصفحة الرئيسية ==================
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <div style="max-width:820px;margin:24px auto;font-family:system-ui;line-height:1.5">
      <h1>🤖 Bassam Brain — بحث ويب + سوشيال</h1>
      <p>اختر: بحث عام أو فعّل <b>وضع السوشيال</b> للبحث عن الحسابات في المنصات.</p>

      <form method="post" action="/ask" style="margin-top:12px">
        <textarea name="q" rows="5" style="width:100%;padding:10px;border-radius:8px;border:1px solid #ddd"
          placeholder="اكتب سؤالك هنا… مثال: ما عاصمة ألمانيا؟ أو: ابحث عن حساب محمد صالح على تويتر وانستغرام"></textarea>

        <label style="display:flex;gap:10px;align-items:center;margin-top:10px">
          <input type="checkbox" name="social_mode">
          <span>تفعيل وضع السوشيال (Twitter/X, Instagram, Facebook, YouTube, TikTok, LinkedIn, Telegram, Reddit)</span>
        </label>

        <div style="margin-top:10px">
          <button style="background:#0d6efd;color:white;padding:10px 18px;border:none;border-radius:8px;cursor:pointer">
            إرسال
          </button>
        </div>
      </form>

      <details style="margin-top:18px">
        <summary>كيف يعمل؟</summary>
        <ul>
          <li>الوضع الافتراضي: Google → Wikipedia → Deep Web (Ahmia + CommonCrawl) → Bing → DuckDuckGo</li>
          <li>وضع السوشيال: يبحث في المنصات العامة عبر محركات البحث ويعرض روابط الحسابات/الملفات ذات الصلة.</li>
        </ul>
      </details>
    </div>
    """

# ================== معالجة النموذج ==================
@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request):
    form = await request.form()
    q         = (form.get("q") or "").strip()
    social_on = bool(form.get("social_mode"))

    if not q:
        return "<p>⚠️ الرجاء كتابة سؤال.</p><p><a href='/'>◀ رجوع</a></p>"

    # إذا فعّل المستخدم وضع السوشيال، نجبر المسار السوشيالي
    if social_on:
        results = search_social(q, max_per_platform=3)
        pack    = compose_social_answer(q, results)
        answer  = pack["answer"]
        links   = pack.get("links", [])
        mode    = "social-forced"
    else:
        # نترك العقل يقرر — ولو السؤال أصلاً اجتماعي، سيحوّل تلقائيًا
        answer, meta = smart_answer(q)
        links = meta.get("links", []) if isinstance(meta, dict) else []
        mode  = meta.get("mode", "web") if isinstance(meta, dict) else "web"

    # تنسيق روابط
    links_html = ""
    if links:
        items = "".join([f"<li><a href='{u}' target='_blank' rel='noopener'>{u}</a></li>" for u in links])
        links_html = f"<h3>روابط:</h3><ul>{items}</ul>"

    # واجهة النتيجة
    html = f"""
    <div style='max-width:820px;margin:24px auto;font-family:system-ui;line-height:1.6'>
      <p><b>🧠 سؤالك:</b> {q}</p>
      <div style="background:#f8f9fa;border:1px solid #e9ecef;border-radius:10px;padding:14px;white-space:pre-wrap">
        {answer}
      </div>
      {links_html}
      <p style='margin-top:16px'><a href='/'>◀ رجوع</a></p>
      <p style="color:#6c757d">mode: {mode}</p>
    </div>
    """
    return html

# ================== JSON API ==================
@app.post("/api/answer")
async def api_answer(req: Request):
    body = await req.json()
    q    = (body.get("question") or "").strip()
    force_social = bool(body.get("social", False))

    if not q:
        raise HTTPException(status_code=400, detail="ضع حقل 'question'")

    if force_social:
        results = search_social(q, max_per_platform=3)
        pack    = compose_social_answer(q, results)
        return {"ok": True, "mode": "social-forced", "answer": pack["answer"], "links": pack.get("links", [])}

    # autodetect
    if is_social_query(q):
        results = search_social(q, max_per_platform=3)
        pack    = compose_social_answer(q, results)
        return {"ok": True, "mode": "social", "answer": pack["answer"], "links": pack.get("links", [])}

    results = web_search_pipeline(q, max_results=8)
    pack    = compose_web_answer(q, results)
    return {"ok": True, "mode": "web", "answer": pack["answer"], "links": pack.get("links", [])}

# صحة الخدمة
@app.get("/ready")
def ready():
    return {"ok": True}
