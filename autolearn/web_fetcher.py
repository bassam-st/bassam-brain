# autolearn/web_fetcher.py
from __future__ import annotations
from typing import List, Dict
from duckduckgo_search import DDGS

def search_web(query: str, max_results: int = 5) -> List[Dict]:
    with DDGS() as ddgs:
        hits = ddgs.text(query, max_results=max_results)
    out = []
    for h in hits or []:
        out.append({"title": h.get("title",""), "url": h.get("href",""), "snippet": h.get("body","")})
    return out
