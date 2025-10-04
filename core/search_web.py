# core/search_web.py — محرك بحث ويب ذكي
from duckduckgo_search import DDGS
from bs4 import BeautifulSoup
import httpx

async def web_search(query: str, max_results: int = 8):
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title": r.get("title",""),
                "snippet": r.get("body",""),
                "link": r.get("href","")
            })
    return results

def summarize_snippets(results):
    texts = [r["snippet"] for r in results if r.get("snippet")]
    joined = " ".join(texts)
    words = joined.split()
    if len(words) > 180:
        joined = " ".join(words[:180]) + "..."
    return joined
