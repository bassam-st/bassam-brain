# app.py — Bassam Brain (نسخة تعليمية خفيفة مع ذاكرة وRAG)
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
import os, httpx, json, time, pathlib, re

app = FastAPI(title="Bassam Brain – Lite")

# ====== مسارات الملفات والذاكرة ======
DATA_DIR   = pathlib.Path("data"); DATA_DIR.mkdir(exist_ok=True)
NOTES_DIR  = DATA_DIR / "notes";   NOTES_DIR.mkdir(exist_ok=True)
LOG_FILE   = DATA_DIR / "log.jsonl"             # كل الأسئلة/الأجوبة
FEED_FILE  = DATA_DIR / "feedback_pool.jsonl"   # أمثلة ممتازة للتدريب لاحقًا
KB_FILE    = NOTES_DIR / "knowledge.txt"        # دفتر معرفة بسيط
if not KB_FILE.exists():
    KB_FILE.write_text("أضف هنا فقرات قصيرة من معلوماتك المهمة.\n", encoding="utf-8")

# ====== إعدادات واجهة نموذج خارجية (اختياري) ======
# يمكنك تغييرها من Environment Variables في Render
UPSTREAM_API_URL   = os.getenv("UPSTREAM_API_URL", "https://api.freegpt4.ai/v1/chat/completions")
UPSTREAM_API_KEY   = os.getenv("UPSTREAM_API_KEY", "")   # إن كان مطلوب
UPSTREAM_MODEL     = os.getenv("UPSTREAM_MODEL", "gpt-4o-mini")  # اسم الموديل حسب مزودك

# ====== أدوات مساعدة ======
def clamp(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n]

def pick_relevant(text: str, query: str, k: int = 6):
    """اختيار جُمل قريبة جدًا بالكلمات (RAG بسيط بدون مكتبات)."""
    sents = re.split(r"[\.!\?\n…]+", text)
    qtok = set(re.findall(r"\w+", query))
    scored = []
    for s in sents:
        t = s.strip()
        if not t: continue
        stok = set(re.findall(r"\w+", t))
        score = len(qtok & stok)
        if score: scored.append((score, t))
    scored.sort(reverse=True)
    return [t for _, t in scored[:k]]

def build_context(question: str, extra: str) -> str:
    kb = KB_FILE.read_text(encoding="utf-8")
    rel = pick_relevant(kb, question, k=6)
    ctx = ""
    if rel:
        ctx += "مقتطفات معرفة:\n- " + "\n- ".join(rel) + "\n\n"
    if extra:
        ctx += f"معلومات إضافية من المستخدم:\n{extra}\n\n"
    return ctx

async def call_model(prompt: str, temperature: float = 0.7, max_tokens: int = 180) -> str:
    """
    يستدعي أي واجهة متوافقة مع شكل OpenAI Chat Completions.
    إن فشل الطلب، يرجع ردًا بسيطًا بدل الانهيار.
    """
    headers = {"Content-Type": "application/json"}
    if UPSTREAM_API_KEY:
        headers["Authorization"] = f"Bearer {UPSTREAM_API_KEY}"

    payload = {
        "model": UPSTREAM_MODEL,
        "messages": [
            {"role": "system", "content": "أجب بالعربية بدقة واختصار. إن لم تكن واثقًا قل: لا أعلم."},
            {"role": "user", "content": prompt}
        ],
        "temperature": float(temperature),
        "max_tokens": int(max_tokens)
    }

    try:
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.post(UPSTREAM_API_URL, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            msg = (data.get("choices") or [{}])[0].get("message", {}).get("content")
            if not msg:
                raise ValueError("no content")
            return msg.strip()
    except Exception as e:
        # فallback مهذب بدل INTERNAL ERROR
        return f"عذرًا، تعذّر الاتصال بالموديل الخارجي الآن. سبب تقني: {type(e).__name__}. جرّب ثانية."

# ====== صفحات وتجارب ======
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <div style="max-width:720px;margin:24px auto;font-family:system-ui">
      <h1>🤖 Bassam Brain — النسخة التجريبية</h1>
      <form method="post" action="/ask">
        <textarea name="q" rows="5" style="width:100%" placeholder="اكتب سؤالك هنا..."></textarea>
        <details style="margin:8px 0">
          <summary>سياق إضافي (اختياري)</summary>
          <textarea name="extra" rows="4" style="width:100%" placeholder="ألصق نصًا أو نقاطًا تساعد الإجابة"></textarea>
        </details>
        <label>Temperature</label>
        <input type="number" step="0.1" name="temperature" value="0.7" style="width:90px">
        <label style="margin-inline-start:8px">Max tokens</label>
        <input type="number" name="max_new_tokens" value="180" style="width:100px">
        <div><button style="margin-top:10px">إرسال</button></div>
      </form>
    </div>
    """

@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request):
    form = await request.form()
    q     = clamp(form.get("q",""), 1000)
    extra = clamp(form.get("extra",""), 3000)
    temp  = float(form.get("temperature", 0.7))
    mx    = int(form.get("max_new_tokens", 180))

    ctx   = build_context(q, extra)
    prompt = f"""{ctx}السؤال: {q}
الجواب المختصر بدقة:"""
    ans = await call_model(prompt, temperature=temp, max_tokens=mx)

    # سجل في log.jsonl
    rec = {"ts": int(time.time()), "instruction": q, "input": extra, "output": ans}
    with open(LOG_FILE, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False)+"\n")

    return f"<div style='max-width:720px;margin:24px auto;font-family:system-ui'>" \
           f"<p><b>سؤالك:</b> {q}</p><p><b>الجواب:</b> {ans}</p>" \
           f"<form method='post' action='/save'><input type='hidden' name='q' value='{q}'>" \
           f"<input type='hidden' name='a' value='{ans}'><button>👍 حفظ في مجموعة التدريب</button></form>" \
           f"<p><a href='/'>◀ رجوع</a></p></div>"

@app.post("/save", response_class=HTMLResponse)
async def save(request: Request):
    form = await request.form()
    rec = {"ts": int(time.time()), "instruction": form.get("q",""), "input": "", "output": form.get("a","")}
    with open(FEED_FILE, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False)+"\n")
    return "<p>✅ تمت إضافة المثال إلى مجموعة التدريب.</p><p><a href='/'>◀ رجوع</a></p>"

# ====== واجهات API ======
@app.get("/ready")
def ready():
    return {"ok": True}

@app.post("/generate")
async def generate(request: Request):
    body = await request.json()
    q     = clamp(body.get("question",""), 1000)
    extra = clamp(body.get("extra",""), 3000)
    temp  = float(body.get("temperature", 0.7))
    mx    = int(body.get("max_new_tokens", 180))

    ctx = build_context(q, extra)
    prompt = f"""{ctx}السؤال: {q}
الجواب المختصر بدقة:"""
    ans = await call_model(prompt, temperature=temp, max_tokens=mx)

    # سجل
    rec = {"ts": int(time.time()), "instruction": q, "input": extra, "output": ans}
    with open(LOG_FILE, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False)+"\n")
    return JSONResponse({"ok": True, "answer": ans})

@app.post("/feedback")
async def feedback(request: Request):
    data = await request.json()
    if not bool(data.get("good", True)):
        return {"ok": True}
    rec = {
        "ts": int(time.time()),
        "instruction": data.get("q",""),
        "input": data.get("extra",""),
        "output": data.get("a","")
    }
    with open(FEED_FILE, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False)+"\n")
    return {"ok": True}

@app.get("/export/feedback")
def export_feedback():
    if not FEED_FILE.exists(): FEED_FILE.write_text("", encoding="utf-8")
    return FileResponse(path=str(FEED_FILE), media_type="text/plain", filename="feedback_pool.jsonl")
