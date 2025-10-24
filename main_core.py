# main_core.py — Bassam Core (NLU + DM + Tools) 🇸🇦
# يعمل مع متطلباتك الحالية (fastapi, duckduckgo-search, httpx, requests, apscheduler, sqlite3...)

import os, re, math, json, time, sqlite3
from typing import Dict, Any, Optional
from datetime import datetime
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from duckduckgo_search import DDGS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

DB_PATH = os.path.join(BASE_DIR, "data", "bassam_mem.db")
os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS facts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            role TEXT NOT NULL,
            text TEXT NOT NULL
        )""")
init_db()

# ---------- Utils ----------
AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
def norm_ar(text: str) -> str:
    # تلميع بسيط للنص العربي
    t = text.strip()
    t = re.sub(r"\s+", " ", t)
    t = t.translate(AR_DIGITS)
    return t

LANG_WORDS = {
    "ar": ["عربي","العربية","AR","Arabic"],
    "en": ["انجليزي","الإنجليزية","انجليزية","EN","English"],
    "fr": ["فرنسي","الفرنسية","FR","French"],
    "tr": ["تركي","التركية","TR","Turkish"],
}

def detect_target_lang(text: str) -> str:
    for code, keys in LANG_WORDS.items():
        for k in keys:
            if k.lower() in text.lower():
                return code
    return "ar"

# ---------- NLU (Intents) ----------
INTENTS = {
    "remember": [r"^تذكر", r"^احفظ", r"^سجل"],
    "recall": [r"^ما الذي.*تذكر", r"^اعرض.*المحفوظ", r"^اذكر لي"],
    "translate": [r"ترجم", r"ترجمة", r"الى العربية", r"to arabic", r"translate"],
    "calc": [r"احسب", r"كم يساوي", r"حاسبة", r"calculate"],
    "define": [r"ما معنى", r"اشرح", r"تعريف"],
    "search": [r"ابحث", r"ما هو", r"من هو", r"اخبار", r"متى", r"اين"],
    "chitchat": [r"السلام", r"مرحبا", r"شلونك", r"كيف الحال", r"شكرا", r"وداعا"]
}

def classify_intent(q: str) -> str:
    qn = norm_ar(q).lower()
    for intent, patterns in INTENTS.items():
        for pat in patterns:
            if re.search(pat, qn):
                return intent
    # heuristics
    if re.search(r"https?://", qn):
        return "search"
    if re.search(r"[+\-*/^%()=]", qn):
        return "calc"
    return "search"

def extract_url(q: str) -> Optional[str]:
    m = re.search(r"(https?://\S+)", q)
    return m.group(1) if m else None

# ---------- Tools ----------
async def tool_search_web(q: str, max_results: int = 3) -> str:
    out = []
    with DDGS() as ddgs:
        for r in ddgs.text(q, region="xa-ar", safesearch="moderate", max_results=max_results):
            out.append(f"• {r.get('title','')} — {r.get('href','')}\n{r.get('body','')}")
    return "\n\n".join(out) if out else "لم أجد نتيجة مناسبة."

async def tool_translate(text: str, target: str = "ar") -> str:
    url = "https://libretranslate.de/translate"
    payload = {"q": text, "source": "auto", "target": target}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=payload, headers={"Content-Type":"application/json"})
            data = r.json()
            return data.get("translatedText", "تعذر إتمام الترجمة الآن.")
    except Exception:
        return "تعذر الاتصال بخدمة الترجمة."

SAFE_MATH = re.compile(r"^[0-9\.\+\-\*/\^\%\(\)\s]+$")
def tool_calc(expr: str) -> str:
    expr = expr.replace("^", "**")
    expr = norm_ar(expr)
    if not SAFE_MATH.match(expr):
        return "لأسباب أمان لا أستطيع حساب هذه الصيغة."
    try:
        val = eval(expr, {"__builtins__":{}}, {"math":math})
        return f"النتيجة: {val}"
    except Exception:
        return "صيغة غير صالحة للحساب."

def save_fact(key: str, value: str):
    with db() as con:
        con.execute("INSERT INTO facts(key,value,created_at) VALUES (?,?,?)",
                    (key.strip(), value.strip(), datetime.utcnow().isoformat()))
def load_facts() -> Dict[str,str]:
    with db() as con:
        rows = con.execute("SELECT key,value FROM facts ORDER BY id DESC LIMIT 50").fetchall()
    return {r["key"]: r["value"] for r in rows}

def log_msg(role:str, text:str):
    with db() as con:
        con.execute("INSERT INTO logs(ts,role,text) VALUES (?,?,?)",
                    (datetime.utcnow().isoformat(), role, text))

# ---------- Dialogue Manager ----------
async def handle_user(q: str) -> str:
    q = norm_ar(q)
    log_msg("user", q)

    intent = classify_intent(q)

    if intent == "chitchat":
        resp = "هلا بك! كيف أقدر أساعدك اليوم؟"
    elif intent == "remember":
        # مثال: "تذكر اسمي بسام" → يحفظ (اسمي -> بسام)
        m = re.search(r"تذكر\s+(.+?)\s+(.*)$", q)
        if m:
            save_fact(m.group(1), m.group(2))
            resp = f"تم الحفظ ✅ ({m.group(1)} ← {m.group(2)})"
        else:
            resp = "قل: تذكر <المفتاح> <القيمة>."
    elif intent == "recall":
        facts = load_facts()
        if not facts:
            resp = "لا توجد حقائق محفوظة بعد."
        else:
            items = [f"• {k}: {v}" for k,v in facts.items()]
            resp = "أحدث ما أتذكره:\n" + "\n".join(items)
    elif intent == "translate":
        # لو فيه اقتباس/نص نترجمه، وإلا نعتبر كامل السؤال نصًا
        target = detect_target_lang(q)  # غالبًا سترجع "ar"
        text = q
        m = re.search(r"«(.+?)»|\"(.+?)\"|‚(.+?)‘|‚(.+?)’", q)
        if m:
            text = next(g for g in m.groups() if g)
        resp = await tool_translate(text, target=target)
    elif intent == "calc":
        expr = re.sub(r"^(احسب|كم يساوي)\s*", "", q, flags=re.I)
        if expr.strip()=="":
            expr = q
        resp = tool_calc(expr)
    elif intent in ("define","search"):
        url = extract_url(q)
        query = q if not url else f"site:{url} "
        resp = await tool_search_web(query, max_results=3)
    else:
        # fallback بحث
        resp = await tool_search_web(q, max_results=3)

    log_msg("assistant", resp)
    return resp

# ---------- FastAPI ----------
app = FastAPI(title="Bassam Brain — Core")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

INDEX_HTML = """
<!doctype html><html lang="ar" dir="rtl"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>بسّام الذكي</title>
<link rel="stylesheet" href="/static/style.css"/>
<style>
body{background:#0b0f19;color:#e5e7eb;font-family:system-ui;-apple-system,Segoe UI,Roboto}
.wrap{max-width:860px;margin:28px auto}
.card{background:#111827;border:1px solid #1f2937;border-radius:14px;padding:16px 18px;margin:16px 0}
input{width:100%;padding:12px 14px;border-radius:12px;border:none;background:#0f172a;color:#e5e7eb}
button{padding:12px 16px;border-radius:12px;border:none;background:#6d28d9;color:#fff;cursor:pointer}
.resp{white-space:pre-wrap;line-height:1.7}
.small{opacity:.8;font-size:13px}
</style></head><body>
<div class="wrap">
  <h1>🤖 بسّام الذكي — النواة</h1>
  <div class="card">
    <form id="f">
      <input id="q" placeholder="اكتب سؤالاً بالعربية… مثل: ترجم «Good morning» للعربية / احسب 7*8 / تذكر اسمي بسّام"/>
      <div style="margin-top:10px;display:flex;gap:10px">
        <button type="submit">أرسل</button>
        <button type="button" id="recall">ما الذي تتذكره؟</button>
      </div>
    </form>
  </div>
  <div class="card resp" id="out"></div>
  <div class="small">تجريبي: فهم نوايا + أدوات (بحث، ترجمة، حاسبة، ذاكرة).</div>
</div>
<script>
const f = document.getElementById('f');
const q = document.getElementById('q');
const out = document.getElementById('out');
const recallBtn = document.getElementById('recall');

async function ask(text){
  out.textContent = "… جاري التفكير";
  const r = await fetch('/ask', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({q:text})});
  const j = await r.json();
  out.textContent = j.reply || j.error || 'حدث خطأ.';
}

f.addEventListener('submit', (e)=>{e.preventDefault(); ask(q.value); q.value='';});
recallBtn.addEventListener('click', ()=> ask('اعرض ما الذي تذكرته'));
</script>
</body></html>
"""

@app.get("/", response_class=HTMLResponse)
async def root(_: Request):
    return HTMLResponse(INDEX_HTML)

@app.post("/ask")
async def ask(req: Dict[str, Any]):
    q = req.get("q","").strip()
    if not q:
        return JSONResponse({"error":"الرجاء كتابة سؤال."}, status_code=400)
    reply = await handle_user(q)
    return {"reply": reply}
