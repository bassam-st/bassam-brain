# core/brain.py
# =========================================================
# Bassam Brain Pro v3.5 — بحث ذكي + تلخيص + سوشال + Deep Web
# يعتمد على httpx + BeautifulSoup + lxml
# =========================================================

from __future__ import annotations
import re, asyncio, random
from urllib.parse import quote_plus
import httpx
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "ar,en;q=0.8"}

# ---------- أدوات مساعدة ----------

def _clean_text(t: str, max_len: int = 1200) -> str:
    if not t:
        return ""
    t = re.sub(r"\s+", " ", t).strip()
    return t[:max_len]

def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")

async def _fetch_text(client: httpx.AsyncClient, url: str, timeout=12) -> str:
    try:
        r = await client.get(url, timeout=timeout, headers=HEADERS, follow_redirects=True)
        if r.status_code == 200:
            return r.text
    except Exception:
        return ""
    return ""

def as_bullet_sources(urls: list[tuple[str, str]]) -> list[dict]:
    # كل عنصر: {"title": "...", "url": "..."}
    out = []
    for title, url in urls[:12]:
        out.append({"title": _clean_text(title, 120), "url": url})
    return out

# ---------- تحليل نوع السؤال ----------
def detect_intent(q: str) -> str:
    ql = q.strip()
    if not ql:
        return "general"
    p = ql.lower()
    if any(w in p for w in ["حساب", "يوزر", "يوزرز", "username", "user", "اكاونت"]):
        return "social"
    if any(w in p for w in ["من هو", "من هي", "ابحث عن شخص", "سيرة", "حياة", "twitter", "facebook", "instagram"]):
        return "social"
    if any(w in p for w in ["وزارة", "gov", "جهة", "جامعة", "تعليم", "نتيجة", "قبول"]):
        return "gov"
    return "general"

# ---------- مولّد روابط السوشال (قابلة للنقر) ----------
def build_social_links(name: str) -> list[dict]:
    q = quote_plus(name)
    links = [
        ("Google", f"https://www.google.com/search?q={q}"),
        ("Twitter / X", f"https://twitter.com/search?q={q}&f=user"),
        ("Facebook", f"https://www.facebook.com/search/people/?q={q}"),
        ("Instagram", f"https://www.instagram.com/explore/search/keyword/?q={q}"),
        ("TikTok", f"https://www.tiktok.com/search/user?q={q}"),
        ("LinkedIn", f"https://www.linkedin.com/search/results/people/?keywords={q}"),
        ("Telegram", f"https://t.me/s/{q}"),
        ("Reddit", f"https://www.reddit.com/search/?q={q}"),
        ("YouTube", f"https://www.youtube.com/results?search_query={q}")
    ]
    return [{"name": n, "url": u} for n, u in links]

# ---------- البحث: Google → Bing → Wikipedia ----------
async def search_google(client: httpx.AsyncClient, q: str) -> list[tuple[str, str]]:
    # ملاحظة: قد يمنع Google بعض الطلبات. لدينا سقوط على Bing تلقائيًا في app.py
    html = await _fetch_text(client, f"https://www.google.com/search?q={quote_plus(q)}&hl=ar")
    if not html:
        return []
    s = _soup(html)
    results = []
    for g in s.select("a"):
        href = g.get("href") or ""
        title = g.get_text(" ").strip()
        # تجاهل الروابط الداخلية
        if href.startswith("/url?q="):
            url = href.split("/url?q=")[-1].split("&")[0]
            if title and url.startswith("http"):
                results.append((title, url))
        if len(results) >= 8:
            break
    return results

async def search_bing(client: httpx.AsyncClient, q: str) -> list[tuple[str, str]]:
    html = await _fetch_text(client, f"https://www.bing.com/search?q={quote_plus(q)}&setlang=ar")
    if not html:
        return []
    s = _soup(html)
    results = []
    for li in s.select("li.b_algo h2 a"):
        url = li.get("href")
        title = li.get_text(" ").strip()
        if url and title:
            results.append((title, url))
        if len(results) >= 8:
            break
    return results

async def search_wikipedia(client: httpx.AsyncClient, q: str) -> list[tuple[str, str]]:
    html = await _fetch_text(client, f"https://ar.wikipedia.org/w/index.php?search={quote_plus(q)}")
    if not html:
        return []
    s = _soup(html)
    results = []
    for a in s.select("ul.mw-search-results li a"):
        href = a.get("href")
        title = a.get_text(" ").strip()
        if href and title:
            url = "https://ar.wikipedia.org" + href
            results.append((title, url))
        if len(results) >= 6:
            break
    return results

# ---------- Deep Web (سطحي آمن: ahmia) ----------
async def search_deep_web(client: httpx.AsyncClient, q: str) -> list[tuple[str, str]]:
    # ahmia.fi مفهرس لمواقع onion ويعمل عبر الويب السطحي
    html = await _fetch_text(client, f"https://ahmia.fi/search/?q={quote_plus(q)}")
    if not html:
        return []
    s = _soup(html)
    out = []
    for a in s.select("a"):
        href = a.get("href") or ""
        txt = a.get_text(" ").strip()
        if ".onion" in href and txt:
            out.append((txt, href))
        if len(out) >= 5:
            break
    return out

# ---------- جلب وقراءة صفحة للمُلخّص ----------
async def fetch_and_summarize(client: httpx.AsyncClient, url: str, max_words: int = 120) -> str:
    # r.jina.ai يُرجع صفحة نصية نظيفة قابلة للقراءة
    page = await _fetch_text(client, f"https://r.jina.ai/http://{url.replace('https://','').replace('http://','')}")
    page = _clean_text(page, 5000)
    if not page:
        return ""
    # تلخيص بسيط: أخذ أهم الجُمل العربية/الإنجليزية الأولى
    # (إصدار Pro موسّع لكن يبقى خفيفًا لخطّة Starter)
    parts = re.split(r"(?<=[.!؟])\s+", page)
    kept, count = [], 0
    for sent in parts:
        if len(sent) < 20:
            continue
        kept.append("• " + sent.strip())
        count += len(sent.split())
        if count >= max_words:
            break
    return "\n".join(kept) if kept else page[:800]

# ---------- نقطة التشغيل الرئيسية ----------
async def smart_answer(q: str, force_social: bool = False) -> dict:
    intent = detect_intent(q)
    if force_social:
        intent = "social"

    async with httpx.AsyncClient(headers=HEADERS) as client:
        sources: list[tuple[str, str]] = []
        answer = ""
        social_links = []

        if intent == "social":
            social_links = build_social_links(q)
            # نبحث أيضاً بجوجل للحصول على روابط إضافية
            results = await search_google(client, q)
            if not results:
                results = await search_bing(client, q)
            sources = results or []
            if sources:
                answer = "‏هذه روابط سريعة لحسابات أو نتائج لها علاقة بالاسم المدخل. اختر المصدر الصحيح وافتحه."
            else:
                answer = "لم أعثر على حسابات واضحة. جرّب إضافة مدينة/دولة أو لقب."

        else:
            # ترتيب البحث: Google → Bing → Wikipedia → Deep Web
            results = await search_google(client, q)
            if not results:
                results = await search_bing(client, q)
            wiki = await search_wikipedia(client, q)
            deep = await search_deep_web(client, q)

            # حاول التلخيص من أول نتيجة موثوقة
            candidate = (results or wiki or [])[:1]
            if candidate:
                _, url = candidate[0]
                summary = await fetch_and_summarize(client, url)
                answer = summary or "لم أتمكّن من توليد ملخّص، هذه بعض المصادر المفيدة."
            else:
                answer = "لم أجد نتيجة مباشرة. هذه بعض الروابط المفيدة للاطّلاع."

            # دمج المصادر مع وضع أولوية
            sources = (results[:6]) + (wiki[:4]) + (deep[:3])

        return {
            "intent": intent,
            "answer": _clean_text(answer, 3000),
            "sources": as_bullet_sources(sources),
            "social": social_links,
        }
