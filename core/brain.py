# core/brain.py
# العقل المزدوج (مجاني) — بحث متعدد المصادر + تلخيص + ذاكرة محلية
# المصادر: DuckDuckGo + Bing + Wikipedia + Hacker News + Stack Overflow + RSS (+ Nitter اختياري)

from typing import List, Dict, Tuple, Optional
from pathlib import Path
import os, re, json, urllib.parse

import httpx
from bs4 import BeautifulSoup
from rapidfuzz import fuzz, process
from duckduckgo_search import DDGS
import feedparser

# ------------------------ إعدادات عامة ------------------------
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
KB_FILE = DATA_DIR / "knowledge.txt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
HTTP_TIMEOUT = httpx.Timeout(12.0, connect=12.0)
MAX_RESULTS_PER_ENGINE = 5

# ------------------------ تهيئة قاعدة المعرفة -----------------
if not KB_FILE.exists():
    KB_FILE.write_text(
        "سؤال: ما فوائد القراءة؟\n"
        "جواب: القراءة توسّع المدارك وتقوّي الخيال وتزيد الثقافة.\n"
        "---\n",
        encoding="utf-8"
    )

# ------------------------ أدوات عربية بسيطة -------------------
AR_DIAC  = re.compile(r'[\u064B-\u0652]')
TOKEN_RE = re.compile(r'[A-Za-z\u0621-\u064A0-9]+')

def normalize_ar(s: str) -> str:
    s = s or ""
    s = AR_DIAC.sub("", s)
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    s = s.replace("گ", "ك").replace("پ", "ب").replace("ڤ", "ف")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def tokens(s: str) -> List[str]:
    return TOKEN_RE.findall(normalize_ar(s))

def is_arabic(text: str) -> bool:
    return bool(re.search(r'[\u0600-\u06FF]', text or ""))

# ------------------------ تحميل Q/A ----------------------------
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

# ------------------------ أدوات مساعدة للروابط -----------------
def unredirect_ddg(url: str) -> str:
    """إزالة تحويلة DuckDuckGo (uddg=) إن وجدت."""
    if not url:
        return url
    try:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        if "uddg" in qs and qs["uddg"]:
            return urllib.parse.unquote(qs["uddg"][0])
    except Exception:
        pass
    return url

def clean_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return u
    u = unredirect_ddg(u)
    # إزالة تتبّعات شائعة
    for k in ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ved"]:
        u = re.sub(rf"([?&]){k}=[^&#]+", r"\1", u)
    u = u.rstrip("?&")
    return u

# ------------------------ محرك DuckDuckGo ----------------------
def search_duckduckgo(query: str, k: int = MAX_RESULTS_PER_ENGINE) -> List[Dict]:
    out = []
    with DDGS() as dd:
        for r in dd.text(query, max_results=k):
            out.append({
                "title": (r.get("title") or "").strip(),
                "snippet": (r.get("body") or "").strip(),
                "link": clean_url(r.get("href") or ""),
                "src": "DuckDuckGo"
            })
    return out

# ------------------------ محرك Bing (Scrape) -------------------
def search_bing(query: str, k: int = MAX_RESULTS_PER_ENGINE) -> List[Dict]:
    url = "https://www.bing.com/search?q=" + urllib.parse.quote(query)
    out: List[Dict] = []
    try:
        with httpx.Client(headers=HEADERS, timeout=HTTP_TIMEOUT, follow_redirects=True) as cx:
            resp = cx.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.select("li.b_algo h2 a")[:k]:
                title = (a.get_text() or "").strip()
                link = clean_url(a.get("href") or "")
                desc_el = a.find_parent("li").select_one("div.b_caption p")
                snippet = (desc_el.get_text().strip() if desc_el else "")
                if title and link:
                    out.append({"title": title, "snippet": snippet, "link": link, "src": "Bing"})
    except Exception:
        pass
    return out

# ------------------------ Wikipedia API ------------------------
def search_wikipedia(query: str, k: int = 3) -> List[Dict]:
    lang = "ar" if is_arabic(query) else "en"
    api = f"https://{lang}.wikipedia.org/w/api.php"
    params = {"action": "opensearch", "search": query, "limit": str(k), "namespace": "0", "format": "json"}
    out: List[Dict] = []
    try:
        with httpx.Client(headers=HEADERS, timeout=HTTP_TIMEOUT) as cx:
            r = cx.get(api, params=params)
            r.raise_for_status()
            data = r.json()
            titles = data[1] if len(data) > 1 else []
            descs  = data[2] if len(data) > 2 else []
            links  = data[3] if len(data) > 3 else []
            for t, d, u in zip(titles, descs, links):
                out.append({"title": t.strip(), "snippet": (d or "").strip(), "link": clean_url(u or ""), "src": "Wikipedia"})
    except Exception:
        pass
    return out

# ------------------------ Hacker News (Algolia API) --------------------------
def search_hackernews(query: str, k: int = 5) -> List[Dict]:
    url = "https://hn.algolia.com/api/v1/search"
    out: List[Dict] = []
    try:
        with httpx.Client(headers=HEADERS, timeout=HTTP_TIMEOUT) as cx:
            r = cx.get(url, params={"query": query, "hitsPerPage": str(k)})
            r.raise_for_status()
            data = r.json()
            for h in data.get("hits", [])[:k]:
                title = (h.get("title") or h.get("story_title") or "").strip()
                link = (h.get("url") or h.get("story_url") or "").strip()
                if title and link:
                    out.append({
                        "title": title,
                        "snippet": (h.get("story_text") or "")[:180],
                        "link": clean_url(link),
                        "src": "HackerNews"
                    })
    except Exception:
        pass
    return out

# ------------------------ Stack Overflow (StackExchange API) -----------------
def search_stackoverflow(query: str, k: int = 5) -> List[Dict]:
    url = "https://api.stackexchange.com/2.3/search/advanced"
    out: List[Dict] = []
    try:
        with httpx.Client(headers=HEADERS, timeout=HTTP_TIMEOUT) as cx:
            r = cx.get(url, params={
                "order": "desc",
                "sort": "relevance",
                "q": query,
                "site": "stackoverflow",
                "pagesize": str(k)
            })
            r.raise_for_status()
            data = r.json()
            for item in data.get("items", [])[:k]:
                title = (item.get("title") or "").strip()
                link  = clean_url(item.get("link") or "")
                if title and link:
                    out.append({
                        "title": title,
                        "snippet": "سؤال/إجابة من StackOverflow",
                        "link": link,
                        "src": "StackOverflow"
                    })
    except Exception:
        pass
    return out

# ------------------------ RSS عام (قابل للتخصيص) ----------------------------
DEFAULT_RSS_FEEDS = [
    "https://news.ycombinator.com/rss",
    "https://arstechnica.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://www.aljazeera.net/aljazeeraalarabiaportal/rss",
    "https://www.wired.com/feed/rss",
]

def search_rss(query: str, feeds: Optional[List[str]] = None, k: int = 5) -> List[Dict]:
    feeds = feeds or DEFAULT_RSS_FEEDS
    out: List[Dict] = []
    qn = normalize_ar(query).lower()
    try:
        for feed_url in feeds:
            fp = feedparser.parse(feed_url)
            for entry in fp.entries[:20]:
                title = normalize_ar((getattr(entry, "title", "") or "")).strip()
                summary = normalize_ar((getattr(entry, "summary", "") or "")).strip()
                link = clean_url((getattr(entry, "link", "") or "").strip())
                text = f"{title} {summary}".lower()
                if title and link and any(w in text for w in qn.split()):
                    out.append({
                        "title": title,
                        "snippet": summary[:180],
                        "link": link,
                        "src": "RSS"
                    })
                if len(out) >= k:
                    break
            if len(out) >= k:
                break
    except Exception:
        pass
    return out

# ------------------------ (اختياري) Nitter (بديل تويتر) ---------------------
# فعّل بتحديد NITTER_URL كمتغير بيئة (مثال: https://nitter.net)
def search_nitter(query: str, k: int = 5) -> List[Dict]:
    base = os.getenv("NITTER_URL", "").rstrip("/")
    out: List[Dict] = []
    if not base:
        return out
    try:
        q = urllib.parse.quote(query)
        url = f"{base}/search?f=tweets&q={q}"
        with httpx.Client(headers=HEADERS, timeout=HTTP_TIMEOUT, follow_redirects=True) as cx:
            resp = cx.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            for art in soup.select("div.timeline-item")[:k]:
                content = art.select_one(".tweet-content")
                snippet = (content.get_text(" ", strip=True) if content else "")[:200]
                link_el = art.select_one("a.tweet-date")
                link = clean_url(urllib.parse.urljoin(base, link_el.get("href"))) if link_el else ""
                if snippet and link:
                    out.append({
                        "title": snippet[:80] + ("…" if len(snippet) > 80 else ""),
                        "snippet": snippet,
                        "link": link,
                        "src": "Nitter"
                    })
    except Exception:
        pass
    return out

# ------------------------ دمج النتائج وتلخيص -------------------
def _clean_lines(text: str, max_lines: int = 2) -> List[str]:
    if not text: return []
    lines = [l.strip(" .\t\r\n") for l in text.splitlines() if l.strip()]
    lines = [l for l in lines if 15 <= len(l) <= 220]
    out, seen = [], set()
    for l in lines:
        if l in seen: continue
        seen.add(l); out.append(l)
        if len(out) >= max_lines: break
    return out

def multi_search(query: str) -> List[Dict]:
    """تجميع نتائج من عدة محرّكات/مصادر مجانية."""
    results: List[Dict] = []
    # محرّكات عامة
    try: results += search_duckduckgo(query)
    except Exception: pass
    try: results += search_bing(query)
    except Exception: pass
    # موسوعي
    try: results += search_wikipedia(query)
    except Exception: pass
    # تقني/مجتمعي
    try: results += search_hackernews(query)
    except Exception: pass
    try: results += search_stackoverflow(query)
    except Exception: pass
    # أخبار عامة عبر RSS
    try: results += search_rss(query)
    except Exception: pass
    # (اختياري) شبكات اجتماعية عبر Nitter
    try: results += search_nitter(query)
    except Exception: pass

    # إزالة التكرارات حسب الرابط
    seen, uniq = set(), []
    for r in results:
        u = r.get("link") or ""
        if u and u not in seen:
            seen.add(u); uniq.append(r)
    return uniq[:20]

def compose_web_answer(question: str, results: List[Dict]) -> Dict:
    bullets, links = [], []
    for r in results:
        t = (r.get("title") or "").strip()
        s = (r.get("snippet") or "").strip()
        u = r.get("link") or ""
        if u: links.append(u)
        if 10 <= len(t) <= 140: bullets.append(t)
        bullets.extend(_clean_lines(s, max_lines=1))

    clean, seen = [], set()
    for b in bullets:
        if not b or b in seen: continue
        seen.add(b); clean.append(b)
        if len(clean) >= 10: break

    if not clean:
        return {
            "answer": "بحثت في الويب ولم أحصل على نقاط واضحة. جرّب إعادة الصياغة أو أضف تفاصيل.",
            "links": [clean_url(u) for u in links[:5]]
        }

    head = f"سؤالك: {question}\n\nملخص من عدّة مصادر:\n"
    body = "\n".join([f"• {b}" for b in clean])

    uniq_links = []
    for u in links:
        u = clean_url(u)
        if u and u not in uniq_links:
            uniq_links.append(u)
        if len(uniq_links) >= 5:
            break
    tail = "\n\nروابط للاستزادة:\n" + "\n".join([f"- {u}" for u in uniq_links]) if uniq_links else ""

    return {"answer": head + body + tail, "links": uniq_links}

# ------------------------ الواجهة الموحدة ----------------------
def smart_answer(question: str) -> Tuple[str, Dict]:
    q = (question or "").strip()
    if not q:
        return "لم أستلم سؤالًا.", {"mode": "invalid"}

    # 1) ذاكرة محلية
    doc, score = local_search(q)
    if doc and score >= 87:
        return doc["a"], {"mode": "local", "score": score, "match": doc["q"]}

    # 2) بحث متعدد المصادر
    results = multi_search(q)
    if results:
        pack = compose_web_answer(q, results)
        return pack["answer"], {"mode": "web", "links": pack.get("links", [])}

    # 3) fallback عند فشل الشبكة
    if doc:
        return (
            f"لم أجد إجابة مؤكدة عبر الويب.\nأقرب سؤال عندي:\n«{doc['q']}»\n"
            f"الجواب المخزن: {doc['a']}\n\n"
            "يمكنك حفظ جواب مُحسّن في القاعدة لتحسين الدقة لاحقًا."
        ), {"mode": "suggest", "score": score}

    return "لا تتوفر معلومات كافية حاليًا. أعد صياغة سؤالك أو أضف س/ج مشابه في قاعدة المعرفة.", {"mode": "none"}

def save_to_knowledge(q: str, a: str) -> None:
    q = (q or "").strip()
    a = (a or "").strip()
    if not q or not a:
        return
    with KB_FILE.open("a", encoding="utf-8") as f:
        f.write(f"\nسؤال: {q}\nجواب: {a}\n---\n")
