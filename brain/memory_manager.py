# brain/memory_manager.py
from __future__ import annotations
import json, os, time
from typing import List, Dict

DEFAULT_PATH = "data/memory.json"

class MemoryManager:
    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f: json.dump({"facts": []}, f, ensure_ascii=False)

    def _load(self) -> Dict:
        with open(self.path, "r", encoding="utf-8") as f: return json.load(f)

    def _save(self, data: Dict) -> None:
        with open(self.path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

    def add_fact(self, content: str, source: str = "", tags: List[str] = None) -> str:
        data = self._load()
        fact = {
            "id": f"m{int(time.time()*1000)}",
            "content": content.strip(),
            "source": source,
            "tags": tags or [],
            "ts": int(time.time())
        }
        # منع التكرار البسيط
        if not any(f["content"] == fact["content"] for f in data["facts"]):
            data["facts"].append(fact); self._save(data)
        return fact["id"]

    def search(self, query: str, limit: int = 5) -> List[Dict]:
        q = query.lower().strip()
        data = self._load()
        scored = []
        for f in data["facts"]:
            text = (f["content"]+" "+" ".join(f["tags"])).lower()
            score = sum(w in text for w in q.split())
            if score>0: scored.append((score, f))
        scored.sort(key=lambda x: (-x[0], -x[1]["ts"]))
        return [f for _,f in scored[:limit]]

    def all(self) -> List[Dict]:
        return self._load()["facts"]
