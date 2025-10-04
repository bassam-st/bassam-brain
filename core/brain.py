# ===========================
# core/brain.py — Bassam الذكي
# ===========================
import httpx, re
from bs4 import BeautifulSoup
from urllib.parse import quote

SEARCH_ENGINES = [
    ("Google", "https://www.google.com/search?q="),
    ("Bing", "https://www.bing.com/search?q="),
    ("DuckDuckGo", "https://duckduckgo.com/html?q="),
]

SOCIAL_PLATFORMS = {
    "Google": "https://www.google.com/search?q=",
    "Twitter/X": "https://twitter.com/search?q=",
    "Facebook": "https://www.facebook.com/search/people/?q=",
    "Instagram": "https://www.instagram.com/explore/search/keyword/?q=",
    "TikTok": "https://www.tiktok.com/search/user?q=",
    "LinkedIn": "https://www.linkedin.com/search/results/people/?keywords=",
    "Telegram": "https://t.me/s/",
    "Reddit": "https://www.reddit.com/search/?q=",
    "YouTube": "https://www.youtube.com/results?search_query=",
}


async def smart_search(q: str, want_social=False):
    """البحث الذكي العميق"""
    results = []
    q_encoded = quote(q)

    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        # 1️⃣ البحث الأساسي في جوجل وبنج ودك دك جو
        for name, base in SEARCH_ENGINES:
            url = f"{base}{q_encoded}"
            try:
                r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                soup = BeautifulSoup(r.text, "html.parser")
                links = [a.get("href") for a in soup.find_all("a", href=True)]
                clean_links = [l for l in links if l and "http" in l and "google.com" not in l]
                results.extend(clean_links[:10])
            except:
                continue

    # 2️⃣ استخراج النصوص من أول الصفحات
    summaries = []
    async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
        for link in results[:5]:
            try:
                r = await client.get(link, headers={"User-Agent": "Mozilla/5.0"})
                text = BeautifulSoup(r.text, "html.parser").get_text()
                text = re.sub(r"\s+", " ", text).strip()
                if len(text) > 300:
                    summaries.append(text[:400])
            except:
                pass

    # 3️⃣ بحث اجتماعي (اختياري)
    social_links = []
    if want_social:
        for platform, base in SOCIAL_PLATFORMS.items():
            social_links.append(f"{platform}: {base}{q_encoded}")

    # 🔹 الإخراج النهائي
    return {
        "answer": summaries[0] if summaries else "لم يتم العثور على معلومات كافية.",
        "sources": results[:10],
        "social": social_links
    }
# ✅ دالة ذكية شاملة للإجابة — تستخدم البحث والتحليل
async def smart_answer(query: str):
    """
    هذه الدالة مسؤولة عن تنفيذ البحث الذكي الكامل:
    1. تبحث في الويب (Google، Bing، Deep Web...)
    2. تبحث في ويكيبيديا والمصادر العربية.
    3. تبحث في السوشال ميديا إن كان الاسم شخصاً.
    4. ترجع إجابة ذكية + روابط المصادر.
    """
    from core.search import deep_search  # تأكد أن هذا موجود في مشروعك
    result = await deep_search(query)
    return result


# ✅ لتخزين المعرفة محلياً (اختياري)
def save_to_knowledge(question: str, answer: str):
    """
    تخزن السؤال والإجابة في ملف knowledge.json المحلي.
    """
    import json, os
    path = "knowledge.json"
    data = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except:
                data = []
    data.append({"question": question, "answer": answer})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
