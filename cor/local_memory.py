# core/local_memory.py
import os

DATA_FILE = os.path.join("data", "knowledge.txt")

def local_search(question: str) -> str:
    if not os.path.exists(DATA_FILE):
        return ""
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        content = f.read().lower()
    q = question.lower()
    # بحث بسيط عن وجود كلمات السؤال في قاعدة المعرفة
    if any(word in content for word in q.split()):
        lines = [line.strip() for line in content.splitlines() if q.split()[0] in line]
        if lines:
            return "\n".join(lines[:5])
    return ""
