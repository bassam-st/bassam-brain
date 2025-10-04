# core/search_web.py
# بحث ويب + جلب نص صفحة + تلخيص مقتطفات
from __future__ import annotations

from typing import List, Dict, Optional
from duckduckgo_search import DDGS
import httpx
from bs4 import BeautifulSoup

# ===== إعدادات عامة =====
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/119.0 Safari/537.36"
    )
}

def _clean_visible_text(html: str) -> str:
    """يحذف السكربتات والستايلات ثم يستخرج نصًا نظيفًا متوسط الطول."""
    soup = BeautifulSoup(html, "html.parser")

    # إزالة عناصر لا تفيد في النص
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    # إزالة بعض الأقسام الشائعة قليلة الفائدة إن وجدت
    for sel in ["nav", "footer", "header", "aside"]:
        for t in soup.select(sel):
            t.decompose()

    text = soup.get_text(separator="\n", strip=True)

    # أسطر بطول مناسب فقط
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if 30 <= len(line) <= 300:
            lines.append(line)

    # تجميع أول ~1200 حرف كحد أقصى
    out = []
    total = 0
    for l in lines:
        out.append(l)
        total += len(l)
        if total > 1200:
            break
    return "\n".join(out).strip()


async def fetch_page_text(url: str, timeout: float = 12.0) -> str:
    """
    يجلب محتوى صفحة ويب كنص منظّف (بدون سكربتات/ستايل).
    يعيد نصًا قصيرًا/متوسطًا مناسبًا للعرض أو التلخيص.
    """
    if not url:
        return ""
    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=timeout) as client:
            resp = await client.get(url)
            ct = (resp.headers.get("content-type") or "").lower()
            if "text/html" not in ct and "xml" not in ct:
                # محتوى غير HTML (مثل PDF/صورة/ملف)
                return ""
            html = resp.text
    except Exception:
        return ""

    try:
        return _clean_visible_text(html)
    except Exception:
        return ""


def web_search(query: str, max_results: int = 6) -> List[Dict]:
    """
    بحث سريع عبر DuckDuckGo.
    يعيد قائمة قوامها: {title, snippet, link}
    """
    query = (query or "").strip()
    if not query:
        return []

    results: List[Dict] = []
    try:
        with DDGS() as ddgs:
            # السيف سيرش "moderate" يكفي لمعظم الاستخدامات
            for r in ddgs.text(query, region="wt-wt", safesearch="moderate", max_results=max_results):
                # r: {'title':..., 'href':..., 'body':...}
                title = (r.get("title") or "").strip()
                link = (r.get("href") or "").strip()
                snippet = (r.get("body") or "").strip()
                if link:
                    results.append({"title": title, "snippet": snippet, "link": link})
                if len(results) >= max_results:
                    break
    except Exception:
        # في حال أي خطأ بالبحث نعيد قائمة فارغة
        return []

    return results


def summarize_snippets(results: List[Dict], question: Optional[str] = None) -> str:
    """
    تلخيص بسيط للمقتطفات إلى نقاط جاهزة للعرض (اختياري).
    يمكن استخدامه إن كان app.py يستدعيه.
    """
    bullets: List[str] = []

    def _pick_lines(text: str, limit: int = 2) -> List[str]:
        if not text:
            return []
        lines = [l.strip(" .\t\r\n") for l in text.splitlines() if l.strip()]
        # نفلتر الأسطر بطول مناسب
        lines = [l for l in lines if 30 <= len(l) <= 220]
        return lines[:limit]

    for r in results[:6]:
        title = (r.get("title") or "").strip()
        snippet = (r.get("snippet") or "").strip()
        if title and 15 <= len(title) <= 140:
            bullets.append(f"• {title}")
        for l in _pick_lines(snippet, limit=2):
            bullets.append(f"• {l}")

    # إزالة التكرارات مع الحفاظ على الترتيب
    seen = set()
    uniq: List[str] = []
    for b in bullets:
        if b and b not in seen:
            seen.add(b)
            uniq.append(b)
        if len(uniq) >= 8:
            break

    if not uniq:
        return "لم أستخرج نقاطًا واضحة من نتائج البحث."

    header = ""
    if question:
        header = f"سؤالك: {question}\n\n"

    return header + "\n".join(uniq)
