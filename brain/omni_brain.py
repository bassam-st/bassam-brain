# brain/omni_brain.py — نواة توليد إجابة عربية بدون LLM مدفوع
from __future__ import annotations
import re, html, hashlib
from typing import List, Dict, Any, Tuple, Optional
from urllib.parse import urlparse

# ==== فلتر محتوى حساس ====
HARAM_WORDS = {"اباحي","اباحية","جنس","جنسية","سكس","لواط","سحاق","مثير","فحص العذرية",
               "porn","sex","xxx","nsfw","nude","naked","onlyfans","camgirl","strip"}
SENSITIVE_PERSONAL = [r"(اسم|رقم|عنوان).{0,6}(زوج(ة|ته)?|والد(ة)?|أم|اب|اخ|اخت|بنت|ولد)"]
def _is_haram(q: str) -> bool:
    qn = re.sub(r"\s+", "", (q or "").lower());  return any(w.replace(" ","") in qn for w in HARAM_WORDS)
def _is_sensitive(q: str) -> bool: return any(re.search(p, (q or "").lower()) for p in SENSITIVE_PERSONAL)

# ==== أدوات نصية ====
_AR_DIAC = r"ًٌٍَُِّْ"
def _norm_ar(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(f"[{_AR_DIAC}]", "", s)
    return s.replace("أ","ا").replace("إ","ا").replace("آ","ا").replace("ى","ي").replace("ة","ه")

def _clean(s: str) -> str:
    s = html.unescape(s or "");  return re.sub(r"\s+", " ", s).strip()

def _sentences(text: str) -> List[str]:
    if not text: return []
    parts = re.split(r"(?<=[\.\!\؟\?])\s+|[\n\r]+", text)
    return [p.strip() for p in parts if len(p.split()) >= 4]

def _hostname(url: str) -> str:
    try: return urlparse(url).netloc or ""
    except: return ""

# ==== نية السؤال ====
def _intent(q: str) -> str:
    qn = _norm_ar(q.lower())
    if re.search(r"\b(من هو|من هي|من)\b", qn): return "person"
    if re.search(r"\b(كيف|خطوات|طريقة|شرح)\b", qn): return "howto"
    if re.search(r"\b(تعريف|ما هو|ماهي)\b", qn): return "definition"
    if re.search(r"\b(مقارن(ه|ة)|vs|افضل)\b", qn): return "compare"
    if re.search(r"\b(متى|تاريخ|عام|سنه)\b", qn): return "timeline"
    return "general"

# ==== ترتيب/تلخيص ====
def _score_sentence(sent: str, q: str, title_hint: Optional[str]=None, source_hint: Optional[str]=None) -> float:
    q_tokens = [w for w in re.split(r"[\W_]+", _norm_ar(q).lower()) if len(w)>1]
    s_tokens = [w for w in re.split(r"[\W_]+", _norm_ar(sent).lower()) if len(w)>1]
    if not s_tokens: return 0.0
    overlap = sum(1 for w in q_tokens if w in s_tokens)
    length_penalty = 1.0 if 6 <= len(s_tokens) <= 40 else 0.6
    title_boost = 0.0
    if title_hint:
        t_tokens = [w for w in re.split(r"[\W_]+", _norm_ar(title_hint).lower()) if len(w)>1]
        title_boost = 0.3 * sum(1 for w in q_tokens if w in t_tokens)
    source_boost = 0.5 if any(t in _hostname(source_hint or "") for t in {"wikipedia.org","who.int","un.org","bbc.com","nature.com","arxiv.org"}) else 0.0
    return (overlap * length_penalty) + title_boost + source_boost

def _fingerprint(s: str) -> str:
    return hashlib.sha1(_norm_ar(re.sub(r"\W+","",s.lower()))[:256].encode()).hexdigest()[:16]

def _dedup(scored: List[Tuple[float,str]], max_sents: int) -> List[str]:
    seen, out = set(), []
    for sc, s in scored:
        fp = _fingerprint(s)
        if fp in seen: continue
        seen.add(fp); out.append(s)
        if len(out) >= max_sents: break
    return out

def extractive_summary(snippets: List[str], q: str, titles: List[str], links: List[str], max_sents: int = 7) -> List[str]:
    pool: List[Tuple[float,str]] = []
    for i, t in enumerate(snippets):
        title = titles[i] if i < len(titles) else ""
        link  = links[i]  if i < len(links)  else ""
        for s in _sentences(t):
            pool.append((_score_sentence(s, q, title, link), s))
    pool.sort(key=lambda x:x[0], reverse=True)
    return _dedup(pool, max_sents)

def render_sources(results: List[Dict]) -> str:
    items = []
    for i, r in enumerate(results[:10], 1):
        title = _clean(r.get("title") or r.get("site") or "مصدر")
        url = _clean(r.get("url") or r.get("link") or "");  host = _hostname(url)
        if url: items.append(f'<li><a href="{url}" target="_blank" rel="noopener">{i}. {title}</a> <small>({host})</small></li>')
    return "<ul class='sources-list'>" + "".join(items) + "</ul>" if items else "لا توجد مصادر متاحة."

def summarize_answer_html(query: str, results: List[Dict], *, memory_hits: Optional[List[Dict]] = None, max_points: int=7) -> str:
    q = _clean(query)
    if _is_haram(q):     return "<div class='answer error'>⚠️ رجاءً تجنّب المحتوى المخالف.</div>"
    if _is_sensitive(q): return "<div class='answer error'>حفاظًا على الخصوصية، لا نعرض/نبحث عن بيانات شخصية.</div>"

    titles, links, snippets = [], [], []
    for r in (results or []):
        titles.append(_clean(r.get("title") or ""))
        links.append(_clean(r.get("url") or r.get("link") or ""))
        snip = _clean(r.get("snippet") or r.get("description") or r.get("text") or "")
        if titles[-1] and titles[-1] not in snip: snip = f"{titles[-1]}. {snip}" if snip else titles[-1]
        snippets.append(snip)

    if not any(snippets):
        bullets = "\n".join([f"• {t}" for t in titles[:max_points] if t]) or "لم أجد تفاصيل كافية."
        return f"<div class='answer'><p>هذه أبرز النقاط:</p><div class='bullets'>{bullets}</div><h3>المصادر:</h3>{render_sources(results)}</div>"

    picked = extractive_summary(snippets, q, titles, links, max_sents=max_points)
    header = {"person":"بطاقة تعريف","definition":"تعريف مختصر","howto":"خطوات/كيفية","compare":"مقارنة سريعة","timeline":"جدول زمني مختصر"}.get(_intent(q),"الخلاصة")

    bullets_html = "\n".join([f"• {s}" for s in picked]) if picked else "لم أجد ما يكفي لتوليد خلاصة."
    memory_html = ""
    if memory_hits:
        items = []
        for m in memory_hits[:3]:
            items.append(f"<li><b>{_clean(m.get('q',''))}</b><br/><small>{_clean(m.get('ts',''))}</small><div class='mem-a'>{_clean(m.get('a',''))}</div></li>")
        if items: memory_html = "<h3>من الذاكرة:</h3><ul class='memory-list'>" + "".join(items) + "</ul>"

    return f"""
    <div class="answer">
      <p>مرحبًا، أنا <b>بسام</b>. حلّلت النتائج من محرّكات بحث ومصادر مفتوحة، وبدون أي اشتراكات.</p>
      <h3>{header}:</h3>
      <div class="bullets">{bullets_html}</div>
      {memory_html}
      <h3>المصادر:</h3>{render_sources(results)}
      <div class='note'>تبي تفاصيل أدق (إحصاءات/خطوات/مقارنة)؟ قلّي وحدّد الزاوية.</div>
    </div>
    """

def summarize_as_json(query: str, results: List[Dict], *, memory_hits: Optional[List[Dict]] = None, max_points: int = 7) -> Dict[str,Any]:
    html_block = summarize_answer_html(query, results, memory_hits=memory_hits, max_points=max_points)
    src_struct = []
    for r in (results or [])[:10]:
        t = _clean(r.get("title") or r.get("site") or "مصدر")
        u = _clean(r.get("url") or r.get("link") or "")
        if u: src_struct.append({"title": t, "url": u, "host": _hostname(u)})
    bullets = [re.sub(r"^\s*•\s*", "", ln).strip() for ln in html_block.splitlines() if ln.strip().startswith("•")]
    return {"ok": True, "html": html_block, "bullets": bullets, "sources": src_struct}
