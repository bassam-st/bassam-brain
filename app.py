# -*- coding: utf-8 -*-
# app.py — Bassam AI (العقل المزدوج: بحث + فهم + توليد إجابات + سوشال ميديا + رياضيات)
import time, json, asyncio
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.brain import smart_answer
from core.math_solver import explain_math_answer

# إعداد التطبيق
app = FastAPI(title="Bassam AI — العقل المزدوج (بحث + توليد + سوشال ميديا + رياضيات)")

# المسارات الأساسية
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

LOG_FILE = "data/log.jsonl"

# الصفحة الرئيسية
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ✅ معالجة الطلبات من النموذج (واجهة المستخدم)
@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request):
    form = await request.form()
    q = (form.get("q") or "").strip()
    if not q:
        return HTMLResponse("<p>⚠️ يرجى كتابة سؤال.</p>")

    # تحليل رياضي أولًا
    if any(k in q for k in ["حل", "كامل", "فرق", "معادلة", "تكامل", "جهاز", "نظام"]):
        ans = explain_math_answer(q)
        meta = {"mode": "math"}
    else:
        # بحث ذكي (سوشال أو معرفي أو ويب)
        ans, sources = await smart_answer(q)
        meta = {"mode": "ai", "sources": sources}

    # حفظ في السجل
    rec = {"ts": int(time.time()), "q": q, "a": ans, "meta": meta}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # عرض الإجابة والمصادر
    sources_html = ""
    if meta.get("mode") == "ai" and meta.get("sources"):
        sources_html = (
            "<div class='sources'><h3>🔗 المصادر:</h3><ul>"
            + "".join(
                [
                    f"<li><a href='{u}' target='_blank' rel='noopener'>{t}</a></li>"
                    for t, u in meta["sources"]
                ]
            )
            + "</ul></div>"
        )

    return f"""
    <div style="max-width:780px;margin:24px auto;font-family:system-ui;direction:rtl">
      <h2>🧠 سؤالك:</h2>
      <div style="background:#222;color:#fff;padding:12px;border-radius:8px">
        {q}
      </div>
      <h2 style="margin-top:18px">💬 الجواب:</h2>
      <div style="background:#f7f7f7;padding:12px;border-radius:8px;color:#111;white-space:pre-line">
        {ans}
      </div>
      {sources_html}
      <div style="margin-top:20px">
        <a href="/" style="text-decoration:none;background:#007bff;color:white;padding:10px 18px;border-radius:6px">◀ رجوع</a>
      </div>
    </div>
    """

# ✅ API JSON للمطورين أو التطبيقات
@app.post("/api/ask")
async def api_ask(req: Request):
    body = await req.json()
    q = (body.get("question") or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="يرجى إدخال السؤال.")
    if any(k in q for k in ["حل", "كامل", "فرق", "معادلة", "تكامل", "جهاز", "نظام"]):
        ans = explain_math_answer(q)
        return {"ok": True, "mode": "math", "answer": ans}

    ans, sources = await smart_answer(q)
    return {"ok": True, "mode": "ai", "answer": ans, "sources": sources}

# ✅ فحص الجاهزية
@app.get("/ready")
def ready():
    return {"ok": True, "status": "Bassam AI جاهز للعمل ✅"}
