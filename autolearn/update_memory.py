# autolearn/update_memory.py
from __future__ import annotations
from typing import List, Dict
from brain.memory_manager import MemoryManager

mm = MemoryManager()

def save_facts(facts: List[Dict]) -> int:
    n = 0
    for f in facts:
        content = f.get("content","").strip()
        if content:
            mm.add_fact(content, source=f.get("source",""), tags=f.get("tags",[]))
            n += 1
    return n
