# main.py — Bassam Brain (FastAPI) + بحث + رفع صور + GPT
# + إشعارات مباريات OneSignal مجدولة بتوقيت مكة + Deeplink ياسين/جنرال + لوحة إدارة
import os, uuid, json, traceback, sqlite3, hashlib, io, csv, re
import datetime as dt
from typing import Optional, List, Dict
from urllib.parse import quote

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import httpx
from duckduckgo_search import DDGS

# جدولة
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

# OpenAI (اختياري)
from openai import OpenAI

# ----------------------------- مسارات
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

# ----------------------------- مفاتيح/إعدادات
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL", "") or "").rstrip("/")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "093589")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "bassam-secret")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5-mini").strip()
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# OneSignal + الدوريات + التوقيت + باكدجات
ONESIGNAL_APP_ID = os.getenv("ONESIGNAL_APP_ID", "").strip()
ONESIGNAL_REST_API_KEY = os.getenv("ONESIGNAL_REST_API_KEY", "").strip()  # os_v2_app_...
TIMEZONE = os.getenv("TIMEZONE", "Asia/Riyadh").strip()  # توقيت مكة
TZ = ZoneInfo(TIMEZONE)

LEAGUE_IDS = [x.strip() for x in os.getenv("LEAGUE_IDS", "4328,4335,4332,4331,4334,4480,4790").split(",") if x.strip()]

YACINE_PACKAGE = os.getenv("YACINE_PACKAGE", "com.yacine.app").strip()
GENERAL_PACKAGE = os.getenv("GENERAL_PACKAGE", "com.general.live").strip()
YACINE_SCHEME = os.getenv("YACINE_SCHEME", "yacine").strip()
GENERAL_SCHEME = os.getenv("GENERAL_SCHEME", "general").strip()

# أسماء الدوريات حسب TheSportsDB
LEAGUE_NAME_BY_ID = {
    "4328": "English Premier League",
    "4335": "Spanish La Liga",
    "4332": "Italian Serie A",
    "4331": "German Bundesliga",
    "4334": "French Ligue 1",
    "4480": "Saudi Pro League",
    "4790": "UEFA Champions League",
}

# ============================== قاعدة البيانات
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                type TEXT NOT NULL,      -- search | image | ask | push
                query TEXT,
                file_name TEXT,
                engine_used TEXT,
                ip TEXT,
                ua TEXT
            );
            """
        )
init_db()

def log_event(event_type: str, ip: str, ua: str, query: Optional[str]=None,
              file_name: Optional[str]=None, engine_used: Optional[str]=None):
    with db() as con:
        con.execute(
            "INSERT INTO logs (ts, type, query, file_name, engine_used, ip, ua) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (dt.datetime.utcnow().isoformat(timespec="seconds")+"Z", event_type, query, file_name, engine_used, ip, ua)
        )

# ============================== ردود ثابتة + خصوصية
CANNED_ANSWER = "بسام الشتيمي هو منصوريّ الأصل، وهو صانع هذا التطبيق."
INTRO_ANSWER = "أنا بسام الشتيمي، مساعدك. أخبرني بما ترغب أن تسألني."
SENSITIVE_PRIVACY_ANSWER = (
    "حرصًا على خصوصيتك وخصوصية الآخرين، بما في ذلك اسم زوجتك أو والدتك، "
    "لا يقدّم بسام أي معلومات شخصية أو عائلية. "
    "يُرجى استخدام التطبيق في الأسئلة العامة أو التعليمية فقط."
)

def normalize_ar(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"[ًٌٍَُِّْ]", "", t)
    t = t.replace("أ","ا").replace("إ","ا").replace("آ","ا").replace("ى","ي").replace("ة","ه")
    return t

INTRO_PATTERNS = [r"من انت", r"من أنت", r"مين انت", r"من تكون", r"من هو المساعد", r"تعرف بنفسك", r"عرف بنفسك"]
BASSAM_PATTERNS = [
    r"من هو بسام", r"مين بسام", r"من هو بسام الذكي", r"من هو بسام الشتيمي",
    r"من صنع التطبيق", r"من هو صانع التطبيق", r"من المطور", r"من هو صاحب التطبيق",
    r"من مطور التطبيق", r"من برمج التطبيق", r"من انشأ التطبيق", r"مين المطور"
]
SENSITIVE_PATTERNS = [
    r"اسم\s*زوج(ة|ه)?\s*بسام", r"زوج(ة|ه)\s*بسام", r"مرت\s*بسام",
    r"اسم\s*ام\s*بسام", r"اسم\s*والدة\s*بسام", r"ام\s*بسام", r"والدة\s*بسام",
    r"اسم\s*زوجة", r"اسم\s*ام", r"من هي زوجة", r"من هي ام"
]

def is_intro_query(user_text: str) -> bool:
    q = normalize_ar(user_text);  return any(re.search(p, q) for p in INTRO_PATTERNS)
def is_bassam_query(user_text: str) -> bool:
    q = normalize_ar(user_text);  return any(re.search(p, q) for p in BASSAM_PATTERNS)
def is_sensitive_personal_query(user_text: str) -> bool:
    q = normalize_ar(user_text);  return any(re.search(p, q) for p in SENSITIVE_PATTERNS)

# ============================== تلخيص بسيط
def _clean(txt: str) -> str:
    txt = (txt or "").strip()
    return re.sub(r"[^\w\s\u0600-\u06FF]", " ", txt)

def make_bullets(snippets: List[str], max_items: int = 8) -> List[str]:
    text = " ".join(_clean(s) for s in snippets if s).strip()
    parts = re.split(r"[.!؟\n]", text)
    cleaned, seen = [], set()
    for p in parts:
        p = re.sub(r"\s+", " ", p).strip(" -•،,")
        if len(p.split()) >= 4:
            key = p[:80]
            if key not in seen:
                seen.add(key); cleaned.append(p)
        if len(cleaned) >= max_items: break
    return cleaned

# ============================== البحث (Serper ثم DuckDuckGo)
async def search_google_serper(q: str, num: int = 6) -> List[Dict]:
    if not SERPER_API_KEY: raise RuntimeError("No SERPER_API_KEY configured")
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {"q": q, "num": num, "hl": "ar"}
    async with httpx.AsyncClient(timeout=25) as client_httpx:
        r = await client_httpx.post(url, headers=headers, json=payload)
        r.raise_for_status(); data = r.json()
    out = []
    for it in (data.get("organic", []) or [])[:num]:
        out.append({"title": it.get("title"), "link": it.get("link"),
                    "snippet": it.get("snippet"), "source": "Google"})
    return out

def search_duckduckgo(q: str, num: int = 6) -> List[Dict]:
    out = []
    with DDGS() as ddgs:
        for r in ddgs.text(q, region="xa-ar", safesearch="moderate", max_results=num):
            out.append({"title": r.get("title"), "link": r.get("href") or r.get("url"),
                        "snippet": r.get("body"), "source": "DuckDuckGo"})
            if len(out) >= num: break
    return out

async def smart_search(q: str, num: int = 6) -> Dict:
    q = (q or "").strip()
    try:
        used, results = None, []
        if SERPER_API_KEY:
            try: results = await search_google_serper(q, num); used = "Google"
            except Exception: results = search_duckduckgo(q, num); used = "DuckDuckGo"
        else:
            results = search_duckduckgo(q, num); used = "DuckDuckGo"
        bullets = make_bullets([r.get("snippet") for r in results], max_items=8)
        return {"ok": True, "used": used, "bullets": bullets, "results": results}
    except Exception as e:
        traceback.print_exc();  return {"ok": False, "used": None, "results": [], "error": str(e)}

# ============================== صفحات HTML
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/healthz")
def health():
    return {"ok": True}

# ============================== بحث نصي
@app.post("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Form(...)):
    q = (q or "").strip()
    if not q:
        return templates.TemplateResponse("index.html", {"request": request, "error": "📝 الرجاء كتابة سؤالك أولًا."})

    if is_intro_query(q):
        ip = request.client.host if request.client else "?"
        ua = request.headers.get("user-agent", "?")
        log_event("search", ip, ua, query=q, engine_used="CANNED_INTRO")
        ctx = {"request": request, "query": q, "engine_used": "CANNED_INTRO", "results": [], "bullets": [INTRO_ANSWER]}
        return templates.TemplateResponse("index.html", ctx)

    if is_bassam_query(q):
        ip = request.client.host if request.client else "?"
        ua = request.headers.get("user-agent", "?")
        log_event("search", ip, ua, query=q, engine_used="CANNED")
        ctx = {"request": request, "query": q, "engine_used": "CANNED", "results": [], "bullets": [CANNED_ANSWER]}
        return templates.TemplateResponse("index.html", ctx)

    if is_sensitive_personal_query(q):
        ip = request.client.host if request.client else "?"
        ua = request.headers.get("user-agent", "?")
        log_event("search", ip, ua, query=q, engine_used="CANNED_PRIVACY")
        ctx = {"request": request, "query": q, "engine_used": "CANNED_PRIVACY", "results": [], "bullets": [SENSITIVE_PRIVACY_ANSWER]}
        return templates.TemplateResponse("index.html", ctx)

    result = await smart_search(q, num=8)
    ip = request.client.host if request.client else "?"
    ua = request.headers.get("user-agent", "?")
    log_event("search", ip, ua, query=q, engine_used=result.get("used"))

    ctx = {"request": request, "query": q, "engine_used": result.get("used"),
           "results": result.get("results", []), "bullets": result.get("bullets", [])}
    if not result.get("ok"):
        ctx["error"] = f"⚠️ حدث خطأ في البحث: {result.get('error')}"
    return templates.TemplateResponse("index.html", ctx)

# ============================== رفع صورة + روابط عدسات
@app.post("/upload", response_class=HTMLResponse)
async def upload_image(request: Request, file: UploadFile = File(...)):
    try:
        if not file or not file.filename:
            return templates.TemplateResponse("index.html", {"request": request, "error": "لم يتم اختيار صورة."})

        ext = (file.filename.split(".")[-1] or "jpg").lower()
        if ext not in ["jpg", "jpeg", "png", "webp", "gif"]: ext = "jpg"
        filename = f"{uuid.uuid4().hex}.{ext}"
        save_path = os.path.join(UPLOADS_DIR, filename)
        with open(save_path, "wb") as f:  f.write(await file.read())

        public_base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
        image_url = f"{public_base}/uploads/{filename}"

        google_lens = f"https://lens.google.com/uploadbyurl?url={image_url}"
        bing_visual = f"https://www.bing.com/visualsearch?imgurl={image_url}"

        ip = request.client.host if request.client else "?"
        ua = request.headers.get("user-agent", "?")
        log_event("image", ip, ua, file_name=filename)

        return templates.TemplateResponse("index.html",
