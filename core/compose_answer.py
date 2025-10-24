from core.utils import ensure_arabic
# core/compose_answer.py — تركيب إجابات ذكية من نتائج الويب
from typing import List, Dict

def _pick_clean_lines(text: str, max_lines: int = 6) -> List[str]:
    if not text: return []
    lines = [l.strip(" .\t\r\n") for l in text.splitlines()]
    lines = [l for l in lines if 15 <= len(l) <= 220]
    seen, uniq = set(), []
    for l in lines:
        if l not in seen:
            uniq.append(l); seen.add(l)
            if len(uniq) >= max_lines: break
    return uniq

def compose_answer_ar(question: str, results: List[Dict]) -> Dict:
    bullets, links = [], []
    for r in results[:6]:
        snip, title, link = (r.get("snippet") or ""), (r.get("title") or ""), (r.get("link") or "")
        if link: links.append(link)
        if title and 15 <= len(title) <= 120: bullets.append(title)
        bullets.extend(_pick_clean_lines(snip, 2))

    seen, clean = set(), []
    for b in bullets:
        if b not in seen:
            clean.append(b); seen.add(b)
        if len(clean) >= 8: break

    if not clean:
        return {"answer": "لم أستطع استخراج نقاط مفيدة من الويب.", "links": links[:5]}

    answer = f"سؤالك: {question}\n\nإليك ملخصًا ذكيًا من الويب:\n" + "\n".join([f"• {x}" for x in clean])
    if links:
        answer += "\n\n📎 روابط للاستزادة:\n" + "\n".join([f"- {u}" for u in links[:5]])
    return {"answer": answer, "links": links[:5]}
