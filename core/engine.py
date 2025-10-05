import os, time, math, urllib.parse
import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")       # اختياري
GOOGLE_CX      = os.getenv("GOOGLE_CX")            # اختياري
BING_API_KEY   = os.getenv("BING_API_KEY")         # اختياري

USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)

class SearchResult:
    def __init__(self, sources, texts, elapsed_ms, page, pages):
        self.sources = sources  # list of {title,url,site}
        self.texts = texts      # list of raw texts
        self.elapsed_ms = elapsed_ms
        self.page = page
        self.pages = pages

async def smart_search(q: str, page: int = 1, per_page: int = 10) -> SearchResult:
    """
    ترتيب الأولوية:
    1) Google CSE (إذا متوفر مفتاح)
    2) Bing Web Search (إذا متوفر مفتاح)
    3) Wikipedia (مباشر)
    4) DuckDuckGo (مجاني)
    """
    t0 = time.time()
    all_hits = []

    # 1) Google programmable search API
    if GOOGLE_API_KEY and GOOGLE_CX:
        try:
            start = (page - 1) * per_page + 1
            url = (
                "https://www.googleapis.com/customsearch/v1?"
                f"key={GOOGLE_API_KEY}&cx={GOOGLE_CX}&q={urllib.parse.quote(q)}&start={start}"
            )
            async with httpx.AsyncClient(timeout=15, headers={"User-Agent": USER_AGENT}) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    data = r.json()
                    items = data.get("items", [])
                    for it in items:
                        all_hits.append({
                            "title": it.get("title", "")[:200],
                            "url": it.get("link"),
                            "site": urllib.parse.urlparse(it.get("link","")).netloc,
                        })
        except Exception:
            pass

    # 2) Bing (اختياري)
    if len(all_hits) < per_page and BING_API_KEY:
        try:
            start = (page - 1) * per_page
            endpoint = "https://api.bing.microsoft.com/v7.0/search"
            params = {"q": q, "count": per_page, "offset": start}
            headers = {"Ocp-Apim-Subscription-Key": BING_API_KEY, "User-Agent": USER_AGENT}
            async with httpx.AsyncClient(timeout=15, headers=headers) as client:
                r = await client.get(endpoint, params=params)
                if r.status_code == 200:
                    web = r.json().get("webPages", {}).get("value", [])
                    for it in web:
                        all_hits.append({
                            "title": it.get("name", "")[:200],
                            "url": it.get("url"),
                            "site": urllib.parse.urlparse(it.get("url","")).netloc,
                        })
        except Exception:
            pass

    # 3) Wikipedia (AR + EN)
    if len(all_hits) < per_page:
        for lang in ("ar", "en"):
            try:
                api = f"https://{lang}.wikipedia.org/w/api.php"
                params = {
                    "action": "query",
                    "list": "search",
                    "srsearch": q,
                    "utf8": 1,
                    "format": "json",
                    "srlimit": 3,
                }
                async with httpx.AsyncClient(timeout=15, headers={"User-Agent": USER_AGENT}) as client:
                    r = await client.get(api, params=params)
                    data = r.json()
                    for s in data.get("query", {}).get("search", []):
                        title = s["title"]
                        url = f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                        all_hits.append({"title": f"{title} - ويكيبيديا", "url": url, "site": f"{lang}.wikipedia.org"})
            except Exception:
                pass
            if len(all_hits) >= per_page:
                break

    # 4) DuckDuckGo (fallback مجاني قوي)
    if len(all_hits) < per_page:
        try:
            with DDGS() as ddgs:
                start = (page - 1) * per_page
                res = ddgs.text(q, max_results=start + per_page)
                res = list(res)[start:start + per_page]
                for it in res:
                    all_hits.append({
                        "title": it.get("title","")[:200],
                        "url": it.get("href"),
                        "site": urllib.parse.urlparse(it.get("href","")).netloc,
                    })
        except Exception:
            pass

    # إزالة التكرار مع الحفاظ على الترتيب
    seen = set()
    uniq = []
    for h in all_hits:
        u = h.get("url")
        if not u or u in seen:
            continue
        seen.add(u)
        uniq.append(h)

    # قصّ حسب الصفحة
    hits = uniq[:per_page]
    pages = max(1, math.ceil(len(uniq) / per_page))

    # جلب النصوص (readability)
    texts = await fetch_texts([h["url"] for h in hits])

    elapsed = int((time.time() - t0) * 1000)
    return SearchResult(hits, texts, elapsed, page=page, pages=pages)

async def fetch_texts(urls: list[str]) -> list[str]:
    from readability import Document
    texts = []
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": USER_AGENT}) as client:
        for u in urls:
            try:
                r = await client.get(u)
                html = r.text
                doc = Document(html)
                summary_html = doc.summary()
                soup = BeautifulSoup(summary_html, "lxml")
                text = soup.get_text(separator="\n", strip=True)
                texts.append(text[:5000])
            except Exception:
                texts.append("")
    return texts
