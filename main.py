# main.py — Bassam AI v4 (نصي + رفع صورة + PWA + لوحة بسيطة)
import os, uuid, json, time, traceback
from pathlib import Path
from typing import Optional, List, Dict

from fastapi import FastAPI, Request, Form, UploadFile, File, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import httpx
from duckduckgo_search import DDGS

# مسارات
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
UPLOADS_DIR = STATIC_DIR / "uploads"          # ✅ نرفع الصور داخل static/uploads ليتم خدمتها علنًا
CACHE_DIR = BASE_DIR / "cache"
for p in (STATIC_DIR, TEMPLATES_DIR, UPLOADS_DIR, CACHE_DIR):
    p.mkdir(parents=True, exist_ok=True)

# إعدادات
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")   # مثال: https://rain.onrender.com
ADMIN_PASSWORD  = os.getenv("ADMIN_PASSWORD", "093589")          # كوكي بسيطة للوحة
LOG_FILE = CACHE_DIR / "logs.jsonl"

# FastAPI
app = FastAPI(title="Bassam AI")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# أدوات
def log_event(row: dict):
    row["ts"] = int(time.time())
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

def admin_required(request: Request):
    if request.cookies.get("admin_auth") != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

# ---- بحث الويب
async def search_google_serper(q: str, num: int = 8) -> List[Dict]:
    if not SERPER_API_KEY:
        raise RuntimeError("No SERPER_API_KEY")
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {"q": q, "num": num, "hl": "ar"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    out = []
    for it in (data.get("organic", []) or [])[:num]:
        out.append({
            "title": it.get("title"),
            "link": it.get("link"),
            "snippet": it.get("snippet"),
            "source": "Google"
        })
    return out

def search_duckduckgo(q: str, num: int = 8) -> List[Dict]:
    out = []
    with DDGS() as ddgs:
        for r in ddgs.text(q, region="xa-ar", safesearch="moderate", max_results=num):
            out.append({
                "title": r.get("title"),
                "link": r.get("href") or r.get("url"),
                "snippet": r.get("body"),
                "source": "DuckDuckGo"
            })
            if len(out) >= num:
                break
    return out

async def smart_search(q: str, prefer_google=True, num=8) -> Dict:
    try:
        if prefer_google and SERPER_API_KEY:
            try:
                return {"ok": True, "used": "Google", "results": await search_google_serper(q, num)}
            except Exception:
                pass
        return {"ok": True, "used": "DuckDuckGo", "results": search_duckduckgo(q, num)}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": str(e), "results": [], "used": None}

# ---- الصفحات
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/healthz")
def health():
    return {"ok": True}

# ---- بحث نصّي
@app.post("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Form(...), include_prices: Optional[bool] = Form(False)):
    q = (q or "").strip()
    if not q:
        return templates.TemplateResponse("index.html", {"request": request, "error": "الرجاء كتابة سؤالك أولًا."})
    result = await smart_search(q, prefer_google=True, num=8)
    rows = result.get("results", [])
    if include_prices:
        rows = [r for r in rows if any(k in (r.get("title","")+r.get("snippet","")).lower()
                                       for k in ["price","سعر","ريال","درهم","دولار","$"])]
    log_event({"type":"text_search","q":q,"n":len(rows)})
    return templates.TemplateResponse("index.html", {
        "request": request,
        "query": q,
        "engine_used": result.get("used"),
        "results": rows,
        "include_prices": bool(include_prices),
        "error": None if result.get("ok") else result.get("error")
    })

# ---- رفع صورة + روابط Lens/Bing/Yandex
@app.post("/upload", response_class=HTMLResponse)
async def upload_image(request: Request, file: UploadFile = File(...)):
    try:
        if not file or not file.filename:
            return templates.TemplateResponse("index.html", {"request": request, "error": "لم يتم اختيار صورة."})

        # حفظ داخل static/uploads باسم فريد
        ext = (file.filename.split(".")[-1] or "jpg").lower()
        if ext not in ["jpg","jpeg","png","webp","gif"]:
            ext = "jpg"
        filename = f"{uuid.uuid4().hex}.{ext}"
        (UPLOADS_DIR / filename).write_bytes(await file.read())

        # نحتاج رابطًا عامًا https … بدون سلاش زائد
        if not PUBLIC_BASE_URL:
            raise RuntimeError("يرجى ضبط PUBLIC_BASE_URL في إعدادات Render (مثل https://rain.onrender.com)")
        image_url = f"{PUBLIC_BASE_URL}/static/uploads/{filename}"

        links = {
            "google_lens": f"https://lens.google.com/uploadbyurl?url={image_url}",
            "bing_visual": f"https://www.bing.com/images/searchbyimage?cbir=sbi&imgurl={image_url}",
            "yandex":      f"https://yandex.com/images/search?rpt=imageview&url={image_url}",
        }
        log_event({"type":"image_upload","file":filename})

        return templates.TemplateResponse("index.html", {
            "request": request,
            "uploaded_image": filename,
            "img_url": image_url,
            **links,
            "message": "تم رفع الصورة بنجاح ✅ اختر محرك البحث:"
        })
    except Exception as e:
        traceback.print_exc()
        return templates.TemplateResponse("index.html", {"request": request, "error": f"فشل رفع الصورة: {e}"})

# ---- لوحة إدارة بسيطة (سجل الاستعلامات)
@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    if request.cookies.get("admin_auth") == ADMIN_PASSWORD:
        rows = []
        if LOG_FILE.exists():
            with LOG_FILE.open("r", encoding="utf-8") as f:
                for line in f.readlines()[-400:]:
                    try: rows.append(json.loads(line))
                    except: pass
        rows.reverse()
        return templates.TemplateResponse("admin.html", {"request": request, "rows": rows, "ok": True})
    return templates.TemplateResponse("admin.html", {"request": request, "ok": False})

@app.post("/admin/login")
def admin_login(password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        resp = RedirectResponse("/admin", status_code=302)
        resp.set_cookie("admin_auth", ADMIN_PASSWORD, httponly=True, max_age=60*60*6)
        return resp
    return RedirectResponse("/admin", status_code=302)
