# -*- coding: utf-8 -*-
# Bassam Brain – Web reasoning & summarization core (Arabic-first)
# يعمل مجانًا: ويكيبيديا API + DuckDuckGo HTML
from __future__ import annotations

import re
import math
import random
from urllib.parse import quote, unquote, urlparse
from html import unescape

import httpx
from bs4 import BeautifulSoup

# ============ أدوات مساعدة ============

HTTP_TIMEOUT = 18.0
DUCK_HTML = "https://html.duckduckgo.com/html/?q="   # واجهة HTML خفيفة
WIKI_OPEN = "https://{lang}.wikipedia.org/w/api.php"
WIKI_SUMMARY = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"

AR_SENT_END = re.compile(r"[\.!\؟\!؟]+\s*")
SPACES = re.compile(r"\s+")

def _clean_text(t: str) -> str:
    if not t:
        return ""
    t = unescape(t)
    t = re.sub(r"\u200f|\u200e|\u202a|\u202b|\u202c|\u202d|\u202e", "", t)
    t = SPACES.sub(" ", t).strip()
    return t

def _decode_url(u: str) -> str:
    try:
        return unquote(u)
    except Exception:
        return u

def _dedup_keep_order(items, key=lambda x: x):
    seen = set()
    out = []
    for it in items:
        k = key(it)
        if k in seen: 
            continue
        seen.add(k)
        out.append(it)
    return out

def _take_top(xs, k):
    return xs[:k] if len(xs) > k else xs

# ============ جلب من ويكيبيديا ============

async def _wiki_search(client: httpx.AsyncClient, query: str, lang: str = "ar", limit: int = 5):
    params = {
        "action": "opensearch",
        "search": query,
        "limit": str(limit),
        "namespace": "0",
        "format": "json",
    }
    url = WIKI_OPEN.format(lang=lang)
    r = await client.get(url, params=params, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    titles = data[1] or []
    urls = data[3] or []
    results = []
    for t, u in zip(titles, urls):
        results.append({
            "title": _clean_text(t),
            "url": _decode_url(u),
            "engine": f"Wikipedia-{lang}"
        })
    return results

async def _wiki_summary(client: httpx.AsyncClient, title: str, lang: str = "ar") -> str:
    url = WIKI_SUMMARY.format(lang=lang, title=quote(title))
    r = await client.get(url, timeout=HTTP_TIMEOUT)
    if r.status_code != 200:
        return ""
    j = r.json()
    # بعض الصفحات تعطي extract أو description
    for k in ("extract", "description"):
        if k in j and j[k]:
            return _clean_text(j[k])
    return ""

# ============ جلب من DuckDuckGo (HTML) ============

async def _ddg_search(client: httpx.AsyncClient, query: str, limit: int = 8):
    url = DUCK_HTML + quote(query)
    r = await client.get(url, timeout=HTTP_TIMEOUT, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119 Safari/537.36"
    })
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    out = []
    # العناوين تظهر في a.result__a داخل div.result
    for a in soup.select("a.result__a"):
        href = a.get("href", "")
        title = a.get_text(" ", strip=True)
        if not href or not title:
            continue
        # تجاهل روابط ddg الداخلية
        if "duckduckgo.com" in urlparse(href).netloc:
            continue
        out.append({
            "title": _clean_text(title),
            "url": _decode_url(href),
            "engine": "DuckDuckGo"
        })
        if len(out) >= limit:
            break
    return out

# ============ تلخيص عربي بسيط وفعّال ============

def _sent_split_ar(text: str):
    # تقسيم جُمل عربي (تقريبي لكنه فعّال)
    parts = AR_SENT_END.split(text)
    sents = [s.strip() for s in parts if _clean_text(s)]
    return sents

def _keywords(q: str):
    q = _clean_text(q)
    # حذف كلمات توقف عربية بسيطة
    stop = set("ما ماذا لماذا كيف اين اينَ أين من في على عن إلى الى هل هو هي هم هن ثم أو او أم ان إن أن لو إذا اذا قد لقد هذا هذه ذلك تلك هناك هنا جدا جداً مثل لدى عند حتى كان كانت يكون تكون وغيرها اكثر أقل أي اى إحدى احد".split())
    toks = [t for t in re.split(r"[^\w\u0600-\u06FF]+", q) if t]
    toks = [t for t in toks if t not in stop and len(t) > 1]
    return toks[:8]

def _score_sent(sent: str, kws):
    if not sent:
        return 0.0
    s = sent.lower()
    score = 0.0
    for k in kws:
        if k in s:
            score += 1.0
    score += min(len(sent)/120.0, 1.0) * 0.3  # مُكافأة لطول معتدل
    return score

def summarize_ar(text: str, query: str, max_lines: int = 6) -> str:
    text = _clean_text(text)
    if not text:
        return ""
    sents = _sent_split_ar(text)
    if not sents:
        return text
    kws = _keywords(query)
    scored = [(s, _score_sent(s, kws)) for s in sents]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = [s for s, _ in _take_top(scored, max_lines)]
    # ترتيب الظهور الأصلي للحفاظ على سياق منطقي
    order = {s: i for i, s in enumerate(sents)}
    top.sort(key=lambda s: order.get(s, 10**9))
    bullets = ["• " + s for s in top]
    return "\n".join(bullets)

# ============ توليف الإجابة ============

async def smart_answer(query: str, lang: str = "ar", max_sources: int = 8) -> dict:
    """
    يُرجع: {"answer": نص مُلخّص, "sources":[{"title":..., "url":...}, ...]}
    """
    query = _clean_text(query)
    if not query:
        return {"answer": "اكتب سؤالك أولًا.", "sources": []}

    async with httpx.AsyncClient(follow_redirects=True, timeout=HTTP_TIMEOUT) as client:
        # 1) ويكيبيديا أولًا (حسب اللغة)
        wiki_hits = []
        try:
            wiki_hits = await _wiki_search(client, query, lang=lang, limit=4)
        except Exception:
            wiki_hits = []

        wiki_texts = []
        for h in wiki_hits:
            try:
                t = await _wiki_summary(client, h["title"], lang=lang)
                if t:
                    wiki_texts.append(t)
            except Exception:
                pass

        # 2) محرك عام مجّاني (DuckDuckGo HTML)
        ddg_hits = []
        try:
            ddg_hits = await _ddg_search(client, query, limit=8)
        except Exception:
            ddg_hits = []

    # دمج وتنظيف مصادر
    sources = wiki_hits + ddg_hits
    sources = _dedup_keep_order(sources, key=lambda d: d.get("url", "").split("#")[0])
    sources = _take_top(sources, max_sources)

    # نص للملخص
    corpus = " ".join(wiki_texts)
    if not corpus and sources:
        # سنجلب مقتطفًا قصيرًا من بعض الصفحات (اختياري خفيف)
        # لتفادي الكشط الثقيل، سنكتفي بأخذ العنوانين لعمل ملخص سريع.
        titles_join = " ".join([s["title"] for s in sources[:5]])
        corpus = f"{titles_join}. "

    answer = summarize_ar(corpus, query, max_lines=6) if corpus else ""
    if not answer:
        answer = "لم أعثر على إجابة مؤكدة بعد، لكن أدرجت لك أهم الروابط الموثوقة للاطلاع."

    # إعادة هيكلة المصادر (عنوان نظيف + رابط مفكوك)
    final_sources = []
    for s in sources:
        title = _clean_text(s.get("title") or "")
        url = _decode_url(s.get("url") or "")
        if not url:
            continue
        if not title:
            # fallback من الدومين/المسار
            p = urlparse(url)
            title = p.netloc or url
        final_sources.append({"title": title, "url": url})

    return {"answer": answer, "sources": final_sources}

# ============ ربط حفظ محلي (اختياري) ============

def save_to_knowledge(question: str, user_answer: str) -> dict:
    """
    ضع هنا منطق الحفظ المحلي إن رغبت (ملف JSON أو DB).
    تُعاد بنية بسيطة للواجهة.
    """
    q = _clean_text(question)
    a = _clean_text(user_answer)
    # مثال مبسّط بدون تخزين فعلي:
    return {"ok": True, "saved": True, "q": q, "a": a}

# ============ بحث اجتماعي – روابط منصات (اختياري للاستخدام من الـ API) ============

SOCIAL_PATTERNS = {
    "google": "https://www.google.com/search?q={q}",
    "twitter": "https://twitter.com/search?q={q}&f=user",
    "facebook": "https://www.facebook.com/search/people/?q={q}",
    "instagram": "https://www.instagram.com/explore/search/keyword/?q={q}",
    "tiktok": "https://www.tiktok.com/search/user?q={q}",
    "linkedin": "https://www.linkedin.com/search/results/people/?keywords={q}",
    "telegram": "https://t.me/s/{q}",
    "reddit": "https://www.reddit.com/search/?q={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}",
}

def social_links(name: str) -> list[dict]:
    q = quote(_clean_text(name))
    out = []
    for k, pat in SOCIAL_PATTERNS.items():
        out.append({"platform": k, "url": pat.format(q=q)})
    return out
