# core/search.py — Bassam الذكي
# Google CSE → Serper → Google Scrape → DuckDuckGo (+ نصوص الصفحات)

import httpx, re, time
from bs4 import BeautifulSoup
from readability import Document
from duckduckgo_search import DDGS
from typing import List, Dict

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/123.0.0.0 Safari/537.36")

# ---------- Google CSE ----------
async def google_cse(query: str, max_results: int, google_api_key: str, google_cse_id: str) -> List[Dict]:
    if not (google_api_key and google_cse_id):
        raise RuntimeError("Google CSE not configured")
    url = "https://www.googleapis.com/customsearch/v1"
    params = {"key": google_api_key, "cx": google_cse_id, "q": query, "num": min(max_results,10), "hl":"ar","lr":"lang_ar"}
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": UA}) as ax:
        r = await ax.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    out = []
    for it in (data.get("items") or [])[:max_results]:
        out.append({"title": it.get("title"), "link": it.get("link"), "snippet": it.get("snippet"), "source": "Google CSE"})
    return out

# ---------- Serper.dev ----------
async def google_serper(query: str, max_results: int, serper_api_key: str) -> List[Dict]:
    if not serper_api_key:
        raise RuntimeError("Serper not configured")
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": serper_api_key, "Content-Type": "application/json"}
    payload = {"q": query, "num": max_results, "hl": "ar"}
    async with httpx.AsyncClient(timeout=20, headers=headers) as ax:
        r = await ax.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
    out = []
    for it in (data.get("organic") or [])[:max_results]:
        out.append({"title": it.get("title"), "link": it.get("link"), "snippet": it.get("snippet"), "source": "Serper"})
    return out

# ---------- Google Scrape ----------
async def google_scrape(query: str, max_results: int = 5) -> List[Dict]:
    url = f"https://www.google.com/search?q={query}&num={max_results}&hl=ar"
    results: List[Dict] = []
    try:
        async with httpx.AsyncClient(headers={"User-Agent": UA}, timeout=20, follow_redirects=True) as ax:
            resp = await ax.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for g in soup.select("div.g"):
                h3 = g.find("h3")
                if not h3: continue
                a = g.find("a", href=True)
                if not a: continue
                link = a["href"]
                if not link.startswith("http"): continue
                snippet = ""
                sn_el = g.select_one("div.VwiC3b, span.aCOpRe")
                if sn_el:
                    snippet = sn_el.get_text(" ", strip=True)
                results.append({"title": h3.get_text(strip=True), "link": link, "snippet": snippet, "source": "Google"})
                if len(results) >= max_results: break
    except Exception as e:
        print("Google scrape error:", e)
    return results

# ---------- DuckDuckGo ----------
def duckduckgo(query: str, max_results: int = 5) -> List[Dict]:
    out = []
    try:
        with DDGS() as ddgs:
            for attempt in range(2):
                try:
                    for r in ddgs.text(query, region="xa-ar", safesearch="moderate", max_results=max_results):
                        out.append({"title": r.get("title"), "link": r.get("href") or r.get("url"),
                                    "snippet": r.get("body"), "source": "DuckDuckGo"})
                        if len(out) >= max_results: break
                    break
                except Exception as e:
                    print("DuckDuckGo error:", e)
                    time.sleep(3)
    except Exception as e:
        print("DuckDuckGo init error:", e)
    return out

# ---------- بحث موحّد ----------
async def smart_search(
    query: str,
    max_results: int = 8,
    *,
    google_api_key: str = "",
    google_cse_id: str = "",
    serper_api_key: str = "",
) -> Dict:
    query = (query or "").strip()
    try:
        used, results = None, []

        if google_api_key and google_cse_id:
            try:
                results = await google_cse(query, max_results, google_api_key, google_cse_id)
                used = "Google CSE"
            except Exception as e:
                print("Google CSE error:", e)

        if not results and serper_api_key:
            try:
                results = await google_serper(query, max_results, serper_api_key)
                used = "Serper"
            except Exception as e:
                print("Serper error:", e)

        if not results:
            results = await google_scrape(query, max_results=max_results)
            used = "Google" if results else used

        if not results:
            results = duckduckgo(query, max_results=max_results)
            used = "DuckDuckGo" if results else used

        return {"ok": True, "used": used or "NoEngine", "results": results}
    except Exception as e:
        return {"ok": False, "used": None, "results": [], "error": str(e)}

# ---------- جلب نصوص الصفحات (اختياري للتلخيص) ----------
async def deep_fetch_texts(results: List[Dict], max_pages: int = 5) -> List[str]:
    texts: List[str] = []
    headers = {"User-Agent": UA}
    async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as ax:
        for r in (results or [])[:max_pages]:
            url = r.get("link")
            if not url: continue
            try:
                resp = await ax.get(url)
                if resp.status_code >= 400:
                    continue
                doc = Document(resp.text)
                html = doc.summary()
                text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
                text = re.sub(r"\s+", " ", text)
                if len(text) > 80:
                    texts.append(text[:5000])
            except Exception:
                continue
    return texts
