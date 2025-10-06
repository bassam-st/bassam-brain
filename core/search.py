from duckduckgo_search import DDGS
import requests
from bs4 import BeautifulSoup

def google_search(query, num_results=5):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = f"https://www.google.com/search?q={query}"
        r = requests.get(url, headers=headers)
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for g in soup.select("div.yuRUbf a")[:num_results]:
            link = g["href"]
            results.append(link)
        return results
    except Exception as e:
        print("Google search error:", e)
        return []

def duckduckgo_search(query, num_results=5):
    try:
        with DDGS() as ddgs:
            results = [r["href"] for r in ddgs.text(query, max_results=num_results)]
        return results
    except Exception as e:
        print("DuckDuckGo search error:", e)
        return []

def deep_search(query):
    # أولًا جرّب جوجل
    google_results = google_search(query)
    if google_results:
        print("✅ Using Google search results")
        return google_results

    # إذا لم يوجد، استخدم ديك دي جو
    print("🔄 Fallback to DuckDuckGo")
    ddg_results = duckduckgo_search(query)
    return ddg_results
# core/search.py — Bassam الذكي / ALSHOTAIMI v13.6

import httpx, re
from bs4 import BeautifulSoup
from readability import Document
from duckduckgo_search import DDGS
from diskcache import Cache

cache = Cache("cache")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36"
}

# 🔎 دالة البحث الرئيسية
async def deep_search(query: str):
    query = query.strip()
    cache_key = f"search:{query}"

    # التحقق من الكاش (تخزين سابق)
    if cache_key in cache:
        return cache[cache_key]

    results = []
    with DDGS() as ddgs:
        search_results = [r for r in ddgs.text(query, max_results=5)]
        for r in search_results:
            link = r.get("href") or r.get("url")
            title = r.get("title", "")
            if not link:
                continue
            text = await fetch_and_clean(link)
            if text:
                results.append({
                    "title": title,
                    "link": link,
                    "summary": text[:1000]
                })

    # حفظ النتائج في الكاش
    cache[cache_key] = results
    return results


# 🧹 تنظيف صفحات الويب
async def fetch_and_clean(url: str):
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=10.0) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return ""
            doc = Document(r.text)
            html = doc.summary()
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator="\n")
            text = re.sub(r"\n+", "\n", text).strip()
            return text
    except Exception:
        return ""
