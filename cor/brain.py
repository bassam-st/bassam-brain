# core/brain.py
import httpx
from duckduckgo_search import DDGS
from core.compose_answer import compose_answer_ar
from core.local_memory import local_search

async def ask_brain(question: str):
    # 1. محاولة البحث في الذاكرة المحلية (ملفات ومعرفة سابقة)
    local_results = local_search(question)
    if local_results:
        return {"answer": local_results, "links": []}

    # 2. البحث في الإنترنت إذا لم توجد إجابة محلية
    web_results = []
    async with httpx.AsyncClient(timeout=15) as client:
        with DDGS() as ddgs:
            for r in ddgs.text(question, max_results=6):
                web_results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "link": r.get("href", "")
                })
    # 3. تركيب الإجابة النهائية
    final = compose_answer_ar(question, web_results)
    return final
