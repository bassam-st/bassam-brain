# main.py — Bassam Brain Plus v1 (ذكاء فوري + بحث نصي وصوري + لوحة إدارة)
import os, uuid, json, traceback, sqlite3, hashlib, io, csv, difflib, re
from datetime import datetime
from typing import Optional, List, Dict
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

# ====== المسارات ======
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "bassam.db")

# ====== الإعداد ======
app = FastAPI(title="Bassam Brain Plus")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ====== المتغيرات ======
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/") if os.getenv("PUBLIC_BASE_URL") else ""
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "093589")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "bassam-secret")

# ====== قاعدة البيانات ======
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT, type TEXT, query TEXT, file_name TEXT,
                engine_used TEXT, ip TEXT, ua TEXT
            );
        """)
init_db()

def log_event(event_type, ip, ua, query=None, file_name=None, engine_used=None):
    with db() as con:
        con.execute(
            "INSERT INTO logs (ts,type,query,file_name,engine_used,ip,ua) VALUES (?,?,?,?,?,?,?)",
            (datetime.utcnow().isoformat(timespec="seconds")+"Z", event_type, query, file_name, engine_used, ip, ua)
        )

# ====== دوال الذكاء الفوري ======
def clean_query(text: str) -> str:
    """تصحيح الأخطاء الشائعة"""
    text = text.strip()
    text = re.sub(r"[^\w\s\u0600-\u06FF]", "", text)  # حذف الرموز
    return text

def correct_spelling(query: str, candidates: List[str]) -> str:
    """محاولة تصحيح الكلمات"""
    matches = difflib.get_close_matches(query, candidates, n=1, cutoff=0.6)
    return matches[0] if matches else query

async def generate_summary(texts: List[str]) -> str:
    """تلخيص فوري للنصوص المجمّعة"""
    joined = " ".join(texts)[:2000]
    sentences = re.split(r"[.!؟]", joined)
    unique = list(dict.fromkeys([s.strip() for s in sentences if len(s.split()) > 4]))
    summary = "، ".join(unique[:3]) + "..."
    return summary if summary else "لم أجد تفاصيل كافية، لكن إليك بعض المصادر المفيدة 👇"

# ====== دوال البحث ======
async def search_google_serper(q: str, num: int = 6) -> List[Dict]:
    if not SERPER_API_KEY:
        raise RuntimeError("No SERPER_API_KEY configured")
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {"q": q, "num": num, "hl": "ar"}
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    results = []
    for it in (data.get("organic", []) or [])[:num]:
        results.append({"title": it.get("title"), "link": it.get("link"), "snippet": it.get("snippet"), "source": "Google"})
    return results

def search_duckduckgo(q: str, num: int = 6) -> List[Dict]:
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

async def smart_search(q: str, prefer_google=True) -> Dict:
    q = clean_query(q)
    try:
        results = []
        used = None
        if prefer_google and SERPER_API_KEY:
            try:
                results = await search_google_serper(q)
                used = "Google"
            except Exception:
                results = search_duckduckgo(q)
                used = "DuckDuckGo"
        else:
            results = search_duckduckgo(q)
            used = "DuckDuckGo"

        texts = [r["snippet"] or "" for r in results]
        summary = await generate_summary(texts)
        return {"ok": True, "used": used, "summary": summary, "results": results}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": str(e), "used": None, "results": []}

# ====== الصفحات ======
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/healthz")
def health():
    return {"ok": True}

# ====== البحث النصي ======
@app.post("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Form(...)):
    q = (q or "").strip()
    if not q:
        return templates.TemplateResponse("index.html", {"request": request, "error": "📝 الرجاء كتابة سؤالك أولًا."})

    ip = request.client.host if request.client else "?"
    ua = request.headers.get("user-agent", "?")

    result = await smart_search(q)
    log_event("search", ip, ua, query=q, engine_used=result.get("used"))

    ctx = {
        "request": request,
        "query": q,
        "summary": result.get("summary"),
        "engine_used": result.get("used"),
        "results": result.get("results", []),
    }
    if not result.get("ok"):
        ctx["error"] = f"⚠️ خطأ أثناء البحث: {result.get('error')}"
    return templates.TemplateResponse("index.html", ctx)

# ====== رفع الصور ======
@app.post("/upload", response_class=HTMLResponse)
async def upload_image(request: Request, file: UploadFile = File(...)):
    try:
        if not file or not file.filename:
            return templates.TemplateResponse("index.html", {"request": request, "error": "لم يتم اختيار صورة."})

        ext = (file.filename.split(".")[-1] or "jpg").lower()
        if ext not in ["jpg", "jpeg", "png", "webp", "gif"]:
            ext = "jpg"
        filename = f"{uuid.uuid4().hex}.{ext}"
        path = os.path.join(UPLOADS_DIR, filename)
        with open(path, "wb") as f:
            f.write(await file.read())

        public_base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
        image_url = f"{public_base}/uploads/{filename}"
        google_lens = f"https://lens.google.com/uploadbyurl?url={image_url}"
        bing_visual = f"https://www.bing.com/visualsearch?imgurl={image_url}"

        ip = request.client.host if request.client else "?"
        ua = request.headers.get("user-agent", "?")
        log_event("image", ip, ua, file_name=filename)

        return templates.TemplateResponse("index.html", {
            "request": request,
            "uploaded_image": filename,
            "google_lens": google_lens,
            "bing_visual": bing_visual,
            "message": "✅ تم رفع الصورة بنجاح، اختر طريقة البحث 👇",
        })
    except Exception as e:
        traceback.print_exc()
        return templates.TemplateResponse("index.html", {"request": request, "error": f"⚠️ فشل رفع الصورة: {e}"})

# ====== لوحة الإدارة ======
@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, login: Optional[int] = None):
    token = hashlib.sha256((ADMIN_PASSWORD + "|" + ADMIN_SECRET).encode()).hexdigest()
    if request.cookies.get("bb_admin") != token:
        return templates.TemplateResponse("admin.html", {"request": request, "login": True, "error": None})
    with db() as con:
        rows = con.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 200").fetchall()
    return templates.TemplateResponse("admin.html", {"request": request, "rows": rows})

@app.post("/admin/login")
def admin_login(request: Request, password: str = Form(...)):
    token = hashlib.sha256((ADMIN_PASSWORD + "|" + ADMIN_SECRET).encode()).hexdigest()
    if password == ADMIN_PASSWORD:
        r = RedirectResponse(url="/admin", status_code=302)
        r.set_cookie("bb_admin", token)
        return r
    return templates.TemplateResponse("admin.html", {"request": request, "login": True, "error": "❌ كلمة المرور غير صحيحة"})

@app.get("/admin/logout")
def admin_logout():
    r = RedirectResponse(url="/admin?login=1", status_code=302)
    r.delete_cookie("bb_admin")
    return r
