# core/search.py
# Bassam الذكي — بحث عميق (Google أولاً ثم DuckDuckGo)

import httpx
from bs4 import BeautifulSoup
from readability import Document
from duckduckgo_search import DDGS


def google_search(query, max_results=5):
    """
    البحث الأساسي من Google
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        )
    }
    url = f"https://www.google.com/search?q={query}&num={max_results}"

    results = []
    try:
        with httpx.Client(headers=headers, timeout=10.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            for g in soup.select("div.g"):
                title_el = g.find("h3")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                link_tag = g.find("a", href=True)
                link = link_tag["href"] if link_tag else ""
                if link.startswith("http"):
                    results.append({"title": title, "link": link})

    except Exception as e:
        print("Google search error:", e)

    return results


def duckduckgo_search_fallback(query, max_results=5):
    """
    البحث الاحتياطي من DuckDuckGo
    """
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({"title": r["title"], "link": r["href"]})
    except Exception as e:
        print("DuckDuckGo search error:", e)
    return results


def deep_search(query):
    """
    بحث عميق يبدأ من Google ثم ينتقل إلى DuckDuckGo عند الحاجة
    """
    print(f"🔍 بدء البحث عن: {query}")

    results = google_search(query)
    if not results:
        print("⚠️ لم يتم العثور على نتائج من Google — الانتقال إلى DuckDuckGo...")
        results = duckduckgo_search_fallback(query)

    print(f"✅ عدد النتائج التي تم إيجادها: {len(results)}")
    return results
