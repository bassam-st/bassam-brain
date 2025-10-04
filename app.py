# app.py — Bassam Brain (عقل مزدوج: محلي + بحث ويب)
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import json, time

from core.brain import smart_answer, save_to_knowledge, KB_FILE

app = FastAPI(title="Bassam Brain — Local + Web Intelligence")

# إنشاء مجلدات ثابتة
Path("static").mkdir(exist_ok=True)
Path("templates").mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
LOG_FILE = DATA_DIR / "log.jsonl"

# ✅ الصفحة الرئيسية
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ✅ استقبال السؤال من المستخدم وتحليل الإجابة
@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request):
    form = await request.form()
    q = (form.get("q") or "").strip()

    # تحليل السؤال وتوليد الإجابة
    ans, meta = smart_answer(q)

    # تسجيل العملية
    rec = {"ts": int(time.time()), "q": q, "answer": ans, "meta": meta}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "last_q": q, "last_a": ans, "links": meta.get("links", [])},
    )


# ✅ حفظ سؤال وجواب في قاعدة المعرفة
@app.post("/save", response_class=HTMLResponse)
async def save(request: Request):
    form = await request.form()
    q = (form.get("q") or "").strip()
    a = (form.get("a") or "").strip()
    if not q or not a:
        return HTMLResponse("<p>⚠️ أدخل سؤالًا وجوابًا.</p><p><a href='/'>رجوع</a></p>", status_code=400)
    save_to_knowledge(q, a)
    return HTMLResponse("<p>✅ تم الحفظ في قاعدة المعرفة.</p><p><a href='/'>◀ رجوع</a></p>")


# ✅ واجهة API لربط النموذج بتطبيق بسام لاحقًا
@app.post("/api/answer")
async def api_answer(req: Request):
    body = await req.json()
    q = (body.get("question") or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="ضع حقل 'question'")
    ans, meta = smart_answer(q)

    # سجل
    rec = {"ts": int(time.time()), "q": q, "answer": ans, "meta": meta}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return JSONResponse({"ok": True, "answer": ans, "meta": meta})


# ✅ فحص الجاهزية
@app.get("/ready")
def ready():
    return {"ok": True, "kb_exists": KB_FILE.exists()}
