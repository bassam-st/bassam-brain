# core/brain.py
# عقل مزدوج: (1) قاعدة معرفة محلية + فَهْم/تصحيح خفيف
#            (2) بحث ويب عبر DuckDuckGo + تلخيص نقطي وتهيئة إجابة عربية واضحة

from typing import List, Dict, Tuple
from pathlib import Path
import re

from rapidfuzz import fuzz, process
from duckduckgo_search import DDGS

# ===================== إعداد ملفات البيانات =====================
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
KB_FILE = DATA_DIR / "knowledge.txt"

# إنشاء قاعدة معرفة مبدئية إن لم تكن موجودة
if not KB_FILE.exists():
    KB_FILE.write_text(
        "سؤال: ما فوائد القراءة؟\n"
        "جواب: القراءة توسّع المدارك وتقوّي الخيال وتزيد الثقافة.\n"
        "---\n",
        encoding="utf-8"
    )

# ===================== أدوات عربية خفيفة =====================
AR_DIAC  = re.compile(r'[\u064B-\u0652]')  # التشكيل
TOKEN_RE = re.compile(r'[A-Za-z\u0621-\u064A0-9]+')

def normalize_ar(s: str) -> str:
    s = s or ""
    s = AR_DIAC.sub("", s)
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    s = s.replace("گ", "ك").replace("پ", "ب").replace("ڤ", "ف")
    s = s.replace("ظ", "ض")  # تسامح ظ/ض
    s = re.sub(r"\s+", " ", s).strip()
    return s

def tokens(s: str) -> List[str]:
    return TOKEN_RE.findall(normalize_ar(s))

# ===================== تحميل Q/A وبناء مفردات =====================
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

QA: List[Dict] = load_qa()
VOCAB = {w.lower() for qa in QA for w in tokens(qa["q"] + " " + qa["a"]) if len(w) > 2}

def reload_kb() -> None:
    """للاستدعاء من /reload_all في التطبيق إن رغبت."""
    global QA, VOCAB
    QA = load_qa()
    VOCAB = {w.lower() for qa in QA for w in tokens(qa["q"] + " " + qa["a"]) if len(w) > 2}

# ===================== تصحيح إملائي بسيط =====================
def correct_spelling_ar(text: str) -> str:
    if not VOCAB:
        return normalize_ar(text)
    toks = tokens(text)
    out = []
    for w in toks:
        lw = w.lower()
        if lw in VOCAB or len(lw) <= 2:
            out.append(lw)
            continue
        cand = process.extractOne(lw, VOCAB, scorer=fuzz.WRatio)
        out.append(cand[0] if cand and cand[1] >= 90 else lw)
    return " ".join(out)

# ===================== بحث محلي في قاعدة المعرفة =====================
def local_search(q: str) -> Tuple[Dict, float]:
    """بحث سريع بالـ rapidfuzz فقط (بدون numpy)."""
    if not QA:
        return None, 0.0
    qn = correct_spelling_ar(q)
    best_doc, best_score = None, 0.0
    for qa in QA:
        s = fuzz.token_set_ratio(qn, normalize_ar(qa["q"]))
        if s > best_score:
            best_doc, best_score = qa, float(s)
    return best_doc, best_score

# ===================== بحث الويب عبر DuckDuckGo =====================
def web_search(query: str, max_results: int = 6) -> List[Dict]:
    results: List[Dict] = []
    with DDGS() as dd:
        for r in dd.text(query, max_results=max_results):
            results.append({
                "title": (r.get("title") or "").strip(),
                "snippet": (r.get("body") or "").strip(),
                "link": (r.get("href") or "").strip(),
            })
    return results

def _clean_lines(text: str, max_lines: int = 3) -> List[str]:
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

    # إزالة التكرار
    clean, seen = [], set()
    for b in bullets:
        if b and b not in seen:
            seen.add(b)
            clean.append(b)
        if len(clean) >= 10:
            break

    if not clean:
        return {
            "answer": "بحثت في الويب لكن لم أجد نقاطًا واضحة كفاية. جرّب إعادة صياغة سؤالك.",
            "links": links[:5]
        }

    head = f"سؤالك: {question}\n\nهذا ملخص مُنظم من عدة مصادر:\n"
    body = "\n".join([f"• {b}" for b in clean])
    tail = ""
    if links:
        tail = "\n\nروابط للاستزادة:\n" + "\n".join([f"- {u}" for u in links[:5]])
    return {"answer": head + body + tail, "links": links[:5]}

# ✅ هذا القسم مسؤول عن تحليل السؤال، البحث في الويب، تلخيص النتائج، وتوليد الإجابة للمستخدم
def smart_answer(question: str) -> Tuple[str, Dict]:
    q = (question or "").strip()
    if not q:
        return "لم أستلم سؤالًا.", {"mode": "invalid"}

    # 1) قاعدة المعرفة (تطابق قوي)
    doc, score = local_search(q)
    if doc and score >= 85:
        return doc["a"], {"mode": "local", "score": score, "match": doc["q"]}

    # 2) احتياطي الويب
    results = web_search(q, max_results=6)
    if results:
        pack = compose_web_answer(q, results)
        return pack["answer"], {"mode": "web", "links": pack.get("links", [])}

    # 3) fallback أخير
    if doc:
        return (
            f"لم أجد إجابة مؤكدة. أقرب سؤال عندي:\n«{doc['q']}».\n"
            f"الجواب المخزن: {doc['a']}\n\n"
            "يمكنك حفظ إجابتك الخاصة في القاعدة لتحسين النتائج لاحقًا."
        ), {"mode": "suggest", "score": score}

    return "لا أملك معلومات كافية بعد. أضف س/ج مشابه في قاعدة المعرفة أو غيّر صياغة السؤال.", {"mode": "none"}

# ===================== حفظ إلى قاعدة المعرفة =====================
def save_to_knowledge(q: str, a: str) -> None:
    q = (q or "").strip()
    a = (a or "").strip()
    if not q or not a:
        return
    with KB_FILE.open("a", encoding="utf-8") as f:
        f.write(f"\nسؤال: {q}\nجواب: {a}\n---\n")
    # حدث الذاكرة الداخلية بعد الحفظ
    reload_kb()
