# core/search_web.py — البحث الذكي في الويب
import httpx, re
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

def web_search(query: str, max_results: int = 5):
    """
    بحث مجاني عبر DuckDuckGo وإرجاع النصوص المفيدة (العربية أولًا).
    """
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, region="xa-ar", safesearch="moderate", max_results=max_results):
                if not r.get("body"): continue
                results.append({
                    "title": r.get("title",""),
                    "snippet": r.get("body",""),
                    "link": r.get("href","")
                })
    except Exception as e:
        results.append({"title":"خطأ في البحث","snippet":str(e),"link":""})
    return results

def summarize_snippets(snippets):
    """
    تلخيص مبسط للنصوص المسترجعة.
    """
    text = " ".join([r["snippet"] for r in snippets])
    sents = re.split(r"[.!؟\n]", text)
    sents = [s.strip() for s in sents if 15 < len(s.strip()) < 200]
    unique = []
    for s in sents:
        if s not in unique:
            unique.append(s)
    return "، ".join(unique[:5]) if unique else "لم يتم العثور على إجابة مباشرة، حاول صياغة سؤالك بشكل آخر."
