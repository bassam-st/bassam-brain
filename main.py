# main.py — Bassam الذكي (بحث عميق من Google أولاً ثم DuckDuckGo)
import os, time, traceback
from typing import Optional, List, Dict

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.search import deep_search
from brain.omni_brain import summarize_answer
from core.utils import ensure_dirs

# إنشاء المجلدات المهمة
os.makedirs("uploads", exist_ok=True)
os.makedirs("cache", exist_ok=True)

# إعداد المسارات
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
ensure_dirs(TEMPLATES_DIR, STATIC_DIR, "uploads", "cache")

# تهيئة التطبيق
app = FastAPI(title="Bassam الذكي — بحث عميق")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """الصفحة الرئيسية"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/search", response_class=JSONResponse)
async def search(request: Request):
    """استقبال السؤال وتنفيذ البحث"""
    try:
        data = await request.json()
        q = data.get("q", "").strip()
        if not q:
            return {"ok": False, "error": "يرجى إدخال سؤال أو عبارة للبحث"}

        # تنفيذ البحث
        results = deep_search(q)
        summary = summarize_answer(q, results)

        return {
            "ok": True,
            "query": q,
            "summary": summary,
            "sources": results,
        }

    except Exception as e:
        print("❌ خطأ أثناء البحث:", e)
        traceback.print_exc()
        return {"ok": False, "error": str(e)}


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    """لوحة المشرف (لاحقًا تضاف فيها إدارة المستخدمين والسجل)"""
    return templates.TemplateResponse("admin.html", {"request": request})
