# core/search_engines.py
from __future__ import annotations
from typing import List, Dict
import os, urllib.parse as u
import httpx
from duckduckgo_search import DDGS

HEADERS = {"User-Agent": "BassamBrain/1.0 (+https://render.com)"}

def _pack(title: str, snippet: str, link: str) -> Dict:
    return {"title": (title or "").strip(),
            "snippet": (snippet or "").strip(),
            "link": (link or "").strip()}

async def google_search(q: str, n: int = 6) -> List[Dict]:
    key = os.getenv("GOOGLE_API_KEY")
    cx  = os.getenv("GOOGLE_CSE_ID")
    if not key or not cx:
        return []
    url = "https://www.googleapis.com/customsearch/v1"
    params = {"q": q, "key": key, "cx": cx, "num": min(n,10), "hl": "ar"}
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as cli:
        r = await cli.get(url, params=params)
        r.raise_for_status()
        items = r.json().get("items", []) or []
        out = []
        for it in items:
            out.append(_pack(it.get("title",""), it.get("snippet",""), it.get("link","")))
        return out

async def bing_search(q: str, n: int = 6) -> List[Dict]:
    key = os.getenv("BING_API_KEY")
    if not key:
        return []
    url = "https://api.bing.microsoft.com/v7.0/search"
    params = {"q": q, "count": n, "mkt": "ar", "setLang": "ar"}
    async with httpx.AsyncClient(timeout=15, headers={**HEADERS, "Ocp-Apim-Subscription-Key": key}) as cli:
        r = await cli.get(url, params=params)
        r.raise_for_status()
        web = (r.json().get("webPages") or {}).get("value", []) or []
        out = []
        for it in web:
            out.append(_pack(it.get("name",""), it.get("snippet",""), it.get("url","")))
        return out

async def wikipedia_search(q: str, n: int = 4) -> List[Dict]:
    # API الرسمي
    url = "https://ar.wikipedia.org/w/api.php"
    params = {"action": "query", "list": "search", "srsearch": q,
              "utf8": 1, "format": "json", "srlimit": n}
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as cli:
        r = await cli.get(url, params=params)
        r.raise_for_status()
        data = r.json().get("query", {}).get("search", []) or []
        out = []
        for it in data:
            title = it.get("title","")
            link  = f"https://ar.wikipedia.org/wiki/{u.quote(title.replace(' ', '_'))}"
            snippet = it.get("snippet","").replace("<span class=\"searchmatch\">","").replace("</span>","")
            out.append(_pack(title, snippet, link))
        return out

async def ddg_fallback(q: str, n: int = 6) -> List[Dict]:
    out = []
    with DDGS() as d:
        for r in d.text(q, max_results=n):
            out.append(_pack(r.get("title",""), r.get("body",""), r.get("href","")))
    return out

# روابط بحث اجتماعي (لا تتطلب مفاتيح)
def social_search_links(name: str) -> Dict[str, str]:
    q = u.quote(name.strip())
    return {
        "Google":      f"https://www.google.com/search?q={q}",
        "Twitter/X":   f"https://twitter.com/search?q={q}&f=user",
        "Facebook":    f"https://www.facebook.com/search/people/?q={q}",
        "Instagram":   f"https://www.instagram.com/explore/search/keyword/?q={q}",
        "TikTok":      f"https://www.tiktok.com/search/user?q={q}",
        "LinkedIn":    f"https://www.linkedin.com/search/results/people/?keywords={q}",
        "Telegram":    f"https://t.me/s/{q}",
        "Reddit":      f"https://www.reddit.com/search/?q={q}",
        "YouTube":     f"https://www.youtube.com/results?search_query={q}",
    }
