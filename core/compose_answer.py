# core/compose_answer.py
# تركيب إجابة عربية نظيفة من خلاصات الويب + إرجاع روابط للاستشهاد

from typing import List, Dict

def _pick_clean_lines(text: str, max_lines: int = 6) -> List[str]:
    """اختيار أسطر موجزة ومفيدة من النص."""
    if not text:
        return []
    lines = [l.strip(" .\t\r\n") for l in text.splitlines()]
    # تخلّص من الأسطر القصيرة جدًا أو الطويلة جدًا
    lines = [l for l in lines if 15 <= len(l) <= 220]
    # إزالة المكررات مع الحفاظ على الترتيب
    seen = set()
    uniq = []
    for l in lines:
        if l in seen:
            continue
        seen.add(l)
        uniq.append(l)
        if len(uniq) >= max_lines:
            break
    return uniq

def compose_answer_ar(question: str, results: List[Dict]) -> Dict:
    """
    يأخذ السؤال + نتائج الويب (كل نتيجة: title, snippet, link)
    ويُرجع: {"answer": نص, "links": [روابط...]}
    """
    # اجمع أفضل الخلاصات
    bullets: List[str] = []
    links: List[str] = []

    for r in results[:6]:
        snip = (r.get("snippet") or "").strip()
        title = (r.get("title") or "").strip()
        link = (r.get("link") or "").strip()

        if link:
            links.append(link)
        # حاول استخدام العنوان كجملة أولى إذا كان واضحًا
        if title and 15 <= len(title) <= 140:
            bullets.append(title)
        bullets.extend(_pick_clean_lines(snip, max_lines=3))

    # احذف المكرر وقلّم
    seen = set()
    clean = []
    for b in bullets:
        if b and b not in seen:
            seen.add(b)
            clean.append(b)
        if len(clean) >= 8:  # لا نطوّل
            break

    if not clean:
        return {
            "answer": "جمعت نتائج من الويب لكن لم أستخرج نقاطًا واضحة بما يكفي. جرّب إعادة صياغة سؤالك.",
            "links": links[:5],
        }

    # صياغة نهائية ودّية مع نقاط واضحة
    header = f"سؤالك: {question}\n\nهذا ملخّص مُنظّم من مصادر الويب:\n"
    body = "\n".join([f"• {b}" for b in clean])
    tail = ""
    if links:
        tail = "\n\nروابط للاستزادة:\n" + "\n".join([f"- {u}" for u in links[:5]])

    return {
        "answer": header + body + tail,
        "links": links[:5],
    }
