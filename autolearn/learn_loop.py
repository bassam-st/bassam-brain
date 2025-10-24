# autolearn/learn_loop.py
from __future__ import annotations
from typing import List
from datetime import datetime
from brain.teacher import learn_from_urls
from .web_fetcher import search_web
from .update_memory import save_facts

SEEDS = [
    "الذكاء الاصطناعي اخبار اليوم",
    "Python tips for production",
    "نماذج لامّا محلية gguf",
]

def run_once() -> dict:
    """يشغّل دورة: (بحث كلمات) → (فتح صفحات) → (استخلاص حقائق) → (حفظ الذاكرة)."""
    urls: List[str] = []
    for q in SEEDS:
        for h in search_web(q, max_results=3):
            if h.get("url"): urls.append(h["url"])
    facts = learn_from_urls(urls[:9])
    saved = save_facts(facts)
    return {"time": datetime.utcnow().isoformat()+"Z", "urls": len(urls), "facts": len(facts), "saved": saved}

if __name__ == "__main__":
    # تشغيل يدوي محلي لاختبار الحلقة مرة واحدة
    print(run_once())
