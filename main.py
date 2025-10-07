# main.py — Bassam Brain (ملخّص مختصر + دمج نتائج + بحث صور مُعزَّز + لوحة إدارة)
import os, uuid, sqlite3, hashlib, traceback, re
from datetime import datetime
from typing import Optional, List, Dict

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import httpx
from duckduckgo_search import DDGS

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR    = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
UPLOADS_DIR   = os.path.join(BASE_DIR, "uploads")
DATA_DIR      = os.path.join(BASE_DIR, "data")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "bassam.db")

app = FastAPI(title="Bassam Brain")
app.mount("/static",  StaticFiles(directory=STATIC_DIR),  name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

SERPER_API_KEY  = os.getenv("SERPER_API_KEY", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/") if os.getenv("PUBLIC_BASE_URL") else ""
ADMIN_PASSWORD  = os.getenv("ADMIN_PASSWORD", "093589")
ADMIN_SECRET    = os.getenv("ADMIN_SECRET",   "bassam-secret")

def db():
    c = sqlite3.connect(DB_PATH); c.row_factory = sqlite3.Row; return c
with db() as con:
    con.execute("""CREATE TABLE IF NOT EXISTS logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, type TEXT, query TEXT, file_name TEXT,
        engine_used TEXT, ip TEXT, ua TEXT
    )""")

def log_event(t, ip, ua, query=None, file_name=None, engine=None):
    with db() as con:
        con.execute("INSERT INTO logs(ts,type,query,file_name,engine_used,ip,ua) VALUES (?,?,?,?,?,?,?)",
                    (datetime.utcnow().isoformat(timespec="seconds")+"Z", t, query, file_name, engine, ip, ua))

# ------------ helpers ------------
def _clean(q: str) -> str:
    q = (q or "").strip()
    q = re.sub(r"[^\w\s\u0600-\u06FF]", " ", q)
    q = re.sub(r"\s+", " ", q)
    return q

def _sentences(text: str) -> List[str]:
    parts = re.split(r"[.!؟\n]+", text or "")
    parts = [p.strip() for p in parts if len(p.strip()) > 3]
    seen, out = set(), []
    for s in parts:
        k = s[:70]
        if k in seen: continue
        seen.add(k); out.append(s)
    return out

def make_bullet_summary(snippets: List[str], max_points=6, max_chars=600) -> str:
    all_text = " ".join(snippets)[:3000]
    sents = _sentences(all_text)
    picked, size = [], 0
    for s in sents:
        if size + len(s) > max_chars: break
        picked.append(f"• {s}"); size += len(s)
        if len(picked) >= max_points: break
    return "\n".join(picked) if picked else "لم أجد محتوى كافيًا. الروابط أدناه 👇"

# ------------ search ------------
async def search_google_serper(q: str, num=8) -> List[Dict]:
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
                    "snippet": it.get("snippet") or "", "source": "Google"})
    return out

def search_duckduckgo(q: str, num=8) -> List[Dict]:
    out = []
    with DDGS() as ddgs:
        for r in ddgs.text(q, region="xa-ar", safesearch="moderate", max_results=num):
            out.append({"title": r.get("title"),
                        "link": r.get("href") or r.get("url"),
                        "snippet": r.get("body") or "", "source": "DuckDuckGo"})
            if len(out) >= num: break
    return out

def dedupe(results: List[Dict]) -> List[Dict]:
    seen, out = set(), []
    for r in results:
        key = (r.get("title","")[:80] + r.get("link","")).lower()
        if key in seen: continue
        seen.add(key); out.append(r)
    return out

async def smart_search(q: str) -> Dict:
    q = _clean(q)
    try:
        results, used = [], None
        # نجمع من المحركين ونزيل التكرار
        if SERPER_API_KEY:
            try:
                g = await search_google_serper(q); used = "Google"
            except Exception:
                g = []
            d = search_duckduckgo(q)
            results = dedupe(g + d)[:10]
            used = "Google+DuckDuckGo" if g else "DuckDuckGo"
        else:
            results = search_duckduckgo(q); used = "DuckDuckGo"
        summary = make_bullet_summary([r["snippet"] for r in results], 6, 600)
        return {"ok": True, "used": used, "summary": summary, "results": results}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": str(e), "used": None, "results": [], "summary": ""}

# ------------ pages ------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/healthz")
def health(): return {"ok": True}

@app.post("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Form(...)):
    if not (q or "").strip():
        return templates.TemplateResponse("index.html", {"request": request, "error": "اكتب سؤالك أولاً."})
    ip = request.client.host if request.client else "?"
    ua = request.headers.get("user-agent", "?")
    out = await smart_search(q)
    log_event("search", ip, ua, query=q, engine=out.get("used"))
    ctx = {"request": request, "query": q, "summary": out.get("summary"),
           "engine_used": out.get("used"), "results": out.get("results")}
    if not out.get("ok"): ctx["error"] = f"حدث خطأ في البحث: {out.get('error')}"
    return templates.TemplateResponse("index.html", ctx)

@app.post("/upload", response_class=HTMLResponse)
async def upload_image(request: Request, file: UploadFile = File(...)):
    try:
        if not file or not file.filename:
            return templates.TemplateResponse("index.html", {"request": request, "error": "لم يتم اختيار صورة."})
        ext = (file.filename.split(".")[-1] or "jpg").lower()
        if ext not in ["jpg","jpeg","png","webp","gif"]: ext = "jpg"
        filename = f"{uuid.uuid4().hex}.{ext}"
        path = os.path.join(UPLOADS_DIR, filename)
        with open(path, "wb") as f: f.write(await file.read())

        public_base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
        img = f"{public_base}/uploads/{filename}"
        links = {
            "google_lens":   f"https://lens.google.com/uploadbyurl?url={img}",
            "bing_visual":   f"https://www.bing.com/visualsearch?imgurl={img}",
            "yandex_images": f"https://yandex.com/images/search?rpt=imageview&url={img}",
            "tineye":        f"https://tineye.com/search?url={img}",
        }

        ip = request.client.host if request.client else "?"
        ua = request.headers.get("user-agent", "?")
        log_event("image", ip, ua, file_name=filename)

        return templates.TemplateResponse("index.html", {"request": request, "uploaded_image": filename, **links,
                                                         "message": "تم رفع الصورة بنجاح ✅، اختر طريقة البحث 👇"})
    except Exception as e:
        traceback.print_exc()
        return templates.TemplateResponse("index.html", {"request": request, "error": f"فشل رفع الصورة: {e}"})

@app.get("/sw.js")
def sw_js():
    return FileResponse(os.path.join(STATIC_DIR, "pwa", "sw.js"), media_type="application/javascript")

def _admin_token() -> str:
    return hashlib.sha256((ADMIN_PASSWORD + "|" + ADMIN_SECRET).encode()).hexdigest()

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
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
    r = RedirectResponse(url="/admin?login=1", status_code=302); r.delete_cookie("bb_admin"); return r
