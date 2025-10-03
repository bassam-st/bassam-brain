# app.py — Bassam Brain (محرك أسئلة/أجوبة محلي مع أدوات الفهم الذكي)
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
import pathlib, re, json, time
from typing import List
from rapidfuzz import fuzz
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

app = FastAPI(title="Bassam Brain – Local QA")

# ================= ملفات وذاكرة =================
DATA_DIR   = pathlib.Path("data");         DATA_DIR.mkdir(exist_ok=True)
NOTES_DIR  = DATA_DIR / "notes";           NOTES_DIR.mkdir(exist_ok=True)
LOG_FILE   = DATA_DIR / "log.jsonl"
FEED_FILE  = DATA_DIR / "feedback_pool.jsonl"
KB_FILE    = NOTES_DIR / "knowledge.txt"

if not KB_FILE.exists():
    KB_FILE.write_text("سؤال: ما فوائد القراءة؟\nجواب: القراءة توسّع المدارك وتقوّي الخيال وتزيد الثقافة.\n---\n", encoding="utf-8")

# ================ أدوات الفهم الذكي ================
AR_DIAC  = re.compile(r'[\u064B-\u0652]')
TOKEN_RE = re.compile(r'[A-Za-z\u0621-\u064A0-9]+')

def normalize_ar(s: str) -> str:
    """تطبيع خفيف للحروف العربية لتقليل أخطاء الكتابة"""
    s = s or ""
    s = AR_DIAC.sub('', s)
    s = s.replace('أ','ا').replace('إ','ا').replace('آ','ا')
    s = s.replace('ة','ه').replace('ى','ي').replace('ؤ','و').replace('ئ','ي')
    s = s.replace('گ','ك').replace('پ','ب').replace('ڤ','ف').replace('ظ','ض')
    s = re.sub(r'\s+',' ', s).strip()
    return s

def ar_tokens(s: str) -> List[str]:
    return TOKEN_RE.findall(normalize_ar(s))

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

def load_qa() -> List[dict]:
    text = KB_FILE.read_text(encoding='utf-8') if KB_FILE.exists() else ""
    blocks = [b.strip() for b in text.split('---') if b.strip()]
    qa = []
    for b in blocks:
        m1 = re.search(r'سؤال\s*:\s*(.+)', b)
        m2 = re.search(r'جواب\s*:\s*(.+)', b)
        if m1 and m2:
            qa.append({"q": m1.group(1).strip(), "a": m2.group(1).strip()})
    return qa

QA_CACHE = load_qa()

def build_indexes(qa_list: List[dict]):
    if not qa_list:
        return None, [], None, None
    docs_tokens = [ar_tokens(x["q"] + " " + x["a"]) for x in qa_list]
    bm25 = BM25Okapi(docs_tokens)
    corpus_norm = [normalize_ar(x["q"]) for x in qa_list]
    tfidf = TfidfVectorizer(analyzer='char', ngram_range=(3,5), min_df=1)
    X = tfidf.fit_transform(corpus_norm)
    return bm25, docs_tokens, tfidf, X

BM25, BM25_DOCS, TFVEC, X_TFIDF = build_indexes(QA_CACHE)

def reload_kb():
    global QA_CACHE, BM25, BM25_DOCS, TFVEC, X_TFIDF
    QA_CACHE = load_qa()
    BM25, BM25_DOCS, TFVEC, X_TFIDF = build_indexes(QA_CACHE)

def combined_search(user_q: str, topk: int = 5):
    if not QA_CACHE:
        return None, 0.0
    q_expanded = expand_query(user_q)
    q_norm = normalize_ar(q_expanded)
    q_tok  = ar_tokens(q_norm)
    scores = {}
    if BM25:
        bm = BM25.get_scores(q_tok)
        for i, s in enumerate(bm):
            if s > 0:
                scores[i] = scores.get(i, 0.0) + s * 10.0
    for i, qa in enumerate(QA_CACHE):
        s = fuzz.token_set_ratio(q_norm, normalize_ar(qa["q"]))
        if s > 0:
            scores[i] = scores.get(i, 0.0) + float(s)
    if TFVEC is not None:
        q_vec = TFVEC.transform([q_norm])
        cos = X_TFIDF @ q_vec.T
        cos = np.asarray(cos.todense()).ravel()
        for i, s in enumerate(cos):
            if s > 0:
                scores[i] = scores.get(i, 0.0) + float(s) * 120.0
    if not scores:
        return None, 0.0
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:topk]
    best_idx, best_score = ranked[0]
    return QA_CACHE[best_idx], best_score

async def local_qa_answer(question: str) -> str:
    question = (question or "").strip()
    if not question:
        return "⚠️ لم أستلم سؤالًا."
    doc, score = combined_search(question, topk=5)
    if doc and score >= 140:
        return doc["a"]
    if doc and score >= 90:
        return f"{doc['a']}\n\n(ℹ️ أقرب سؤال مشابه: «{doc['q']}»)"
    if doc:
        return f"❓ لم أجد إجابة مؤكدة، لكن الأقرب هو:\n«{doc['q']}».\nالجواب: {doc['a']}\n\nيمكنك حفظ سؤالك لتحسين الذكاء لاحقًا."
    return "🤖 لا توجد معلومات كافية بعد لهذا السؤال."

# ================= الصفحات =================
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <div style="max-width:760px;margin:24px auto;font-family:system-ui">
      <h2>🧠 Bassam Brain — الفهم المحلي الذكي</h2>
      <form method="post" action="/ask">
        <textarea name="q" rows="4" style="width:100%" placeholder="اكتب سؤالك هنا..."></textarea>
        <button style="margin-top:8px;padding:8px 16px;background:#007bff;color:white;border:none;border-radius:6px">إرسال</button>
      </form>
    </div>
    """

@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request):
    form = await request.form()
    q = (form.get("q") or "").strip()
    ans = await local_qa_answer(q)
    rec = {"ts": int(time.time()), "q": q, "a": ans}
    with open(LOG_FILE, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return f"""
    <div style='max-width:720px;margin:24px auto;font-family:system-ui'>
      <p><b>سؤالك:</b> {q}</p>
      <p><b>الجواب:</b> {ans}</p>

      <form method='post' action='/save_to_knowledge'>
        <input type='hidden' name='q' value='{q}'>
        <input type='hidden' name='a' value='{ans}'>
        <button style='background:#28a745;color:white;padding:8px 16px;border:none;border-radius:6px'>✅ حفظ الجواب في قاعدة المعرفة</button>
      </form>

      <p style='margin-top:16px'><a href='/'>◀ رجوع</a></p>
    </div>
    """

@app.post("/save_to_knowledge", response_class=HTMLResponse)
async def save_to_knowledge(request: Request):
    form = await request.form()
    q = (form.get("q") or "").strip()
    a = (form.get("a") or "").strip()
    if not q or not a:
        return "<p>⚠️ يرجى كتابة سؤال وجواب أولاً.</p><p><a href='/'>◀ رجوع</a></p>"
    with open(KB_FILE, "a", encoding="utf-8") as f:
        f.write(f"\nسؤال: {q}\nجواب: {a}\n---\n")
    reload_kb()
    return "<p>✅ تم حفظ الجواب في قاعدة المعرفة بنجاح.</p><p><a href='/'>◀ رجوع</a></p>"

@app.get("/ready")
def ready(): return {"ok": True}
