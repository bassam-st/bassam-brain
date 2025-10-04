# core/brain.py — العقل المزدوج: فهم محلي + بحث ويب + تحليل وتوليد ذكي
from typing import List, Dict, Tuple
from pathlib import Path
import re
from rapidfuzz import fuzz, process
from duckduckgo_search import DDGS

# مسار قاعدة المعرفة
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
KB_FILE = DATA_DIR / "knowledge.txt"

if not KB_FILE.exists():
    KB_FILE.write_text("سؤال: ما فوائد القراءة؟\nجواب: القراءة توسّع المدارك وتقوّي الخيال وتزيد الثقافة.\n---\n", encoding="utf-8")

# ======== أدوات اللغة العربية ========
AR_DIAC = re.compile(r'[\u064B-\u0652]')
TOKEN_RE = re.compile(r'[A-Za-z\u0621-\u064A0-9]+')

def normalize_ar(s: str) -> str:
    s = s or ""
    s = AR_DIAC.sub("", s)
    s = s.replace("أ","ا").replace("إ","ا").replace("آ","ا")
    s = s.replace("ة","ه").replace("ى","ي").replace("ؤ","و").replace("ئ","ي")
    s = s.replace("گ","ك").replace("پ","ب").replace("ڤ","ف")
    s = s.replace("ظ","ض")
    s = re.sub(r"\s+"," ", s).strip()
    return s

def tokens(s: str) -> List[str]:
    return TOKEN_RE.findall(normalize_ar(s))

# ======== قاعدة المعرفة المحلية ========
def load_qa() -> List[Dict]:
    text = KB_FILE.read_text(encoding="utf-8")
    blocks = [b.strip() for b in text.split("---") if b.strip()]
    qa = []
    for b in blocks:
        m1 = re.search(r"سؤال\s*:\s*(.+)", b)
        m2 = re.search(r"جواب\s*:\s*(.+)", b)
        if m1 and m2:
            qa.append({"q": m1.group(1).strip(), "a": m2.group(1).strip()})
    return qa

QA = load_qa()
VOCAB = {w.lower() for qa in QA for w in tokens(qa["q"] + " " + qa["a"]) if len(w) > 2}

def correct_spelling_ar(text: str) -> str:
    toks = tokens(text)
    out = []
    for w in toks:
        lw = w.lower()
        if lw in VOCAB or len(lw) <= 2:
            out.append(lw); continue
        cand = process.extractOne(lw, VOCAB, scorer=fuzz.WRatio)
        out.append(cand[0] if cand and cand[1] >= 88 else lw)
    return " ".join(out)

def local_search(q: str) -> Tuple[Dict, float]:
    if not QA:
        return None, 0.0
    qn = correct_spelling_ar(q)
    best, score = None, 0.0
    for qa in QA:
        s = fuzz.token_set_ratio(qn, normalize_ar(qa["q"]))
        if s > score:
            best, score = qa, float(s)
    return best, score

# ======== بحث ويب + تلخيص ذكي ========
def web_search(query: str, max_results: int = 6) -> List[Dict]:
    res = []
    with DDGS() as dd:
        for r in dd.text(query, max_results=max_results):
            res.append({"title": r.get("title"), "snippet": r.get("body"), "link": r.get("href")})
    return res

def _clean_lines(text: str, max_lines: int = 4) -> List[str]:
    if not text:
        return []
    lines = [l.strip(" .\t\r\n") for l in text.splitlines()]
    lines = [l for l in lines if 15 <= len(l) <= 220]
    seen, out = set(), []
    for l in lines:
        if l in seen: continue
        seen.add(l)
        out.append(l)
        if len(out) >= max_lines: break
    return out

def compose_web_answer(question: str, results: List[Dict]) -> Dict:
    bullets, links = [], []
    for r in results[:6]:
        title, snippet, link = r.get("title",""), r.get("snippet",""), r.get("link","")
        if link: links.append(link)
        if 15 <= len(title) <= 140:
            bullets.append(title.strip())
        bullets.extend(_clean_lines(snippet, max_lines=2))
    clean, seen = [], set()
    for b in bullets:
        if b and b not in seen:
            seen.add(b); clean.append(b)
        if len(clean) >= 10: break
    if not clean:
        return {"answer": "لم أجد نقاطًا واضحة من الويب.", "links": links[:5]}
    head = f"سؤالك: {question}\n\n💡 ملخص من مصادر الويب:\n"
    body = "\n".join([f"• {b}" for b in clean])
    tail = "\n\n🔗 روابط:\n" + "\n".join([f"- {u}" for u in links[:5]]) if links else ""
    return {"answer": head + body + tail, "links": links[:5]}

# ======== الدمج الذكي ========
def smart_answer(question: str) -> Tuple[str, Dict]:
    q = (question or "").strip()
    if not q:
        return "لم أستلم سؤالًا.", {"mode": "invalid"}

    doc, score = local_search(q)
    if doc and score >= 85:
        return doc["a"], {"mode": "local", "score": score, "match": doc["q"]}

    results = web_search(q, max_results=6)
    if results:
        pack = compose_web_answer(q, results)
        return pack["answer"], {"mode": "web", "links": pack.get("links", [])}

    if doc:
        return (
            f"لم أجد إجابة مؤكدة، لكن أقرب سؤال كان: «{doc['q']}».\nالجواب المخزن: {doc['a']}"
        ), {"mode": "suggest", "score": score}

    return "لا توجد إجابة بعد. أضفها في قاعدة المعرفة لتحسين ذكاء بسام.", {"mode": "none"}

def save_to_knowledge(q: str, a: str) -> None:
    if not q or not a:
        return
    with open(KB_FILE, "a", encoding="utf-8") as f:
        f.write(f"\nسؤال: {q}\nجواب: {a}\n---\n")
