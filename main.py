# main.py — Bassam Brain Plus v2 (ذكاء فوري مُحسّن + بحث نصي/صوري + لوحة إدارة)
import os, uuid, json, traceback, sqlite3, hashlib, io, csv, re, difflib, math
from datetime import datetime
from typing import Optional, List, Dict
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

# ---------- مسارات
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "bassam.db")

# ---------- تطبيق
app = FastAPI(title="Bassam Brain Plus")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ---------- مفاتيح
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/") if os.getenv("PUBLIC_BASE_URL") else ""
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "093589")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "bassam-secret")

# ---------- قاعدة بيانات (للوغز)
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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
        con.execute("INSERT INTO logs(ts,type,query,file_name,engine_used,ip,ua) VALUES(?,?,?,?,?,?,?)",
                    (datetime.utcnow().isoformat(timespec="seconds")+"Z",
                     event_type, query, file_name, engine_used, ip, ua))

# ---------- أدوات لغة عربية بسيطة
AR_STOP = set("""من في على إلى عن مع ما لا لم لن أن إن كان تكون هذا هذه تلك ذلك ثم لكن أو أم بل إذ إذا قد لقد سوف هناك هنا هو هي هم هن أنت انا نحن كما لدى لدى، الذي التي الذين اللواتي اللاتي حيث بين دون عبر ضد حتى كل أكثر جدا جدًا شيء أشياء خلال بعد قبل فوق تحت عند نحو بسبب بدون كيف لماذا متى أي""".split())
SYN = {
    "فوائد": ["منافع", "مميزات"],
    "اضرار": ["مخاطر", "عيوب"],
    "دواء": ["علاج", "عقاقير"],
    "سعر": ["ثمن", "تكلفة", "كم"],
    "نوم": ["النوم", "النعاس"],
}

def normalize(text: str) -> str:
    text = text.strip()
    # إزالة التشكيل وبعض الرموز
    text = re.sub(r"[\u0617-\u061A\u064B-\u0652]", "", text)
    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text

def expand_query(q: str) -> str:
    q = normalize(q)
    toks = q.split()
    # ترشيح كلمات الوقف
    toks = [t for t in toks if t not in AR_STOP]
    # مرادفات بسيطة
    extra = []
    for t in toks:
        extra += SYN.get(t, [])
    # تصحيح تقريبي لكلمة واحدة (إن كان السؤال قصير)
    if len(toks) <= 3:
        with DDGS() as ddgs:
            try:
                suggestions = [s["phrase"] for s in (ddgs.suggestions(q) or []) if "phrase" in s]
            except Exception:
                suggestions = []
        if suggestions:
            best = difflib.get_close_matches(q, suggestions, n=1, cutoff=0.6)
            if best:
                q = best[0]
    if extra:
        q = q + " " + " ".join(extra[:5])
    return q

# ---------- بحث الويب
async def search_google_serper(q: str, num: int = 8) -> List[Dict]:
    if not SERPER_API_KEY:
        raise RuntimeError("No SERPER_API_KEY configured")
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

def search_duckduckgo(q: str, num: int = 8) -> List[Dict]:
    out = []
    with DDGS() as ddgs:
        for r in ddgs.text(q, region="xa-ar", safesearch="moderate", max_results=num):
            out.append({"title": r.get("title"),
                        "link": r.get("href") or r.get("url"),
                        "snippet": r.get("body"), "source": "DuckDuckGo"})
            if len(out) >= num:
                break
    return out

async def smart_search(q: str, prefer_google=True, num: int = 8) -> Dict:
    qx = expand_query(q)
    try:
        used = None
        if prefer_google and SERPER_API_KEY:
            try:
                results = await search_google_serper(qx, num)
                used = "Google"
            except Exception:
                results = search_duckduckgo(qx, num)
                used = "DuckDuckGo"
        else:
            results = search_duckduckgo(qx, num)
            used = "DuckDuckGo"
        return {"ok": True, "used": used, "results": results, "expanded": qx}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": str(e), "used": None, "results": [], "expanded": qx}

# ---------- جلب النصوص واستخراج جمل
async def fetch_text(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code >= 400:
                return ""
        soup = BeautifulSoup(r.text, "html.parser")
        # إزالة سكربت وستايل
        for t in soup(["script", "style", "noscript"]):
            t.decompose()
        paras = [p.get_text(" ", strip=True) for p in soup.find_all(["p", "li"]) if p.get_text(strip=True)]
        text = " ".join(paras)
        text = normalize(text)
        return text[:12000]
    except Exception:
        return ""

def score_sentence(sent: str, q_terms: List[str], freq: Dict[str, int]) -> float:
    if not sent or len(sent.split()) < 5:
        return 0.0
    words = [w for w in sent.split() if w not in AR_STOP]
    if not words:
        return 0.0
    # تغطية كلمات السؤال + تردد الكلمات
    cover = sum(1 for w in words if w in q_terms)
    tf = sum(freq.get(w, 0) for w in words) / (len(words) + 1)
    return cover * 1.5 + tf

def build_summary(all_texts: List[str], query: str, max_sentences: int = 12) -> str:
    big = " ".join(all_texts)
    # تقسيم جمل عربي/إنجليزي
    sents = re.split(r"(?<=[\.!\?؟])\s+", big)
    # تكرار كلمات
    words = [w for w in normalize(big).split() if w not in AR_STOP]
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    q_terms = [w for w in normalize(query).split() if w not in AR_STOP]
    scored = [(score_sentence(s, q_terms, freq), s) for s in sents]
    scored.sort(reverse=True, key=lambda x: x[0])
    pick = [s for _, s in scored[:max_sentences]]
    # ترتيب كما تظهر في النص الأصلي
    summary = "\n".join(pick)
    return summary

def paginate(text: str, page_chars: int = 800) -> List[str]:
    text = text.strip()
    if len(text) <= page_chars:
        return [text]
    pages, cur = [], []
    count = 0
    for sent in re.split(r"(?<=[\.!\?؟])\s+", text):
        if count + len(sent) > page_chars and cur:
            pages.append(" ".join(cur))
            cur, count = [], 0
        cur.append(sent)
        count += len(sent)
    if cur:
        pages.append(" ".join(cur))
    return pages[:6]  # حد أقصى 6 صفحات للعرض

# ---------- صفحات عامة
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/healthz")
def health():
    return {"ok": True}

# ---------- بحث نصي + ملخص مُحسّن
@app.post("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Form(...), page: int = Form(0)):
    q = (q or "").strip()
    if not q:
        return templates.TemplateResponse("index.html", {"request": request, "error": "اكتب سؤالك أولًا."})

    ip = request.client.host if request.client else "?"
    ua = request.headers.get("user-agent", "?")

    meta = await smart_search(q, prefer_google=True, num=8)
    results = meta.get("results", [])
    used = meta.get("used")
    expanded = meta.get("expanded", q)

    # اجلب نصوص أفضل 4 نتائج
    texts = []
    for r in results[:4]:
        txt = await fetch_text(r["link"])
        if txt:
            texts.append(txt)

    summary = build_summary(texts if texts else [ " ".join([r.get("snippet","") for r in results]) ], q, max_sentences=14)
    pages = paginate(summary, page_chars=900)
    page = max(0, min(page, len(pages)-1))

    log_event("search", ip, ua, query=q, engine_used=used)

    ctx = {
        "request": request,
        "query": q,
        "expanded": expanded,
        "engine_used": used,
        "results": results,
        "summary_pages": pages,
        "summary_total": len(pages),
        "summary_page": page,
    }
    return templates.TemplateResponse("index.html", ctx)

# ---------- سؤال متابعة
@app.post("/follow", response_class=HTMLResponse)
async def follow(request: Request, base_q: str = Form(...), follow_q: str = Form(...), page: int = Form(0)):
    combo = f"{base_q} — تفاصيل عن: {follow_q}"
    return await search(request, q=combo, page=page)

# ---------- رفع صورة + روابط بحث بصري
@app.post("/upload", response_class=HTMLResponse)
async def upload_image(request: Request, file: UploadFile = File(...)):
    try:
        if not file or not file.filename:
            return templates.TemplateResponse("index.html", {"request": request, "error": "لم يتم اختيار صورة."})
        ext = (file.filename.split(".")[-1] or "jpg").lower()
        if ext not in ["jpg","jpeg","png","webp","gif"]:
            ext = "jpg"
        filename = f"{uuid.uuid4().hex}.{ext}"
        with open(os.path.join(UPLOADS_DIR, filename), "wb") as f:
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
            "message": "✅ تم رفع الصورة، اختر طريقة البحث:",
        })
    except Exception as e:
        traceback.print_exc()
        return templates.TemplateResponse("index.html", {"request": request, "error": f"فشل رفع الصورة: {e}"})

# ---------- Service Worker من الجذر
@app.get("/sw.js")
def sw_js():
    return FileResponse(os.path.join(STATIC_DIR, "pwa", "sw.js"), media_type="application/javascript")

# ---------- لوحة الإدارة
@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, login: Optional[int] = None):
    token = hashlib.sha256((ADMIN_PASSWORD + "|" + ADMIN_SECRET).encode()).hexdigest()
    if request.cookies.get("bb_admin") != token:
        return templates.TemplateResponse("admin.html", {"request": request, "login": True, "error": None})
    with db() as con:
        rows = con.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 300").fetchall()
    return templates.TemplateResponse("admin.html", {"request": request, "rows": rows})

@app.post("/admin/login")
def admin_login(request: Request, password: str = Form(...)):
    token = hashlib.sha256((ADMIN_PASSWORD + "|" + ADMIN_SECRET).encode()).hexdigest()
    if password == ADMIN_PASSWORD:
        r = RedirectResponse(url="/admin", status_code=302)
        r.set_cookie("bb_admin", token, httponly=True, samesite="lax")
        return r
    return templates.TemplateResponse("admin.html", {"request": request, "login": True, "error": "❌ كلمة المرور غير صحيحة"})

@app.get("/admin/logout")
def admin_logout():
    r = RedirectResponse(url="/admin?login=1", status_code=302)
    r.delete_cookie("bb_admin")
    return r

@app.get("/admin/export.csv")
def admin_export(request: Request):
    token = hashlib.sha256((ADMIN_PASSWORD + "|" + ADMIN_SECRET).encode()).hexdigest()
    if request.cookies.get("bb_admin") != token:
        return RedirectResponse(url="/admin?login=1", status_code=302)
    with db() as con:
        cur = con.execute("SELECT id,ts,type,query,file_name,engine_used,ip,ua FROM logs ORDER BY id DESC")
        output = io.StringIO()
        w = csv.writer(output)
        w.writerow(["id","ts","type","query","file_name","engine_used","ip","user_agent"])
        for row in cur:
            w.writerow([row["id"],row["ts"],row["type"],row["query"] or "",row["file_name"] or "",
                        row["engine_used"] or "",row["ip"] or "",row["ua"] or ""])
        output.seek(0)
    return StreamingResponse(iter([output.read()]), media_type="text/csv",
                             headers={"Content-Disposition":"attachment; filename=bassam-logs.csv"})
