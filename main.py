# main.py — Bassam AI (بحث نصّي + بحث بالصور)
# -----------------------------------------------
import os, uuid, json, traceback
from typing import Optional, List, Dict

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import httpx
from duckduckgo_search import DDGS

# -----------------------------------------------
# إعداد المسارات والمجلدات
# -----------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
CACHE_DIR = os.path.join(BASE_DIR, "cache")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

app = FastAPI(title="Bassam AI — بحث ذكي")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# -----------------------------------------------
# مفاتيح البيئة (Environment Variables)
# -----------------------------------------------
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

# -----------------------------------------------
# دوال البحث النصي
# -----------------------------------------------
async def search_google_serper(q: str, num: int = 8) -> List[Dict]:
    """بحث Google عبر Serper.dev (يتطلب مفتاح SERPER_API_KEY)."""
    if not SERPER_API_KEY:
        raise RuntimeError("No SERPER_API_KEY configured")

    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {"q": q, "num": num, "hl": "ar"}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()

    results = []
    for item in (data.get("organic", []) or [])[:num]:
        results.append({
            "title": item.get("title"),
            "link": item.get("link"),
            "snippet": item.get("snippet"),
            "source": "Google"
        })
    return results


def search_duckduckgo(q: str, num: int = 8) -> List[Dict]:
    """بحث بديل من DuckDuckGo."""
    out = []
    with DDGS() as ddgs:
        for r in ddgs.text(q, region="xa-ar", safesearch="moderate", max_results=num):
            out.append({
                "title": r.get("title"),
                "link": r.get("href") or r.get("url"),
                "snippet": r.get("body"),
                "source": "DuckDuckGo",
            })
            if len(out) >= num:
                break
    return out


async def smart_search(q: str, prefer_google: bool = True, num: int = 8) -> Dict:
    """يستخدم Google أو DuckDuckGo حسب المفتاح."""
    try:
        results = []
        used = None
        if prefer_google and SERPER_API_KEY:
            try:
                results = await search_google_serper(q, num=num)
                used = "Google"
            except Exception:
                results = search_duckduckgo(q, num=num)
                used = "DuckDuckGo"
        else:
            results = search_duckduckgo(q, num=num)
            used = "DuckDuckGo"

        return {"ok": True, "used": used, "results": results}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": str(e), "used": None, "results": []}

# -----------------------------------------------
# الصفحات
# -----------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/healthz")
def health():
    return {"ok": True}

# -----------------------------------------------
# بحث نصي
# -----------------------------------------------
@app.post("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = Form(...),
    include_prices: Optional[bool] = Form(False)
):
    q = (q or "").strip()
    if not q:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": "الرجاء كتابة سؤالك أولاً."},
        )

    result = await smart_search(q, prefer_google=True, num=8)
    context = {
        "request": request,
        "query": q,
        "engine_used": result.get("used"),
        "results": result.get("results", []),
        "include_prices": include_prices or False,
    }

    if not result.get("ok"):
        context["error"] = f"حدث خطأ في البحث: {result.get('error')}"

    return templates.TemplateResponse("index.html", context)

# -----------------------------------------------
# رفع صورة + إنشاء روابط بحث بصري (عدسات)
# -----------------------------------------------
@app.post("/upload", response_class=HTMLResponse)
async def upload_image(request: Request, file: UploadFile = File(...)):
    """رفع الصورة وإنشاء روابط Google Lens + Bing + Yandex"""
    try:
        if not file or not file.filename:
            return templates.TemplateResponse(
                "index.html",
                {"request": request, "error": "الرجاء اختيار صورة للبحث."},
            )

        # حفظ الصورة
        filename = f"{uuid.uuid4().hex}_{file.filename}"
        save_path = os.path.join(UPLOADS_DIR, filename)
        with open(save_path, "wb") as f:
            f.write(await file.read())

        if not PUBLIC_BASE_URL:
            raise RuntimeError("⚠️ لم يتم ضبط PUBLIC_BASE_URL في إعدادات Render.")

        image_url = f"{PUBLIC_BASE_URL}/uploads/{filename}"

        # إنشاء الروابط
        google_lens = f"https://lens.google.com/uploadbyurl?url={image_url}"
        bing_visual = f"https://www.bing.com/visualsearch?imgurl={image_url}"
        yandex_search = f"https://yandex.com/images/search?rpt=imageview&url={image_url}"

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "uploaded_image": filename,
                "google_lens": google_lens,
                "bing_visual": bing_visual,
                "yandex_search": yandex_search,
                "message": "✅ تم رفع الصورة بنجاح، اختر طريقة البحث 👇",
            },
        )

    except Exception as e:
        traceback.print_exc()
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": f"حدث خطأ أثناء رفع الصورة: {e}"},
        )
