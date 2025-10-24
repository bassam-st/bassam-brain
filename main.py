# main.py — Bassam Brain (FastAPI)
# بحث + رفع صور + GPT/محلي + إشعارات مباريات OneSignal + Deeplink ياسين/جنرال

import os, uuid, json, traceback, sqlite3, hashlib, io, csv, re
import datetime as dt
from typing import Optional, List, Dict
from urllib.parse import quote

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import (
    HTMLResponse, RedirectResponse, FileResponse,
    StreamingResponse, JSONResponse
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import httpx
from duckduckgo_search import DDGS

# ----------------------------- جدولة
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

# ----------------------------- OpenAI (اختياري)
from openai import OpenAI

# ----------------------------- المسارات
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "bassam.db")

# ----------------------------- تطبيق
app = FastAPI(title="Bassam Brain")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ----------------------------- المفاتيح والإعدادات العامة
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "093589")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "bassam-secret")

# مفاتيح البحث
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")

# مفاتيح OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5-mini").strip()
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ----------------------------- النموذج المحلي (اختياري)
LOCAL_LLM_BASE = os.getenv("LOCAL_LLM_BASE", "").rstrip("/")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "local").strip()
USE_LOCAL_FIRST = os.getenv("USE_LOCAL_FIRST", "1").strip()

# ----------------------------- OneSignal
ONESIGNAL_APP_ID = os.getenv("ONESIGNAL_APP_ID", "").strip()
ONESIGNAL_REST_API_KEY = os.getenv("ONESIGNAL_REST_API_KEY", "").strip()
TIMEZONE = os.getenv("TIMEZONE", "Asia/Riyadh").strip()
TZ = ZoneInfo(TIMEZONE)

# ----------------------------- قواعد البيانات
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            type TEXT NOT NULL,
            query TEXT,
            file_name TEXT,
            engine_used TEXT,
            ip TEXT,
            ua TEXT
        );
        """)
init_db()

def log_event(event_type, ip, ua, query=None, file_name=None, engine_used=None):
    with db() as con:
        con.execute(
            "INSERT INTO logs (ts, type, query, file_name, engine_used, ip, ua) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (dt.datetime.utcnow().isoformat(timespec="seconds")+"Z", event_type, query, file_name, engine_used, ip, ua)
        )

# ----------------------------- دوال المساعدة
def normalize_ar(text):
    t = (text or "").strip().lower()
    t = re.sub(r"[ًٌٍَُِّْ]", "", t)
    t = t.replace("أ","ا").replace("إ","ا").replace("آ","ا").replace("ى","ي").replace("ة","ه")
    return t

INTRO_PATTERNS = [r"من انت", r"من أنت", r"مين انت", r"من تكون"]
BASSAM_PATTERNS = [r"من هو بسام", r"مين بسام", r"من صنع التطبيق"]
SENSITIVE_PATTERNS = [r"اسم\s*زوج", r"اسم\s*ام", r"من هي زوجة"]

def is_intro_query(q): return any(re.search(p, normalize_ar(q)) for p in INTRO_PATTERNS)
def is_bassam_query(q): return any(re.search(p, normalize_ar(q)) for p in BASSAM_PATTERNS)
def is_sensitive_query(q): return any(re.search(p, normalize_ar(q)) for p in SENSITIVE_PATTERNS)

# ----------------------------- صفحات HTML
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/healthz")
def health():
    return {"ok": True}

# ----------------------------- البحث الذكي
from core.search import smart_search

@app.post("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Form(...)):
    q = (q or "").strip()
    if not q:
        return templates.TemplateResponse("index.html", {"request": request, "error": "📝 الرجاء كتابة سؤالك أولًا."})

    # استدعاء الذكاء الثابت
    if is_intro_query(q):
        ctx = {"request": request, "query": q, "engine_used": "CANNED_INTRO", "bullets": ["أنا بسام الذكي، مساعدك الشخصي."]}
        return templates.TemplateResponse("index.html", ctx)
    if is_bassam_query(q):
        ctx = {"request": request, "query": q, "engine_used": "CANNED", "bullets": ["بسام الشتيمي هو منشئ هذا التطبيق."]}
        return templates.TemplateResponse("index.html", ctx)
    if is_sensitive_query(q):
        ctx = {"request": request, "query": q, "engine_used": "CANNED_PRIVACY",
               "bullets": ["⚠️ حفاظًا على الخصوصية لا يمكن عرض المعلومات الشخصية."]}
        return templates.TemplateResponse("index.html", ctx)

    # ✅ هنا الجزء الجديد
    result = await smart_search(
        q,
        max_results=8,
        google_api_key=GOOGLE_API_KEY,
        google_cse_id=GOOGLE_CSE_ID,
        serper_api_key=SERPER_API_KEY,
    )

    ip = request.client.host if request.client else "?"
    ua = request.headers.get("user-agent", "?")
    log_event("search", ip, ua, query=q, engine_used=result.get("used"))

    ctx = {"request": request, "query": q, "engine_used": result.get("used"),
           "results": result.get("results", []), "bullets": []}
    if not result.get("ok"):
        ctx["error"] = f"⚠️ حدث خطأ أثناء البحث: {result.get('error')}"
    return templates.TemplateResponse("index.html", ctx)

# ----------------------------- ملفات الخدمة
@app.get("/sw.js")
def sw_js():
    path = os.path.join(STATIC_DIR, "pwa", "sw.js")
    return FileResponse(path, media_type="application/javascript")
