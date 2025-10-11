# main.py — Bassam Brain (إصدار GPT-5 mini + واجهة /api/ask)
import os, uuid, json, traceback, sqlite3, hashlib, io, csv, re
from datetime import datetime
from typing import Optional, List, Dict

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import httpx
from duckduckgo_search import DDGS

# OpenAI
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

# ----------------------------- مفاتيح
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/") if os.getenv("PUBLIC_BASE_URL") else ""
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "093589")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "bassam-secret")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5-mini").strip()

if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)
else:
    client = None

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
                type TEXT NOT NULL,      -- search | image | ask
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
            (datetime.utcnow().isoformat(timespec="seconds")+"Z", event_type, query, file_name, engine_used, ip, ua)
        )

# ============================== ذكاء التلخيص الخفيف (داخل الصندوق)
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
                seen.add(key)
                cleaned.append(p)
        if len(cleaned) >= max_items:
            break
    return cleaned

# ============================== دوال البحث (Google أولاً ثم DuckDuckGo احتياط فقط)
async def search_google_serper(q: str, num: int = 6) -> List[Dict]:
    if not SERPER_API_KEY:
        raise RuntimeError("No SERPER_API_KEY configured")
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {"q": q, "num": num, "hl": "ar"}
    async with httpx.AsyncClient(timeout=25) as client_httpx:
        r = await client_httpx.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    out = []
    for it in (data.get("organic", []) or [])[:num]:
        out.append({
            "title": it.get("title"),
            "link": it.get("link"),
            "snippet": it.get("snippet"),
            "source": "Google",
        })
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

async def smart_search(q: str, num: int = 6) -> Dict:
    q = (q or "").strip()
    try:
        used, results = None, []
        if SERPER_API_KEY:
            try:
                results = await search_google_serper(q, num)
                used = "Google"
            except Exception:
                results = search_duckduckgo(q, num)
                used = "DuckDuckGo"
        else:
            results = search_duckduckgo(q, num)
            used = "DuckDuckGo"

        bullets = make_bullets([r.get("snippet") for r in results], max_items=8)
        return {"ok": True, "used": used, "bullets": bullets, "results": results}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "used": None, "results": [], "error": str(e)}

# ============================== صفحات HTML
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/healthz")
def health():
    return {"ok": True}

# ============================== بحث نصي (سيرفر-سايد؛ كـ fallback لو أُغلق JS)
@app.post("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Form(...)):
    q = (q or "").strip()
    if not q:
        return templates.TemplateResponse("index.html", {"request": request, "error": "📝 الرجاء كتابة سؤالك أولًا."})

    result = await smart_search(q, num=8)
    ip = request.client.host if request.client else "?"
    ua = request.headers.get("user-agent", "?")
    log_event("search", ip, ua, query=q, engine_used=result.get("used"))

    ctx = {
        "request": request,
        "query": q,
        "engine_used": result.get("used"),
        "results": result.get("results", []),
        "bullets": result.get("bullets", []),
    }
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

        ip = request.client.host if request.client else "?"
        ua = request.headers.get("user-agent", "?")
        log_event("image", ip, ua, file_name=filename)

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "uploaded_image": filename,
                "google_lens": google_lens,
                "bing_visual": bing_visual,
                "message": "تم رفع الصورة بنجاح ✅، اختر طريقة البحث 👇",
            },
        )
    except Exception as e:
        traceback.print_exc()
        return templates.TemplateResponse("index.html", {"request": request, "error": f"فشل رفع الصورة: {e}"})

# ============================== API: ردّ الذكاء باستخدام GPT
@app.post("/api/ask")
async def api_ask(request: Request):
    """
    يستقبل JSON: {"q": "سؤال"}
    يعيد: { ok, answer, bullets, sources, engine_used }
    """
    try:
        data = await request.json()
        q = (data.get("q") or "").strip()
        if not q:
            return JSONResponse({"ok": False, "error": "no_query"}, status_code=400)

        # بحث سريع لتجميع سياق + مصادر
        search = await smart_search(q, num=6)
        sources = search.get("results", [])
        context_lines = []
        for i, r in enumerate(sources, start=1):
            title = (r.get("title") or "").strip()
            link = (r.get("link") or "").strip()
            snippet = (r.get("snippet") or "").strip()
            context_lines.append(f"{i}. {title}\n{snippet}\n{link}")

        # إذا لا يوجد مفتاح OpenAI نرجع ملخّص البحث فقط
        if not client:
            return JSONResponse({
                "ok": True,
                "engine_used": search.get("used"),
                "answer": "⚠️ لم يتم إعداد مفتاح OpenAI، لذا أعرض لك ملخّصًا من النتائج فقط.",
                "bullets": search.get("bullets", []),
                "sources": sources
            })

        # رسالة إلى النموذج (بالعربية + مختصر + مراجع)
        system_msg = (
            "أنت مساعد عربي خبير. أجب بإيجاز ووضوح وبنقاط مركزة عند الحاجة. "
            "اعتمد على المعلومات التالية من نتائج البحث كمراجع خارجية. "
            "إن لم تكن واثقًا قل لا أعلم."
        )
        user_msg = (
            f"السؤال:\n{q}\n\n"
            "نتائج البحث (للاستئناس والاستشهاد):\n" +
            "\n\n".join(context_lines[:6])
        )

        # استدعاء Chat Completions (مدعوم على gpt-5-mini)
        resp = client.chat.completions.create(
            model=LLM_MODEL or "gpt-5-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=600,
        )
        answer = (resp.choices[0].message.content or "").strip()
        bullets = make_bullets([answer], max_items=8)

        # سجل العملية
        ip = request.client.host if request.client else "?"
        ua = request.headers.get("user-agent", "?")
        log_event("ask", ip, ua, query=q, engine_used=f"OpenAI:{LLM_MODEL}")

        return JSONResponse({
            "ok": True,
            "engine_used": f"OpenAI:{LLM_MODEL}",
            "answer": answer,
            "bullets": bullets,
            "sources": sources
        })
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# ============================== Service Worker على الجذر
@app.get("/sw.js")
def sw_js():
    path = os.path.join(STATIC_DIR, "pwa", "sw.js")
    return FileResponse(path, media_type="application/javascript")

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
