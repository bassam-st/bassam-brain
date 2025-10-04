# core/brain.py
# عقل مزدوج ++ مع:
# - أستاذ رياضيات يشرح خطوة بخطوة (Sympy)
# - قاموس إملائي ومرادفات (ملفات خارجية + افتراضي)
# - بحث متعدد المصادر + تلخيص نقطي وروابط

from typing import List, Dict, Tuple
from pathlib import Path
import re, json, time, urllib.parse
from dataclasses import dataclass

from rapidfuzz import fuzz, process
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import feedparser
import httpx

# ========= إعداد عام ومسارات =========
DATA_DIR = Path("data"); DATA_DIR.mkdir(parents=True, exist_ok=True)
KB_FILE  = DATA_DIR / "knowledge.txt"

DICT_DIR   = DATA_DIR / "dict"; DICT_DIR.mkdir(exist_ok=True)
TYPOS_FILE = DICT_DIR / "typos.tsv"
SYN_FILE   = DICT_DIR / "synonyms.txt"

HTTP_TIMEOUT = httpx.Timeout(20.0, connect=10.0, read=15.0)
HEADERS = {
    "User-Agent": "BassamBrain/1.3 (+https://render.com)",
    "Accept": "text/html,application/json,application/xml;q=0.9,*/*;q=0.8",
}

if not KB_FILE.exists():
    KB_FILE.write_text(
        "سؤال: ما فوائد القراءة؟\n"
        "جواب: القراءة توسّع المدارك وتقوّي الخيال وتزيد الثقافة.\n"
        "---\n",
        encoding="utf-8"
    )

# ========= أدوات عربية بسيطة =========
AR_DIAC  = re.compile(r'[\u064B-\u0652]')       # التشكيل
TOKEN_RE = re.compile(r'[A-Za-z\u0621-\u064A0-9]+')

def normalize_ar(s: str) -> str:
    s = s or ""
    s = AR_DIAC.sub("", s)
    s = s.replace("أ","ا").replace("إ","ا").replace("آ","ا")
    s = s.replace("ة","ه").replace("ى","ي").replace("ؤ","و").replace("ئ","ي")
    s = s.replace("گ","ك").replace("پ","ب").replace("ڤ","ف")
    s = s.replace("ظ","ض")  # تسامح ظ/ض
    s = re.sub(r"\s+"," ", s).strip()
    return s

def tokens(s: str) -> List[str]:
    return TOKEN_RE.findall(normalize_ar(s))

# ========= Q/A محلية =========
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

# ========= قاموس: أخطاء + مرادفات =========
def _safe_read(p: Path) -> str:
    try: return p.read_text(encoding="utf-8")
    except Exception: return ""

def load_typos() -> Dict[str, str]:
    mp = {}
    txt = _safe_read(TYPOS_FILE)
    for i, line in enumerate(txt.splitlines()):
        line = line.strip()
        if not line or line.startswith("#"): continue
        if "\t" not in line:
            if i == 0: continue
            else: continue
        wrong, right = line.split("\t", 1)
        wrong = normalize_ar(wrong); right = normalize_ar(right)
        if wrong and right: mp[wrong] = right
    # افتراضيات إن كان الملف فارغًا
    if not mp:
        mp.update({
            "زكاء":"ذكاء","الزكاء":"الذكاء","تعيف":"تعريف","برمجه":"برمجة",
            "انتر نت":"انترنت","النت":"انترنت","فايده":"فائدة","فويد":"فوائد",
            "القراءه":"القراءة","الزمنيه":"الزمنية","الاضطناعي":"الاصطناعي"
        })
    return mp

def load_synonyms() -> List[List[str]]:
    groups = []
    txt = _safe_read(SYN_FILE).replace("،", ",")
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        parts = [normalize_ar(p) for p in re.split(r"[,\s]+", line) if p.strip()]
        if len(parts) >= 2: groups.append(parts)
    if not groups:
        groups = [
            ["فوائد","مميزات","ايجابيات","حسنات"],
            ["اضرار","سلبيات","عيوب"],
            ["تعريف","ماهو","ما هي","مفهوم"],
            ["انترنت","شبكه","الويب","نت"],
            ["موبايل","جوال","هاتف"],
            ["حاسوب","كمبيوتر","حاسبه"],
            ["ذكاء اصطناعي","الذكاء الاصطناعي","ai"],
            ["برمجه","تكويد","كود","برمجة"],
            ["امن معلومات","امن سيبراني","حماية"],
        ]
    return groups

TYPOS_MAP  = load_typos()
SYN_GROUPS = load_synonyms()

VOCAB = {w.lower() for qa in QA for w in tokens(qa["q"] + " " + qa["a"]) if len(w) > 2}
for g in SYN_GROUPS:
    for w in g:
        if len(w) > 2: VOCAB.add(w.lower())

def correct_spelling_ar(text: str) -> str:
    toks = tokens(text)
    out = []
    for w in toks:
        lw = w.lower()
        if lw in TYPOS_MAP:
            out.append(TYPOS_MAP[lw]); continue
        if len(lw) <= 2 or lw in VOCAB:
            out.append(lw); continue
        cand = process.extractOne(lw, VOCAB, scorer=fuzz.WRatio)
        out.append(cand[0] if cand and cand[1] >= 90 else lw)
    return " ".join(out)

def expand_query(q: str) -> str:
    qn = normalize_ar(q)
    extra = []
    low = qn.lower()
    for group in SYN_GROUPS:
        if any(g in low for g in group):
            extra.extend(group)
    if extra:
        qn = qn + " " + " ".join(sorted(set(extra))[:12])
    return qn

def local_search(q: str) -> Tuple[Dict, float]:
    if not QA:
        return None, 0.0
    qn = correct_spelling_ar(q)
    best_doc, best_score = None, 0.0
    for qa in QA:
        s = fuzz.token_set_ratio(qn, normalize_ar(qa["q"]))  # 0..100
        if s > best_score:
            best_doc, best_score = qa, float(s)
    return best_doc, best_score

def save_to_knowledge(q: str, a: str) -> None:
    q = (q or "").strip(); a = (a or "").strip()
    if not q or not a: return
    with KB_FILE.open("a", encoding="utf-8") as f:
        f.write(f"\nسؤال: {q}\nجواب: {a}\n---\n")

# ========= أستاذ رياضيات (شرح خطوة بخطوة) =========
MATH_HINTS = re.compile(
    r'(?:\bsolve\b|\bmatrix\b|\bdet\b|\blimit\b|\bdiff\b|\bintegrate\b|∫|√|=|≈|<=|>=|[\+\-\*/\^])|'
    r'(?:مشتق|تفاضل|تكامل|حد|معادلة|حل|مصفوفة|نظام|جذر|قيمة عظمى|قيمة صغرى)'
)

def looks_like_math(q: str) -> bool:
    return bool(MATH_HINTS.search(q.lower()))

try:
    import sympy as sp
except Exception:
    sp = None

@dataclass
class MathResult:
    ok: bool
    answer: str

def _pretty(e):
    try: return sp.pretty(e, use_unicode=True)
    except Exception: return str(e)

def solve_math_step_by_step(q: str) -> MathResult:
    if sp is None:
        return MathResult(False, "محرك الرياضيات غير متاح على هذا الخادم.")
    steps = []
    try:
        txt = q.strip()
        x = sp.symbols('x')
        # 1) معادلة: 2x+3=7 أو "حل المعادلة: ..."
        m = re.search(r"(?:حل|solve).{0,12}?:?\s*(.+)", txt, re.IGNORECASE)
        if m:
            steps.append("🔎 التعرف: مسألة حل معادلة.")
            expr = m.group(1)
            if "=" in expr:
                L, R = expr.split("=",1)
                steps.append(f"الخطوة 1: تفسير الطرفين\nLHS = {L}\nRHS = {R}")
                Ls, Rs = sp.sympify(L), sp.sympify(R)
                eq = sp.Eq(Ls, Rs)
                steps.append(f"الخطوة 2: تأسيس المعادلة\n{_pretty(eq)}")
                sol = sp.solve(eq, dict=True)
            else:
                steps.append(f"الخطوة 1: مساواة التعبير بالصفر: {expr} = 0")
                sol = sp.solve(sp.sympify(expr), dict=True)
            steps.append(f"الخطوة 3: الحل\n{sol}")
            return MathResult(True, "\n".join(steps))

        # 2) تفاضل
        m = re.search(r"(?:مشتق|تفاضل|diff)\s+(.+)", txt, re.IGNORECASE)
        if m:
            steps.append("🔎 التعرف: تفاضل.")
            expr = sp.sympify(m.group(1))
            steps.append(f"الخطوة 1: الدالة\nf(x) = { _pretty(expr) }")
            d = sp.diff(expr, x)
            steps.append(f"الخطوة 2: المشتق\nf'(x) = { _pretty(sp.simplify(d)) }")
            return MathResult(True, "\n".join(steps))

        # 3) تكامل
        m = re.search(r"(?:تكامل|integrate)\s+(.+)", txt, re.IGNORECASE)
        if m:
            steps.append("🔎 التعرف: تكامل.")
            expr = sp.sympify(m.group(1))
            steps.append(f"الخطوة 1: التكامل غير المحدد للتعبير\n∫ { _pretty(expr) } dx")
            I = sp.integrate(expr, x)
            steps.append(f"الخطوة 2: النتيجة\n= { _pretty(I) } + C")
            return MathResult(True, "\n".join(steps))

        # 4) حد
        m = re.search(r"(?:حد|limit)\s+(.+)", txt, re.IGNORECASE)
        if m:
            steps.append("🔎 التعرف: حد.")
            body = m.group(1)
            mm = re.search(r"(.+),\s*([a-zA-Z])\s*->\s*([\-0-9\.]+)", body)
            if mm:
                expr = sp.sympify(mm.group(1)); var = sp.symbols(mm.group(2)); val = sp.sympify(mm.group(3))
                steps.append(f"الخطوة 1: التعبير\n{ _pretty(expr) }")
                steps.append(f"الخطوة 2: أخذ الحد عندما {var}→{val}")
                L = sp.limit(expr, var, val)
                steps.append(f"الخطوة 3: النتيجة\n= { _pretty(sp.simplify(L)) }")
                return MathResult(True, "\n".join(steps))

        # 5) نظام خطي
        m = re.search(r"(?:حل النظام|system|solve system)\s*:\s*(.+)", txt, re.IGNORECASE)
        if m:
            steps.append("🔎 التعرف: نظام معادلات خطي.")
            eqs_txt = m.group(1)
            parts = re.split(r"[;،]+", eqs_txt)
            syms = sorted(list({ch for ch in "".join(parts) if ch.isalpha()}))
            symb = sp.symbols(" ".join(syms))
            equations = []
            for p in parts:
                if "=" in p:
                    L,R = p.split("=",1)
                    equations.append(sp.Eq(sp.sympify(L), sp.sympify(R)))
            steps.append("الخطوة 1: كتابة النظام:")
            for i,eq in enumerate(equations,1):
                steps.append(f"  ({i}) { _pretty(eq) }")
            sol = sp.solve(equations, symb, dict=True)
            steps.append(f"الخطوة 2: الحل العام:\n{sol}")
            return MathResult(True, "\n".join(steps))

        # 6) مصفوفات
        m = re.search(r"(?:det|محدد|inverse|معكوس|rank)\s*(\[\[.+\]\])", txt, re.IGNORECASE)
        if m:
            A = sp.Matrix(sp.sympify(m.group(1)))
            steps.append(f"المصفوفة:\n{_pretty(A)}")
            if re.search(r"(?:det|محدد)", txt):   steps.append(f"det(A) = {A.det()}")
            if re.search(r"(?:inverse|معكوس)", txt): steps.append(f"A^-1 =\n{_pretty(A.inv())}")
            if re.search(r"(?:rank)", txt):      steps.append(f"rank(A) = {A.rank()}")
            return MathResult(True, "\n".join(steps))

        # 7) محاولة عامة
        steps.append("🔎 التعرف: تعبير عام — تبسيط رمزي.")
        expr = sp.sympify(txt)
        steps.append(f"التعبير:\n{_pretty(expr)}")
        steps.append(f"المبسّط:\n{_pretty(sp.simplify(expr))}")
        return MathResult(True, "\n".join(steps))

    except Exception as e:
        return MathResult(False, f"تعذّر الحل ({type(e).__name__}). جرب صياغة أوضح.")
# ========= نهاية الرياضيات =========

# ========= توسعة استعلام (عربي/إنجليزي) =========
AR_EN_SYNS = [
    {"تعريف","يعني","ماهو","ما هي","definition","meaning","explain"},
    {"فوائد","مميزات","إيجابيات","advantages","benefits","pros"},
    {"أضرار","سلبيات","عيوب","disadvantages","cons","risks"},
    {"سعر","تكلفة","ثمن","price","cost"},
    {"خطوات","طريقة","كيف","شرح","how","steps","guide"},
    {"أمثلة","مثال","examples"},
    {"مقارنة","compare","vs","versus"},
    {"عاصمة","capital"},
    {"تعداد","سكان","population"},
    {"عملة","currency"},
    {"برمجة","تكويد","code","coding","programming"},
    {"شبكات","networking","networks"},
    {"ذكاء اصطناعي","الذكاء الاصطناعي","ai","machine learning"},
]

def expand_query_semantic(q: str) -> str:
    qn = expand_query(q)
    extra = []
    low = qn.lower()
    for group in AR_EN_SYNS:
        if any(g in low for g in group):
            extra.extend(group)
    if extra:
        qn = qn + " " + " ".join(sorted(set(extra))[:12])
    return qn

# ========= أدوات ويب ومحركات =========
def clean_url(u: str) -> str:
    u = (u or "").strip()
    if not u: return ""
    try:
        p = urllib.parse.urlsplit(u)
        q = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
        keep = []
        for k, v in q:
            if k.lower() in {"q","query","s"} and v:
                keep.append((k, v))
        new_q = urllib.parse.urlencode(keep) if keep else ""
        return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, new_q, ""))
    except Exception:
        return u

def _lines_from_text(text: str, max_lines: int = 3) -> List[str]:
    if not text: return []
    lines = [l.strip(" .\t\r\n") for l in text.splitlines()]
    lines = [l for l in lines if 15 <= len(l) <= 220]
    uniq, seen = [], set()
    for l in lines:
        if l in seen: continue
        seen.add(l); uniq.append(l)
        if len(uniq) >= max_lines: break
    return uniq

def search_duckduckgo(query: str, k: int = 8) -> List[Dict]:
    out: List[Dict] = []
    try:
        with DDGS() as dd:
            for r in dd.text(query, max_results=k):
                out.append({
                    "title": (r.get("title") or "").strip(),
                    "snippet": (r.get("body") or "").strip(),
                    "link": clean_url(r.get("href") or ""),
                    "src": "DuckDuckGo",
                })
    except Exception:
        pass
    return out

def search_ddg_site(query: str, site: str, k: int = 6) -> List[Dict]:
    return search_duckduckgo(f"site:{site} {query}", k=k)

def search_wikipedia(query: str, k: int = 6) -> List[Dict]:
    url = "https://ar.wikipedia.org/w/api.php"
    out: List[Dict] = []
    try:
        with httpx.Client(headers=HEADERS, timeout=HTTP_TIMEOUT) as cx:
            r = cx.get(url, params={
                "action":"query","list":"search","srsearch":query,
                "utf8":"1","format":"json","srlimit":str(k)
            })
            r.raise_for_status()
            data = r.json()
            for it in data.get("query",{}).get("search",[])[:k]:
                title = it.get("title") or ""
                page = clean_url(f"https://ar.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ','_'))}")
                snippet = BeautifulSoup(it.get("snippet") or "", "html.parser").get_text()[:220]
                if title and page:
                    out.append({"title": title, "snippet": snippet, "link": page, "src": "Wikipedia"})
    except Exception:
        pass
    return out

def search_stackoverflow(query: str, k: int = 5) -> List[Dict]:
    url = "https://api.stackexchange.com/2.3/search/advanced"
    out: List[Dict] = []
    try:
        with httpx.Client(headers=HEADERS, timeout=HTTP_TIMEOUT) as cx:
            r = cx.get(url, params={"order":"desc","sort":"relevance","q":query,"site":"stackoverflow","pagesize":str(k)})
            r.raise_for_status()
            data = r.json()
            for it in data.get("items", [])[:k]:
                title = (it.get("title") or "").strip()
                link = clean_url(it.get("link") or "")
                if title and link:
                    out.append({"title": title, "snippet": "سؤال مبرمجين ذي صلة", "link": link, "src": "StackOverflow"})
    except Exception:
        pass
    return out

def search_hackernews(query: str, k: int = 5) -> List[Dict]:
    url = "http://hn.algolia.com/api/v1/search"
    out: List[Dict] = []
    try:
        with httpx.Client(headers=HEADERS, timeout=HTTP_TIMEOUT) as cx:
            r = cx.get(url, params={"query": query, "hitsPerPage": str(k)})
            r.raise_for_status()
            data = r.json()
            for it in data.get("hits", [])[:k]:
                title = (it.get("title") or "") or (it.get("story_title") or "")
                link = clean_url((it.get("url") or "") or (it.get("story_url") or ""))
                if title and link:
                    out.append({"title": title.strip(), "snippet": "من Hacker News", "link": link, "src": "HackerNews"})
    except Exception:
        pass
    return out

def search_arxiv(query: str, k: int = 5) -> List[Dict]:
    base = "http://export.arxiv.org/api/query"
    out: List[Dict] = []
    try:
        with httpx.Client(headers=HEADERS, timeout=HTTP_TIMEOUT) as cx:
            r = cx.get(base, params={"search_query": f"all:{query}", "start": "0", "max_results": str(k)})
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "xml")
            for entry in soup.find_all("entry")[:k]:
                title = (entry.title.text or "").strip()
                link_el = entry.find("link", {"rel":"alternate"})
                link = clean_url(link_el.get("href")) if link_el else ""
                summary = (entry.summary.text or "").strip()
                if title and link:
                    out.append({"title": title, "snippet": summary[:220], "link": link, "src": "arXiv"})
    except Exception:
        pass
    return out

def search_semantic_scholar(query: str, k: int = 5) -> List[Dict]:
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    out: List[Dict] = []
    try:
        with httpx.Client(headers=HEADERS, timeout=HTTP_TIMEOUT) as cx:
            r = cx.get(url, params={"query": query, "limit": str(k), "fields":"title,url,abstract"})
            r.raise_for_status()
            data = r.json()
            for it in data.get("data", [])[:k]:
                title = (it.get("title") or "").strip()
                link  = clean_url((it.get("url") or "").strip())
                snippet = (it.get("abstract") or "")[:220]
                if title and link:
                    out.append({"title": title, "snippet": snippet, "link": link, "src": "SemanticScholar"})
    except Exception:
        pass
    return out

def search_openalex(query: str, k: int = 5) -> List[Dict]:
    url = "https://api.openalex.org/works"
    out: List[Dict] = []
    try:
        with httpx.Client(headers=HEADERS, timeout=HTTP_TIMEOUT) as cx:
            r = cx.get(url, params={"search": query, "per_page": str(k)})
            r.raise_for_status()
            data = r.json()
            for it in data.get("results", [])[:k]:
                title = (it.get("title") or "").strip()
                link = (it.get("primary_location", {}) or {}).get("source", {}).get("homepage_url") \
                       or (it.get("primary_location", {}) or {}).get("landing_page_url") or ""
                if not link:
                    doi = (it.get("doi") or "").strip()
                    if doi: link = "https://doi.org/" + doi.replace("doi:", "")
                link = clean_url(link)
                snippet = "ملخص متوفر" if it.get("abstract_inverted_index") else ""
                if title and link:
                    out.append({"title": title, "snippet": snippet, "link": link, "src": "OpenAlex"})
    except Exception:
        pass
    return out

def search_internet_archive(query: str, k: int = 5) -> List[Dict]:
    url = "https://archive.org/advancedsearch.php"
    out: List[Dict] = []
    try:
        q = f'title:("{query}") OR description:("{query}")'
        with httpx.Client(headers=HEADERS, timeout=HTTP_TIMEOUT) as cx:
            r = cx.get(url, params={"q": q, "fl[]": ["identifier","title","description"], "rows": str(k), "page":"1", "output":"json"})
            r.raise_for_status()
            data = r.json()
            for doc in data.get("response",{}).get("docs",[])[:k]:
                title = (doc.get("title") or "").strip()
                ident = doc.get("identifier") or ""
                link = clean_url(f"https://archive.org/details/{ident}") if ident else ""
                snip = (doc.get("description") or "")[:220]
                if title and link:
                    out.append({"title": title, "snippet": snip, "link": link, "src": "InternetArchive"})
    except Exception:
        pass
    return out

COUNTRY_BUNDLES: Dict[str, Dict[str, List[str]]] = {
    "yemen":   {"sites": ["saba.ye","yemen.gov.ye","moe-ye.net"], "rss": ["https://saba.ye/rss.xml"]},
    "saudi":   {"sites": ["spa.gov.sa","www.my.gov.sa","data.gov.sa","moh.gov.sa","moe.gov.sa"], "rss": []},
    "uae":     {"sites": ["wam.ae","u.ae","data.gov.ae","mohap.gov.ae","moe.gov.ae"], "rss": []},
    "qatar":   {"sites": ["qna.org.qa","portal.www.gov.qa","data.gov.qa","moph.gov.qa","edu.gov.qa"], "rss": []},
    "egypt":   {"sites": ["gate.ahram.org.eg","cabinet.gov.eg","mohp.gov.eg","moe.gov.eg"], "rss": []},
    "morocco": {"sites": ["www.maroc.ma","sante.gov.ma","education.gov.ma"], "rss": []},
    "algeria": {"sites": ["www.el-mouradia.dz","sante.gov.dz","education.gov.dz"], "rss": []},
    "tunisia": {"sites": ["www.tunisiegouv.tn","sante.gov.tn","education.tn"], "rss": []},
    "jordan":  {"sites": ["petra.gov.jo","moh.gov.jo","moe.gov.jo"], "rss": []},
    "usa":     {"sites": ["usa.gov","data.gov","cdc.gov","ed.gov","nih.gov"], "rss": []},
    "uk":      {"sites": ["gov.uk","data.gov.uk","nhs.uk","education.gov.uk"], "rss": []},
    "canada":  {"sites": ["canada.ca","healthcanada.gc.ca","ised-isde.canada.ca"], "rss": []},
    "germany": {"sites": ["bund.de","govdata.de","bmbf.de","bmg.bund.de"], "rss": []},
    "france":  {"sites": ["gouvernement.fr","data.gouv.fr","education.gouv.fr","sante.gouv.fr"], "rss": []},
    "turkey":  {"sites": ["turkiye.gov.tr","saglik.gov.tr","meb.gov.tr"], "rss": []},
    "india":   {"sites": ["india.gov.in","data.gov.in","mohfw.gov.in","education.gov.in"], "rss": []},
    "japan":   {"sites": ["japan.go.jp","mext.go.jp","mhlw.go.jp","data.go.jp"], "rss": []},
}

def search_country_bundle(country: str, query: str) -> List[Dict]:
    bundle = COUNTRY_BUNDLES.get(country.lower())
    if not bundle: return []
    results: List[Dict] = []
    for site in bundle.get("sites", []):
        try: results += search_ddg_site(query, site, k=5)
        except Exception: pass
    # RSS إن وجدت
    for url in bundle.get("rss", []):
        try:
            d = feedparser.parse(url)
            for e in d.entries[:3]:
                title = (getattr(e,"title","") or "").strip()
                link  = clean_url(getattr(e,"link","") or "")
                summ  = (getattr(e,"summary","") or "")[:220]
                if title and link:
                    results.append({"title": title, "snippet": summ, "link": link, "src": "RSS"})
        except Exception:
            pass
    return results

def multi_search(query: str) -> List[Dict]:
    qx = expand_query_semantic(query)
    results: List[Dict] = []

    # عام
    results += search_duckduckgo(qx, k=10)

    # موسوعي/أكاديمي
    for fn in (search_wikipedia, search_arxiv, search_semantic_scholar, search_openalex):
        try: results += fn(qx)
        except Exception: pass

    # تقني/مجتمعي
    for fn in (search_stackoverflow, search_hackernews):
        try: results += fn(qx)
        except Exception: pass

    # أرشيفات
    for fn in (search_internet_archive, ):
        try: results += fn(qx)
        except Exception: pass

    # حزم دول
    for country in COUNTRY_BUNDLES.keys():
        try: results += search_country_bundle(country, qx)
        except Exception: pass

    # إزالة التكرار
    seen, uniq = set(), []
    for r in results:
        u = (r.get("link") or "").strip()
        if u and u not in seen:
            seen.add(u); uniq.append(r)
    return uniq[:50]

def compose_web_answer(question: str, results: List[Dict]) -> Dict:
    bullets: List[str] = []; links: List[str] = []
    for r in results[:16]:
        title = (r.get("title") or "").strip()
        snip  = (r.get("snippet") or "").strip()
        link  = (r.get("link") or "").strip()
        src   = (r.get("src") or "").strip()
        if link: links.append(link)
        if title and 15 <= len(title) <= 140:
            bullets.append(f"{title}" + (f" [{src}]" if src else ""))
        bullets += _lines_from_text(snip, max_lines=2)

    seen, clean = set(), []
    for b in bullets:
        if b and b not in seen:
            seen.add(b); clean.append(b)
        if len(clean) >= 14:
            break

    if not clean:
        return {
            "answer": "بحثت في المصادر ولم أجد نقاطًا واضحة كفاية. جرّب إعادة صياغة سؤالك.",
            "links": links[:8]
        }

    head = f"سؤالك: {question}\n\nهذا ملخص مُنظَّم من مصادر متعددة (يشمل مواقع/وكالات رسمية عند الإمكان):\n"
    body = "\n".join([f"• {b}" for b in clean])
    tail = ("\n\nروابط للاستزادة:\n" + "\n".join([f"- {u}" for u in links[:8]])) if links else ""
    return {"answer": head + body + tail, "links": links[:8]}

def _lines_from_text(text: str, max_lines: int = 3) -> List[str]:
    if not text: return []
    lines = [l.strip(" .\t\r\n") for l in text.splitlines()]
    lines = [l for l in lines if 15 <= len(l) <= 220]
    uniq, seen = [], set()
    for l in lines:
        if l in seen: continue
        seen.add(l); uniq.append(l)
        if len(uniq) >= max_lines: break
    return uniq

# ========= الواجهة الموحدة =========
def smart_answer(question: str) -> Tuple[str, Dict]:
    """
    المسار:
      1) لو سؤال رياضي => حل خطوة بخطوة
      2) لو تطابق محلي قوي في Q/A => أعد الجواب
      3) وإلا => بحث متعدد المصادر + تلخيص
      4) fallback باقتراح أقرب سؤال محلي
    """
    q = (question or "").strip()
    if not q:
        return "لم أستلم سؤالًا.", {"mode": "invalid"}

    # (1) رياضيات
    if looks_like_math(q):
        res = solve_math_step_by_step(q)
        if res.ok: return res.answer, {"mode": "math"}
        # لو فشل: نكمل

    # (2) Q/A محلية
    doc, score = local_search(q)
    if doc and score >= 85:
        return doc["a"], {"mode": "local", "score": score, "match": doc["q"]}

    # (3) الويب
    results = multi_search(q)
    if results:
        pack = compose_web_answer(q, results)
        return pack["answer"], {"mode": "web", "links": pack.get("links", [])}

    # (4) fallback
    if doc:
        return (
            f"لم أجد إجابة مؤكدة. أقرب سؤال عندي:\n«{doc['q']}».\n"
            f"الجواب المخزن: {doc['a']}\n\n"
            "يمكنك حفظ إجابتك الخاصة في القاعدة لتحسين النتائج لاحقًا."
        ), {"mode": "suggest", "score": score}

    return "لا أملك معلومات كافية بعد. أضف س/ج مشابه في قاعدة المعرفة أو غيّر صياغة السؤال.", {"mode": "none"}
