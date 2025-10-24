# ================================================
# main.py — Bassam Brain (إصدار مطور للنشر في Render)
# بحث + رفع صور + GPT/محلي + إشعارات مباريات OneSignal
# لوحة إدارة + PWA + Deeplink ياسين/جنرال
# ================================================

import os, json, traceback, sqlite3, io, hashlib, datetime as dt
from typing import List, Dict, Optional
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx
from duckduckgo_search import DDGS
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo
from openai import OpenAI

# =================================================
# إعداد المسارات
# =================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
DB_PATH = os.path.join(BASE_DIR, "data.db")

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

app = FastAPI(title="Bassam Brain", version="3.1")

# =================================================
# الضبط العام
# =================================================
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "093589")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "bassam-secret")
ONESIGNAL_APP_ID = os.getenv("ONESIGNAL_APP_ID", "")
ONESIGNAL_REST_API_KEY = os.getenv("ONESIGNAL_REST_API_KEY", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LOCAL_LLM_BASE = os.getenv("LOCAL_LLM_BASE", "")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Aden").strip()
TZ = ZoneInfo(TIMEZONE)

# =================================================
# إعداد القوالب
# =================================================
templates = Jinja2Templates(directory=TEMPLATES_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# =================================================
# استدعاء نواة التحليل والتلخيص المجاني
# =================================================
from brain.omni_brain import summarize_answer, summarize_as_json

# =================================================
# أدوات مساعدة
# =================================================
def make_bullets(items: List[str], max_items: int = 6) -> str:
    return "\n".join([f"• {i.strip()}" for i in items[:max_items] if i.strip()])

def hash_password(p: str) -> str:
    return hashlib.sha256(p.encode()).hexdigest()

def is_admin(request: Request) -> bool:
    token = request.cookies.get("bb_admin")
    return token == hash_password(ADMIN_SECRET + ADMIN_PASSWORD)

# =================================================
# البحث الذكي (Google + Serper + DuckDuckGo)
# =================================================
async def search_google_cse(q: str, num: int = 6) -> List[Dict]:
    if not (GOOGLE_API_KEY and GOOGLE_CSE_ID):
        raise RuntimeError("Google CSE not configured")
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_API_KEY, "cx": GOOGLE_CSE_ID, "q": q,
        "num": min(num, 10), "hl": "ar", "lr": "lang_ar"
    }
    async with httpx.AsyncClient(timeout=20) as ax:
        r = await ax.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    return [{"title": it.get("title"), "link": it.get("link"),
             "snippet": it.get("snippet"), "source": "Google CSE"}
            for it in data.get("items", [])[:num]]

async def search_google_serper(q: str, num: int = 6) -> List[Dict]:
    if not SERPER_API_KEY:
        raise RuntimeError("No SERPER_API_KEY configured")
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {"q": q, "num": num, "hl": "ar"}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    return [{"title": it.get("title"), "link": it.get("link"),
             "snippet": it.get("snippet"), "source": "Google (Serper)"}
            for it in (data.get("organic", []) or [])[:num]]

def search_duckduckgo(q: str, num: int = 6) -> List[Dict]:
    out = []
    with DDGS() as ddgs:
        for r in ddgs.text(q, region="xa-ar", safesearch="moderate", max_results=num):
            out.append({
                "title": r.get("title"), "link": r.get("href") or r.get("url"),
                "snippet": r.get("body"), "source": "DuckDuckGo"
            })
            if len(out) >= num:
                break
    return out

async def smart_search(q: str, num: int = 6) -> Dict:
    try:
        results, used = [], None
        if GOOGLE_API_KEY and GOOGLE_CSE_ID:
            try:
                results = await search_google_cse(q, num)
                used = "Google CSE"
            except Exception:
                results = []
        if not results and SERPER_API_KEY:
            try:
                results = await search_google_serper(q, num)
                used = "Google (Serper)"
            except Exception:
                results = []
        if not results:
            results = search_duckduckgo(q, num)
            used = "DuckDuckGo"
        return {"ok": True, "used": used, "results": results}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "used": None, "results": [], "error": str(e)}

# =================================================
# OneSignal Push
# =================================================
def send_push(title: str, body: str, url_path: str = "/", request: Request = None) -> bool:
    if not (ONESIGNAL_APP_ID and ONESIGNAL_REST_API_KEY):
        return False
    base = PUBLIC_BASE_URL or (str(request.base_url).rstrip("/") if request else "")
    payload = {
        "app_id": ONESIGNAL_APP_ID,
        "included_segments": ["Subscribed Users"],
        "headings": {"ar": title, "en": title},
        "contents": {"ar": body, "en": body},
        "url": f"{base}{url_path}"
    }
    try:
        r = httpx.post(
            "https://onesignal.com/api/v1/notifications",
            headers={"Authorization": f"Basic {ONESIGNAL_REST_API_KEY}"},
            json=payload, timeout=15
        )
        return r.status_code < 300
    except Exception:
        traceback.print_exc()
        return False

# =================================================
# لوحة الإدارة
# =================================================
@app.get("/admin", response_class=HTMLResponse)
def admin_panel(request: Request):
    if not is_admin(request):
        return templates.TemplateResponse("login.html", {"request": request})
    return templates.TemplateResponse("admin.html", {"request": request})

@app.post("/admin/login")
def admin_login(request: Request, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        token = hash_password(ADMIN_SECRET + ADMIN_PASSWORD)
        resp = RedirectResponse(url="/admin", status_code=302)
        resp.set_cookie("bb_admin", token, httponly=True, samesite="lax", secure=True)
        return resp
    return RedirectResponse(url="/admin?login=fail", status_code=302)

# =================================================
# API: السؤال الذكي
# =================================================
@app.post("/api/ask")
async def api_ask(request: Request, q: str = Form(...)):
    q = q.strip()
    if not q:
        return JSONResponse({"ok": False, "error": "فارغ"})

    # محاولة استخدام البحث
    search_data = await smart_search(q, 8)
    results = search_data.get("results", [])
    used = search_data.get("used")

    # محاولة توليد إجابة
    try:
        html_answer = summarize_answer(q, results)
        return JSONResponse({"ok": True, "engine": used, "html": html_answer})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"ok": False, "error": str(e)})

# =================================================
# الصفحة الرئيسية
# =================================================
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# =================================================
# Scheduler (للتحديثات الدورية أو التعليم الذاتي لاحقًا)
# =================================================
scheduler = BackgroundScheduler(timezone=TZ)

def scheduled_job():
    print("[Scheduler] تحديث تلقائي -", dt.datetime.now(TZ))

@app.on_event("startup")
def startup_event():
    try:
        scheduler.add_job(scheduled_job, CronTrigger(minute="*/30"))
        scheduler.start()
        print("[Bassam Brain] Scheduler started.")
    except Exception:
        traceback.print_exc()

@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown(wait=False)
    print("[Bassam Brain] Scheduler stopped.")

# =================================================
# Run (محلي فقط)
# =================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
