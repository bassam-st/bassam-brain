# main_plus_skills.py — Bassam Brain + SkillRouter (No heavy model)
# يضيف مهارات: بلد/مدينة (ويكيبيديا), آلة حاسبة, تحويل وحدات, توقيت مدن, تعريف سريع
# إن لم تُكتشف مهارة مناسبة → يعود لمحركات البحث الحالية لديك

import os, uuid, json, traceback, sqlite3, hashlib, io, csv, re, math, asyncio, datetime as dt
from typing import Optional, List, Dict, Tuple
from urllib.parse import quote

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import httpx
from duckduckgo_search import DDGS
from zoneinfo import ZoneInfo

# اختياري: لتحسين استخراج النص من الصفحات (لو موجودة في requirements)
USE_READABILITY = True
try:
    from bs4 import BeautifulSoup
    from readability import Document
except Exception:
    USE_READABILITY = False

# ============================= إعدادات ومسارات أساسية (مثل كودك الأصلي)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "bassam.db")

app = FastAPI(title="Bassam Brain")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/") if os.getenv("PUBLIC_BASE_URL") else ""
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "093589")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "bassam-secret")

# OneSignal & توقيت (كما لديك)
ONESIGNAL_APP_ID = os.getenv("ONESIGNAL_APP_ID", "").strip()
ONESIGNAL_REST_API_KEY = os.getenv("ONESIGNAL_REST_API_KEY", "").strip()
TIMEZONE = os.getenv("TIMEZONE", "Asia/Riyadh").strip()
TZ = ZoneInfo(TIMEZONE)

LEAGUE_NAME_BY_ID = {
    "4328": "English Premier League", "4335": "Spanish La Liga",
    "4332": "Italian Serie A", "4331": "German Bundesliga",
    "4334": "French Ligue 1", "4480": "Saudi Pro League",
    "4790": "UEFA Champions League",
}
LEAGUE_IDS = [x.strip() for x in os.getenv("LEAGUE_IDS", "4328,4335,4332,4331,4334,4480,4790").split(",") if x.strip()]

# ============================= DB و Logs
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                type TEXT NOT NULL,      -- search | image | ask | push
                query TEXT, file_name TEXT, engine_used TEXT, ip TEXT, ua TEXT
            );""")
init_db()

def log_event(event_type: str, ip: str, ua: str, query: Optional[str]=None,
              file_name: Optional[str]=None, engine_used: Optional[str]=None):
    with db() as con:
        con.execute("INSERT INTO logs (ts, type, query, file_name, engine_used, ip, ua) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (dt.datetime.utcnow().isoformat(timespec="seconds")+"Z", event_type, query, file_name, engine_used, ip, ua))

# ============================= أدوات نصية سريعة
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

# ============================= مهارات (SkillRouter)
CITY_TZ = {
    "الرياض": "Asia/Riyadh", "جدة": "Asia/Riyadh", "مكة": "Asia/Riyadh",
    "صنعاء": "Asia/Aden", "أبوظبي": "Asia/Dubai", "دبي": "Asia/Dubai",
    "القاهرة": "Africa/Cairo", "الاسكندرية": "Africa/Cairo",
    "الدوحة": "Asia/Qatar", "الكويت": "Asia/Kuwait", "المنامة": "Asia/Bahrain",
    "عمّان": "Asia/Amman", "دمشق": "Asia/Damascus", "بيروت": "Asia/Beirut",
    "الجزائر": "Africa/Algiers", "الرباط": "Africa/Casablanca", "تونس": "Africa/Tunis",
    "لندن": "Europe/London", "باريس": "Europe/Paris", "برلين": "Europe/Berlin",
    "اسطنبول": "Europe/Istanbul", "طوكيو": "Asia/Tokyo", "نيويورك": "America/New_York",
    "الدوادمي": "Asia/Riyadh"
}

UNIT_MAP = {
    ("km","mi"): 0.621371, ("mi","km"): 1.60934,
    ("kg","lb"): 2.20462,  ("lb","kg"): 0.453592,
    ("mph","kmh"): 1.60934,("kmh","mph"): 0.621371,
    ("c","f"): ("temp", lambda c: c*9/5+32), ("f","c"): ("temp", lambda f: (f-32)*5/9),
}

def _safe_calc(expr: str) -> Optional[float]:
    # آلة حاسبة آمنة للغاية: أرقام + +-*/%^() ومسافات فقط
    if not re.fullmatch(r"[0-9\.\s\+\-\*\/\%\^\(\)]+", expr):
        return None
    try:
        # استبدال ^ بـ ** للأسّ
        expr = expr.replace("^", "**")
        return float(eval(expr, {"__builtins__": {}}, {}))
    except Exception:
        return None

async def wiki_summary(term: str, lang: str="ar") -> Tuple[Optional[str], Optional[str], Dict]:
    """
    يرجع (ملخّص, رابط, حقائق) من ويكيبيديا REST.
    facts قد تحتوي: capital, region, location, coords...
    """
    term_q = term.strip().replace(" ", "_")
    langs = [lang, "en"] if lang != "en" else ["en","ar"]
    for L in langs:
        url = f"https://{L}.wikipedia.org/api/rest_v1/page/summary/{term_q}"
        try:
            async with httpx.AsyncClient(timeout=12) as ax:
                r = await ax.get(url)
            if r.status_code != 200:
                continue
            data = r.json()
            extract = (data.get("extract") or "").strip()
            page_url = data.get("content_urls", {}).get("desktop", {}).get("page")
            facts = {}
            # محاولة بسيطة لالتقاط معلومات من extract
            if extract:
                # capital
                m = re.search(r"(عاصمتها|العاصمة)\s+([^\s،\.]+)", extract)
                if m: facts["capital"] = m.group(2)
                # region
                m2 = re.search(r"(في\s+)?(?:شبه الجزيرة العربية|أفريقيا|آسيا|أوروبا|أمريكا(?:\s+(?:الشمالية|الجنوبية))?)", extract)
                if m2: facts["region"] = m2.group(0).replace("في ","")
            return extract, page_url, facts
        except Exception:
            continue
    return None, None, {}

def parse_country_city_q(q: str) -> Optional[Dict]:
    qn = q.strip()
    # أين تقع اليمن/عُمان/نجران/باريس...
    m = re.search(r"(اين|أين)\s+تقع\s+(.+)", qn)
    if m:
        return {"type": "geo", "ask": "where", "term": m.group(2).strip()}
    # ما عاصمة X؟
    m2 = re.search(r"(ما\s+)?(عاصمه|عاصمة)\s+(.+)", qn)
    if m2:
        return {"type": "geo", "ask": "capital", "term": m2.group(3).strip()}
    # ما هي/هو دولة/مدينة X
    m3 = re.search(r"(ما\s+هي|ما\s+هو)\s+(?:دوله|دولة|مدينه|مدينة)\s+(.+)", qn)
    if m3:
        return {"type": "geo", "ask": "about", "term": m3.group(2).strip()}
    return None

def parse_unit_convert(q: str) -> Optional[Tuple[float, str, str]]:
    # أمثلة: 50 mph إلى كم/س | 100 km to mi | 70 kg to lb
    q = q.lower().replace("الى","to").replace("إلى","to").replace("كم/س","kmh")
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(kmh|mph|km|mi|kg|lb|c|f)\s*(?:to|ل|في)\s*(kmh|mph|km|mi|kg|lb|c|f)", q)
    if not m: return None
    val = float(m.group(1)); src = m.group(2); dst = m.group(3)
    return val, src, dst

def parse_time_city(q: str) -> Optional[str]:
    # الوقت الآن في طوكيو/القاهرة/الرياض...
    m = re.search(r"(?:الوقت\s+الان|الوقت\s+الآن|كم\s+الساعة|ما\s+الوقت)\s+في\s+(.+)", q)
    if m:
        return m.group(1).strip(" ؟!.،")
    return None

async def skill_router(q: str) -> Optional[Dict]:
    """ يحاول الإجابة مباشرة. إن نجح يرجّع dict فيه answer/bullets/sources """
    q_stripped = (q or "").strip()

    # 1) آلة حاسبة
    m_calc = re.search(r"^([0-9\.\s\+\-\*\/\%\^\(\)]+)$", q_stripped)
    if m_calc:
        res = _safe_calc(m_calc.group(1))
        if res is not None:
            return {"answer": f"النتيجة: {res}", "bullets": [f"التعبير: {m_calc.group(1)}", f"النتيجة: {res}"], "sources": []}

    # 2) تحويل وحدات
    m_conv = parse_unit_convert(q_stripped)
    if m_conv:
        val, src, dst = m_conv
        key = (src, dst)
        if key in UNIT_MAP:
            factor = UNIT_MAP[key]
            if isinstance(factor, tuple) and factor[0] == "temp":
                out = factor[1](val)
            else:
                out = val * factor
            return {"answer": f"{val} {src} ≈ {round(out, 4)} {dst}",
                    "bullets": [f"تحويل {src}→{dst}", f"القيمة التقريبية: {round(out,4)}"], "sources": []}

    # 3) الوقت في مدينة
    city = parse_time_city(q_stripped)
    if city:
        tz = CITY_TZ.get(city) or CITY_TZ.get(city.capitalize())
        if tz:
            now = dt.datetime.now(ZoneInfo(tz))
            return {"answer": f"الوقت الآن في {city}: {now.strftime('%Y-%m-%d %H:%M')}",
                    "bullets": [f"المنطقة الزمنية: {tz}"], "sources": []}

    # 4) بلد/مدينة/تعريف سريع (ويكيبيديا)
    geo = parse_country_city_q(q_stripped)
    if geo:
        term = geo["term"]
        summary, link, facts = await wiki_summary(term, "ar")
        if summary:
            bullets = []
            if geo["ask"] == "where":
                bullets.append(f"الموقع: {facts.get('region','—')}")
            if facts.get("capital"):
                bullets.append(f"العاصمة: {facts['capital']}")
            bullets += make_bullets([summary], max_items=6)
            return {"answer": summary, "bullets": bullets, "sources": [{"title": f"Wikipedia — {term}", "link": link or ""}]}

    # 5) تعريف عام من ويكيبيديا لو بدأ بـ ما هو/هي
    if re.match(r"^(ما\s+هو|ما\s+هي)\s+", q_stripped):
        term = re.sub(r"^(ما\s+هو|ما\s+هي)\s+", "", q_stripped).strip()
        if term:
            summary, link, _ = await wiki_summary(term, "ar")
            if summary:
                return {"answer": summary, "bullets": make_bullets([summary], max_items=6),
                        "sources": [{"title": f"Wikipedia — {term}", "link": link or ""}]}

    return None  # لم تُكتشف مهارة

# ============================= البحث (كما هو عندك)
async def search_google_serper(q: str, num: int = 6) -> List[Dict]:
    if not SERPER_API_KEY:
        raise RuntimeError("No SERPER_API_KEY configured")
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {"q": q, "num": num, "hl": "ar"}
    async with httpx.AsyncClient(timeout=25) as ax:
        r = await ax.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    out = []
    for it in (data.get("organic", []) or [])[:num]:
        out.append({"title": it.get("title"), "link": it.get("link"),
                    "snippet": it.get("snippet"), "source": "Google"})
    return out

def search_duckduckgo(q: str, num: int = 6) -> List[Dict]:
    out = []
    with DDGS() as ddgs:
        for r in ddgs.text(q, region="xa-ar", safesearch="moderate", max_results=num):
            out.append({"title": r.get("title"),
                        "link": r.get("href") or r.get("url"),
                        "snippet": r.get("body"), "source": "DuckDuckGo"})
            if len(out) >= num: break
    return out

def make_bullets_from_results(results: List[Dict]) -> List[str]:
    return make_bullets([r.get("snippet") for r in results], max_items=8)

async def smart_search(q: str, num: int = 8) -> Dict:
    try:
        if SERPER_API_KEY:
            try:
                res = await search_google_serper(q, num); used = "Google"
            except Exception:
                res = search_duckduckgo(q, num); used = "DuckDuckGo"
        else:
            res = search_duckduckgo(q, num); used = "DuckDuckGo"
        return {"ok": True, "used": used, "results": res, "bullets": make_bullets_from_results(res)}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "used": None, "results": [], "error": str(e)}

# ============================= الصفحات
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/healthz")
def health():
    return {"ok": True}

# ============================= نقاط الإدخال مع SkillRouter أولاً
@app.post("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Form(...)):
    q = (q or "").strip()
    if not q:
        return templates.TemplateResponse("index.html", {"request": request, "error": "📝 الرجاء كتابة سؤالك أولًا."})

    # 1) جرّب المهارات أولاً
    handled = await skill_router(q)
    if handled:
        ip = request.client.host if request.client else "?"
        ua = request.headers.get("user-agent", "?")
        log_event("search", ip, ua, query=q, engine_used="Skills")
        ctx = {"request": request, "query": q, "engine_used": "Skills",
               "results": handled.get("sources", []),
               "bullets": handled.get("bullets") or make_bullets([handled.get("answer","")], max_items=6)}
        return templates.TemplateResponse("index.html", ctx)

    # 2) وإلا نرجع للبحث العادي
    result = await smart_search(q, num=8)
    ip = request.client.host if request.client else "?"
    ua = request.headers.get("user-agent", "?")
    log_event("search", ip, ua, query=q, engine_used=result.get("used"))

    ctx = {"request": request, "query": q,
           "engine_used": result.get("used"),
           "results": result.get("results", []),
           "bullets": result.get("bullets", [])}
    if not result.get("ok"):
        ctx["error"] = f"⚠️ حدث خطأ في البحث: {result.get('error')}"
    return templates.TemplateResponse("index.html", ctx)

@app.post("/upload", response_class=HTMLResponse)
async def upload_image(request: Request, file: UploadFile = File(...)):
    try:
        if not file or not file.filename:
            return templates.TemplateResponse("index.html", {"request": request, "error": "لم يتم اختيار صورة."})

        ext = (file.filename.split(".")[-1] or "jpg").lower()
        if ext not in ["jpg","jpeg","png","webp","gif"]: ext = "jpg"
        filename = f"{uuid.uuid4().hex}.{ext}"
        save_path = os.path.join(UPLOADS_DIR, filename)
        with open(save_path, "wb") as f: f.write(await file.read())

        public_base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
        image_url = f"{public_base}/uploads/{filename}"

        google_lens = f"https://lens.google.com/uploadbyurl?url={image_url}"
        bing_visual = f"https://www.bing.com/visualsearch?imgurl={image_url}"

        ip = request.client.host if request.client else "?"
        ua = request.headers.get("user-agent", "?")
        log_event("image", ip, ua, file_name=filename)

        return templates.TemplateResponse("index.html", {
            "request": request, "uploaded_image": filename, "google_lens": google_lens,
            "bing_visual": bing_visual, "message": "تم رفع الصورة بنجاح ✅، اختر طريقة البحث 👇"
        })
    except Exception as e:
        traceback.print_exc()
        return templates.TemplateResponse("index.html", {"request": request, "error": f"فشل رفع الصورة: {e}"})

# ============================= API JSON (يستفيد من المهارات أيضاً)
@app.post("/api/ask")
async def api_ask(request: Request):
    try:
        data = await request.json()
        q = (data.get("q") or "").strip()
        if not q:
            return JSONResponse({"ok": False, "error": "no_query"}, status_code=400)

        handled = await skill_router(q)
        if handled:
            ip = request.client.host if request.client else "?"
            ua = request.headers.get("user-agent", "?")
            log_event("ask", ip, ua, query=q, engine_used="Skills")
            return JSONResponse({"ok": True, "engine_used": "Skills",
                                 "answer": handled.get("answer",""),
                                 "bullets": handled.get("bullets", []),
                                 "sources": handled.get("sources", [])})

        # لا توجد مهارة → استخدم البحث
        search = await smart_search(q, num=6)
        sources = search.get("results", [])
        bullets = search.get("bullets", [])
        return JSONResponse({"ok": True, "engine_used": search.get("used"),
                             "answer": "نتيجة منسقة من البحث.",
                             "bullets": bullets, "sources": sources})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# ============================= Service Workers و OneSignal و Matches (كما هي عندك)
@app.get("/sw.js")
def sw_js():
    path = os.path.join(STATIC_DIR, "pwa", "sw.js")
    return FileResponse(path, media_type="application/javascript")

@app.get("/OneSignalSDKWorker.js")
def onesignal_worker_root():
    path = os.path.join(STATIC_DIR, "onesignal", "OneSignalSDKWorker.js")
    return FileResponse(path, media_type="application/javascript")

@app.get("/OneSignalSDKUpdaterWorker.js")
def onesignal_updater_root():
    path = os.path.join(STATIC_DIR, "onesignal", "OneSignalSDKUpdaterWorker.js")
    return FileResponse(path, media_type="application/javascript")

@app.get("/deeplink", response_class=HTMLResponse)
def deeplink(request: Request, match: Optional[str] = None):
    ctx = {"request": request, "mat": (match or "").strip(),
           "yacine_pkg": "com.yacine.app", "general_pkg": "com.general.live",
           "yacine_scheme": "yacine", "general_scheme": "general"}
    html = f"""<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"/>
    <body style="text-align:center;padding-top:60px;font-family:sans-serif;background:#0b0f19;color:#fff">
      <h2>جاري فتح القناة…</h2><p>{ctx['mat']}</p>
      <p><a style="color:#7cf" href="intent://open#Intent;scheme={ctx['yacine_scheme']};package={ctx['yacine_pkg']};end">افتح في ياسين</a></p>
      <p><a style="color:#7cf" href="intent://open#Intent;scheme={ctx['general_scheme']};package={ctx['general_pkg']};end">افتح في جنرال</a></p>
    </body></html>"""
    return HTMLResponse(html)

def send_push(title: str, body: str, url_path: str = "/") -> bool:
    if not (ONESIGNAL_APP_ID and ONESIGNAL_REST_API_KEY): return False
    full_url = url_path if url_path.startswith("http") else (PUBLIC_BASE_URL.rstrip("/") + url_path)
    payload = {"app_id": ONESIGNAL_APP_ID, "included_segments": ["Subscribed Users"],
               "headings": {"ar": title, "en": title}, "contents": {"ar": body, "en": body}, "url": full_url}
    headers = {"Authorization": f"Bearer {ONESIGNAL_REST_API_KEY}", "Content-Type": "application/json; charset=utf-8"}
    try:
        with httpx.Client(timeout=20) as client:
            r = client.post("https://api.onesignal.com/notifications", headers=headers, json=payload)
        return r.status_code in (200, 201)
    except Exception:
        return False

def _to_local(date_str: str, time_str: str) -> dt.datetime:
    t = (time_str or "00:00:00").split("+")[0]
    naive = dt.datetime.fromisoformat(f"{date_str}T{t}")
    if naive.tzinfo is None: naive = naive.replace(tzinfo=dt.timezone.utc)
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
                if not (home and away): continue
                kickoff = _to_local(e.get("dateEvent"), e.get("strTime") or "00:00:00")
                matches.append({"id": e.get("idEvent"), "league": e.get("strLeague") or lname,
                                "home": home, "away": away, "kickoff": kickoff, "venue": e.get("strVenue") or "",
                                "click_url": f"/deeplink?match={quote(f'{home} vs {away}')}"} )
    matches.sort(key=lambda x: x["kickoff"])
    return matches

def job_daily_digest_15():
    matches = fetch_today_matches()
    if not matches: return
    lines = [f"{m['kickoff'].strftime('%H:%M')} - {m['home']} × {m['away']} ({m['league']})" for m in matches]
    title = f"مباريات اليوم {dt.date.today().strftime('%Y-%m-%d')}"
    body = "\n".join(lines[:10])
    send_push(title, body, "/")

def job_half_hour_and_kickoff():
    matches = fetch_today_matches()
    if not matches: return
    now = dt.datetime.now(TZ)
    for m in matches:
        mins = int((m["kickoff"] - now).total_seconds() // 60)
        if 25 <= mins <= 35:
            send_push(f"⏰ بعد 30 دقيقة: {m['home']} × {m['away']}", f"البطولة: {m['league']}", m["click_url"])
        if -2 <= mins <= 2:
            send_push(f"🎬 بدأت الآن: {m['home']} × {m['away']}", f"البطولة: {m['league']}", m["click_url"])

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

def start_scheduler():
    sch = BackgroundScheduler(timezone=TIMEZONE)
    sch.add_job(job_daily_digest_15, CronTrigger(hour=15, minute=0, timezone=TIMEZONE))
    sch.add_job(job_half_hour_and_kickoff, CronTrigger(minute="*/5", timezone=TIMEZONE))
    sch.start()

@app.on_event("startup")
def _on_startup():
    try:
        start_scheduler()
    except Exception:
        traceback.print_exc()
