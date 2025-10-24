# brain/omni_brain.py
# مولد إجابة عربي احترافي بدون LLM مدفوع — تجميعي/تحليلي/تلخيصي من نتائج البحث (مجاني 100%)

from __future__ import annotations
import re, html, hashlib
from typing import List, Dict, Any, Tuple, Optional
from urllib.parse import urlparse

# =========================== سلامة المحتوى ===========================
# فلتر أخلاقي/إباحي + أسئلة شخصية حساسة
HARAM_WORDS = {
    # عربي
    "اباحي","اباحية","جنس","جنسية","مثير","مثيره","سكس","لواط","سحاق","مضاجعة","اغراء",
    "صور اباحية","مواقع اباحية","افلام اباحية","زواج متعة","فحص العذرية","ايباحي",
    # إنجليزي
    "porn","porno","sex","xxx","nsfw","nude","naked","onlyfans","camgirl","strip",
}
SENSITIVE_PERSONAL = [
    r"(اسم|رقم|عنوان).{0,6}(زوج(ة|ته)?|والد(ة)?|أم|اب|اخ|اخت|بنت|ولد)",
    r"(بيانات|هوية|رقم وطني|هوية وطنية)",
]

def _is_haram(q: str) -> bool:
    qn = re.sub(r"\s+", "", q.lower())
    for w in HARAM_WORDS:
        if w.replace(" ", "") in qn:
            return True
    return False

def _is_sensitive(q: str) -> bool:
    qn = q.strip().lower()
    return any(re.search(p, qn) for p in SENSITIVE_PERSONAL)

# =========================== أدوات نصية ===========================
_AR_DIAC = r"ًٌٍَُِّْ"
def _norm_ar(s: str) -> str:
    s = s or ""
    s = s.strip()
    s = re.sub(f"[{_AR_DIAC}]", "", s)
    s = s.replace("أ","ا").replace("إ","ا").replace("آ","ا")
    s = s.replace("ى","ي").replace("ة","ه")
    return s

def _clean(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _sentences(text: str) -> List[str]:
    if not text:
        return []
    # تقسيم جُمَل بسيط يدعم العربية/الإنجليزية
    parts = re.split(r"(?<=[\.\!\؟\?])\s+|[\n\r]+", text)
    out = []
    for p in parts:
        p = p.strip()
        if len(p.split()) >= 4:
            out.append(p)
    return out

def _hostname(url: str) -> str:
    try:
        return urlparse(url).netloc or ""
    except Exception:
        return ""

# =========================== كشف نية السؤال ===========================
def _detect_intent(q: str) -> str:
    qn = _norm_ar(q.lower())
    if re.search(r"\b(من هو|من هي|من هما|من)\b", qn):
        return "person"
    if re.search(r"\b(ما هو|ماهي|ما هي|تعريف)\b", qn):
        return "definition"
    if re.search(r"\b(كيف|طريقة|خطوات|حل|شرح)\b", qn):
        return "howto"
    if re.search(r"\b(مقارن(ه|ة)|افضل|الافضل|vs|مقارنة)\b", qn):
        return "compare"
    if re.search(r"\b(متى|تاريخ|timeline|سنة|عام)\b", qn):
        return "timeline"
    if re.search(r"\b(قائمة|list|انواع|تصنيفات)\b", qn):
        return "list"
    return "general"

# =========================== ترتيب/تلخيص ===========================
def _score_sentence(sent: str, q: str, title_hint: Optional[str] = None, source_hint: Optional[str] = None) -> float:
    q_tokens = [w for w in re.split(r"[\W_]+", _norm_ar(q).lower()) if len(w) > 1]
    s_tokens = [w for w in re.split(r"[\W_]+", _norm_ar(sent).lower()) if len(w) > 1]
    if not s_tokens:
        return 0.0
    overlap = sum(1 for w in q_tokens if w in s_tokens)
    length_penalty = 1.0 if 6 <= len(s_tokens) <= 40 else 0.6
    title_boost = 0.0
    if title_hint:
        t_tokens = [w for w in re.split(r"[\W_]+", _norm_ar(title_hint).lower()) if len(w) > 1]
        title_boost = 0.3 * sum(1 for w in q_tokens if w in t_tokens)
    source_boost = 0.0
    if source_hint:
        # مواقع موثوقة تعطي دفعة بسيطة (قابلة للتوسّع)
        trusted = {"wikipedia.org","who.int","un.org","bbc.com","nature.com","arxiv.org"}
        host = _hostname(source_hint)
        if any(t in host for t in trusted):
            source_boost = 0.5
    return (overlap * length_penalty) + title_boost + source_boost

def _fingerprint(s: str) -> str:
    return hashlib.sha1(_norm_ar(re.sub(r"\W+", "", s.lower()))[:256].encode()).hexdigest()[:16]

def _dedup_sentences(scored: List[Tuple[float, str]], max_sents: int) -> List[str]:
    seen, out = set(), []
    for score, s in scored:
        fp = _fingerprint(s)
        if fp in seen:
            continue
        seen.add(fp)
        out.append(s)
        if len(out) >= max_sents:
            break
    return out

def _extractive_summary(snippets: List[str], q: str, titles: List[str], links: List[str], max_sents: int = 6) -> List[str]:
    pool: List[Tuple[float, str]] = []
    for i, t in enumerate(snippets):
        title = titles[i] if i < len(titles) else ""
        link = links[i] if i < len(links) else ""
        for s in _sentences(t):
            sc = _score_sentence(s, q, title_hint=title, source_hint=link)
            pool.append((sc, s))
    pool.sort(key=lambda x: x[0], reverse=True)
    return _dedup_sentences(pool, max_sents=max_sents)

# =========================== عرض المصادر ===========================
def _render_sources(results: List[Dict]) -> str:
    items = []
    for i, r in enumerate(results[:10], start=1):
        title = _clean(r.get("title") or r.get("site") or "مصدر")
        url = _clean(r.get("url") or r.get("link") or "")
        if not url:
            continue
        host = _hostname(url)
        items.append(f'<li><a href="{url}" target="_blank" rel="noopener">{i}. {title}</a> <small>({host})</small></li>')
    return "<ul class='sources-list'>" + "".join(items) + "</ul>" if items else "لا توجد مصادر متاحة."

# =========================== واجهة نهائية ===========================
def summarize_answer(
    query: str,
    results: List[Dict[str, Any]],
    *,
    memory_hits: Optional[List[Dict[str, Any]]] = None,   # اختياري: [{ts,q,a,rank}]
    max_points: int = 7
) -> str:
    """
    يُولّد إجابة عربية واضحة + مصادر من نتائج البحث.
    :param results: عناصر تحتوي مفاتيح: title, url/link, snippet/description/text, source (اختياري)
    :param memory_hits: نتائج ذاكرة داخلية (إن وجدت في تطبيقك) تُعرض كمرجع إضافي.
    يعيد HTML جاهز للعرض.
    """

    q = _clean(query)

    # حواجز السلامة
    if _is_haram(q):
        return "<div class='answer error'>⚠️ رجاءً تجنّب المحتوى المخالف.</div>"
    if _is_sensitive(q):
        return "<div class='answer error'>حفاظًا على الخصوصية، لا نعرض/نبحث عن بيانات شخصية أو عائلية.</div>"

    # نوايا السؤال
    intent = _detect_intent(q)

    titles, links, snippets = [], [], []
    for r in (results or []):
        titles.append(_clean(r.get("title") or ""))
        links.append(_clean(r.get("url") or r.get("link") or ""))
        snip = _clean(r.get("snippet") or r.get("description") or r.get("text") or "")
        if titles[-1] and titles[-1] not in snip:
            snip = f"{titles[-1]}. {snip}" if snip else titles[-1]
        snippets.append(snip)

    # إذا لا توجد مقتطفات، اعرض العناوين فقط
    if not any(snippets):
        titles_only = [t for t in titles[:max_points] if t]
        bullets = "\n".join([f"• {t}" for t in titles_only]) if titles_only else "لم أجد تفاصيل كافية."
        return (
            f"<div class='answer'>"
            f"<p>هذه أبرز النقاط حول سؤالك:</p>"
            f"<div class='bullets'>{bullets}</div>"
            f"<h3>المصادر:</h3>{_render_sources(results)}"
            f"</div>"
        )

    picked = _extractive_summary(snippets, q, titles, links, max_sents=max_points)
    header = {
        "person": "بطاقة تعريف",
        "definition": "تعريف مختصر",
        "howto": "خطوات/كيفية",
        "compare": "مقارنة سريعة",
        "timeline": "جدول زمني مختصر",
        "list": "قائمة/تصنيفات",
        "general": "الخلاصة",
    }.get(intent, "الخلاصة")

    # إبراز بسيط للأسماء/التواريخ عند نمط الشخص/الزمن
    if intent in {"person", "timeline"}:
        highlighted = []
        for s in picked:
            s2 = re.sub(r"(\b\d{4}\b)", r"<mark>\1</mark>", s)  # سنة
            s2 = re.sub(r"(\b\d{1,2}\s*(يناير|فبراير|مارس|ابريل|أبريل|مايو|يونيو|يوليو|اغسطس|أغسطس|سبتمبر|اكتوبر|أكتوبر|نوفمبر|ديسمبر)\b)", r"<mark>\1</mark>", s2, flags=re.I)
            highlighted.append(s2)
        picked = highlighted

    bullets_html = "\n".join([f"• {s}" for s in picked]) if picked else "لم أجد ما يكفي لتوليد خلاصة."
    sources_html = _render_sources(results)

    # ذاكرة داخلية (اختياري)
    memory_html = ""
    if memory_hits:
        items = []
        for m in memory_hits[:3]:
            items.append(
                f"<li><b>{_clean(m.get('q',''))}</b><br/><small>{_clean(m.get('ts',''))}</small>"
                f"<div class='mem-a'>{_clean(m.get('a',''))}</div></li>"
            )
        if items:
            memory_html = "<h3>من الذاكرة:</h3><ul class='memory-list'>" + "".join(items) + "</ul>"

    intro = (
        "مرحبًا، أنا <b>بسام</b>. جمّعت لك أبرز النقاط بعد تحليل النتائج من محرّكات بحث ومصادر مفتوحة، "
        "وبدون أي اشتراكات أو نماذج مدفوعة."
    )
    guidance = (
        "<div class='note'>هل تريد تعميق البحث في زاوية محدّدة (إحصاءات، خطوات تنفيذ، مقارنة مفصّلة، أخبار حديثة)؟ أخبرني بذلك.</div>"
    )

    html_out = f"""
    <div class="answer">
      <p>{intro}</p>
      <h3>{header}:</h3>
      <div class="bullets">
        {bullets_html}
      </div>
      {memory_html}
      <h3>المصادر:</h3>
      {sources_html}
      {guidance}
    </div>
    """
    return html_out


# =========================== مخرجات بديلة (للاستخدام في API) ===========================
def summarize_as_json(
    query: str,
    results: List[Dict[str, Any]],
    *,
    memory_hits: Optional[List[Dict[str, Any]]] = None,
    max_points: int = 7
) -> Dict[str, Any]:
    """
    بديل يرجّع JSON منسّق: {html, bullets, sources}
    """
    # نعيد HTML كامل + قائمة نقاط + المصادر بشكل منظم
    html_block = summarize_answer(query, results, memory_hits=memory_hits, max_points=max_points)

    titles, links = [], []
    for r in (results or [])[:10]:
        titles.append(_clean(r.get("title") or r.get("site") or "مصدر"))
        links.append(_clean(r.get("url") or r.get("link") or ""))

    # استخراج النقاط من HTML (بسيط)
    bullets = []
    for line in html_block.splitlines():
        if line.strip().startswith("•"):
            bullets.append(_clean(line.replace("•", "", 1)))

    src_struct = []
    for t, u in zip(titles, links):
        if u:
            src_struct.append({"title": t, "url": u, "host": _hostname(u)})

    return {
        "ok": True,
        "html": html_block,
        "bullets": bullets,
        "sources": src_struct,
    }
