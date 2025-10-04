# core/brain.py
# عقل مزدوج:
#   1) قاعدة معرفة محلية + تصحيح/تطبيع عربي خفيف + مطابقة غامضة
#   2) بحث متعدد المصادر (سطح + "ديب ويب" قانوني + حزم حكومية/إعلامية لكل من اليمن، السعودية، الإمارات، قطر)
# مع توسعة استعلام عربية/إنجليزية وتلخيص نقطي وروابط.

from typing import List, Dict, Tuple
from pathlib import Path
import re, json, time, urllib.parse, itertools

from rapidfuzz import fuzz, process
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import feedparser
import httpx

# ========== إعداد عام ==========
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
KB_FILE = DATA_DIR / "knowledge.txt"

HTTP_TIMEOUT = httpx.Timeout(20.0, connect=10.0, read=15.0)
HEADERS = {
    "User-Agent": "BassamBrain/1.1 (+https://render.com)",
    "Accept": "text/html,application/json,application/xml;q=0.9,*/*;q=0.8",
}

# ملف معرفة مبدئي
if not KB_FILE.exists():
    KB_FILE.write_text(
        "سؤال: ما فوائد القراءة؟\n"
        "جواب: القراءة توسّع المدارك وتقوّي الخيال وتزيد الثقافة.\n"
        "---\n",
        encoding="utf-8"
    )

# ========== أدوات عربية بسيطة ==========
AR_DIAC  = re.compile(r'[\u064B-\u0652]')  # التشكيل
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

# ========== Q/A محلية ==========
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
            out.append(lw)
            continue
        cand = process.extractOne(lw, VOCAB, scorer=fuzz.WRatio)
        out.append(cand[0] if cand and cand[1] >= 90 else lw)
    return " ".join(out)

def local_search(q: str) -> Tuple[Dict, float]:
    """مطابقة غامضة بسيطة على الأسئلة المخزنة."""
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
    q = (q or "").strip()
    a = (a or "").strip()
    if not q or not a:
        return
    with KB_FILE.open("a", encoding="utf-8") as f:
        f.write(f"\nسؤال: {q}\nجواب: {a}\n---\n")

# ========== توسعة استعلام (عربي/إنجليزي) ==========
AR_EN_SYNS = [
    # عامة
    {"تعريف","يعني","ماهو","ما هي","definition","meaning","explain"},
    {"فوائد","مميزات","إيجابيات","advantages","benefits","pros"},
    {"أضرار","سلبيات","عيوب","disadvantages","cons","risks"},
    {"سعر","تكلفة","ثمن","price","cost"},
    {"خطوات","طريقة","كيف","شرح","how","steps","guide"},
    {"أمثلة","مثال","examples"},
    {"مقارنة","compare","vs","versus"},
    # جغرافيا/إحصاء
    {"عاصمة","capital"},
    {"تعداد","سكان","population"},
    {"ناتج محلي","gdp","gross domestic product"},
    {"عملة","currency"},
    # تقنية
    {"برمجة","تكويد","code","coding","programming"},
    {"شبكات","networking","networks"},
    {"ذكاء اصطناعي","الذكاء الاصطناعي","ai","machine learning"},
]

def expand_query(q: str) -> str:
    qn = normalize_ar(q)
    extra = []
    low = qn.lower()
    for group in AR_EN_SYNS:
        if any(g in low for g in group):
            extra.extend(group)
    if extra:
        qn = qn + " " + " ".join(sorted(set(extra))[:12])
    return qn

# ========== أدوات مساعدة للويب ==========
def clean_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    try:
        parsed = urllib.parse.urlsplit(u)
        q = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        keep = []
        for k, v in q:
            if k.lower() in {"q","query","s"} and v:
                keep.append((k, v))
        new_q = urllib.parse.urlencode(keep) if keep else ""
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_q, ""))
    except Exception:
        return u

def _lines_from_text(text: str, max_lines: int = 3) -> List[str]:
    if not text:
        return []
    lines = [l.strip(" .\t\r\n") for l in text.splitlines()]
    lines = [l for l in lines if 15 <= len(l) <= 220]
    uniq, seen = [], set()
    for l in lines:
        if l in seen: 
            continue
        seen.add(l)
        uniq.append(l)
        if len(uniq) >= max_lines:
            break
    return uniq

# ========== محركات/مصادر عامة ==========
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
    """بحث DDG مع تقييد دومين: site:domain"""
    return search_duckduckgo(f"site:{site} {query}", k=k)

def search_wikipedia(query: str, k: int = 6) -> List[Dict]:
    url = "https://ar.wikipedia.org/w/api.php"
    out: List[Dict] = []
    try:
        with httpx.Client(headers=HEADERS, timeout=HTTP_TIMEOUT) as cx:
            r = cx.get(url, params={
                "action":"query","list":"search","srsearch":query,"utf8":"1","format":"json","srlimit":str(k)
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

# تقنية/مجتمع
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

def search_rss_filtered(query: str, feeds: List[str], k_per: int = 3) -> List[Dict]:
    out: List[Dict] = []
    key = normalize_ar(query).lower()
    try:
        for url in feeds:
            d = feedparser.parse(url)
            for e in d.entries[:k_per]:
                title = (getattr(e, "title", "") or "").strip()
                link  = clean_url(getattr(e, "link", "") or "")
                summ  = (getattr(e, "summary", "") or "")[:220]
                if not title or not link: 
                    continue
                # ترشيح بسيط
                if any(w in (title + " " + summ).lower() for w in key.split()):
                    out.append({"title": title, "snippet": summ, "link": link, "src": "RSS"})
    except Exception:
        pass
    return out

# ========= ديب ويب قانوني (أكاديمي/أرشيفي) =========
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
                    if doi:
                        link = "https://doi.org/" + doi.replace("doi:", "")
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

def search_commoncrawl(query: str, k: int = 5) -> List[Dict]:
    bases = [
        "https://index.commoncrawl.org/CC-MAIN-2024-26-index",
        "https://index.commoncrawl.org/CC-MAIN-2024-18-index",
        "https://index.commoncrawl.org/CC-MAIN-2023-50-index",
    ]
    out: List[Dict] = []
    key = urllib.parse.quote(query.strip())
    if not key:
        return out
    params = {"url": f"*{key}*", "output": "json", "page": "0"}
    try:
        for base in bases:
            with httpx.Client(headers=HEADERS, timeout=HTTP_TIMEOUT) as cx:
                r = cx.get(base, params=params)
                if r.status_code != 200 or not r.text:
                    continue
                for ln in r.text.splitlines():
                    try:
                        item = json.loads(ln)
                        url = clean_url(item.get("url") or "")
                        if not url:
                            continue
                        out.append({"title": url[:120], "snippet": "نسخة مؤرشفة عبر CommonCrawl", "link": url, "src": "CommonCrawl"})
                        if len(out) >= k:
                            return out
                    except Exception:
                        continue
    except Exception:
        pass
    return out

# ========== حِزم دولية: اليمن، السعودية، الإمارات، قطر ==========
COUNTRY_BUNDLES: Dict[str, Dict[str, List[str]]] = {
    # ملاحظة: نستخدم DDG مع site: لتجنّب مفاتيح وقيود، + RSS لو أمكن.
    "yemen": {
        "sites": [
            "saba.ye",           # وكالة سبأ
            "yemen.gov.ye",      # بوابة حكومية عامة
            "moe-ye.net",        # مثال وزارة (قد يتغير)
        ],
        "rss": [
            # لو لا تعمل، يتم تجاهلها بصمت
            "https://saba.ye/rss.xml",
        ],
    },
    "saudi": {
        "sites": [
            "spa.gov.sa",        # وكالة الأنباء السعودية
            "www.my.gov.sa",     # البوابة الوطنية
            "data.gov.sa",       # بيانات مفتوحة
            "moh.gov.sa",        # الصحة
            "moe.gov.sa",        # التعليم
        ],
        "rss": [
            "https://www.my.gov.sa/wps/portal/snp/content/ar/rss",  # قد يتغير
        ],
    },
    "uae": {
        "sites": [
            "wam.ae",            # وكالة أنباء الإمارات
            "u.ae",              # البوابة الرسمية
            "data.gov.ae",       # بيانات مفتوحة
            "mohap.gov.ae",      # الصحة
            "moe.gov.ae",        # التعليم
        ],
        "rss": [
            "https://wam.ae/en/rss",  # قد تختلف اللغة/المسار
        ],
    },
    "qatar": {
        "sites": [
            "qna.org.qa",        # وكالة الأنباء القطرية
            "portal.www.gov.qa", # البوابة الحكومية
            "data.gov.qa",       # بيانات مفتوحة
            "moph.gov.qa",       # الصحة
            "edu.gov.qa",        # التعليم
        ],
        "rss": [
            "https://www.qna.org.qa/en/rss",  # قد يتغير
        ],
    },
}

def search_country_bundle(country: str, query: str) -> List[Dict]:
    bundle = COUNTRY_BUNDLES.get(country.lower())
    if not bundle:
        return []
    results: List[Dict] = []
    # بحث مقيّد بالمواقع
    for site in bundle.get("sites", []):
        try:
            results += search_ddg_site(query, site, k=5)
        except Exception:
            pass
    # RSS إن وجد
    rss_list = bundle.get("rss", [])
    if rss_list:
        try:
            results += search_rss_filtered(query, rss_list, k_per=3)
        except Exception:
            pass
    return results

# ========== تجميع نتائج من مصادر متعددة ==========
def multi_search(query: str) -> List[Dict]:
    """تجميع نتائج من عدّة مصادر (سطح + ديب ويب + حِزم دولية)."""
    qx = expand_query(query)
    results: List[Dict] = []

    # عام
    try: results += search_duckduckgo(qx, k=10)
    except Exception: pass

    # موسوعي/أكاديمي
    for fn in [search_wikipedia, search_arxiv, search_semantic_scholar, search_openalex]:
        try:
            results += fn(qx)
        except Exception:
            pass

    # تقني/مجتمعي
    for fn in [search_stackoverflow, search_hackernews]:
        try:
            results += fn(qx)
        except Exception:
            pass

    # أرشيف وخلاصات عامة
    for fn in [search_internet_archive, search_commoncrawl]:
        try:
            results += fn(qx)
        except Exception:
            pass

    # حزم الدول (Yemen / Saudi / UAE / Qatar)
    for country in ["yemen","saudi","uae","qatar"]:
        try:
            results += search_country_bundle(country, qx)
        except Exception:
            pass

    # إزالة التكرارات حسب الرابط
    seen, uniq = set(), []
    for r in results:
        u = (r.get("link") or "").strip()
        if u and u not in seen:
            seen.add(u); uniq.append(r)
    return uniq[:40]

# ========== تلخيص نقاط + تركيب جواب ==========
def compose_web_answer(question: str, results: List[Dict]) -> Dict:
    bullets: List[str] = []
    links: List[str] = []

    for r in results[:16]:
        title = (r.get("title") or "").strip()
        snip  = (r.get("snippet") or "").strip()
        link  = (r.get("link") or "").strip()
        src   = (r.get("src") or "").strip()

        if link:
            links.append(link)
        if title and 15 <= len(title) <= 140:
            bullets.append(f"{title}" + (f" [{src}]" if src else ""))
        bullets += _lines_from_text(snip, max_lines=2)

    # إزالة التكرارات
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

    head = f"سؤالك: {question}\n\nهذا ملخص مُنظَّم من مصادر متعددة (يتضمن مواقع/وكالات رسمية عند الإمكان):\n"
    body = "\n".join([f"• {b}" for b in clean])
    tail = ""
    if links:
        tail = "\n\nروابط للاستزادة:\n" + "\n".join([f"- {u}" for u in links[:8]])
    return {"answer": head + body + tail, "links": links[:8]}

# ========== الواجهة الموحدة ==========
def smart_answer(question: str) -> Tuple[str, Dict]:
    """
    يُرجع (الجواب، بيانات ميتا مثل الروابط/الوضع).
    المسار:
      1) Q/A محلية — إن كان التطابق قويًا
      2) بحث متعدد المصادر (مع ديب ويب قانوني + حزم اليمن/السعودية/الإمارات/قطر) + تلخيص
      3) fallback باقتراح أقرب سؤال محلي
    """
    q = (question or "").strip()
    if not q:
        return "لم أستلم سؤالًا.", {"mode": "invalid"}

    # 1) قاعدة المعرفة
    doc, score = local_search(q)
    if doc and score >= 85:
        return doc["a"], {"mode": "local", "score": score, "match": doc["q"]}

    # 2) الويب (سطح + ديب ويب + باقات دولية)
    results = multi_search(q)
    if results:
        pack = compose_web_answer(q, results)
        return pack["answer"], {"mode": "web", "links": pack.get("links", [])}

    # 3) fallback — أقرب شيء محلي
    if doc:
        return (
            f"لم أجد إجابة مؤكدة. أقرب سؤال عندي:\n«{doc['q']}».\n"
            f"الجواب المخزن: {doc['a']}\n\n"
            "يمكنك حفظ إجابتك الخاصة في القاعدة لتحسين النتائج لاحقًا."
        ), {"mode": "suggest", "score": score}

    return "لا أملك معلومات كافية بعد. أضف س/ج مشابه في قاعدة المعرفة أو غيّر صياغة السؤال.", {"mode": "none"}
