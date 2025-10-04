# app.py — Bassam Brain (محلي + تصحيح + فهم ذكي + بحث ويب + عقل مزدوج)
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
import pathlib, re, json, time, asyncio
from typing import List, Dict, Set, Tuple

# ==================== الإعداد الأساسي ====================
app = FastAPI(title="Bassam Brain – Dual AI Engine")

DATA_DIR   = pathlib.Path("data"); DATA_DIR.mkdir(exist_ok=True)
NOTES_DIR  = DATA_DIR / "notes";  NOTES_DIR.mkdir(exist_ok=True)
DICT_DIR   = DATA_DIR / "dict";   DICT_DIR.mkdir(exist_ok=True)

LOG_FILE   = DATA_DIR / "log.jsonl"
FEED_FILE  = DATA_DIR / "feedback_pool.jsonl"
KB_FILE    = NOTES_DIR / "knowledge.txt"
TYPOS_FILE = DICT_DIR / "typos.tsv"
SYN_FILE   = DICT_DIR / "synonyms.txt"

# قاعدة معرفة افتراضية
if not KB_FILE.exists():
    KB_FILE.write_text("سؤال: ما فوائد القراءة؟\nجواب: القراءة توسّع المدارك وتقوّي الخيال وتزيد الثقافة.\n---\n", encoding="utf-8")

# ==================== المكاتب المطلوبة ====================
from rapidfuzz import fuzz, process
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

# استيراد البحث في الويب وصياغة الإجابة
from core.search_web import web_search
from core.compose_answer import compose_answer_ar

# ==================== أدوات اللغة ====================
AR_DIAC  = re.compile(r'[\u064B-\u0652]')
TOKEN_RE = re.compile(r'[A-Za-z\u0621-\u064A0-9]+')

def normalize_ar(s: str) -> str:
    s = s or ""
    s = AR_DIAC.sub('', s)
    s = s.replace('أ','ا').replace('إ','ا').replace('آ','ا')
    s = s.replace('ة','ه').replace('ى','ي').replace('ؤ','و').replace('ئ','ي')
    s = s.replace('گ','ك').replace('پ','ب').replace('ڤ','ف').replace('ظ','ض')
    return re.sub(r'\s+',' ', s).strip()

def ar_tokens(s: str) -> List[str]:
    return TOKEN_RE.findall(normalize_ar(s))

# ==================== تحميل المعرفة والقواميس ====================
def load_qa() -> List[dict]:
    text = KB_FILE.read_text(encoding='utf-8') if KB_FILE.exists() else ""
    qa = []
    for b in [x.strip() for x in text.split('---') if x.strip()]:
        m1, m2 = re.search(r'سؤال\s*:\s*(.+)', b), re.search(r'جواب\s*:\s*(.+)', b)
        if m1 and m2:
            qa.append({"q": m1.group(1).strip(), "a": m2.group(1).strip()})
    return qa

QA_CACHE = load_qa()

def build_indexes(qa_list: List[dict]):
    if not qa_list: return None, [], None, None
    docs_tokens = [ar_tokens(x["q"]+" "+x["a"]) for x in qa_list]
    bm25 = BM25Okapi(docs_tokens)
    corpus_norm = [normalize_ar(x["q"]) for x in qa_list]
    tfidf = TfidfVectorizer(analyzer='char', ngram_range=(3,5), min_df=1)
    X = tfidf.fit_transform(corpus_norm)
    return bm25, docs_tokens, tfidf, X

BM25, BM25_DOCS, TFVEC, X_TFIDF = build_indexes(QA_CACHE)

def reload_all():
    global QA_CACHE, BM25, BM25_DOCS, TFVEC, X_TFIDF
    QA_CACHE = load_qa()
    BM25, BM25_DOCS, TFVEC, X_TFIDF = build_indexes(QA_CACHE)

# ==================== البحث المحلي الذكي ====================
def combined_search(user_q: str, topk: int = 5):
    if not QA_CACHE: return None, 0.0
    qn = normalize_ar(user_q)
    q_tok = ar_tokens(qn)
    scores = {}

    # BM25
    if BM25:
        for i, s in enumerate(BM25.get_scores(q_tok)):
            if s > 0: scores[i] = scores.get(i, 0) + s * 10

    # غموض (fuzz)
    for i, qa in enumerate(QA_CACHE):
        s = fuzz.token_set_ratio(qn, normalize_ar(qa["q"]))
        if s > 0: scores[i] = scores.get(i, 0) + s

    # TF-IDF
    if TFVEC:
        q_vec = TFVEC.transform([qn])
        cos = X_TFIDF @ q_vec.T
        for i, s in enumerate(np.asarray(cos.todense()).ravel()):
            if s > 0: scores[i] = scores.get(i, 0) + s * 120

    if not scores: return None, 0
    best = sorted(scores.items(), key=lambda x: x[1], reverse=True)[0]
    return QA_CACHE[best[0]], best[1]

# ==================== بحث الويب وصياغة الإجابة ====================
async def web_answer(query: str, include_prices: bool = False, max_results: int = 6):
    results = await web_search(query, max_results=max_results)
    if not results:
        return ("لم أجد نتائج مناسبة على الويب.", [])
    payload = compose_answer_ar(query, results)
    summary = payload.get("answer", "لم أستطع توليد ملخص واضح.")
    links = payload.get("links", []) or [r.get("link","") for r in results if r.get("link")][:5]
    if include_prices:
        shop_q = f"{query} سعر"
        links.insert(0, f"https://www.google.com/search?q={shop_q}")
    return (summary, links[:5])

# ==================== العقل المزدوج ====================
@app.post("/search")
async def search(req: Request):
    body = await req.json()
    q = body.get("q","").strip()
    want_prices = body.get("want_prices", False)
    dual = body.get("dual_mode", True)

    if not q:
        raise HTTPException(status_code=400, detail="يرجى إدخال سؤال.")

    if dual:
        local_task = asyncio.create_task(local_qa(q))
        web_task = asyncio.create_task(web_answer(q, include_prices=want_prices))
        local_ans, (web_ans, web_links) = await asyncio.gather(local_task, web_task)
        return {"ok": True, "local": local_ans, "web": web_ans, "links": web_links}

    ans, meta = await smart_answer(q)
    return {"ok": True, "answer": ans, "meta": meta}

# ==================== الذكاء المحلي ====================
async def local_qa(q: str) -> str:
    doc, score = combined_search(q)
    if doc and score >= 140:
        return doc["a"]
    elif doc and score >= 90:
        return f"{doc['a']}\n\n(ℹ️ أقرب سؤال كان: «{doc['q']}»)"
    elif doc:
        return f"لم أجد إجابة دقيقة، لكن الأقرب: {doc['q']} → {doc['a']}"
    return "لم أجد إجابة في قاعدة المعرفة."

# ==================== الصفحة التجريبية ====================
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html><body style='font-family:Tahoma'>
    <h2>🧠 Bassam Brain — العقل المزدوج</h2>
    <form method='post' action='/search'>
    <textarea name='q' rows='5' style='width:100%'></textarea><br>
    <label><input type='checkbox' name='want_prices'/> روابط أسعار</label><br>
    <button>بحث</button>
    </form>
    </body></html>
    """
