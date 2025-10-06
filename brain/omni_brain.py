# brain/omni_brain.py — Bassam الذكي / ALSHOTAIMI v13.6
# مسؤول عن توليد إجابة عربية طبيعية اعتمادًا على نتائج البحث المنظَّفة.

from typing import List, Dict
import re

def _clean_text(s: str) -> str:
    if not s:
        return ""
    # إزالة المسافات الزائدة
    s = re.sub(r"\s+", " ", s).strip()
    # تقصير النصوص الطويلة جدًا
    return s[:700]

def _pick_sentences(text: str, limit_sentences: int = 3) -> str:
    """
    يلتقط 2-3 جُمل الأكثر إفادة من الملخص المنظّف.
    """
    if not text:
        return ""
    # تقسيم على علامات الوقف العربية والإنجليزية
    parts = re.split(r"(?<=[\.!\?؟])\s+", text)
    # الترتيب بسيط: أول الجمل بعد التنظيف تكفي كبداية جيدة
    chosen = []
    for p in parts:
        p = p.strip()
        if 8 <= len(p) <= 280:
            chosen.append(p)
        if len(chosen) >= limit_sentences:
            break
    if not chosen:
        return text[:280]
    return " ".join(chosen)

def summarize_answer(results: List[Dict]) -> str:
    """
    يستقبل قائمة نتائج بالشكل:
    [
      {"title": "...", "link": "https://...", "summary": "نص مستخرج من الصفحة"},
      ...
    ]
    ويعيد إجابة عربية طبيعية + نقاط مختصرة + تنبيه بالمصادر.
    """
    if not results:
        return "لم أعثر على معلومات كافية حاليًا. جرّب توضيح سؤالك أو اسأل بصيغة أخرى."

    # 1) مقدّمة طبيعية قصيرة
    intro = "إليك خلاصة سريعة مبنية على أكثر الصفحات وثوقًا ووضوحًا مما عثرت عليه:"

    # 2) نبني نقاط موجزة من أول 3–5 نتائج
    bullets = []
    for r in results[:5]:
        title = (r.get("title") or "").strip()
        summary = _clean_text(r.get("summary") or "")
        picked = _pick_sentences(summary, limit_sentences=2)
        if not picked and summary:
            picked = summary[:200]
        if title and picked:
            bullets.append(f"• {title}: {picked}")
        elif picked:
            bullets.append(f"• {picked}")

    if not bullets:
        # لو ما قدرنا نركّب نقاط مفيدة، نرجع ملخصًا عامًا من أول نتيجة
        first = results[0]
        return _pick_sentences(_clean_text(first.get("summary") or ""), limit_sentences=4)

    body = "\n".join(bullets)

    # 3) خاتمة لطيفة + تلميح للمصادر
    outro = "للتوسّع يمكنك فتح الروابط في قسم “المصادر” أسفل الإجابة."

    answer = f"{intro}\n\n{body}\n\n{outro}"
    return answer
