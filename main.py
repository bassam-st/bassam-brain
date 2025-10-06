# main.py — Bassam AI (نص + صورة) + PWA جاهز
import os, uuid, json, traceback
from typing import Optional, List, Dict

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import httpx
from duckduckgo_search import DDGS

# مسارات
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
CACHE_DIR = os.path.join(BASE_DIR, "cache")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

# تطبيق + ملفات ثابتة
app = FastAPI(title="Bassam Brain")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# مفاتيح البيئة
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/") if os.getenv("PUBLIC_BASE_URL") else ""

# ----------------------------- دوال البحث -----------------------------
async def search_google_serper(q: str, num: int = 8):
    if not SERPER_API_KEY:
        raise RuntimeError("No SERPER_API_KEY configured")
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {"q": q, "num": num, "hl": "ar"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    out = []
    for it in (data.get("organic", []) or [])[:num]:
        out.append({"title": it.get("title"), "link": it.get("link"), "snippet": it.get("snippet"), "source": "Google"})
    return out

def search_duckduckgo(q: str, num: int = 8):
    out = []
    with DDGS() as ddgs:
        for r in ddgs.text(q, region="xa-ar", safesearch="moderate", max_results=num):
            out.append({"title": r.get("title"), "link": r.get("href") or r.get("url"), "snippet": r.get("body"), "source": "DuckDuckGo"})
            if len(out) >= num:
                break
    return out

async def smart_search(q: str, prefer_google: bool = True, num: int = 8):
    try:
        if prefer_google and SERPER_API_KEY:
            try:
                return {"ok": True, "used": "Google", "results": await search_google_serper(q, num)}
            except Exception:
                return {"ok": True, "used": "DuckDuckGo", "results": search_duckduckgo(q, num)}
        else:
            return {"ok": True, "used": "DuckDuckGo", "results": search_duckduckgo(q, num)}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "used": None, "results": [], "error": str(e)}

# ----------------------------- الصفحات -----------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/healthz")
def health():
    return {"ok": True}

# ----------------------------- بحث نصي -----------------------------
@app.post("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Form(...), include_prices: Optional[bool] = Form(False)):
    q = (q or "").strip()
    if not q:
        return templates.TemplateResponse("index.html", {"request": request, "error": "الرجاء كتابة سؤالك أولًا."})
    result = await smart_search(q, prefer_google=True, num=8)
    ctx = {
        "request": request,
        "query": q,
        "engine_used": result.get("used"),
        "results": result.get("results", []),
        "include_prices": bool(include_prices),
    }
    if not result.get("ok"):
        ctx["error"] = f"حدث خطأ في البحث: {result.get('error')}"
    return templates.TemplateResponse("index.html", ctx)

# ----------------------------- رفع صورة + روابط عدسة -----------------------------
@app.post("/upload", response_class=HTMLResponse)
async def upload_image(request: Request, file: UploadFile = File(...)):
    try:
        if not file or not file.filename:
            return templates.TemplateResponse("index.html", {"request": request, "error": "لم يتم اختيار صورة."})

        ext = (file.filename.split(".")[-1] or "jpg").lower()
        if ext not in ["jpg", "jpeg", "png", "webp", "gif"]:
            ext = "jpg"
        filename = f"{uuid.uuid4().hex}.{ext}"
        save_path = os.path.join(UPLOADS_DIR, filename)
        with open(save_path, "wb") as f:
            f.write(await file.read())

        public_base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
        image_url = f"{public_base}/uploads/{filename}"

        google_lens = f"https://lens.google.com/uploadbyurl?url={image_url}"
        bing_visual = f"https://www.bing.com/visualsearch?imgurl={image_url}"

        return templates.TemplateResponse("index.html", {
            "request": request,
            "uploaded_image": filename,
            "google_lens": google_lens,
            "bing_visual": bing_visual,
            "message": "تم رفع الصورة بنجاح ✅، اختر طريقة البحث 👇",
        })
    except Exception as e:
        traceback.print_exc()
        return templates.TemplateResponse("index.html", {"request": request, "error": f"فشل رفع الصورة: {e}"})

# ----------------------------- خدمة SW على الجذر /sw.js -----------------------------
@app.get("/sw.js")
def sw_js():
    path = os.path.join(STATIC_DIR, "pwa", "sw.js")
    return FileResponse(path, media_type="application/javascript")
