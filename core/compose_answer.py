# core/compose_answer.py — توليد إجابة من نتائج الويب
from typing import List, Dict

def _pick_clean_lines(text: str, max_lines: int = 6) -> List[str]:
    lines = [l.strip(" .\t\r\n") for l in text.splitlines()]
    lines = [l for l in lines if 15 <= len(l) <= 220]
    seen, uniq = set(), []
    for l in lines:
        if l not in seen:
            seen.add(l)
            uniq.append(l)
            if len(uniq) >= max_lines:
                break
    return uniq

def compose_answer_ar(question: str, results: List[Dict]) -> Dict:
    bullets, links = [], []
    for r in results[:6]:
        snip = (r.get("snippet") or "").strip()
        title = (r.get("title") or "").strip()
        link = (r.get("link") or "").strip()
        if link: links.append(link)
        if title and 15 <= len(title) <= 140:
            bullets.append(title)
        bullets.extend(_pick_clean_lines(snip, max_lines=3))
    clean = []
    seen = set()
    for b in bullets:
        if b not in seen:
            seen.add(b)
            clean.append(b)
            if len(clean) >= 8:
                break
    if not clean:
        return {"answer": "لم أجد نقاطًا واضحة من الويب، جرّب إعادة صياغة السؤال.", "links": links[:5]}
    body = "\n".join([f"• {b}" for b in clean])
    tail = "\n\n📚 روابط مفيدة:\n" + "\n".join([f"- {u}" for u in links[:5]]) if links else ""
    return {"answer": f"سؤالك: {question}\n\nهذا ملخّص من الويب:\n{body}{tail}", "links": links[:5]}
