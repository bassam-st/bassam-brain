# app.py — Bassam Brain (ذكاء محلي + بحث ويب احتياطي)
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
import pathlib, re, json, time
from typing import List, Dict, Set, Tuple

# استيراد أدوات البحث والملخص
from core.search_web import web_search, summarize_snippets
from core.compose_answer import compose_answer_ar

app = FastAPI(title="Bassam Brain — محلي + بحث ويب ذكي")

# ========= مجلدات البيانات =========
DATA_DIR = pathlib.Path("data"); DATA_DIR.mkdir(exist_ok=True)
NOTES_DIR = DATA_DIR / "notes"; NOTES_DIR.mkdir(exist_ok=True)
DICT_DIR = DATA_DIR / "dict"; DICT_DIR.mkdir(exist_ok=True)

KB_FILE = NOTES_DIR / "knowledge.txt"
LOG_FILE = DATA_DIR / "log.jsonl"
TYPOS_FILE = DICT_DIR / "typos.tsv"
SYN_FILE = DICT_DIR / "synonyms.txt"

# قاعدة معرفة افتراضية
if not KB_FILE.exists():
    KB_FILE.write_text("سؤال: ما فوائد القراءة؟\nجواب: القراءة توسّع المدارك وتزيد الثقافة.\n---\n", encoding="utf-8")

# ========= أدوات لغوية =========
from rapidfuzz import fuzz, process
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

AR_DIAC = re.compile(r'[\u064B-\u0652]')
TOKEN_RE = re.compile(r'[A-Za-z\u0621-\u064A0-9]+')

def normalize_ar(s: str) -> str:
    s = s or ""
    s = AR_DIAC.sub('', s)
    s = s.replace('أ','ا').replace('إ','ا').replace('آ','ا')
    s = s.replace('ة','ه').replace('ى','ي').replace('ؤ','و').replace('ئ','ي')
    s = re.sub(r'\s+',' ', s).strip()
    return s

def ar_tokens(s: str) -> List[str]:
    return TOKEN_RE.findall(normalize_ar(s))

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

def build_indexes(qa):
    docs_tokens = [ar_tokens(x["q"]) for x in qa]
    bm25 = BM25Okapi(docs_tokens)
    tfidf = TfidfVectorizer(analyzer='char', ngram_range=(3,5))
    X = tfidf.fit_transform([normalize_ar(x["q"]) for x in qa])
    return bm25, tfidf, X

BM25, TFVEC, X_TFIDF = build_indexes(QA_CACHE)

def combined_search(q: str):
    qn = normalize_ar(q)
    scores = {}
    tokens = ar_tokens(qn)
    bm = BM25.get_scores(tokens)
    for i, s in enumerate(bm):
        scores[i] = s * 10
    for i, qa in enumerate(QA_CACHE):
        s = fuzz.token_set_ratio(qn, normalize_ar(qa["q"]))
        scores[i] = scores.get(i, 0) + s
    q_vec = TFVEC.transform([qn])
    cos = (X_TFIDF @ q_vec.T).ravel().toarray()
    for i, s in enumerate(cos):
        scores[i] = scores.get(i, 0) + s * 120
    best = sorted(scores.items(), key=lambda x: x[1], reverse=True)[0]
    return QA_CACHE[best[0]], best[1]

async def smart_answer(question: str) -> Tuple[str, dict]:
    if not question.strip():
        return "اكتب سؤالك أولاً.", {}
    doc, score = combined_search(question)
    if doc and score >= 140:
        return doc["a"], {"mode": "local"}
    if doc and score >= 90:
        return f"{doc['a']}\n\n(ℹ️ أقرب سؤال مشابه: «{doc['q']}»)", {"mode": "similar"}

    try:
        results = await web_search(question, max_results=8)
        if results:
            comp = compose_answer_ar(question, results)
            return comp["answer"], {"mode": "web", "links": comp["links"]}
    except Exception:
        pass

    if doc:
        return f"أقرب ما لدي:\n{doc['q']}\nالجواب: {doc['a']}", {"mode": "fallback"}
    return "لم أجد إجابة كافية بعد.", {"mode": "none"}

@app.get("/", response_class=HTMLResponse)
def home():
    return """<h2>🤖 Bassam Brain — محلي + بحث ويب ذكي</h2>
<form method='post' action='/ask'>
<textarea name='q' placeholder='اكتب سؤالك هنا...' rows='4' cols='60'></textarea><br>
<button>إرسال</button>
</form>"""

@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request):
    form = await request.form()
    q = form.get("q","")
    ans, meta = await smart_answer(q)
    links = meta.get("links", [])
    html_links = "<ul>" + "".join([f"<li><a href='{u}' target='_blank'>{u}</a></li>" for u in links]) + "</ul>" if links else ""
    return f"<h3>سؤالك:</h3><p>{q}</p><h3>الإجابة:</h3><p>{ans.replace(chr(10),'<br>')}</p>{html_links}<br><a href='/'>رجوع</a>"
