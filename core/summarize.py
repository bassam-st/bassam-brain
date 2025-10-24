from langdetect import detect
from rapidfuzz import fuzz
from typing import List

def smart_summarize(question: str, texts: List[str], max_bullets: int = 6) -> str:
    """
    تلخيص عربي مبسّط:
    - يلتقط الجُمل الأقرب للسؤال
    - يدمج النتائج في نقاط عربية قصيرة
    """
    lines = []
    for t in texts:
        if not t:
            continue
        for sent in t.split("\n"):
            s = sent.strip()
            if 10 <= len(s) <= 220:
                score = fuzz.partial_ratio(question, s)
                if score >= 40:
                    lines.append((score, s))
    if not lines:
        for t in texts:
            if t:
                lines = [(0, x.strip()) for x in t.split("\n")[:8] if len(x.strip()) > 10]
                break

    lines = sorted(lines, key=lambda x: x[0], reverse=True)
    picked = []
    seen = set()
    for _, s in lines:
        if s in seen:
            continue
        seen.add(s)
        picked.append(s)
        if len(picked) >= max_bullets:
            break

    if not picked:
        return "لم أجد نصًا كافيًا، جرّب إعادة صياغة سؤالك أو أضف كلمة مفتاحية."

    try:
        lang = detect(" ".join(picked))
    except Exception:
        lang = "ar"
    bullet = "• "
    joiner = "\n"
    answer = joiner.join(f"{bullet}{p}" for p in picked)
    if lang != "ar":
        answer = joiner.join(f"{bullet}{p}" for p in picked)
    return answer
