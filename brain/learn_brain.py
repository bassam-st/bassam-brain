# brain/learn_brain.py
from __future__ import annotations
from typing import List, Dict, Optional
from .memory_manager import MemoryManager
from .analyzer import analyze_query

mm = MemoryManager()

def learn_from_interaction(query: str, sources: List[Dict], answer: str, extra_facts: Optional[List[str]] = None) -> Dict:
    """
    يُستدعى بعد توليد الجواب.
    - يحفظ أهم النقاط من المصادر والجواب في الذاكرة.
    - يربطها بالكلمات المفتاحية للسؤال.
    """
    a = analyze_query(query)
    tags = ["user", a["intent"], a["lang"]] + a.get("key_phrases", [])
    saved_ids = []

    # حفظ مقتطفات من المصادر
    for s in sources or []:
        snippet = (s.get("snippet") or s.get("content") or s.get("title") or "")[:300]
        if snippet.strip():
            saved_ids.append(mm.add_fact(snippet, source=s.get("url",""), tags=tags))

    # حفظ ملخص من الإجابة نفسها
    if answer:
        brief = (answer[:400] + ("…" if len(answer)>400 else ""))
        saved_ids.append(mm.add_fact(brief, source="model", tags=tags))

    # حقن حقائق إضافية (إن وُجدت)
    for f in (extra_facts or []):
        if f.strip():
            saved_ids.append(mm.add_fact(f, source="extra", tags=tags))

    return {"saved": saved_ids, "tags": tags}
