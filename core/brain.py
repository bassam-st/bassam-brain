# core/brain.py
# عقل مزدوج:
#   (1) قاعدة معرفة محلية + تصحيح/تطبيع عربي خفيف + مطابقة غامضة
#   (2) بحث ويب + "ديب ويب" قانوني (arXiv / Semantic Scholar / OpenAlex / Internet Archive / CommonCrawl)
# ثم تلخيص نقطي وإرجاع جواب مع روابط.

from typing import List, Dict, Tuple
from pathlib import Path
import re, json, time, urllib.parse

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
    "User-Agent": "BassamBrain/1.0 (+https://render.com)",
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

# ========== أدوات مساعدة للويب ==========
def clean_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    # إزالة تتبّع شائع
    try:
        parsed = urllib.parse.urlsplit(u)
        # نعيد بناء بدون query التتبعي الطويلة، لكن نُبقي الأساسية
        q = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        keep = []
        for k, v in q:
            if k.lower() in {"q", "query", "s"} and v:
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

# ========== محركات/مصادر ==========
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

def search_wikipedia(query: str, k: int = 6) -> List[Dict]:
    # استخدام API القياسي
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

def search_stackoverflow(query: str, k: int = 5) -> List[Dict]:
    # عبر Stack Exchange Search (بدون مفتاح، معدّل محدود)
    url = "https://api.stackexchange.com/2.3/search/advanced"
    out: List[Dict] = []
    try:
        with httpx.Client(headers=HEADERS, timeout=HTTP_TIMEOUT) as cx:
            r = cx.get(url, params={
                "order":"desc","sort":"relevance","q":query,"site":"stackoverflow","pagesize":str(k)
            })
            r.raise_for_status()
            data = r.json()
            for it in data.get("items", [])[:k]:
                title = (it.get("title") or "").strip()
                link = clean_url(it.get("link") or "")
                snip = "سؤال مبرمجين ذي صلة"
                if title and link:
                    out.append({"title": title, "snippet": snip, "link": link, "src": "StackOverflow"})
    except Exception:
        pass
    return out

def search_hackernews(query: str, k: int = 5) -> List[Dict]:
    # Algolia HN search
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

def search_rss(query: str, k_per_feed: int = 3) -> List[Dict]:
    """
    نجلب من خلاصات عامة ثم نُرشّح/ننتقي بالعناوين.
    يمكنك توسيع قائمة الخلاصات حسب تخصصك.
    """
    feeds = [
        "https://news.ycombinator.com/rss",
        "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
        "https://www.theverge.com/rss/index.xml",
    ]
    out: List[Dict] = []
    qn = normalize_ar(query).lower()
    try:
        for url in feeds:
            d = feedparser.parse(url)
            for e in d.entries[:k_per_feed]:
                title = (getattr(e, "title", "") or "").strip()
                link  = clean_url(getattr(e, "link", "") or "")
                summ  = (getattr(e, "summary", "") or "")[:220]
                if not title or not link: 
                    continue
                # ترشيح بسيط بالعنوان
                if any(w in title.lower() for w in qn.split()):
                    out.append({"title": title, "snippet": summ, "link": link, "src": "RSS"})
    except Exception:
        pass
    return out

# ========= ديب ويب قانوني =========
def search_arxiv(query: str, k: int = 5) -> List[Dict]:
    base = "http://export.arxiv.org/api/query"
    out: List[Dict] = []
    try:
        with httpx.Client(headers=HEADERS, timeout=HTTP_TIMEOUT) as cx:
            r = cx.get(base, params={"search_query": f"all:{query}", "start": "0", "max_results": str(k)})
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "xml")  # Atom feed
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
            r = cx.get(url, params={
                "q": q,
                "fl[]": ["identifier","title","description"],
                "rows": str(k),
                "page": "1",
                "output": "json"
            })
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
    """
    البحث عبر فهارس Common Crawl (CDX API). هذا بحث بالعناوين/الروابط، وليس نص الصفحة الكامل.
    """
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
                        out.append({
                            "title": url[:120],
                            "snippet": "نسخة مؤرشفة عبر CommonCrawl",
                            "link": url,
                            "src": "CommonCrawl"
                        })
                        if len(out) >= k:
                            return out
                    except Exception:
                        continue
    except Exception:
        pass
    return out

# (اختياري) نِتر لتويتر بدون مفاتيح — عطّله افتراضياً لتجنّب الحظر
def search_nitter(query: str, k: int = 4, enabled: bool = False) -> List[Dict]:
    if not enabled:
        return []
    base = "https://nitter.net/search"
    out: List[Dict] = []
    try:
        with httpx.Client(headers=HEADERS, timeout=HTTP_TIMEOUT) as cx:
            r = cx.get(base, params={"f":"tweets","q":query})
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for item in soup.select(".timeline .tweet")[:k]:
                content = item.select_one(".tweet-content")
                href = item.get("href") or ""
                link = clean_url("https://nitter.net" + href) if href else ""
                snip = content.get_text(" ", strip=True)[:220] if content else ""
                if snip and link:
                    out.append({"title": "منشور على Nitter", "snippet": snip, "link": link, "src": "Nitter"})
    except Exception:
        pass
    return out

# ========== تجميع نتائج من المصادر ==========
def multi_search(query: str) -> List[Dict]:
    """تجميع نتائج من عدّة مصادر (سطح + ديب ويب قانوني)."""
    results: List[Dict] = []

    # عام
    try: results += search_duckduckgo(query)
    except Exception: pass

    # موسوعي/أكاديمي (ديب ويب قانوني)
    try: results += search_wikipedia(query)
    except Exception: pass
    try: results += search_arxiv(query)
    except Exception: pass
    try: results += search_semantic_scholar(query)
    except Exception: pass
    try: results += search_openalex(query)
    except Exception: pass

    # تقني/مجتمعي
    try: results += search_stackoverflow(query)
    except Exception: pass
    try: results += search_hackernews(query)
    except Exception: pass

    # أرشيف وخلاصات
    try: results += search_rss(query)
    except Exception: pass
    try: results += search_internet_archive(query)
    except Exception: pass
    try: results += search_commoncrawl(query)
    except Exception: pass

    # (اختياري) شبكات اجتماعية (معطّل افتراضياً)
    try: results += search_nitter(query, enabled=False)
    except Exception: pass

    # إزالة التكرارات حسب الرابط
    seen, uniq = set(), []
    for r in results:
        u = r.get("link") or ""
        if u and u not in seen:
            seen.add(u); uniq.append(r)
    return uniq[:30]

# ========== تلخيص نقاط + تركيب جواب ==========
def compose_web_answer(question: str, results: List[Dict]) -> Dict:
    bullets: List[str] = []
    links: List[str] = []

    for r in results[:12]:
        title = (r.get("title") or "").strip()
        snip  = (r.get("snippet") or "").strip()
        link  = (r.get("link") or "").strip()
        src   = (r.get("src") or "").strip()

        if link:
            links.append(link)
        # ننتقي عنوانًا جيدًا كنقطة
        if title and 15 <= len(title) <= 140:
            bullets.append(f"{title}" + (f" [{src}]" if src else ""))
        # ونضيف سطرين من المقتطف
        bullets += _lines_from_text(snip, max_lines=2)

    # إزالة التكرارات
    seen, clean = set(), []
    for b in bullets:
        if b and b not in seen:
            seen.add(b); clean.append(b)
        if len(clean) >= 12:
            break

    if not clean:
        return {
            "answer": "بحثت في الويب لكن لم أجد نقاطًا واضحة كفاية. جرّب إعادة صياغة سؤالك.",
            "links": links[:6]
        }

    head = f"سؤالك: {question}\n\nهذا ملخص مُنظَّم من مصادر متعددة:\n"
    body = "\n".join([f"• {b}" for b in clean])
    tail = ""
    if links:
        tail = "\n\nروابط للاستزادة:\n" + "\n".join([f"- {u}" for u in links[:6]])
    return {"answer": head + body + tail, "links": links[:6]}

# ========== الواجهة الموحدة ==========
def smart_answer(question: str) -> Tuple[str, Dict]:
    """
    يُرجع (الجواب، بيانات ميتا مثل الروابط/الوضع).
    المسار:
      1) Q/A محلية — إن كان التطابق قويًا
      2) بحث متعدد المصادر (مع ديب ويب قانوني) + تلخيص
      3) fallback باقتراح أقرب سؤال محلي
    """
    q = (question or "").strip()
    if not q:
        return "لم أستلم سؤالًا.", {"mode": "invalid"}

    # 1) قاعدة المعرفة
    doc, score = local_search(q)
    if doc and score >= 85:  # تطابق قوي
        return doc["a"], {"mode": "local", "score": score, "match": doc["q"]}

    # 2) الويب (سطح + ديب ويب قانوني)
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
