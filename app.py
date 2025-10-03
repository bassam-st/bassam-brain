# app.py — Bassam Brain (محلي + قاموس تصحيح + فهم ذكي)
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
import pathlib, re, json, time
from typing import List, Dict, Set, Tuple

app = FastAPI(title="Bassam Brain – Local QA (Smart)")

# ========= مسارات البيانات =========
DATA_DIR   = pathlib.Path("data");         DATA_DIR.mkdir(exist_ok=True)
NOTES_DIR  = DATA_DIR / "notes";           NOTES_DIR.mkdir(exist_ok=True)
DICT_DIR   = DATA_DIR / "dict";            DICT_DIR.mkdir(exist_ok=True)

LOG_FILE   = DATA_DIR / "log.jsonl"
FEED_FILE  = DATA_DIR / "feedback_pool.jsonl"
KB_FILE    = NOTES_DIR / "knowledge.txt"
TYPOS_FILE = DICT_DIR / "typos.tsv"
SYN_FILE   = DICT_DIR / "synonyms.txt"

# ملف معرفة افتراضي
if not KB_FILE.exists():
    KB_FILE.write_text("سؤال: ما فوائد القراءة؟\nجواب: القراءة توسّع المدارك وتقوّي الخيال وتزيد الثقافة.\n---\n", encoding="utf-8")

# ملفات القاموس الافتراضية
if not TYPOS_FILE.exists():
    TYPOS_FILE.write_text(
        "# wrong<TAB>right  (سطر يبدأ بـ# يُهمل)\n"
        "زكاء\tذكاء\n"
        "الزكاء\tالذكاء\n"
        "تعيف\tتعريف\n"
        "برمجه\tبرمجة\n"
        "انتر نت\tانترنت\n"
        "النت\tانترنت\n"
        "فايده\tفائدة\n"
        "فويد\tفوائد\n"
        "القراءه\tالقراءة\n"
        "الزمنيه\tالزمنية\n"
        "الاضطناعي\tالاصطناعي\n"
        , encoding="utf-8"
    )

if not SYN_FILE.exists():
    SYN_FILE.write_text(
        "# اكتب كل مجموعة مرادفات في سطر مفصولة بفواصل\n"
        "فوائد,مميزات,إيجابيات,حسنات\n"
        "أضرار,سلبيات,عيوب\n"
        "تعريف,ماهو,ما هي,مفهوم\n"
        "انترنت,شبكة,الويب,نت\n"
        "موبايل,جوال,هاتف\n"
        "حاسوب,كمبيوتر,حاسبة\n"
        "ذكاء اصطناعي,الذكاء الاصطناعي,AI\n"
        "برمجة,تكويد,كود\n"
        "أمن معلومات,أمن سيبراني,حماية\n"
        , encoding="utf-8"
    )

# ========= أدوات NLP محلية =========
from rapidfuzz import fuzz, process
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

# --- تطبيع عربي خفيف
AR_DIAC  = re.compile(r'[\u064B-\u0652]')                # التشكيل
TOKEN_RE = re.compile(r'[A-Za-z\u0621-\u064A0-9]+')

def normalize_ar(s: str) -> str:
    s = s or ""
    s = AR_DIAC.sub('', s)
    s = s.replace('أ','ا').replace('إ','ا').replace('آ','ا')
    s = s.replace('ة','ه').replace('ى','ي').replace('ؤ','و').replace('ئ','ي')
    s = s.replace('گ','ك').replace('پ','ب').replace('ڤ','ف')
    s = s.replace('ظ','ض')  # نتسامح الض/ظ
    s = re.sub(r'\s+',' ', s).strip()
    return s

def ar_tokens(s: str) -> List[str]:
    return TOKEN_RE.findall(normalize_ar(s))

# --- تحميل قاعدة المعرفة (س/ج)
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

QA_CACHE: List[dict] = load_qa()

# --- فهارس البحث (BM25 + TF-IDF)
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

# --- قاموس: مرادفات + تصحيحات + خريطة لبس حروف
SYN_SETS: List[Set[str]] = []
TYPOS_MAP: Dict[str,str] = {}

# لبس الحروف (نستخدمه لتوليد مرشحين حرفيًا ثم نتحقق من وجودهم في المفردات)
CONFUSION_MAP: Dict[str, List[str]] = {
    'س':['ص'], 'ص':['س'],
    'ز':['ذ'], 'ذ':['ز'],
    'ت':['ث'], 'ث':['ت'],
    'د':['ذ'], 'ط':['ت'],
    'ق':['غ'], 'غ':['ق'],
    'ح':['خ','ج'], 'ج':['ح','خ'], 'خ':['ح','ج'],
    'ض':['ظ'],  # الظ طُبّعت إلى ض، نسمح بالعكس عند التوليد
}

def load_synonyms():
    global SYN_SETS
    SYN_SETS = []
    if SYN_FILE.exists():
        for line in SYN_FILE.read_text(encoding='utf-8').splitlines():
            line=line.strip()
            if not line or line.startswith('#'): continue
            words = [normalize_ar(w) for w in line.split(',') if w.strip()]
            if len(words)>=2:
                SYN_SETS.append(set(words))
    # fallback بسيط لو الملف فاضي
    if not SYN_SETS:
        SYN_SETS = [
            {"فوائد","مميزات","ايجابيات","حسنات"},
            {"اضرار","سلبيات","عيوب"},
            {"تعريف","ماهو","ما هي","مفهوم"},
        ]

def load_typos():
    global TYPOS_MAP
    TYPOS_MAP = {}
    if TYPOS_FILE.exists():
        for line in TYPOS_FILE.read_text(encoding='utf-8').splitlines():
            line=line.strip()
            if not line or line.startswith('#'): continue
            if '\t' not in line: continue
            wrong,right = line.split('\t',1)
            wrong = normalize_ar(wrong)
            right = normalize_ar(right)
            if wrong and right:
                TYPOS_MAP[wrong]=right

load_synonyms(); load_typos()

# --- مفردات من قاعدة المعرفة (للمصحّح)
VOCAB: Set[str] = set()
def build_vocab():
    global VOCAB
    VOCAB = set()
    for qa in QA_CACHE:
        for w in ar_tokens(qa["q"] + " " + qa["a"]):
            if len(w) > 2:
                VOCAB.add(w.lower())
    # نضيف مرادفات أيضاً للفائدة
    for syn in SYN_SETS:
        for w in syn:
            if len(w)>2: VOCAB.add(w.lower())

build_vocab()

def expand_query(q: str) -> str:
    qn = normalize_ar(q)
    extra = []
    for syn in SYN_SETS:
        if any(w in qn for w in syn):
            extra.extend(list(syn))
    if extra:
        qn += " " + " ".join(extra)
    return qn

def generate_confusion_candidates(token: str) -> List[str]:
    """توليد مرشحين بتبديل حرف واحد وفق خريطة اللبس ثم نتحقق هل المرشح موجود في المفردات."""
    cands=set()
    chars=list(token)
    for i,ch in enumerate(chars):
        if ch in CONFUSION_MAP:
            for alt in CONFUSION_MAP[ch]:
                trial = chars.copy()
                trial[i]=alt
                cands.add("".join(trial))
    return [c for c in cands if c in VOCAB]

def correct_spelling_ar(text: str) -> str:
    """تصحيح: (1) من القاموس الصريح، (2) مرشحو اللبس، (3) أقرب مفردة بالفَزّي."""
    toks = TOKEN_RE.findall(normalize_ar(text))
    out=[]
    for w in toks:
        lw=w.lower()
        if len(lw)<=2 or lw in VOCAB:
            out.append(lw); continue
        # 1) قاموس صريح
        if lw in TYPOS_MAP:
            out.append(TYPOS_MAP[lw]); continue
        # 2) مرشحو اللبس
        vcands = generate_confusion_candidates(lw)
        if vcands:
            # اختر الأقرب شبهاً
            best = process.extractOne(lw, vcands, scorer=fuzz.WRatio)[0]
            out.append(best); continue
        # 3) أقرب مفردة عامة
        cand = process.extractOne(lw, VOCAB, scorer=fuzz.WRatio)
        if cand and cand[1] >= 88:
            out.append(cand[0])
        else:
            out.append(lw)
    return " ".join(out)

# --- فهرسة من جديد
def reload_all():
    global QA_CACHE, BM25, BM25_DOCS, TFVEC, X_TFIDF
    QA_CACHE = load_qa()
    BM25, BM25_DOCS, TFVEC, X_TFIDF = build_indexes(QA_CACHE)
    load_synonyms(); load_typos()
    build_vocab()

# --- البحث المركّب
def combined_search(user_q: str, topk: int = 5):
    if not QA_CACHE:
        return None, 0.0

    q_base     = normalize_ar(user_q)
    q_correct  = correct_spelling_ar(q_base)     # ⬅ تصحيح إملائي
    q_expanded = expand_query(q_correct)         # ⬅ توسيع دلالي

    q_norm = q_expanded
    q_tok  = ar_tokens(q_norm)
    scores = {}

    # BM25
    if BM25:
        bm = BM25.get_scores(q_tok)
        for i, s in enumerate(bm):
            if s > 0:
                scores[i] = scores.get(i, 0.0) + s * 10.0

    # غموض على السؤال
    for i, qa in enumerate(QA_CACHE):
        s = fuzz.token_set_ratio(q_norm, normalize_ar(qa["q"]))  # 0..100
        if s > 0:
            scores[i] = scores.get(i, 0.0) + float(s) * 1.0

    # TF-IDF حرفي (n-grams)
    if TFVEC is not None:
        q_vec = TFVEC.transform([q_norm])
        cos = X_TFIDF @ q_vec.T
        cos = np.asarray(cos.todense()).ravel()
        for i, s in enumerate(cos):
            if s > 0:
                scores[i] = scores.get(i, 0.0) + float(s) * 120.0

    if not scores:
        return None, 0.0

    best_idx, best_score = sorted(scores.items(), key=lambda x: x[1], reverse=True)[0]
    return QA_CACHE[best_idx], best_score

# --- الإجابة
async def local_qa_answer(question: str) -> str:
    question = (question or "").strip()
    if not question:
        return "لم أستلم سؤالًا."
    doc, score = combined_search(question, topk=5)
    if doc and score >= 140:
        return doc["a"]
    if doc and score >= 90:
        return f"{doc['a']}\n\n(ℹ️ أقرب سؤال مطابق لدي كان: «{doc['q']}»)"
    if doc:
        return (
            f"لم أجد إجابة مؤكدة. أقرب سؤال عندي:\n"
            f"«{doc['q']}».\n"
            f"الجواب المخزن: {doc['a']}\n\n"
            f"يمكنك حفظ صياغتك الحالية عبر زر الحفظ لتحسين الفهم لاحقًا."
        )
    return "لا أملك معلومات كافية لهذا السؤال بعد. أضف س/ج مشابه إلى قاعدة المعرفة أو غيّر صياغة السؤال."

# ========= أدوات مساعدة =========
def clamp(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n]

# ========= صفحات وتجربة =========
@app.get("/", response_class=HTMLResponse)
def home():
    return f"""
    <div style="max-width:780px;margin:24px auto;font-family:system-ui">
      <h1>🤖 Bassam Brain — المحلي (مع تصحيح إملائي + فهم ذكي)</h1>
      <form method="post" action="/ask">
        <textarea name="q" rows="5" style="width:100%" placeholder="اكتب سؤالك هنا..."></textarea>
        <div style="margin-top:8px"><button>إرسال</button></div>
      </form>

      <details style="margin-top:18px">
        <summary>إدارة قاعدة المعرفة والقواميس</summary>

        <form method="post" action="/save_to_knowledge" style="margin-top:10px">
          <input type="text" name="q" placeholder="سؤال" style="width:100%;padding:6px"><br>
          <textarea name="a" rows="3" placeholder="جواب" style="width:100%;margin-top:6px"></textarea><br>
          <button>✅ حفظ هذا الجواب في قاعدة المعرفة</button>
        </form>

        <form method="post" action="/dict/add_typo" style="margin-top:12px">
          <input type="text" name="wrong" placeholder="الكتابة الخاطئة" style="width:48%;padding:6px">
          <input type="text" name="right" placeholder="التصحيح الصحيح" style="width:48%;padding:6px;margin-inline-start:4px">
          <button>✍️ إضافة تصحيح إملائي</button>
        </form>
        <p style="margin:6px 0">تحميل: <a href="/export/typos">typos.tsv</a> • <a href="/export/synonyms">synonyms.txt</a></p>

        <form method="post" action="/reload_all" style="margin-top:10px">
          <button>🔄 إعادة تحميل الفهارس والقواميس</button>
        </form>
      </details>
    </div>
    """

@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request):
    form = await request.form()
    q     = clamp(form.get("q",""), 1000)
    ans   = await local_qa_answer(q)
    rec = {"ts": int(time.time()), "instruction": q, "input": "", "output": ans}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return f"""
<div style='max-width:780px;margin:24px auto;font-family:system-ui'>
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
    rec = {"ts": int(time.time()), "instruction": form.get("q",""), "input": "", "output": form.get("a","")}
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
    with open(KB_FILE, "a", encoding="utf-8") as f:
        f.write(entry)
    return "<p>✅ تم الحفظ في قاعدة المعرفة. لا تنسَ الضغط على إعادة التحميل.</p><p><a href='/'>◀ رجوع</a></p>"

@app.post("/dict/add_typo", response_class=HTMLResponse)
async def add_typo(request: Request):
    form = await request.form()
    wrong = normalize_ar((form.get("wrong","") or "").strip())
    right = normalize_ar((form.get("right","") or "").strip())
    if not wrong or not right:
        return "<p>⚠️ أدخل قيمًا صحيحة.</p><p><a href='/'>◀ رجوع</a></p>"
    with open(TYPOS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{wrong}\t{right}\n")
    return "<p>✅ أُضيف التصحيح إلى القاموس. اضغط إعادة التحميل لتفعيله.</p><p><a href='/'>◀ رجوع</a></p>"

@app.post("/reload_all")
def reload_all_endpoint():
    reload_all()
    return {"ok": True, "qa_count": len(QA_CACHE), "vocab": len(VOCAB)}

# ===== API =====
@app.get("/ready")
def ready(): return {"ok": True}

@app.post("/answer")
async def answer(req: Request):
    body = await req.json()
    q = (body.get("question") or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="ضع حقل 'question'")
    text = await local_qa_answer(q)
    rec  = {"ts": int(time.time()), "instruction": q, "input": "", "output": text}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False)+"\n")
    return {"ok": True, "answer": text}

# تنزيل ملفات القاموس
@app.get("/export/typos")
def export_typos():
    return FileResponse(path=str(TYPOS_FILE), media_type="text/plain", filename="typos.tsv")

@app.get("/export/synonyms")
def export_synonyms():
    return FileResponse(path=str(SYN_FILE), media_type="text/plain", filename="synonyms.txt")
