# main.py — Bassam Brain (الإصدار المستقر قبل إشعارات OneSignal)
import os, traceback
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.search import deep_search
from core.utils import ensure_dirs

# المسارات
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
CACHE_DIR = os.path.join(BASE_DIR, "cache")
ensure_dirs(TEMPLATES_DIR, STATIC_DIR, UPLOADS_DIR, CACHE_DIR)

# إعداد التطبيق
app = FastAPI(title="Bassam — Deep Search & Summary")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """الصفحة الرئيسية"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/search")
async def search(request: Request):
    """نقطة البحث"""
    try:
        data = await request.json()
        q = data.get("q", "").strip()
        want_prices = data.get("want_prices", False)
        if not q:
            return {"ok": False, "error": "empty_query"}

        # استدعاء البحث العميق
        result = await deep_search(q, want_prices=want_prices)
        return {"ok": True, **result}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": str(e)}


@app.get("/admin/health")
async def health():
    """فحص الحالة"""
    return {"status": "ready", "message": "Bassam Brain يعمل الآن بنجاح ✅"}
