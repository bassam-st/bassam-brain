# main.py — Bassam AI: بحث نصي + بحث بالصور + PWA + لوحة إدارة
import os, uuid, json, traceback, sqlite3, hashlib, csv, io
from datetime import datetime
from typing import Optional, List, Dict

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import httpx
from duckduckgo_search import DDGS

# مسارات
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "bassam.db")

# تطبيق
app = FastAPI(title="Bassam Brain")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# مفاتيح/إعدادات من البيئة
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/") if os.getenv("PUBLIC_BASE_URL") else ""
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "bassam-admin")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "change-this-secret")

# ========= قاعدة البيانات =========
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
                type TEXT NOT NULL,      -- search | image
                query TEXT,
                file_name TEXT,
                engine_used TEXT,
                ip TEXT,
                ua TEXT
            );
        """)
init_db()

def log_event(event_type: str, request: Request, query: Optional[str]=None,
              file_name: Optional[str]=None, engine_used: Optional[str]=None):
    ip = request.client.host if request.client else "?"
    ua = request.headers.get("user-agent", "?")
    with db() as con:
        con.execute(
            "INSERT INTO logs (ts, type, query, file_name, engine_used, ip, ua) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(timespec="seconds")+"Z", event_type, query, file_name, engine_used, ip, ua)
        )

# ========= أدوات الإدارة =========
def make_token(password: str) -> str:
    return hashlib.sha256((password + "|" + ADMIN_SECRET).encode("utf-8")).hexdigest()

ADMIN_TOKEN = make_token(ADMIN_PASSWORD)

def is_admin(request: Request) -> bool:
    return request.cookies.get("bb_admin") == ADMIN_TOKEN

# ========= دوال البحث =========
async def search_google_serper(q: str, num: int = 8) -> List[Dict]:
    if not SERPER_API_KEY:
        raise RuntimeError("No SERPER_API_KEY configured")
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
                "source": "DuckDuckGo",
            })
            if len(out) >= num:
                break
    return out

async def smart_search(q: str, prefer_google: bool = True, num: int = 8) -> Dict:
    try:
        if prefer_google and SERPER_API_KEY:
            try:
                return {"ok": True, "used": "Google", "results": await search_google_serper(q, num)}
            except Exception:
                return {"ok": True, "used": "DuckDuckGo", "results": search_duckduckgo(q, num)}
        else:
            return {"ok": True, "used": "DuckDuckGo", "results": search_duckduckgo(q, num)}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "used": None, "results": [], "error": str(e)}

# ========= صفحات عامة =========
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/healthz")
def health():
    return {"ok": True}

# ========= بحث نصي =========
@app.post("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Form(...), include_prices: Optional[bool] = Form(False)):
    q = (q or "").strip()
    if not q:
        return templates.TemplateResponse("index.html", {"request": request, "error": "الرجاء كتابة سؤالك أولًا."})

    result = await smart_search(q, prefer_google=True, num=8)
    log_event("search", request, query=q, engine_used=result.get("used"))

    ctx = {
        "request": request,
        "query": q,
        "engine_used": result.get("used"),
        "results": result.get("results", []),
        "include_prices": bool(include_prices),
    }
    if not result.get("ok"):
        ctx["error"] = f"حدث خطأ في البحث: {result.get('error')}"
    return templates.TemplateResponse("index.html", ctx)

# ========= رفع صورة + روابط عدسات =========
@app.post("/upload", response_class=HTMLResponse)
async def upload_image(request: Request, file: UploadFile = File(...)):
    try:
        if not file or not file.filename:
            return templates.TemplateResponse("index.html", {"request": request, "error": "لم يتم اختيار صورة."})

        ext = (file.filename.split(".")[-1] or "jpg").lower()
        if ext not in ["jpg", "jpeg", "png", "webp", "gif"]:
            ext = "jpg"
        filename = f"{uuid.uuid4().hex}.{ext}"
        save_path = os.path.join(UPLOADS_DIR, filename)
        with open(save_path, "wb") as f:
            f.write(await file.read())

        public_base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
        image_url = f"{public_base}/uploads/{filename}"

        google_lens = f"https://lens.google.com/uploadbyurl?url={image_url}"
        bing_visual = f"https://www.bing.com/visualsearch?imgurl={image_url}"

        log_event("image", request, file_name=filename)

        return templates.TemplateResponse("index.html", {
            "request": request,
            "uploaded_image": filename,
            "google_lens": google_lens,
            "bing_visual": bing_visual,
            "message": "تم رفع الصورة بنجاح ✅، اختر طريقة البحث 👇",
        })
    except Exception as e:
        traceback.print_exc()
        return templates.TemplateResponse("index.html", {"request": request, "error": f"فشل رفع الصورة: {e}"})

# ========= Service Worker على الجذر =========
@app.get("/sw.js")
def sw_js():
    path = os.path.join(STATIC_DIR, "pwa", "sw.js")
    return FileResponse(path, media_type="application/javascript")

# ========= لوحة الإدارة =========
@app.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request, login: Optional[int] = None):
    if not is_admin(request):
        return templates.TemplateResponse("admin.html", {"request": request, "page": "login", "error": None, "login": login})
    with db() as con:
        rows = con.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 500").fetchall()
    return templates.TemplateResponse("admin.html", {"request": request, "page": "dashboard", "rows": rows, "count": len(rows)})

@app.post("/admin/login")
def admin_login(request: Request, password: str = Form(...)):
    if make_token(password) == ADMIN_TOKEN:
        resp = RedirectResponse(url="/admin", status_code=302)
        resp.set_cookie("bb_admin", ADMIN_TOKEN, httponly=True, samesite="lax")
        return resp
    return templates.TemplateResponse("admin.html", {"request": request, "page": "login", "error": "❌ كلمة المرور غير صحيحة"})

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
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["id","ts","type","query","file_name","engine_used","ip","user_agent"])
        for r in cur:
            w.writerow([r["id"], r["ts"], r["type"], r["query"] or "", r["file_name"] or "", r["engine_used"] or "", r["ip"] or "", r["ua"] or ""])
        out.seek(0)
    return StreamingResponse(iter([out.read()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=bassam-logs.csv"})
