# brain/omni_brain.py
# مولد إجابة عربي بدون LLM مدفوع — تجميعي/تلخيصي من نتائج البحث
from __future__ import annotations
import re
from typing import List, Dict

HARAM_WORDS = {
    "اباحي","اباحية","جنس","جنسية","مثير","مثيره","مواقعباحية","مواقع اباحية","صوراباحية",
    "افلام اباحية","سكس","سحاق","لواط","ممارسة جنسية","مضاجعة","اغراء","فحص العذرية",
    "porn","porno","sex","xxx","nsfw","nude","naked","onlyfans","camgirl","strip",
}
def _is_haram(q: str) -> bool:
    qn = re.sub(r"\s+", "", q.lower())
    for w in HARAM_WORDS:
        if w.replace(" ", "") in qn:
            return True
    return False

def _clean(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s

def _sentences(text: str) -> List[str]:
    if not text:
        return []
    parts = re.split(r"(?<=[\.\!\؟\?])\s+|[\n\r]+", text)
    return [p.strip() for p in parts if p.strip()]

def _score_sentence(sent: str, query: str) -> float:
    q_tokens = [w for w in re.split(r"[\W_]+", query.lower()) if w]
    s_tokens = [w for w in re.split(r"[\W_]+", sent.lower()) if w]
    if not s_tokens:
        return 0.0
    overlap = sum(1 for w in q_tokens if w in s_tokens)
    length_penalty = 1.0 if 6 <= len(s_tokens) <= 40 else 0.6
    return overlap * length_penalty

def _extractive_summary(texts: List[str], query: str, max_sents: int = 6) -> List[str]:
    pool: List[str] = []
    for t in texts:
        pool.extend(_sentences(t))
    scored = sorted(pool, key=lambda s: _score_sentence(s, query), reverse=True)
    seen, picked = set(), []
    for s in scored:
        k = re.sub(r"\W+", "", s.lower())
        if k in seen: continue
        seen.add(k); picked.append(s)
        if len(picked) >= max_sents: break
    return picked

def _render_sources(results: List[Dict]) -> str:
    if not results:
        return "لا توجد مصادر متاحة."
    lines = []
    for r in results[:10]:
        title = _clean(r.get("title") or r.get("site") or "مصدر")
        url = _clean(r.get("url") or r.get("link") or "")
        if not url: continue
        lines.append(f"- <a href=\"{url}\" target=\"_blank\" rel=\"noopener\">{title}</a>")
    return "\n".join(lines) or "لا توجد مصادر متاحة."

def _detect_person_query(q: str) -> bool:
    if re.search(r"\b(من\s+هو|من\s+هي|من\s+هما)\b", q):
        return True
    words = q.strip().split()
    return len(words) <= 5 and any(w.istitle() for w in words)

def summarize_answer(query: str, results: List[Dict]) -> str:
    q = _clean(query)
    if _is_haram(q):
        return "<div class='answer error'>⚠️ رجاءً تجنّب المحتوى غير الملائم.</div>"

    snippets = []
    for r in results:
        snip = _clean(r.get("snippet") or r.get("description") or r.get("text") or "")
        title = _clean(r.get("title") or "")
        if title and title not in snip:
            snip = f"{title}. {snip}" if snip else title
        if snip:
            snippets.append(snip)

    if not snippets and results:
        titles = [_clean(r.get("title") or "") for r in results[:6] if _clean(r.get("title") or "")]
        summary_points = "\n".join([f"• {t}" for t in titles]) if titles else "لم أجد تفاصيل كافية."
        sources_html = _render_sources(results)
        return (
            f"<p>مرحبًا، أنا <b>بسام</b>. هذه أبرز النقاط حول سؤالك:</p>"
            f"<div class='bullets'>{summary_points}</div>"
            f"<h3>المصادر:</h3><div class='sources'>{sources_html}</div>"
        )

    picked = _extractive_summary(snippets, q, max_sents=7)
    person_mode = _detect_person_query(q)
    header = "بطاقة تعريف" if person_mode else "الخلاصة"

    bullets = "\n".join([f"• {s}" for s in picked]) if picked else "لم أجد ما يكفي لتوليد خلاصة."
    sources_html = _render_sources(results)

    intro = (
        "مرحبًا، أنا <b>بسام</b>—حللت سؤالك ثم بحثت أولًا في Google ثم استكملت بمنصات أخرى "
        "(DuckDuckGo/الخ). جمّعت لك زبدة النتائج."
    )
    guidance = (
        "<div class='note'>بحاجة تفاصيل إضافية (تاريخ، إحصاءات، خطوات)؟ أخبرني لأعمّق البحث.</div>"
    )

    html = f"""
    <div class="answer">
      <p>{intro}</p>
      <h3>{header}:</h3>
      <div class="bullets">
        {bullets}
      </div>
      <h3>المصادر:</h3>
      <div class="sources">
        {sources_html}
      </div>
      {guidance}
    </div>
    """
    return html
