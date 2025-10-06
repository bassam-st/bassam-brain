# main.py — Bassam Brain Plus (ذكاء فوري + بحث نصي/صوري + PWA + لوحة إدارة + سجلات)
import os, uuid, traceback, sqlite3, hashlib, io, csv, difflib, re
from datetime import datetime
from typing import Optional, List, Dict

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import httpx
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

# ====== التطبيق ======
app = FastAPI(title="Bassam Brain Plus")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ====== المتغيرات ======
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL") or "").rstrip("/")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "093589")
ADMIN_SECRET   = os.getenv("ADMIN_SECRET",   "bassam-secret")

# ====== قاعدة البيانات ======
def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS logs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT, type TEXT, query TEXT, file_name TEXT,
                engine_used TEXT, ip TEXT, ua TEXT
            );
        """)
init_db()

def log_event(event_type, ip, ua, query=None, file_name=None, engine_used=None):
    with db() as con:
        con.execute(
            "INSERT INTO logs(ts,type,query,file_name,engine_used,ip,ua) VALUES(?,?,?,?,?,?,?)",
            (datetime.utcnow().isoformat(timespec="seconds")+"Z", event_type, query, file_name, engine_used, ip, ua)
        )

# ====== ذكاء فوري خفيف (بدون موديل خارجي) ======
def _clean(text: str) -> str:
    text = (text or "").strip()
    return re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)

def _summarize(snippets: List[str], max_parts: int = 3) -> str:
    packed = " ".join([s or "" for s in snippets])[:2000]
    parts = [p.strip() for p in re.split(r"[.!؟\n]", packed) if len(p.split()) > 4]
    seen, uniq = set(), []
    for p in parts:
        if p not in seen:
            uniq.append(p); seen.add(p)
        if len(uniq) >= max_parts:
            break
    return ("، ".join(uniq) + "...") if uniq else ""

# ====== دوال البحث ======
async def search_google_serper(q: str, num: int = 6) -> List[Dict]:
    if not SERPER_API_KEY:
        raise RuntimeError("SERPER_API_KEY missing")
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {"q": q, "num": num, "hl": "ar"}
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.post(url, headers=headers, json=payload)
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
            out.append({
                "title": r.get("title"),
                "link": r.get("href") or r.get("url"),
                "snippet": r.get("body"),
                "source": "DuckDuckGo",
            })
            if len(out) >= num:
                break
    return out

async def smart_search(q: str) -> Dict:
    q = _clean(q)
    try:
        used = "DuckDuckGo"
        results: List[Dict] = []
        if SERPER_API_KEY:
            try:
                results = await search_google_serper(q)
                used = "Google"
            except Exception:
                results = search_duckduckgo(q)
                used = "DuckDuckGo"
        else:
            results = search_duckduckgo(q)
            used = "DuckDuckGo"

        summary = _summarize([r.get("snippet", "") for r in results])
        if not summary:
            summary = "لم أجد خلاصة كافية من المصادر، هذه أفضل النتائج الموثوقة 👇"
        return {"ok": True, "used": used, "summary": summary, "results": results}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": str(e), "used": None, "results": []}

# ====== صفحات عامة ======
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/healthz")
def health():
    return {"ok": True}

# ====== بحث نصي ======
@app.post("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Form(...)):
    q = (q or "").strip()
    if not q:
        return templates.TemplateResponse("index.html", {"request": request, "error": "📝 اكتب سؤالك أولًا."})

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
        ctx["error"] = f"⚠️ حدث خطأ: {result.get('error')}"
    return templates.TemplateResponse("index.html", ctx)

# ====== رفع صورة + إنشاء روابط عدسات ======
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
        image_url   = f"{public_base}/uploads/{filename}"
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
            "message": "✅ تم رفع الصورة، اختر طريقة البحث 👇",
        })
    except Exception as e:
        traceback.print_exc()
        return templates.TemplateResponse("index.html", {"request": request, "error": f"فشل رفع الصورة: {e}"})

# ====== Service Worker من الجذر ======
@app.get("/sw.js")
def sw_js():
    return FileResponse(os.path.join(STATIC_DIR, "pwa", "sw.js"),
                        media_type="application/javascript")

# ====== لوحة الإدارة ======
def _admin_token() -> str:
    return hashlib.sha256((ADMIN_PASSWORD + "|" + ADMIN_SECRET).encode()).hexdigest()

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, login: Optional[int] = None):
    if request.cookies.get("bb_admin") != _admin_token():
        return templates.TemplateResponse("admin.html", {"request": request, "login": True, "error": None})
    with db() as con:
        rows = con.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 200").fetchall()
    return templates.TemplateResponse("admin.html", {"request": request, "rows": rows})

@app.post("/admin/login")
def admin_login(request: Request, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        r = RedirectResponse(url="/admin", status_code=302)
        r.set_cookie("bb_admin", _admin_token(), httponly=True, samesite="lax")
        return r
    return templates.TemplateResponse("admin.html", {"request": request, "login": True, "error": "❌ كلمة المرور غير صحيحة"})

@app.get("/admin/logout")
def admin_logout():
    r = RedirectResponse(url="/admin?login=1", status_code=302)
    r.delete_cookie("bb_admin")
    return r

@app.get("/admin/export.csv")
def admin_export(request: Request):
    if request.cookies.get("bb_admin") != _admin_token():
        return RedirectResponse(url="/admin?login=1", status_code=302)
    with db() as con:
        cur = con.execute("SELECT id,ts,type,query,file_name,engine_used,ip,ua FROM logs ORDER BY id DESC")
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id","ts","type","query","file_name","engine_used","ip","ua"])
        for r in cur:
            w.writerow([r["id"],r["ts"],r["type"],r["query"] or "",r["file_name"] or "",r["engine_used"] or "",r["ip"] or "",r["ua"] or ""])
        buf.seek(0)
    return StreamingResponse(iter([buf.read()]), media_type="text/csv",
                             headers={"Content-Disposition":"attachment; filename=bassam-logs.csv"})
