# main.py – Bassam AI (بحث نصّي + رفع صورة للبحث البصري)
# -----------------------------------------------
import os, uuid, json, traceback
from typing import Optional, List, Dict

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import httpx
from duckduckgo_search import DDGS

# -----------------------------
# إعدادات ومسارات أساسية
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")   # نعرضه على /uploads
CACHE_DIR = os.path.join(BASE_DIR, "cache")

# إنشاء المجلدات اللازمة
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

app = FastAPI(title="Bassam Brain")

# ملفات ثابتة + القوالب
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# مفاتيح البيئة
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()      # مفتاح serper.dev (اختياري)
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/") # مثال: https://rain.onrender.com

# -----------------------------
# دوال البحث
# -----------------------------
async def search_google_serper(q: str, num: int = 8) -> List[Dict]:
    """
    بحث Google عبر Serper.dev (يتطلب SERPER_API_KEY).
    يعيد قائمة نتائج قياسية: title, link, snippet, source="Google"
    """
    if not SERPER_API_KEY:
        raise RuntimeError("No SERPER_API_KEY configured")

    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {"q": q, "num": num, "hl": "ar"}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()

    results: List[Dict] = []
    for item in (data.get("organic", []) or [])[:num]:
        results.append({
            "title": item.get("title"),
            "link": item.get("link"),
            "snippet": item.get("snippet"),
            "source": "Google",
        })
    return results


def search_duckduckgo(q: str, num: int = 8) -> List[Dict]:
    """بحث DuckDuckGo كبديل احتياطي."""
    out: List[Dict] = []
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
    """
    يجرّب Google (إن توفر المفتاح)، وإلا ينتقل لـ DuckDuckGo.
    """
    try:
        results: List[Dict] = []
        used: Optional[str] = None

        if prefer_google and SERPER_API_KEY:
            try:
                results = await search_google_serper(q, num=num)
                used = "Google"
            except Exception:
                # فشل Google → جرّب DuckDuckGo
                results = search_duckduckgo(q, num=num)
                used = "DuckDuckGo"
        else:
            results = search_duckduckgo(q, num=num)
            used = "DuckDuckGo"

        return {"ok": True, "used": used, "results": results}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": str(e), "used": None, "results": []}

# -----------------------------
# الصفحات
# -----------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/healthz")
def health():
    return {"ok": True}

# -----------------------------
# بحث نصّي
# -----------------------------
@app.post("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = Form(...),
    include_prices: Optional[bool] = Form(False),
):
    """
    يستقبل سؤال المستخدم من النموذج ويعيد النتائج ضمن نفس الصفحة.
    خانة include_prices فقط لتفعيل/تعطيل روابط الأسعار (حسب واجهتك).
    """
    q = (q or "").strip()
    if not q:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": "الرجاء كتابة سؤالك أولًا."},
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

# -----------------------------
# رفع صورة + إنشاء روابط بحث بصري
# -----------------------------
@app.post("/upload", response_class=HTMLResponse)
async def upload_image(request: Request, file: UploadFile = File(...)):
    """
    يرفع الصورة إلى /uploads ويصنع روابط Google Lens و Bing Visual Search
    ثم يعرضها على نفس صفحة index.html لتضغط وتبحث.
    """
    try:
        if not file or not file.filename:
            return templates.TemplateResponse(
                "index.html",
                {"request": request, "error": "لم يتم اختيار صورة."},
            )

        # حفظ الصورة
        filename = file.filename
        save_path = os.path.join(UPLOADS_DIR, filename)
        with open(save_path, "wb") as f:
            f.write(await file.read())

        # الرابط العام للصورة
        if not PUBLIC_BASE_URL:
            raise RuntimeError("يرجى ضبط PUBLIC_BASE_URL في Environment Variables")

        image_url = f"{PUBLIC_BASE_URL}/uploads/{filename}"

        # روابط البحث البصري
        google_lens = f"https://lens.google.com/uploadbyurl?url={image_url}"
        bing_visual = f"https://www.bing.com/visualsearch?imgurl={image_url}"

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "uploaded_image": filename,
                "google_lens": google_lens,
                "bing_visual": bing_visual,
                "message": "تم رفع الصورة بنجاح ✅، اختر طريقة البحث 👇",
            },
        )

    except Exception as e:
        traceback.print_exc()
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": f"فشل رفع الصورة: {e}"},
        )
