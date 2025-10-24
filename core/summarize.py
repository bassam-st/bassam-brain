from rapidfuzz import fuzz

def smart_summarize(question: str, texts: list[str], max_bullets: int = 6) -> str:
    lines = []
    for t in texts or []:
        for sent in (t or "").split("\n"):
            s = sent.strip()
            if 10 <= len(s) <= 220:
                score = fuzz.partial_ratio(question, s)
                if score >= 40:
                    lines.append((score, s))
    if not lines:
        for t in texts or []:
            if t:
                lines = [(0, x.strip()) for x in t.split("\n")[:8] if len(x.strip()) > 10]
                break
    lines = sorted(lines, key=lambda x: x[0], reverse=True)
    picked, seen = [], set()
    for _, s in lines:
        if s in seen: continue
        seen.add(s); picked.append(s)
        if len(picked) >= max_bullets: break
    if not picked:
        return "لم أجد نصًا كافيًا، جرّب إعادة صياغة سؤالك أو أضف كلمة مفتاحية."
    return "\n".join(f"• {p}" for p in picked)
