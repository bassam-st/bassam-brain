# main.py — Bassam Brain (FastAPI) — بدون OpenAI
# بحث Google CSE أولًا ثم Google Scrape ثم DuckDuckGo + تلخيص/عرض + إشعارات + Deeplink + إدارة

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
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

# ========== استيراد النواة والبحث/التلخيص ==========
from brain.omni_brain import summarize_answer
from core.search import smart_search, deep_fetch_texts  # Google CSE → Google → DDG
from core.summarize import smart_summarize

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

# ----------------------------- مفاتيح/إعدادات عامة
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/") if os.getenv("PUBLIC_BASE_URL") else ""
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "093589")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "bassam-secret")

# بحث Google CSE (اختياري لكنه مفضّل)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
GOOGLE_CSE_ID  = os.getenv("GOOGLE_CSE_ID", "").strip()

# OneSignal + الدوريات + التوقيت
ONESIGNAL_APP_ID = os.getenv("ONESIGNAL_APP_ID", "").strip()
ONESIGNAL_REST_API_KEY = os.getenv("ONESIGNAL_REST_API_KEY", "").strip()
TIMEZONE = os.getenv("TIMEZONE", "Asia/Riyadh").strip()
TZ = ZoneInfo(TIMEZONE)

LEAGUE_NAME_BY_ID = {
    "4328": "English Premier League",
    "4335": "Spanish La Liga",
    "4332": "Italian Serie A",
    "4331": "German Bundesliga",
    "4334": "French Ligue 1",
    "4480": "Saudi Pro League",
    "4790": "UEFA Champions League",
}

LEAGUE_IDS = [x.strip() for x in os.getenv(
    "LEAGUE_IDS", "4328,4335,4332,4331,4334,4480,4790"
).split(",") if x.strip()]

YACINE_PACKAGE = os.getenv("YACINE_PACKAGE", "com.yacine.app").strip()
GENERAL_PACKAGE = os.getenv("GENERAL_PACKAGE", "com.general.live").strip()
YACINE_SCHEME = os.getenv("YACINE_SCHEME", "yacine").strip()
GENERAL_SCHEME = os.getenv("GENERAL_SCHEME", "general").strip()

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
    t = t.replace("أ","ا").replace("إ","ا").replace("آ","ا")
    t = t.replace("ى","ي").replace("ة","ه")
    return t

INTRO_PATTERNS = [r"من انت", r"من أنت", r"مين انت", r"من تكون", r"من هو المساعد", r"تعرف بنفسك", r"عرف بنفسك"]
BASSAM_PATTERNS = [
    r"من هو بسام", r"مين بسام", r"من هو بسام الذكي", r"من هو بسام الشتيمي",
    r"من صنع التطبيق", r"من هو صانع التطبيق", r"من المطور", r"من هو صاحب التطبيق",
    r"من مطور التطبيق", r"من برمج التطبيق", r"من انشأ التطبيق", r"مين المطور"
]
SENSITIVE_PATTERNS = [
    r"اسم\s+زوج(ة|ه)?\s*بسام", r"زوج(ة|ه)\s*بسام", r"مرت\s*بسام",
    r"اسم\s*ام\s*بسام", r"اسم\s*والدة\s*بسام", r"ام\s*بسام", r"والدة\s*بسام",
    r"اسم\s*زوجة", r"اسم\s*ام", r"من هي زوجة", r"من هي ام"
]

def is_intro_query(user_text: str) -> bool:
    q = normalize_ar(user_text);  return any(re.search(p, q) for p in INTRO_PATTERNS)
def is_bassam_query(user_text: str) -> bool:
    q = normalize_ar(user_text);  return any(re.search(p, q) for p in BASSAM_PATTERNS)
def is_sensitive_personal_query(user_text: str) -> bool:
    q = normalize_ar(user_text);  return any(re.search(p, q) for p in SENSITIVE_PATTERNS)

# ============================== صفحات HTML
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/healthz")
def health():
    return {"ok": True}

# ============================== بحث نصي (واجهة صفحة)
@app.post("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Form(...)):
    q = (q or "").strip()
    if not q:
        return templates.TemplateResponse("index.html", {"request": request, "error": "📝 الرجاء كتابة سؤالك أولًا."})

    # تعريفات ثابتة
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

    # البحث الذكي + تلخيص
    result = await smart_search(q, max_results=8, google_api_key=GOOGLE_API_KEY, google_cse_id=GOOGLE_CSE_ID)
    ip = request.client.host if request.client else "?"
    ua = request.headers.get("user-agent", "?")
    log_event("search", ip, ua, query=q, engine_used=result.get("used"))

    # لو في مقتطفات قليلة، نعزز بجلب نصوص الصفحات لأفضل خلاصة
    if not any(r.get("snippet") for r in result.get("results", [])):
        texts = await deep_fetch_texts(result.get("results", []), max_pages=5)
        bullets_txt = smart_summarize(q, texts, max_bullets=7)
        ctx = {"request": request, "query": q, "engine_used": result.get("used"),
               "results": result.get("results", []), "bullets": bullets_txt.split("\n")}
        return templates.TemplateResponse("index.html", ctx)

    # عرض منسّق عبر نواة omni_brain
    html_block = summarize_answer(q, result.get("results", []))
    ctx = {"request": request, "query": q, "engine_used": result.get("used"),
           "results": result.get("results", []), "html_block": html_block}
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

        return templates.TemplateResponse(
            "index.html",
            {"request": request, "uploaded_image": filename, "google_lens": google_lens,
             "bing_visual": bing_visual, "message": "تم رفع الصورة بنجاح ✅، اختر طريقة البحث 👇"}
        )
    except Exception as e:
        traceback.print_exc()
        return templates.TemplateResponse("index.html", {"request": request, "error": f"فشل رفع الصورة: {e}"})

# ============================== API: السؤال كـ JSON
@app.post("/api/ask")
async def api_ask(request: Request):
    try:
        data = await request.json()
    except Exception:
        form = await request.form()
        data = {"q": form.get("q")}

    q = (data.get("q") or "").strip()
    if not q:
        return JSONResponse({"ok": False, "error": "no_query"}, status_code=400)

    # ردود ثابتة
    if is_intro_query(q):
        ip = request.client.host if request.client else "?"
        ua = request.headers.get("user-agent", "?")
        log_event("ask", ip, ua, query=q, engine_used="CANNED_INTRO")
        return JSONResponse({"ok": True, "engine_used": "CANNED_INTRO",
                             "answer": INTRO_ANSWER, "bullets": [INTRO_ANSWER], "sources": []})

    if is_bassam_query(q):
        ip = request.client.host if request.client else "?"
        ua = request.headers.get("user-agent", "?")
        log_event("ask", ip, ua, query=q, engine_used="CANNED")
        return JSONResponse({"ok": True, "engine_used": "CANNED",
                             "answer": CANNED_ANSWER, "bullets": [CANNED_ANSWER], "sources": []})

    if is_sensitive_personal_query(q):
        ip = request.client.host if request.client else "?"
        ua = request.headers.get("user-agent", "?")
        log_event("ask", ip, ua, query=q, engine_used="CANNED_PRIVACY")
        return JSONResponse({"ok": True, "engine_used": "CANNED_PRIVACY",
                             "answer": SENSITIVE_PRIVACY_ANSWER, "bullets": [SENSITIVE_PRIVACY_ANSWER], "sources": []})

    # البحث
    result = await smart_search(q, max_results=8, google_api_key=GOOGLE_API_KEY, google_cse_id=GOOGLE_CSE_ID)
    sources = result.get("results", [])

    # توليد HTML من النواة
    if any(r.get("snippet") for r in sources):
        html_block = summarize_answer(q, sources)
        bullets_txt = None
    else:
        # تعزيز بالزحف الخفيف لاستخراج نصوص ثم تلخيص
        texts = await deep_fetch_texts(sources, max_pages=5)
        bullets_txt = smart_summarize(q, texts, max_bullets=7)
        html_block = None

    ip = request.client.host if request.client else "?"
    ua = request.headers.get("user-agent", "?")
    log_event("ask", ip, ua, query=q, engine_used=result.get("used"))

    return JSONResponse({
        "ok": True,
        "engine_used": result.get("used"),
        "html": html_block,
        "bullets": bullets_txt.split("\n") if bullets_txt else None,
        "sources": [{"title": s.get("title"), "url": s.get("link")} for s in sources],
    })

# ============================== Service Workers
@app.get("/sw.js")
def sw_js():
    path = os.path.join(STATIC_DIR, "pwa", "sw.js")
    return FileResponse(path, media_type="application/javascript")

# ⚠️ مسارات OneSignal workers على جذر الموقع
@app.get("/OneSignalSDKWorker.js")
def onesignal_worker_root():
    path = os.path.join(STATIC_DIR, "onesignal", "OneSignalSDKWorker.js")
    return FileResponse(path, media_type="application/javascript")

@app.get("/OneSignalSDKUpdaterWorker.js")
def onesignal_updater_root():
    path = os.path.join(STATIC_DIR, "onesignal", "OneSignalSDKUpdaterWorker.js")
    return FileResponse(path, media_type="application/javascript")

# ============================== Deeplink (فتح البث في ياسين/جنرال)
@app.get("/deeplink", response_class=HTMLResponse)
def deeplink(request: Request, match: Optional[str] = None):
    ctx = {"request": request, "mat": (match or "").strip(),
           "yacine_pkg": YACINE_PACKAGE, "general_pkg": GENERAL_PACKAGE,
           "yacine_scheme": YACINE_SCHEME, "general_scheme": GENERAL_SCHEME}
    tpl_path = os.path.join(TEMPLATES_DIR, "deeplink.html")
    if os.path.exists(tpl_path):
        return templates.TemplateResponse("deeplink.html", ctx)
    html = f"""
    <!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"/>
    <body style="text-align:center;padding-top:60px;font-family:sans-serif;background:#0b0f19;color:#fff">
      <h2>جاري فتح القناة…</h2>
      <p>{ctx['mat']}</p>
      <p><a style="color:#7cf" href="intent://open#Intent;scheme={YACINE_SCHEME};package={YACINE_PACKAGE};end">افتح في ياسين</a></p>
      <p><a style="color:#7cf" href="intent://open#Intent;scheme={GENERAL_SCHEME};package={GENERAL_PACKAGE};end">افتح في جنرال</a></p>
    </body></html>
    """
    return HTMLResponse(html)

# ============================== لوحة الإدارة
def make_token(password: str) -> str:
    return hashlib.sha256((password + "|" + ADMIN_SECRET).encode("utf-8")).hexdigest()
ADMIN_TOKEN = make_token(ADMIN_PASSWORD)

def is_admin(request: Request) -> bool:
    return request.cookies.get("bb_admin") == ADMIN_TOKEN

@app.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request, login: Optional[int] = None):
    if not is_admin(request):
        return templates.TemplateResponse("admin.html", {"request": request, "page": "login", "error": None, "login": True})
    with db() as con:
        rows = con.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 200").fetchall()
    return templates.TemplateResponse("admin.html", {"request": request, "page": "dashboard", "rows": rows, "count": len(rows)})

@app.post("/admin/login")
def admin_login(request: Request, password: str = Form(...)):
    if make_token(password) == ADMIN_TOKEN:
        resp = RedirectResponse(url="/admin", status_code=302)
        resp.set_cookie("bb_admin", ADMIN_TOKEN, httponly=True, samesite="lax")
        return resp
    return templates.TemplateResponse("admin.html", {"request": request, "page": "login", "error": "❌ كلمة المرور غير صحيحة", "login": True})

@app.get("/admin/logout")
def admin_logout():
    resp = RedirectResponse(url="/admin?login=1", status_code=302)
    resp.delete_cookie("bb_admin")
    return resp

@app.get("/admin/export.csv")
def admin_export(request: Request):
    if not is_admin(request):
        return RedirectResponse(url="/admin?login=1", status_code=302)
    with db() as con:
        cur = con.execute("SELECT id, ts, type, query, file_name, engine_used, ip, ua FROM logs ORDER BY id DESC")
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id","ts","type","query","file_name","engine_used","ip","user_agent"])
        for row in cur:
            writer.writerow([
                row["id"], row["ts"], row["type"], row["query"] or "",
                row["file_name"] or "", row["engine_used"] or "", row["ip"] or "", row["ua"] or ""
            ])
        output.seek(0)
    return StreamingResponse(iter([output.read()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=bassam-logs.csv"})

# ============================== مباريات اليوم + إشعارات OneSignal (بتوقيت مكة)
def _to_local(date_str: str, time_str: str) -> dt.datetime:
    t = (time_str or "00:00:00").split("+")[0]
    naive = dt.datetime.fromisoformat(f"{date_str}T{t}")
    if naive.tzinfo is None:
        naive = naive.replace(tzinfo=dt.timezone.utc)
    return naive.astimezone(TZ)

def fetch_today_matches() -> List[Dict]:
    today = dt.date.today()
    s_today = today.strftime("%Y-%m-%d")
    matches: List[Dict] = []
    with httpx.Client(timeout=20) as client:
        for lid, lname in LEAGUE_NAME_BY_ID.items():
            url = f"https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d={s_today}&l={quote(lname)}"
            try:
                data = client.get(url).json()
            except Exception:
                continue
            for e in (data or {}).get("events", []) or []:
                home, away = e.get("strHomeTeam"), e.get("strAwayTeam")
                if not (home and away):
                    continue
                kickoff = _to_local(e.get("dateEvent"), e.get("strTime") or "00:00:00")
                matches.append({
                    "id": e.get("idEvent"),
                    "league": e.get("strLeague") or lname,
                    "home": home, "away": away,
                    "kickoff": kickoff,
                    "venue": e.get("strVenue") or "",
                    "click_url": f"/deeplink?match={quote(f'{home} vs {away}')}"
                })
    matches.sort(key=lambda x: x["kickoff"])
    return matches

def send_push(title: str, body: str, url_path: str = "/") -> bool:
    if not (ONESIGNAL_APP_ID and ONESIGNAL_REST_API_KEY):
        return False
    full_url = url_path if url_path.startswith("http") else (PUBLIC_BASE_URL.rstrip("/") + url_path)
    payload = {
        "app_id": ONESIGNAL_APP_ID,
        "included_segments": ["Subscribed Users"],
        "headings": {"ar": title, "en": title},
        "contents": {"ar": body, "en": body},
        "url": full_url,
    }
    headers = {"Authorization": f"Bearer {ONESIGNAL_REST_API_KEY}",
               "Content-Type": "application/json; charset=utf-8"}
    try:
        with httpx.Client(timeout=20) as client:
            r = client.post("https://api.onesignal.com/notifications", headers=headers, json=payload)
        return r.status_code in (200, 201)
    except Exception:
        return False

def job_daily_digest_15():
    matches = fetch_today_matches()
    if not matches:
        return
    lines = [f"{m['kickoff'].strftime('%H:%M')} - {m['home']} × {m['away']} ({m['league']})" for m in matches]
    title = f"مباريات اليوم {dt.date.today().strftime('%Y-%m-%d')}"
    body = "\n".join(lines[:10])
    send_push(title, body, "/")

def job_half_hour_and_kickoff():
    matches = fetch_today_matches()
    if not matches:
        return
    now = dt.datetime.now(TZ)
    for m in matches:
        mins = int((m["kickoff"] - now).total_seconds() // 60)
        if 25 <= mins <= 35:
            send_push(f"⏰ بعد 30 دقيقة: {m['home']} × {m['away']}", f"البطولة: {m['league']}", m["click_url"])
        if -2 <= mins <= 2:
            send_push(f"🎬 بدأت الآن: {m['home']} × {m['away']}", f"البطولة: {m['league']}", m["click_url"])

def start_scheduler():
    sch = BackgroundScheduler(timezone=TIMEZONE)
    sch.add_job(job_daily_digest_15, CronTrigger(hour=15, minute=0, timezone=TIMEZONE))   # ⏰ 15:00 يوميًا مكة
    sch.add_job(job_half_hour_and_kickoff, CronTrigger(minute="*/5", timezone=TIMEZONE))  # ⏱️ كل 5 دقائق
    sch.start()

@app.on_event("startup")
def _on_startup():
    try:
        start_scheduler()
    except Exception:
        traceback.print_exc()
