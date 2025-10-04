# core/brain.py
# عقل مزدوج مع بحث ويب "مُتحمِّل للأخطاء" (DDGS + HTML fallback)
from typing import List, Dict, Tuple, Optional
from pathlib import Path
import re, time, random

from rapidfuzz import fuzz, process
from duckduckgo_search import DDGS
from bs4 import BeautifulSoup
import requests

# ================= إعداد ملف المعرفة =================
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
KB_FILE = DATA_DIR / "knowledge.txt"

if not KB_FILE.exists():
    KB_FILE.write_text(
        "سؤال: ما فوائد القراءة؟\n"
        "جواب: القراءة توسّع المدارك وتقوّي الخيال وتزيد الثقافة.\n"
        "---\n",
        encoding="utf-8"
    )

# ================= أدوات عربية بسيطة =================
AR_DIAC  = re.compile(r'[\u064B-\u0652]')
TOKEN_RE = re.compile(r'[A-Za-z\u0621-\u064A0-9]+')

def normalize_ar(s: str) -> str:
    s = s or ""
    s = AR_DIAC.sub("", s)
    s = s.replace("أ","ا").replace("إ","ا").replace("آ","ا")
    s = s.replace("ة","ه").replace("ى","ي").replace("ؤ","و").replace("ئ","ي")
    s = s.replace("گ","ك").replace("پ","ب").replace("ڤ","ف").replace("ظ","ض")
    return re.sub(r"\s+"," ", s).strip()

def tokens(s: str) -> List[str]:
    return TOKEN_RE.findall(normalize_ar(s))

# ================= تحميل Q/A =================
def load_qa() -> List[Dict]:
    text = KB_FILE.read_text(encoding="utf-8")
    blocks = [b.strip() for b in text.split("---") if b.strip()]
    out = []
    for b in blocks:
        m1 = re.search(r"سؤال\s*:\s*(.+)", b)
        m2 = re.search(r"جواب\s*:\s*(.+)", b)
        if m1 and m2:
            out.append({"q": m1.group(1).strip(), "a": m2.group(1).strip()})
    return out

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
        out.append(cand[0] if cand and cand[1] >= 90 else lw)
    return " ".join(out)

def local_search(q: str) -> Tuple[Optional[Dict], float]:
    if not QA:
        return None, 0.0
    qn = correct_spelling_ar(q)
    best_doc, best_score = None, 0.0
    for qa in QA:
        s = fuzz.token_set_ratio(qn, normalize_ar(qa["q"]))
        if s > best_score:
            best_doc, best_score = qa, float(s)
    return best_doc, best_score

# ================= Web Search (متحمّل للأخطاء) =================
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

class WebSearcher:
    def __init__(self, timeout: float = 8.0, retries: int = 2):
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA, "Accept-Language": "ar,en;q=0.8"})

    def ddgs_search(self, query: str, max_results: int) -> List[Dict]:
        # نحاول عدة مرات مع backoff بسيط
        for i in range(self.retries + 1):
            try:
                results = []
                # DDGS يدير الـ session الداخلي؛ هنا لا نمرر session لتجنب تعارضات
                with DDGS() as dd:
                    for r in dd.text(query, max_results=max_results):
                        results.append({
                            "title": (r.get("title") or "").strip(),
                            "snippet": (r.get("body") or "").strip(),
                            "link": (r.get("href") or "").strip(),
                        })
                if results:
                    return results
            except Exception:
                # انتظار عشوائي قصير ثم إعادة المحاولة
                time.sleep(0.6 + 0.4 * i)
        return []

    def html_fallback(self, query: str, max_results: int) -> List[Dict]:
        """Fallback عبر واجهة DuckDuckGo HTML (غير رسمية)."""
        try:
            # استخدام boole=1 لإجابات أكثر نصية، وkl=ar-ar للغة
            url = "https://duckduckgo.com/html/"
            params = {"q": query, "kl": "ar-ar"}
            r = self.session.get(url, params=params, timeout=self.timeout)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            items, results = soup.select(".result"), []
            for it in items:
                a = it.select_one("a.result__a")
                s = it.select_one(".result__snippet")
                if not a:
                    continue
                results.append({
                    "title": (a.get_text(strip=True) or "")[:180],
                    "snippet": (s.get_text(" ", strip=True) if s else "")[:300],
                    "link": a.get("href", "").strip(),
                })
                if len(results) >= max_results:
                    break
            return results
        except Exception:
            return []

    def search(self, query: str, max_results: int = 6) -> List[Dict]:
        # 1) DDGS أولاً
        res = self.ddgs_search(query, max_results)
        if res:
            return res
        # 2) Fallback HTML
        return self.html_fallback(query, max_results)

ws = WebSearcher()

def web_search(query: str, max_results: int = 6) -> List[Dict]:
    query = (query or "").strip()
    if not query:
        return []
    return ws.search(query, max_results=max_results)

# ================= تلخيص النتائج =================
def _clean_lines(text: str, max_lines: int = 4) -> List[str]:
    if not text:
        return []
    lines = [l.strip(" .\t\r\n") for l in text.splitlines()]
    lines = [l for l in lines if 15 <= len(l) <= 220]
    out, seen = [], set()
    for l in lines:
        if l in seen:
            continue
        seen.add(l)
        out.append(l)
        if len(out) >= max_lines:
            break
    return out

def compose_web_answer(question: str, results: List[Dict]) -> Dict:
    bullets, links = [], []
    for r in results[:6]:
        t = r.get("title") or ""
        s = r.get("snippet") or ""
        u = r.get("link") or ""
        if u:
            links.append(u)
        if 15 <= len(t) <= 140:
            bullets.append(t.strip())
        bullets.extend(_clean_lines(s, max_lines=2))

    clean, seen = [], set()
    for b in bullets:
        if b and b not in seen:
            seen.add(b)
            clean.append(b)
        if len(clean) >= 10:
            break

    if not clean:
        return {
            "answer": (
                f"سؤالك: {question}\n\n"
                "حاولت البحث في الويب لكن النتائج لم تكن متاحة الآن. "
                "أعد المحاولة بعد دقائق أو غيّر صياغة سؤالك."
            ),
            "links": links[:5]
        }

    head = f"سؤالك: {question}\n\nهذا ملخص مُنظم من عدة مصادر:\n"
    body = "\n".join([f"• {b}" for b in clean])
    tail = ""
    if links:
        tail = "\n\nروابط للاستزادة:\n" + "\n".join([f"- {u}" for u in links[:5]])
    return {"answer": head + body + tail, "links": links[:5]}

# ================= الواجهة الموحدة =================
def smart_answer(question: str) -> Tuple[str, Dict]:
    q = (question or "").strip()
    if not q:
        return "لم أستلم سؤالًا.", {"mode": "invalid"}

    # 1) قاعدة المعرفة
    doc, score = local_search(q)
    if doc and score >= 85:
        return doc["a"], {"mode": "local", "score": score, "match": doc["q"]}

    # 2) الويب (آمن)
    results = web_search(q, max_results=6)
    if results:
        pack = compose_web_answer(q, results)
        return pack["answer"], {"mode": "web", "links": pack.get("links", [])}

    # 3) fallback: أقرب ما لدينا
    if doc:
        return (
            f"لم أجد إجابة مؤكدة من الويب الآن. أقرب سؤال عندي:\n«{doc['q']}».\n"
            f"الجواب المخزن: {doc['a']}"
        ), {"mode": "suggest", "score": score}

    return (
        "لا أملك معلومات كافية الآن، ولم أتمكن من الوصول لنتائج ويب. "
        "جرّب لاحقًا أو أضف س/ج مشابه في قاعدة المعرفة.",
    ), {"mode": "none"}

def save_to_knowledge(q: str, a: str) -> None:
    q = (q or "").strip()
    a = (a or "").strip()
    if not q or not a:
        return
    with KB_FILE.open("a", encoding="utf-8") as f:
        f.write(f"\nسؤال: {q}\nجواب: {a}\n---\n")
