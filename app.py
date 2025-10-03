# app.py — Bassam Brain (تحليل + استرجاع معرفة + توليد)
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
import os, httpx, json, time, pathlib, re, collections

app = FastAPI(title="Bassam Brain – Lite")

# ====== ملفات وذاكرة ======
DATA_DIR   = pathlib.Path("data"); DATA_DIR.mkdir(exist_ok=True)
NOTES_DIR  = DATA_DIR / "notes";   NOTES_DIR.mkdir(exist_ok=True)
LOG_FILE   = DATA_DIR / "log.jsonl"
FEED_FILE  = DATA_DIR / "feedback_pool.jsonl"
KB_FILE    = NOTES_DIR / "knowledge.txt"
if not KB_FILE.exists():
    KB_FILE.write_text("أضف هنا فقرات قصيرة من معلوماتك المهمة.\n", encoding="utf-8")

# ====== إعداد مزوّد LLM خارجي (اختياري) ======
UPSTREAM_API_URL = os.getenv("UPSTREAM_API_URL", "https://api.freegpt4.ai/v1/chat/completions")
UPSTREAM_API_KEY = os.getenv("UPSTREAM_API_KEY", "")
UPSTREAM_MODEL   = os.getenv("UPSTREAM_MODEL", "gpt-4o-mini")
USE_UPSTREAM     = os.getenv("USE_UPSTREAM", "1")  # ضع "0" لتعطيله

# ====== أدوات مساعدة عامة ======
def clamp(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n]

def pick_relevant(text: str, query: str, k: int = 6):
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
    if USE_UPSTREAM != "1":
        # وضع أوفلاين: يرد باختصار مهذّب بدل الانهيار
        return "وضع أوفلاين فعّال: رجاءً أضف معرفة أكثر أو فعّل USE_UPSTREAM=1."
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
        return f"عذرًا، تعذّر الاتصال بالموديل الخارجي الآن. سبب تقني: {type(e).__name__}. جرّب ثانية."

# ====== محلّل نصوص خفيف ======
AR_POS = {"جيد","ممتاز","رائع","جميل","سعيد","مبروك","نجاح","إيجابي","محب"}
AR_NEG = {"سيئ","سئ","حزين","فشل","سخط","كره","غضب","ضعيف","كارثي","مشكل","خطأ","سلبي"}
STOP_AR = set("من في على إلى عن أن إن كان كانت يكون يكونوا تكون تكونين ثم حيث فهو وهي و أو اذا إذا لذلك لكن ما هذا هذه هو هي هم هن نحن أنت انتم انتن كما كما".split())

def simple_tokens(text): return re.findall(r"[A-Za-z\u0621-\u064A0-9]+", text)
def is_question(text):   return text.strip().endswith(("؟","?")) or text.strip().startswith(("هل","كيف","متى","أين","ما","لماذا","كم"))

def sentiment(text):
    t = set(simple_tokens(text)); p = len(t & AR_POS); n = len(t & AR_NEG)
    if p-n > 1: return "إيجابي"
    if n-p > 1: return "سلبي"
    return "محايد"

TOPIC_KWS = {
    "تقنية":{"برمجة","كود","تطبيق","خادم","موبايل","ويب","ذكاء","اصطناعي","API","بايثون","جافا"},
    "تعليم":{"دراسة","جامعة","مدرسة","منهج","واجب","شرح","امتحان"},
    "صحة":{"طبيب","مرض","علاج","أعراض","تشخيص","صحي","تغذية"},
    "دين":{"الصلاة","الزكاة","الصيام","القرآن","حديث","دعاء","فقه"},
    "مال":{"سعر","دفع","فاتورة","ميزانية","استثمار","ربح","خسارة","رسوم"},
    "سفر":{"تأشيرة","رحلة","حجز","مطار","طيران","فندق"},
}
def guess_topic(text):
    t = set(simple_tokens(text))
    scores = {k: len(t & v) for k,v in TOPIC_KWS.items()}
    topic,score = max(scores.items(), key=lambda x:x[1])
    return topic if score>0 else "عام"

def keywords(text, topk=8):
    toks = [w for w in simple_tokens(text) if w not in STOP_AR and len(w)>2]
    freq = collections.Counter([w.lower() for w in toks])
    return [w for w,_ in freq.most_common(topk)]

def summarize(text, max_sent=2):
    sents = re.split(r"[\.!\?؟]\s*", text)
    if len(sents)<=max_sent: return text.strip()
    scores=[]; freq = collections.Counter([w.lower() for w in simple_tokens(text) if w not in STOP_AR])
    for s in sents:
        score = sum(freq[w.lower()] for w in simple_tokens(s)); scores.append((score, s))
    top = [s for _,s in sorted(scores, reverse=True)[:max_sent]]
    return "، ".join([s.strip() for s in top if s.strip()])

def extract_entities(text):
    ents = {}
    ents["emails"]   = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    ents["phones"]   = re.findall(r"\+?\d[\d\s\-]{6,}\d", text)
    ents["currency"] = re.findall(r"(?:\$|€|£|ريال|درهم|دينار|جنيه)\s*\d+(?:[\.,]\d+)?", text)
    ents["dates"]    = re.findall(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b", text)
    ents["names"]    = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", text)
    return ents

# ====== إجابة ذكية: تحليل + استرجاع + توليد ======
async def llm_answer(question: str, extra: str = "", temperature: float = 0.4, max_new_tokens: int = 220):
    question = (question or "").strip()
    if not question: return "لم أستلم سؤالًا."

    # تحليل سريع
    _info = {
        "is_question": is_question(question),
        "sentiment": sentiment(question),
        "topic": guess_topic(question),
        "keywords": keywords(question),
    }

    # سياق من دفتر المعرفة + extra
    ctx = build_context(question, extra)

    prompt = f"""{ctx}حلّل السؤال بإيجاز ذهنياً ثم أجب بدقة وبدون حشو.
- إن لم تكن واثقاً قل: لا أعلم.
- التزم بالمعلومات في (المقتطفات) إن وُجدت.
السؤال: {question}
الإجابة:"""

    ans = await call_model(prompt, temperature=temperature, max_tokens=max_new_tokens)
    if ans.startswith("عذرًا، تعذّر الاتصال") and ctx.strip():
        return summarize(ctx, max_sent=2)
    return ans.strip()

# ====== صفحات بسيطة للتجربة ======
@app.get("/", response_class=HTMLResponse)
def home():
    return f"""
<div style='max-width:720px;margin:24px auto;font-family:system-ui'>
  <p><b>🧠 سؤالك:</b> {q}</p>
  <p><b>💬 الجواب:</b> {ans}</p>

  <form method='post' action='/save'>
    <input type='hidden' name='q' value='{q}'>
    <input type='hidden' name='a' value='{ans}'>
    <button style='background:#007bff;color:white;padding:8px 16px;border:none;border-radius:6px;cursor:pointer'>👍 حفظ في مجموعة التدريب</button>
  </form>

  <form method='post' action='/save_to_knowledge' style='margin-top:8px'>
    <input type='hidden' name='q' value='{q}'>
    <input type='hidden' name='a' value='{ans}'>
    <button style='background:#28a745;color:white;padding:8px 16px;border:none;border-radius:6px;cursor:pointer'>✅ حفظ هذا الجواب في قاعدة المعرفة</button>
  </form>

  <p style='margin-top:16px'><a href='/'>◀ رجوع</a></p>
</div>
"""

@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request):
    form = await request.form()
    q     = clamp(form.get("q",""), 1000)
    extra = clamp(form.get("extra",""), 3000)
    temp  = float(form.get("temperature", 0.7))
    mx    = int(form.get("max_new_tokens", 180))
    ans   = await llm_answer(q, extra=extra, temperature=temp, max_new_tokens=mx)
    rec   = {"ts": int(time.time()), "instruction": q, "input": extra, "output": ans}
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
def ready(): return {"ok": True}

@app.post("/analyze")
async def analyze(req: Request):
    body = await req.json()
    text = (body.get("text") or "").strip()
    if not text: raise HTTPException(status_code=400, detail="ضع حقل text")
    out = {
        "is_question": is_question(text),
        "sentiment": sentiment(text),
        "topic": guess_topic(text),
        "keywords": keywords(text),
        "entities": extract_entities(text),
        "summary": summarize(text, max_sent=2)
    }
    return JSONResponse({"ok": True, "analysis": out})

@app.post("/answer")
async def answer(req: Request):
    body = await req.json()
    q     = clamp(body.get("question",""), 1000)
    extra = clamp(body.get("extra",""), 3000)
    temp  = float(body.get("temperature", 0.4))
    mx    = int(body.get("max_new_tokens", 220))
    if not q: raise HTTPException(status_code=400, detail="ضع حقل 'question'")
    text = await llm_answer(q, extra=extra, temperature=temp, max_new_tokens=mx)
    rec  = {"ts": int(time.time()), "instruction": q, "input": extra, "output": text}
    with open(LOG_FILE, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False)+"\n")
    return JSONResponse({"ok": True, "answer": text})

@app.post("/generate")
async def generate(req: Request):
    body = await req.json()
    q     = clamp(body.get("question",""), 1000)
    extra = clamp(body.get("extra",""), 3000)
    temp  = float(body.get("temperature", 0.7))
    mx    = int(body.get("max_new_tokens", 180))
    ctx   = build_context(q, extra)
    prompt = f"""{ctx}السؤال: {q}
الجواب المختصر بدقة:"""
    ans = await call_model(prompt, temperature=temp, max_tokens=mx)
    rec = {"ts": int(time.time()), "instruction": q, "input": extra, "output": ans}
    with open(LOG_FILE, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False)+"\n")
    return JSONResponse({"ok": True, "answer": ans})

@app.post("/feedback")
async def feedback(req: Request):
    data = await req.json()
    if not bool(data.get("good", True)): return {"ok": True}
    rec = {"ts": int(time.time()), "instruction": data.get("q",""), "input": data.get("extra",""), "output": data.get("a","")}
    with open(FEED_FILE, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False)+"\n")
    return {"ok": True}

@app.get("/export/feedback")
def export_feedback():
    if not FEED_FILE.exists(): FEED_FILE.write_text("", encoding="utf-8")
    return FileResponse(path=str(FEED_FILE), media_type="text/plain", filename="feedback_pool.jsonl")
