# core/brain.py
# Bassam Brain Deep+ with Social Search
# ترتيب البحث العام: Google -> Wikipedia -> Deep (Ahmia + CommonCrawl) -> Bing -> DuckDuckGo
# في حالة طلب اسم/حساب سوشيال: نستخدم بحث مخصص لمنصات التواصل
# يعمل في Render Starter، وبدون مفاتيح مدفوعة

from typing import List, Dict, Tuple
import re, json
import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "ar,en-US;q=0.9,en;q=0.8"}
TIMEOUT = 12  # ثوانٍ

# ====================== أدوات مساعدة ======================
def _clean_text(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"[\u200f\u200e]", "", s)  # RTL/LTR marks
    return s

def _dedupe_keep_order(items: List[str], limit: int) -> List[str]:
    seen, out = set(), []
    for x in items:
        x = (x or "").strip()
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
        if len(out) >= limit:
            break
    return out

def _norm_result(r: Dict) -> Dict:
    return {
        "title": _clean_text(r.get("title", "")),
        "snippet": _clean_text(r.get("snippet", "")),
        "link": (r.get("link", "") or "").strip(),
    }

def _is_valid(r: Dict) -> bool:
    return bool(r.get("title") and r.get("link"))

# ====================== Google ======================
def search_google(query: str, max_results: int = 6) -> List[Dict]:
    url = "https://www.google.com/search"
    params = {"q": query, "hl": "ar"}
    out = []
    try:
        with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")
            for g in soup.select("div.g"):
                a = g.select_one("a")
                h3 = g.select_one("h3")
                if not a or not h3:
                    continue
                title = _clean_text(h3.get_text(" ", strip=True))
                link = a.get("href") or ""
                sn_el = g.select_one("div.VwiC3b, span.aCOpRe")
                snippet = _clean_text(sn_el.get_text(" ", strip=True) if sn_el else "")
                item = _norm_result({"title": title, "snippet": snippet, "link": link})
                if _is_valid(item):
                    out.append(item)
                if len(out) >= max_results:
                    break
    except Exception:
        return []
    return out

# ====================== Wikipedia (Arabic API) ======================
def search_wikipedia(query: str, max_results: int = 6) -> List[Dict]:
    url = "https://ar.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "srlimit": max_results,
        "utf8": 1,
    }
    out = []
    try:
        with httpx.Client(headers=HEADERS, timeout=TIMEOUT) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            data = r.json()
            for it in data.get("query", {}).get("search", []):
                title = _clean_text(it.get("title") or "")
                snippet = _clean_text(re.sub(r"<.*?>", "", it.get("snippet") or ""))
                link = f"https://ar.wikipedia.org/wiki/{title.replace(' ', '_')}"
                item = _norm_result({"title": title, "snippet": snippet, "link": link})
                if _is_valid(item):
                    out.append(item)
                if len(out) >= max_results:
                    break
    except Exception:
        return []
    return out

# ====================== Deep Web (Ahmia) ======================
def search_ahmia(query: str, max_results: int = 6) -> List[Dict]:
    url = "https://ahmia.fi/search/"
    params = {"q": query}
    out = []
    try:
        with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")
            # روابط ظاهرة على الويب (clearnet) تُشير لمحتوى مفهرس لديهم
            for res in soup.select("div#results h4 a"):
                title = _clean_text(res.get_text(" ", strip=True))
                link = (res.get("href") or "").strip()
                if not link:
                    continue
                par = soup.find("p")
                snippet = _clean_text(par.get_text(" ", strip=True)) if par else ""
                item = _norm_result({"title": title, "snippet": snippet, "link": link})
                if _is_valid(item):
                    out.append(item)
                if len(out) >= max_results:
                    break
    except Exception:
        return []
    return out

# ====================== Deep Web (CommonCrawl Index) ======================
def search_commoncrawl(query: str, max_results: int = 6) -> List[Dict]:
    out = []
    api = "https://index.commoncrawl.org/CC-MAIN-2024-10-index"
    params = {"url": f"*{query}*", "output": "json"}
    try:
        with httpx.Client(headers=HEADERS, timeout=TIMEOUT) as c:
            r = c.get(api, params=params)
            if r.status_code != 200:
                return []
            lines = r.text.splitlines()
            for ln in lines[:max_results * 3]:
                try:
                    row = json.loads(ln)
                except Exception:
                    continue
                link = row.get("url", "")
                if not link.startswith(("http://", "https://")):
                    continue
                urlkey = row.get("urlkey", "")
                title = _clean_text(urlkey.split(")")[0].replace(",", " ").replace("_", " "))
                item = _norm_result({"title": title or link, "snippet": "", "link": link})
                if _is_valid(item):
                    out.append(item)
                if len(out) >= max_results:
                    break
    except Exception:
        return []
    return out

# ====================== Bing ======================
def search_bing(query: str, max_results: int = 6) -> List[Dict]:
    url = "https://www.bing.com/search"
    params = {"q": query, "setlang": "ar"}
    out = []
    try:
        with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")
            for li in soup.select("li.b_algo"):
                a = li.select_one("h2 a")
                if not a:
                    continue
                title = _clean_text(a.get_text(" ", strip=True))
                link = a.get("href") or ""
                snippet = _clean_text(li.select_one("p").get_text(" ", strip=True) if li.select_one("p") else "")
                item = _norm_result({"title": title, "snippet": snippet, "link": link})
                if _is_valid(item):
                    out.append(item)
                if len(out) >= max_results:
                    break
    except Exception:
        return []
    return out

# ====================== DuckDuckGo ======================
def search_ddg(query: str, max_results: int = 6) -> List[Dict]:
    out = []
    try:
        with DDGS() as dd:
            for r in dd.text(query, max_results=max_results):
                item = _norm_result({
                    "title": r.get("title") or "",
                    "snippet": r.get("body") or "",
                    "link": r.get("href") or "",
                })
                if _is_valid(item) and "duckduckgo.com/l/?" not in item["link"]:
                    out.append(item)
    except Exception:
        return []
    return out

# ====================== Social Search ======================
SOCIAL_SITES = {
    "X (Twitter)": "site:twitter.com",
    "Instagram": "site:instagram.com",
    "Facebook": "site:facebook.com",
    "YouTube": "site:youtube.com",
    "TikTok": "site:tiktok.com",
    "LinkedIn": "site:linkedin.com",
    "Telegram": "site:t.me",
    "Reddit": "site:reddit.com",
}

SOCIAL_HINTS = [
    "انستغرام","إنستغرام","instagram","انستا",
    "تويتر","x.com","twitter","X",
    "فيسبوك","facebook",
    "يوتيوب","youtube",
    "تيك توك","tiktok",
    "لينكدإن","linkedin",
    "تلغرام","تليجرام","telegram","t.me",
    "رديت","reddit",
    "حساب","username","@","اوجد","ابحث عن","وين حساب",
]

def is_social_query(q: str) -> bool:
    qn = q.lower()
    if any(h.lower() in qn for h in SOCIAL_HINTS):
        return True
    # عامل بسيط: وجود @username أو كلمة "حساب" عربية
    if "@" in q or "حساب" in q:
        return True
    return False

def search_social(name: str, max_per_platform: int = 3) -> List[Dict]:
    """
    نستخدم DuckDuckGo API للبحث المقيد بالموقع لكل منصة.
    """
    results: List[Dict] = []
    with DDGS() as dd:
        for platform, site_q in SOCIAL_SITES.items():
            q = f'{site_q} "{name}"'
            try:
                batch = []
                for r in dd.text(q, max_results=max_per_platform):
                    item = _norm_result({
                        "title": f"[{platform}] " + (r.get("title") or ""),
                        "snippet": r.get("body") or "",
                        "link": r.get("href") or "",
                    })
                    if _is_valid(item):
                        batch.append(item)
                results.extend(batch)
            except Exception:
                continue
    # إزالة تكرارات عامة
    uniq, seen = [], set()
    for r in results:
        key = (r["title"], r["link"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    return uniq

def compose_social_answer(query: str, results: List[Dict]) -> Dict:
    if not results:
        return {
            "answer": f"لم أعثر على حسابات واضحة مرتبطة بـ «{query}». جرّب كتابة الاسم مع دولة/مدينة أو لقب.",
            "links": []
        }
    bullets = []
    links = []
    for r in results:
        t, s, u = r["title"], r.get("snippet", ""), r["link"]
        if u:
            links.append(u)
        if t:
            bullets.append("• " + t)
        if s:
            bullets.append("  – " + s)

    bullets = _dedupe_keep_order(bullets, 18)
    links = _dedupe_keep_order(links, 15)

    head = f"طلبك: البحث عن الحسابات/الملفات المرتبطة بـ «{query}»\n\nنتائج من أكثر منصات السوشيال شيوعًا:\n"
    body = "\n".join(bullets)
    tail = "\n\nروابط مباشرة:\n" + "\n".join([f"- {u}" for u in links]) if links else ""
    return {"answer": head + body + tail, "links": links}

# ====================== خط الأنابيب (ويب عام) ======================
def web_search_pipeline(query: str, max_results: int = 8) -> List[Dict]:
    buckets: List[List[Dict]] = []
    order = [search_google, search_wikipedia, search_ahmia, search_commoncrawl, search_bing, search_ddg]

    for fn in order:
        try:
            res = fn(query, max_results=max_results)
        except Exception:
            res = []
        if res:
            buckets.append(res)
        if len(buckets) >= 2 and sum(len(b) for b in buckets) >= max_results:
            break

    merged: List[Dict] = []
    seen = set()
    for b in buckets:
        for r in b:
            key = (r["title"], r["link"])
            if key in seen:
                continue
            seen.add(key)
            merged.append(r)
            if len(merged) >= max_results:
                break
        if len(merged) >= max_results:
            break

    return merged

def compose_web_answer(question: str, results: List[Dict]) -> Dict:
    bullets, links = [], []
    for r in results:
        t, s, u = r["title"], r.get("snippet", ""), r["link"]
        if u:
            links.append(u)
        if t and 10 <= len(t) <= 140:
            bullets.append("• " + t)
        if s and 20 <= len(s) <= 220:
            bullets.append("  – " + s)

    bullets = _dedupe_keep_order(bullets, 14)
    links   = _dedupe_keep_order(links, 8)

    if not bullets:
        return {
            "answer": f"بحثت عن «{question}» لكن لم تتضح نقاط كافية. جرّب إعادة الصياغة أو أضف تحديدًا أكثر.",
            "links": links
        }

    head = f"سؤالك: {question}\n\nخلاصة من مصادر متعدّدة:\n"
    body = "\n".join(bullets)
    tail = ("\n\nروابط مفيدة:\n" + "\n".join([f"- {u}" for u in links])) if links else ""

    return {"answer": head + body + tail, "links": links}

# ====================== الواجهة لـ app.py ======================
def smart_answer(question: str) -> Tuple[str, Dict]:
    q = (question or "").strip()
    if not q:
        return "لم أستلم سؤالاً.", {"mode": "invalid"}

    # إذا كان المستخدم يطلب حساب/اسم على السوشيال — نفعل نمط السوشيال
    if is_social_query(q):
        soc = search_social(q, max_per_platform=3)
        pack = compose_social_answer(q, soc)
        return pack["answer"], {"mode": "social", "links": pack.get("links", [])}

    # غير ذلك: بحث ويب عام بالترتيب المطلوب
    results = web_search_pipeline(q, max_results=8)
    pack = compose_web_answer(q, results)
    return pack["answer"], {"mode": "web", "links": pack.get("links", [])}
