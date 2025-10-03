# app.py — Bassam Brain (محرك أسئلة/أجوبة محلي مع أدوات الفهم الذكي)
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
import pathlib, re, json, time

app = FastAPI(title="Bassam Brain – Local QA")

# ================= ملفات وذاكرة =================
DATA_DIR   = pathlib.Path("data");         DATA_DIR.mkdir(exist_ok=True)
NOTES_DIR  = DATA_DIR / "notes";           NOTES_DIR.mkdir(exist_ok=True)
LOG_FILE   = DATA_DIR / "log.jsonl"
FEED_FILE  = DATA_DIR / "feedback_pool.jsonl"
KB_FILE    = NOTES_DIR / "knowledge.txt"
if not KB_FILE.exists():
    KB_FILE.write_text("سؤال: ما فوائد القراءة؟\nجواب: القراءة توسّع المدارك وتقوّي الخيال وتزيد الثقافة.\n---\n",
                       encoding="utf-8")

# ================ أدوات الفهم الذكي (محلي) ================
from typing import List
from rapidfuzz import fuzz
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

# --- تطبيع عربي خفيف + تسامح مع لبس الحروف
AR_DIAC  = re.compile(r'[\u064B-\u0652]')                # التشكيل
TOKEN_RE = re.compile(r'[A-Za-z\u0621-\u064A0-9]+')      # رموز كلمة

def normalize_ar(s: str) -> str:
    s = s or ""
    s = AR_DIAC.sub('', s)
    s = s.replace('أ','ا').replace('إ','ا').replace('آ','ا')
    s = s.replace('ة','ه').replace('ى','ي').replace('ؤ','و').replace('ئ','ي')
    s = s.replace('گ','ك').replace('پ','ب').replace('ڤ','ف')
    # تسامح الض/ظ
    s = s.replace('ظ','ض')
    s = re.sub(r'\s+',' ', s).strip()
    return s

def ar_tokens(s: str) -> List[str]:
    return TOKEN_RE.findall(normalize_ar(s))

# --- مرادفات بسيطة للتوسيع الدلالي
SYN_SETS = [
    {"مميزات","فوائد","ايجابيات","حسنات"},
    {"اضرار","سلبيات","عيوب"},
    {"تعريف","ماهو","ما هي","مفهوم"},
    {"انترنت","الشبكه","الويب","نت"},
    {"موبايل","جوال","هاتف"},
    {"حاسوب","كمبيوتر","حاسبه"},
    {"ذكاء اصطناعي","الذكاء الاصطناعي","AI"},
    {"برمجه","تكويد","كود","برمجة"},
    {"امن معلومات","امن سيبراني","حمايه","أمن"},
]

def expand_query(q: str) -> str:
    qn = normalize_ar(q)
    extra = []
    for syn in SYN_SETS:
        if any(w in qn for w in syn):
            extra.extend(list(syn))
    if extra:
        qn += " " + " ".join(extra)
    return qn

# --- تحميل Q/A من دفتر المعرفة
def load_qa() -> List[dict]:
    text = KB_FILE.read_text(encoding='utf-8') if KB_FILE.exists() else ""
    blocks = [b.strip() for b in text.split('---') if b.strip()]
    qa = []
    for b in blocks:
        m1 = re.search(r'سؤال\s*:\s*(.+)', b)
        m2 = re.search(r'جواب\s*:\s*(.+)', b)
        if m1 and m2:
            q = m1.group(1).strip()
            a = m2.group(1).strip()
            qa.append({"q": q, "a": a})
    return qa

QA_CACHE = load_qa()

# --- فهارس البحث: BM25 + TF-IDF (n-grams حرفية)
def build_indexes(qa_list: List[dict]):
    if not qa_list:
        return None, [], None, None
    docs_tokens = [ar_tokens(x["q"] + " " + x["a"]) for x in qa_list]
    bm25 = BM25Okapi(docs_tokens)

    corpus_norm = [normalize_ar(x["q"]) for x in qa_list]  # نُفهرس السؤال فقط
    tfidf = TfidfVectorizer(analyzer='char', ngram_range=(3,5), min_df=1)
    X = tfidf.fit_transform(corpus_norm)
    return bm25, docs_tokens, tfidf, X

BM25, BM25_DOCS, TFVEC, X_TFIDF = build_indexes(QA_CACHE)

def reload_kb():
    """إعادة تحميل قاعدة المعرفة وبناء الفهارس (استدعِها بعد تعديل knowledge.txt)."""
    global QA_CACHE, BM25, BM25_DOCS, TFVEC, X_TFIDF
    QA_CACHE = load_qa()
    BM25, BM25_DOCS, TFVEC, X_TFIDF = build_indexes(QA_CACHE)

# --- المطابقة المركبة (BM25 + غموض + TF-IDF)
def combined_search(user_q: str, topk: int = 5):
    if not QA_CACHE:
        return None, 0.0

    # 1) توسعة دلالية + تطبيع
    q_expanded = expand_query(user_q)
    q_norm = normalize_ar(q_expanded)
    q_tok  = ar_tokens(q_norm)

    scores = {}

    # (أ) BM25
    if BM25:
        bm = BM25.get_scores(q_tok)
        for i, s in enumerate(bm):
            if s > 0:
                scores[i] = scores.get(i, 0.0) + s * 10.0   # وزن BM25

    # (ب) غموض (RapidFuzz) على السؤال فقط
    for i, qa in enumerate(QA_CACHE):
        s = fuzz.token_set_ratio(q_norm, normalize_ar(qa["q"]))  # 0..100
        if s > 0:
            scores[i] = scores.get(i, 0.0) + float(s) * 1.0      # وزن الغموض

    # (ج) TF-IDF n-grams (حرفي) — ممتاز للأخطاء الإملائية
    if TFVEC is not None:
        q_vec = TFVEC.transform([q_norm])
        cos = X_TFIDF @ q_vec.T
        cos = np.asarray(cos.todense()).ravel()   # 0..1 غالبًا
        for i, s in enumerate(cos):
            if s > 0:
                scores[i] = scores.get(i, 0.0) + float(s) * 120.0  # وزن TF-IDF

    if not scores:
        return None, 0.0

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:topk]
    best_idx, best_score = ranked[0]
    return QA_CACHE[best_idx], best_score

# --- الإجابة المحلية الذكية
async def local_qa_answer(question: str) -> str:
    question = (question or "").strip()
    if not question:
        return "لم أستلم سؤالًا."

    doc, score = combined_search(question, topk=5)

    # عتبة عالية وواضحة
    if doc and score >= 140:
        return doc["a"]

    # عتبة متوسطة مع تلميح للسؤال الأقرب
    if doc and score >= 90:
        return f"{doc['a']}\n\n(ℹ️ أقرب سؤال مطابق لدي كان: «{doc['q']}»)".strip()

    # إن لم نبلغ العتبة: نقترح الأقرب
    if doc:
        return (
            f"لم أجد إجابة مؤكدة. أقرب سؤال عندي:\n"
            f"«{doc['q']}».\n"
            f"الجواب المخزن: {doc['a']}\n\n"
            f"يمكنك حفظ صياغتك الحالية عبر زر الحفظ لتحسين الفهم لاحقًا."
        )
    return "لا أملك معلومات كافية لهذا السؤال بعد. أضف س/ج مشابه إلى قاعدة المعرفة أو غيّر صياغة السؤال."

# ================= أدوات مساعدة بسيطة =================
def clamp(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n]

# ================= صفحات وتجربة =================
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <div style="max-width:760px;margin:24px auto;font-family:system-ui">
      <h1>🤖 Bassam Brain — النسخة المحلية</h1>
      <form method="post" action="/ask">
        <textarea name="q" rows="5" style="width:100%" placeholder="اكتب سؤالك هنا..."></textarea>
        <div style="margin-top:8px"><button>إرسال</button></div>
      </form>

      <details style="margin-top:18px">
        <summary>إدارة قاعدة المعرفة</summary>
        <form method="post" action="/save_to_knowledge" style="margin-top:10px">
          <input type="text" name="q" placeholder="سؤال" style="width:100%;padding:6px"><br>
          <textarea name="a" rows="3" placeholder="جواب" style="width:100%;margin-top:6px"></textarea><br>
          <button>✅ حفظ هذا الجواب في قاعدة المعرفة</button>
        </form>
        <form method="post" action="/reload_kb" style="margin-top:10px">
          <button>🔄 إعادة تحميل الفهارس بعد التعديل</button>
        </form>
        <p style="margin-top:6px"><a href="/export/feedback">⬇️ تنزيل مجموعة التدريب (feedback_pool.jsonl)</a></p>
      </details>
    </div>
    """

@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request):
    form = await request.form()
    q     = clamp(form.get("q",""), 1000)
    ans   = await local_qa_answer(q)

    # سجل التفاعل
    rec = {"ts": int(time.time()), "instruction": q, "input": "", "output": ans}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # صفحة النتيجة مع أزرار الحفظ
    return f"""
<div style='max-width:760px;margin:24px auto;font-family:system-ui'>
  <p><b>🧠 سؤالك:</b> {q}</p>
  <p><b>💬 الجواب:</b> {ans}</p>

  <form method='post' action='/save'>
    <input type='hidden' name='q' value='{q}'>
    <input type='hidden' name='a' value='{ans}'>
    <button style='background:#0d6efd;color:white;padding:8px 16px;border:none;border-radius:6px;cursor:pointer'>👍 حفظ في مجموعة التدريب</button>
  </form>

  <form method='post' action='/save_to_knowledge' style='margin-top:8px'>
    <input type='hidden' name='q' value='{q}'>
    <input type='hidden' name='a' value='{ans}'>
    <button style='background:#28a745;color:white;padding:8px 16px;border:none;border-radius:6px;cursor:pointer'>✅ حفظ هذا الجواب في قاعدة المعرفة</button>
  </form>

  <p style='margin-top:16px'><a href='/'>◀ رجوع</a></p>
</div>
"""

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

@app.post("/save_to_knowledge", response_class=HTMLResponse)
async def save_to_knowledge(request: Request):
    form = await request.form()
    q = (form.get("q","") or "").strip()
    a = (form.get("a","") or "").strip()

    if not q or not a:
        return "<p>⚠️ يرجى إدخال سؤال وجواب.</p><p><a href='/'>◀ رجوع</a></p>"

    entry = f"\nسؤال: {q}\nجواب: {a}\n---\n"
    try:
        with open(KB_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
        msg = "✅ تم الحفظ في قاعدة المعرفة بنجاح."
    except Exception as e:
        msg = f"⚠️ حدث خطأ أثناء الحفظ: {type(e).__name__}"

    return f"<p>{msg}</p><p><a href='/'>◀ رجوع</a></p>"

@app.post("/reload_kb")
def reload_kb_endpoint():
    reload_kb()
    return {"ok": True, "count": len(QA_CACHE)}

# ================ واجهات API خفيفة ================
@app.get("/ready")
def ready(): return {"ok": True}

@app.post("/answer")
async def answer(req: Request):
    body = await req.json()
    q = (body.get("question") or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="ضع حقل 'question'")
    text = await local_qa_answer(q)
    # سجل
    rec  = {"ts": int(time.time()), "instruction": q, "input": "", "output": text}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False)+"\n")
    return {"ok": True, "answer": text}

@app.get("/export/feedback")
def export_feedback():
    if not FEED_FILE.exists():
        FEED_FILE.write_text("", encoding="utf-8")
    return FileResponse(path=str(FEED_FILE), media_type="text/plain", filename="feedback_pool.jsonl")
