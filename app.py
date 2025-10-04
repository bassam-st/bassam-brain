# app.py — Bassam Brain (محلي + قاموس + فهم ذكي + بحث ويب كاحتياطي)
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
import pathlib, re, json, time
from typing import List, Dict, Set, Tuple

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

# ========= ملفات افتراضية =========
if not KB_FILE.exists():
    KB_FILE.write_text("سؤال: ما فوائد القراءة؟\nجواب: القراءة توسّع المدارك وتقوّي الخيال وتزيد الثقافة.\n---\n", encoding="utf-8")

if not TYPOS_FILE.exists():
    TYPOS_FILE.write_text(
        "# wrong<TAB>right\n"
        "زكاء\tذكاء\nالزكاء\tالذكاء\nتعيف\tتعريف\nبرمجه\tبرمجة\n"
        "انتر نت\tانترنت\nالنت\tانترنت\nفايده\tفائدة\nفويد\tفوائد\n"
        "القراءه\tالقراءة\nالزمنيه\tالزمنية\nالاضطناعي\tالاصطناعي\n", encoding="utf-8"
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
        "أمن معلومات,أمن سيبراني,حماية\n", encoding="utf-8"
    )

# ========= NLP محلية =========
from rapidfuzz import fuzz, process
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

AR_DIAC  = re.compile(r'[\u064B-\u0652]')
TOKEN_RE = re.compile(r'[A-Za-z\u0621-\u064A0-9]+')

def normalize_ar(s: str) -> str:
    s = s or ""
    s = AR_DIAC.sub('', s)
    s = s.replace('أ','ا').replace('إ','ا').replace('آ','ا')
    s = s.replace('ة','ه').replace('ى','ي').replace('ؤ','و').replace('ئ','ي')
    s = s.replace('گ','ك').replace('پ','ب').replace('ڤ','ف')
    s = s.replace('ظ','ض')
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
            q = m1.group(1).strip()
            a = m2.group(1).strip()
            qa.append({"q": q, "a": a})
    return qa

QA_CACHE: List[dict] = load_qa()

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
        SYN_SETS = [{"فوائد","مميزات","ايجابيات","حسنات"},{"اضرار","سلبيات","عيوب"},{"تعريف","ماهو","ما هي","مفهوم"}]

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

# ========= بحث الويب (نسخة احتياطية) =========
try:
    from core.search_web import web_search, summarize_snippets
except Exception:
    def web_search(query: str, max_results: int = 5):
        return []
    def summarize_snippets(snips): return ""

# ========= الذكاء المحلي + ويب =========
async def smart_answer(question: str) -> Tuple[str, dict]:
    q = (question or "").strip()
    if not q:
        return "لم أستلم سؤالًا.", {"mode": "invalid"}

    doc, score = combined_search(q, topk=5)
    if doc and score >= 140:
        return doc["a"], {"mode": "local-high", "score": float(score)}
    if doc and score >= 90:
        return f"{doc['a']}\n\n(ℹ️ أقرب سؤال مشابه: «{doc['q']}»)", {"mode": "local-mid", "score": float(score)}

    try:
        results = web_search(q, max_results=6)
    except Exception:
        results = []

    if results:
        summary = summarize_snippets(results)
        links   = [r.get("link") for r in results if r.get("link")][:5]
        answer  = summary or "جمعت لك هذه النقاط من نتائج الويب."
        if links:
            answer += "\n\n🔗 مصادر:\n" + "\n".join([f"- {u}" for u in links])
        return answer, {"mode": "web", "links": links}

    if doc:
        return (f"أقرب سؤال مشابه:\n«{doc['q']}».\nالجواب المخزن: {doc['a']}", {"mode": "local-suggestion", "score": float(score)})
    return "لا أملك إجابة بعد. أضف س/ج مشابه أو غيّر صياغة السؤال.", {"mode": "none"}

# ========= البحث =========
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
