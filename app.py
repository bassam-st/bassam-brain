# app.py — Bassam Brain (نسخة كاملة مع حفظ في قاعدة المعرفة)
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
import os, httpx, json, time, pathlib, re, collections

# ====== إعداد التطبيق ======
app = FastAPI(title="Bassam Brain – النسخة الكاملة")

# ====== المجلدات والملفات ======
DATA_DIR   = pathlib.Path("data"); DATA_DIR.mkdir(exist_ok=True)
NOTES_DIR  = DATA_DIR / "notes";   NOTES_DIR.mkdir(exist_ok=True)
LOG_FILE   = DATA_DIR / "log.jsonl"
FEED_FILE  = DATA_DIR / "feedback_pool.jsonl"
KB_FILE    = NOTES_DIR / "knowledge.txt"

if not KB_FILE.exists():
    KB_FILE.write_text("أضف هنا معلوماتك وقواعدك الأساسية.\n", encoding="utf-8")

# ====== إعداد نموذج اللغة الخارجي (اختياري) ======
UPSTREAM_API_URL   = os.getenv("UPSTREAM_API_URL", "https://api.freegpt4.ai/v1/chat/completions")
UPSTREAM_API_KEY   = os.getenv("UPSTREAM_API_KEY", "")
UPSTREAM_MODEL     = os.getenv("UPSTREAM_MODEL", "gpt-4o-mini")

# ====== محلل النصوص ======
AR_POS = {"جيد","ممتاز","رائع","جميل","سعيد","مبروك","نجاح","إيجابي","محب"}
AR_NEG = {"سيئ","سئ","حزين","فشل","سخط","كره","غضب","ضعيف","كارثي","مشكل","خطأ","سلبي"}
STOP_AR = set("من في على إلى عن أن إن كان كانت يكون يكونوا تكون تكونين ثم حيث فهو وهي و أو اذا إذا لذلك لكن ما هذا هذه هو هي هم هن نحن أنت انتم انتن كما كما".split())

def simple_tokens(text):
    return re.findall(r"[A-Za-z\u0621-\u064A0-9]+", text)

def is_question(text):
    return text.strip().endswith(("؟","?")) or text.strip().startswith(("هل","كيف","متى","أين","ما","لماذا","كم"))

def sentiment(text):
    t = set(simple_tokens(text))
    p = len(t & AR_POS); n = len(t & AR_NEG)
    if p-n > 1: return "إيجابي"
    if n-p > 1: return "سلبي"
    return "محايد"

TOPIC_KWS = {
    "تقنية": {"برمجة","كود","تطبيق","ذكاء","اصطناعي","شبكة","ويب","حاسوب","برامج"},
    "تعليم": {"دراسة","جامعة","مدرسة","امتحان","منهج","شرح"},
    "دين": {"قرآن","حديث","صلاة","صوم","زكاة","دعاء"},
    "صحة": {"طبيب","مرض","علاج","صحي","تغذية"},
    "مال": {"سعر","دفع","استثمار","ربح","خسارة","فاتورة"},
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
    freq = collections.Counter([w.lower() for w in simple_tokens(text) if w not in STOP_AR])
    scores=[]
    for s in sents:
        score = sum(freq[w.lower()] for w in simple_tokens(s))
        scores.append((score,s))
    top = [s for _,s in sorted(scores,reverse=True)[:max_sent]]
    return "، ".join([s.strip() for s in top if s.strip()])

# ====== أدوات ======
def clamp(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s)<=n else s[:n]

def pick_relevant(text: str, query: str, k: int = 6):
    sents = re.split(r"[\.!\?\n…]+", text)
    qtok = set(re.findall(r"\w+", query))
    scored=[]
    for s in sents:
        t=s.strip()
        if not t: continue
        stok=set(re.findall(r"\w+",t))
        score=len(qtok & stok)
        if score: scored.append((score,t))
    scored.sort(reverse=True)
    return [t for _,t in scored[:k]]

def build_context(question: str, extra: str) -> str:
    kb = KB_FILE.read_text(encoding="utf-8")
    rel = pick_relevant(kb, question, k=6)
    ctx = ""
    if rel:
        ctx += "مقتطفات معرفة:\n- " + "\n- ".join(rel) + "\n\n"
    if extra:
        ctx += f"معلومات إضافية من المستخدم:\n{extra}\n\n"
    return ctx

# ====== الاتصال بالموديل ======
async def call_model(prompt: str, temperature: float = 0.7, max_tokens: int = 180) -> str:
    headers = {"Content-Type": "application/json"}
    if UPSTREAM_API_KEY:
        headers["Authorization"]=f"Bearer {UPSTREAM_API_KEY}"
    payload={
        "model":UPSTREAM_MODEL,
        "messages":[
            {"role":"system","content":"أجب بالعربية بإيجاز ووضوح. لا تخترع معلومات."},
            {"role":"user","content":prompt}
        ],
        "temperature":temperature,
        "max_tokens":max_tokens
    }
    try:
        async with httpx.AsyncClient(timeout=40) as client:
            r=await client.post(UPSTREAM_API_URL,headers=headers,json=payload)
            r.raise_for_status()
            data=r.json()
            msg=(data.get("choices") or [{}])[0].get("message",{}).get("content","")
            return msg.strip() if msg else "لم أستطع توليد إجابة."
    except Exception as e:
        return f"⚠️ خطأ في الاتصال: {type(e).__name__}"

# ====== الصفحة الرئيسية ======
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <div style="max-width:720px;margin:24px auto;font-family:system-ui">
      <h1>🤖 Bassam Brain — النموذج العربي الذكي</h1>
      <form method="post" action="/ask">
        <textarea name="q" rows="5" style="width:100%" placeholder="اكتب سؤالك هنا..."></textarea>
        <details style="margin:8px 0">
          <summary>📎 سياق إضافي (اختياري)</summary>
          <textarea name="extra" rows="4" style="width:100%" placeholder="ألصق معلومات إضافية هنا..."></textarea>
        </details>
        <label>درجة الإبداع:</label>
        <input type="number" step="0.1" name="temperature" value="0.7" style="width:90px">
        <label style="margin-inline-start:8px">الحد الأقصى للكلمات:</label>
        <input type="number" name="max_new_tokens" value="180" style="width:100px">
        <div><button style="margin-top:10px">🚀 إرسال</button></div>
      </form>
    </div>
    """

# ====== توليد الإجابة ======
@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request):
    form = await request.form()
    q = clamp(form.get("q",""), 1000)
    extra = clamp(form.get("extra",""), 3000)
    temp = float(form.get("temperature", 0.7))
    mx = int(form.get("max_new_tokens", 180))

    ctx = build_context(q, extra)
    prompt = f"""{ctx}السؤال: {q}\nالجواب:"""
    ans = await call_model(prompt, temperature=temp, max_tokens=mx)

    rec = {"ts": int(time.time()), "instruction": q, "input": extra, "output": ans}
    with open(LOG_FILE,"a",encoding="utf-8") as f:
        f.write(json.dumps(rec,ensure_ascii=False)+"\n")

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

# ====== حفظ في مجموعة التدريب ======
@app.post("/save", response_class=HTMLResponse)
async def save(request: Request):
    form = await request.form()
    rec = {
        "ts": int(time.time()),
        "instruction": form.get("q",""),
        "input": "",
        "output": form.get("a","")
    }
    with open(FEED_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False)+"\n")
    return "<p>✅ تمت إضافة المثال إلى مجموعة التدريب.</p><p><a href='/'>◀ رجوع</a></p>"

# ====== حفظ في قاعدة المعرفة ======
@app.post("/save_to_knowledge", response_class=HTMLResponse)
async def save_to_knowledge(request: Request):
    form = await request.form()
    q = form.get("q", "").strip()
    a = form.get("a", "").strip()
    entry = f"\nسؤال: {q}\nجواب: {a}\n---\n"
    try:
        with open(KB_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
        msg = "✅ تم الحفظ في قاعدة المعرفة بنجاح."
    except Exception as e:
        msg = f"⚠️ حدث خطأ أثناء الحفظ: {type(e).__name__}"
    return f"<p>{msg}</p><p><a href='/'>◀ رجوع</a></p>"
