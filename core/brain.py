# -*- coding: utf-8 -*-
# core/brain.py
import asyncio
import re
import urllib.parse
from typing import List, Tuple

import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS  # نستخدمه للبحث الحر بدون API
# ملاحظة: اخترناه لأنه يعمل مجاناً وثابتاً على الاستضافة.
# يمكنك لاحقاً تبديله بمحرّكات أخرى (Google/Bing API) لو وفّرت مفاتيح.

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "ar,en;q=0.8"}

SOCIAL_PLATFORMS = {
    "Google": "https://www.google.com/search?q={q}",
    "Twitter/X": "https://twitter.com/search?q={q}&f=user",
    "Facebook": "https://www.facebook.com/search/people/?q={q}",
    "Instagram": "https://www.instagram.com/explore/search/keyword/?q={q}",
    "TikTok": "https://www.tiktok.com/search/user?q={q}",
    "LinkedIn": "https://www.linkedin.com/search/results/people/?keywords={q}",
    "Telegram": "https://t.me/s/{q}",
    "Reddit": "https://www.reddit.com/search/?q={q}",
    "YouTube": "https://www.youtube.com/results?search_query={q}",
}

def _looks_like_person_or_handle(text: str) -> bool:
    # بسيط: وجود مسافة/اسمين أو وجود @ أو كلمات مثل حساب/يوزر/username
    text = text.strip().lower()
    if "@" in text:
        return True
    if any(k in text for k in ["حساب", "يوزر", "username", "account", "profile"]):
        return True
    # اسم عربي من كلمتين أو أكثر
    if len(text.split()) >= 2 and re.search(r"[\u0600-\u06FF]", text):
        return True
    return False

async def _fetch_snippet(client: httpx.AsyncClient, url: str) -> str:
    try:
        r = await client.get(url, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        # حاول وصف سريع
        for sel in [
            'meta[name="description"]',
            'meta[property="og:description"]',
            'meta[name="og:description"]',
        ]:
            tag = soup.select_one(sel)
            if tag and tag.get("content"):
                return tag["content"].strip()
        # بديل: أول فقرة
        p = soup.find("p")
        if p and p.get_text(strip=True):
            return p.get_text(strip=True)[:300]
    except Exception:
        pass
    return ""

async def _search_web(query: str, max_results: int = 6) -> List[Tuple[str, str]]:
    # DuckDuckGo بحث عام سريع
    results: List[Tuple[str, str]] = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, region="xa-ar", max_results=max_results):
            title = r.get("title") or r.get("source") or "نتيجة"
            href = r.get("href") or r.get("url")
            if href:
                results.append((title, href))
    return results

async def _summarize_from_sources(results: List[Tuple[str, str]]) -> str:
    if not results:
        return "لم أعثر على نتائج مؤكدة للسؤال."

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        snippets = await asyncio.gather(
            *[_fetch_snippet(client, url) for _, url in results]
        )

    # تكوين جواب عربي مختصر من أفضل 3 مقتطفات
    points = []
    for (title, url), snip in zip(results, snippets):
        if snip:
            points.append(f"• **{title}** — {snip}")
        if len(points) >= 3:
            break

    if not points:
        return "وجدت مصادر، يمكنك مراجعتها أدناه."

    return "إليك خلاصة سريعة من عدة مصادر:\n\n" + "\n".join(points)

def _build_social_links(name_or_handle: str) -> List[Tuple[str, str]]:
    q = urllib.parse.quote(name_or_handle, safe="")
    links = []
    for site, tpl in SOCIAL_PLATFORMS.items():
        links.append((site, tpl.format(q=q)))
    return links

# ====== الدالة الرئيسية التي يستدعيها app.py ======
async def smart_answer(query: str, force_social: bool = False):
    """
    ترجع (answer_markdown, sources_list)
    sources_list = List[Tuple[title, url]]
    """
    q = query.strip()
    if not q:
        return "الرجاء إدخال سؤال.", []

    # وضع البحث الاجتماعي
    if force_social or _looks_like_person_or_handle(q):
        links = _build_social_links(q)
        # نجعل الإجابة تمهيدية، والمصادر = الروابط
        answer = (
            "بحثت لك اجتماعيًا عن الاسم/الحساب عبر أكثر المنصات استخدامًا.\n"
            "اضغط على أي رابط لفتح النتائج مباشرة:"
        )
        return answer, links

    # محاولة إجابة معرفية (ويكيبيديا أولًا بشكل سريع)
    wiki_api = (
        "https://ar.wikipedia.org/api/rest_v1/page/summary/"
        + urllib.parse.quote(q, safe="")
    )
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        try:
            wr = await client.get(wiki_api, timeout=8)
            if wr.status_code == 200:
                data = wr.json()
                # نتحقق أن الصفحة لها وصف
                if isinstance(data, dict) and data.get("extract"):
                    title = data.get("title", "ويكيبيديا")
                    # نضع ويكيبيديا ضمن المصادر
                    url = data.get("content_urls", {}).get("desktop", {}).get("page")
                    sources = []
                    if url:
                        sources.append((f"{title} — ويكيبيديا", url))
                    answer = data["extract"]
                    # نضيف بحث ويب عام لزيادة المصادر
                    web_results = await _search_web(q, max_results=5)
                    # دمج المصادر (الويكي + باقي النتائج)
                    sources.extend(web_results)
                    # إن أردت ملخصًا مركبًا:
                    digest = await _summarize_from_sources(web_results[:4])
                    final = f"{answer}\n\n---\n{digest}"
                    return final, sources
        except Exception:
            pass

    # إن فشل ويكي: بحث ويب عام + تلخيص
    web_results = await _search_web(q, max_results=6)
    summary = await _summarize_from_sources(web_results)
    return summary, web_results
