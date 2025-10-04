# core/compose_answer.py
from typing import List, Dict

def _pick_clean_lines(text: str, max_lines: int = 6) -> List[str]:
    if not text:
        return []
    lines = [l.strip(" .\t\r\n") for l in text.splitlines()]
    lines = [l for l in lines if 15 <= len(l) <= 220]
    seen, uniq = set(), []
    for l in lines:
        if l in seen:
            continue
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
        if link:
            links.append(link)
        if title and 15 <= len(title) <= 140:
            bullets.append(title)
        bullets.extend(_pick_clean_lines(snip, max_lines=3))

    seen, clean = set(), []
    for b in bullets:
        if b and b not in seen:
            seen.add(b)
            clean.append(b)
        if len(clean) >= 8:
            break

    if not clean:
        return {"answer": "لم أجد نقاطًا واضحة، جرّب إعادة صياغة سؤالك.", "links": links[:5]}

    header = f"سؤالك: {question}\n\nملخص ذكي من الويب:\n"
    body = "\n".join([f"• {b}" for b in clean])
    tail = "\n\nروابط للمزيد:\n" + "\n".join([f"- {u}" for u in links[:5]])
    return {"answer": header + body + tail, "links": links[:5]}
