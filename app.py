# app.py — Bassam Brain (محلي + قاموس + فهم ذكي + بحث ويب كاحتياطي)
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
import pathlib, re, json, time
from typing import List, Dict, Set, Tuple

# ==== لبنات الويب ====
# يحتاج الملفان التاليان أن يكونا موجودين داخل مجلد core/
# core/search_web.py : يوفر web_search(), summarize_snippets()
# core/compose_answer.py : يوفر compose_answer_ar() لتركيب إجابة عربية من نتائج الويب
from core.search_web import web_search, summarize_snippets
from core.compose_answer import compose_answer_ar

app = FastAPI(title="Bassam Brain – Local QA + Web Fallback")

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
    KB_FILE.write_text(
        "سؤال: ما فوائد القراءة؟\nجواب: القراءة توسّع المدارك وتقوّي الخيال وتزيد الثقافة.\n---\n",
        encoding="utf-8"
    )

# ملفات قاموس افتراضية
if not TYPOS_FILE.exists():
    TYPOS_FILE.write_text(
        "# wrong<TAB>right\n"
        "زكاء\tذكاء\nالزكاء\tالذكاء\nتعيف\tتعريف\nبرمجه\tبرمجة\n"
        "انتر نت\tانترنت\nالنت\tانترنت\nفايده\tفائدة\nفويد\tفوائد\n"
        "القراءه\tالقراءة\nالزمنيه\tالزمنية\nالاضطناعي\tالاصطناعي\n",
        encoding="utf-8"
    )
if not SYN_FILE.exists():
    SYN_FILE.write_text(
        "# مجموعة مرادفات في كل سطر\n"
        "فوائد,مميزات,إيجابيات,حسنات\n"
        "أضرار,سلبيات,عيوب\n"
        "تعريف,ماهو,ما هي,مفهوم\n"
        "انترنت,شبكة,الويب,نت\n"
        "موبايل,جوال,هاتف\n"
        "حاسوب,كمبيوتر,حاسبة\n"
        "ذكاء اصطناعي,الذكاء الاصطناعي,AI\n"
        "برمجة,تكويد,كود\n"
        "أمن معلومات,أمن سيبراني,حماية\n",
        encoding="utf-8"
    )

# ========= NLP محلية =========
from rapidfuzz import fuzz, process
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

# (1) تطبيع عربي خفيف
AR_DIAC  = re.compile(r'[\u064B-\u0652]')                # التشكيل
TOKEN_RE = re.compile(r'[A-Za-z\u0621-\u064A0-9]+')

def normalize_ar(s: str) -> str:
    s = s or ""
    s = AR_DIAC.sub('', s)
    s = s.replace('أ','ا').replace('إ','ا').replace('آ','ا')
    s = s.replace('ة','ه').replace('ى','ي').replace('ؤ','و').replace('ئ','ي')
    s = s.replace('گ','ك').replace('پ','ب').replace('ڤ','ف')
    s = s.replace('ظ','ض')  # تسامح ظ/ض
    s = re.sub(r'\s+',' ', s).strip()
    return s

def ar_tokens(s: str) -> List[str]:
    return TOKEN_RE.findall(normalize_ar(s))

# (2) تحميل Q/A
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

# (3) فهارس BM25 + TF-IDF
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

# (4) قواميس: مرادفات + تصحيحات + مفردات
SYN_SETS: List[Set[str]] = []
TYPOS_MAP: Dict[str,str] = {}
VOCAB: Set[str] = set()

def load_synonyms():
    global SYN_SETS
    SYN_SETS = []
    if SYN_FILE.exists():
        for line in SYN_FILE.read_text(encoding='utf-8').splitlines():
            line=line.strip()
            if not line or line.startswith('#'): continue
            words = [normalize_ar(w) for w in re.split(r"[,\s]+", line.replace("،", ",")) if w.strip()]
            if len(words)>=2:
                SYN_SETS.append(set(words))
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
        for i, line in enumerate(TYPOS_FILE.read_text(encoding='utf-8').splitlines()):
            line=line.strip()
            if not line or line.startswith('#'): continue
            if '\t' not in line:
                if i == 0: continue
                else: continue
            wrong,right = line.split('\t',1)
            wrong = normalize_ar(wrong); right = normalize_ar(right)
            if wrong and right: TYPOS_MAP[wrong]=right

def build_vocab():
    global VOCAB
    VOCAB = set()
    for qa in QA_CACHE:
        for w in ar_tokens(qa["q"] + " " + qa["a"]):
            if len(w) > 2:
                VOCAB.add(w.lower())
    for syn in SYN_SETS:
        for w in syn:
            if len(w)>2: VOCAB.add(w.lower())

load_synonyms(); load_typos(); build_vocab()

def expand_query(q: str) -> str:
    qn = normalize_ar(q)
    extra = []
    for syn in SYN_SETS:
        if any(w in qn for w in syn):
            extra.extend(list(syn))
    if extra:
        qn += " " + " ".join(extra)
    return qn

def correct_spelling_ar(text: str) -> str:
    toks = TOKEN_RE.findall(normalize_ar(text))
    out=[]
    for w in toks:
        lw=w.lower()
        if len(lw)<=2 or lw in VOCAB:
            out.append(lw); continue
        if lw in TYPOS_MAP:
            out.append(TYPOS_MAP[lw]); continue
        cand = process.extractOne(lw, VOCAB, scorer=fuzz.WRatio)
        if cand and cand[1] >= 88:
            out.append(cand[0])
        else:
            out.append(lw)
    return " ".join(out)

def reload_all():
    global QA_CACHE, BM25, BM25_DOCS, TFVEC, X_TFIDF
    QA_CACHE = load_qa()
    BM25, BM25_DOCS, TFVEC, X_TFIDF = build_indexes(QA_CACHE)
    load_synonyms(); load_typos(); build_vocab()

# (5) البحث المركب محليًا
def combined_search(user_q: str, topk: int = 5):
    if not QA_CACHE:
        return None, 0.0
    q_correct  = correct_spelling_ar(user_q)
    q_norm     = expand_query(q_correct)
    q_tok      = ar_tokens(q_norm)
    scores = {}

    if BM25:
        bm = BM25.get_scores(q_tok)
        for i, s in enumerate(bm):
            if s > 0:
                scores[i] = scores.get(i, 0.0) + s * 10.0

    for i, qa in enumerate(QA_CACHE):
        s = fuzz.token_set_ratio(q_norm, normalize_ar(qa["q"]))
        if s > 0:
            scores[i] = scores.get(i, 0.0) + float(s) * 1.0

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

# ========= المُجيب الذكي (محلي + ويب احتياطي) =========
async def smart_answer(question: str) -> Tuple[str, dict]:
    """
    يرجع: (الجواب، معلومات إضافية مثل المصادر أو نوع المسار)
    """
    q = (question or "").strip()
    if not q:
        return "لم أستلم سؤالًا.", {"mode": "invalid"}

    # 1) محاولة محلية
    doc, score = combined_search(q, topk=5)
    if doc and score >= 140:
        return doc["a"], {"mode": "local-high", "score": float(score)}
    if doc and score >= 90:
        return f"{doc['a']}\n\n(ℹ️ أقرب سؤال مطابق لدي كان: «{doc['q']}»)", {"mode": "local-mid", "score": float(score)}

    # 2) احتياطي ويب
    results = await web_search(q, max_results=6)
    if results:
        composed = compose_answer_ar(q, results)
        answer   = composed["answer"]
        links    = composed["links"]
        return answer, {"mode": "web", "links": links}

    # 3) fallback أخير
    if doc:
        text = (
            f"لم أجد إجابة مؤكدة. أقرب سؤال عندي:\n«{doc['q']}».\n"
            f"الجواب المخزن: {doc['a']}\n\n"
            f"يمكنك حفظ صياغتك الحالية عبر زر الحفظ لتحسين الفهم لاحقًا."
        )
        return text, {"mode": "local-suggestion", "score": float(score)}
    return "لا أملك معلومات كافية لهذا السؤال بعد. أضف س/ج مشابه إلى قاعدة المعرفة أو غيّر صياغة السؤال.", {"mode": "none"}

# ========= أدوات مساعدة =========
def clamp(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n]

# ========= صفحات وتجربة =========
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <div style="max-width:780px;margin:24px auto;font-family:system-ui">
      <h1>🤖 Bassam Brain — محلي + بحث ويب</h1>
      <form method="post" action="/ask">
        <textarea name="q" rows="5" style="width:100%" placeholder="اكتب سؤالك هنا..."></textarea>
        <div style="margin-top:8px"><button>إرسال</button></div>
      </form>

      <details style="margin-top:18px">
        <summary>إدارة المعرفة والقواميس</summary>

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

        <p style="margin:6px 0">تنزيل: <a href="/export/typos">typos.tsv</a> • <a href="/export/synonyms">synonyms.txt</a></p>

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
    ans, meta = await smart_answer(q)

    rec = {"ts": int(time.time()), "instruction": q, "input": "", "output": ans, "meta": meta}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    links_html = ""
    if meta.get("mode") == "web":
        links = meta.get("links") or []
        if links:
            links_html = "<ul>" + "".join([f"<li><a href='{l}' target='_blank'>{l}</a></li>" for l in links]) + "</ul>"

    return f"""
<div style='max-width:780px;margin:24px auto;font-family:system-ui'>
  <p><b>🧠 سؤالك:</b> {q}</p>
  <p><b>💬 الجواب:</b><br>{ans.replace("\n","<br>")}</p>
  {links_html}
  <form method='post' action='/save' style='margin-top:10px'>
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
    return {"ok": True, "qa_count": len(QA_CACHE)}

# ===== API =====
@app.get("/ready")
def ready(): return {"ok": True}

@app.post("/answer")
async def answer(req: Request):
    body = await req.json()
    q = (body.get("question") or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="ضع حقل 'question'")
    text, meta = await smart_answer(q)
    rec  = {"ts": int(time.time()), "instruction": q, "input": "", "output": text, "meta": meta}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False)+"\n")
    return {"ok": True, "answer": text, "meta": meta}

# تنزيل القواميس
@app.get("/export/typos")
def export_typos():
    return FileResponse(path=str(TYPOS_FILE), media_type="text/plain", filename="typos.tsv")

@app.get("/export/synonyms")
def export_synonyms():
    return FileResponse(path=str(SYN_FILE), media_type="text/plain", filename="synonyms.txt")
