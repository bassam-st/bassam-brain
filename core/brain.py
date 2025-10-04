# core/brain.py — Bassam Brain Pro (Starter)
# - تحليل سؤال بسيط (عواصم + رياضيات)
# - بحث ويب متعدد المصادر بالترتيب: Wikipedia → Bing → Brave → SerpAPI → DuckDuckGo
# - تلخيص نقاط + روابط
# - Deep Web: مُعطّل افتراضيًا (يتطلب تور)، مضاف كـ stub آمن

from typing import List, Dict, Tuple
import os, re, math, asyncio
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

# ========= تعريب خفيف =========
AR_DIAC  = re.compile(r'[\u064B-\u0652]')
def normalize_ar(s: str) -> str:
    s = s or ""
    s = AR_DIAC.sub("", s)
    s = s.replace("أ","ا").replace("إ","ا").replace("آ","ا")
    s = s.replace("ة","ه").replace("ى","ي").replace("ؤ","و").replace("ئ","ي")
    s = s.replace("گ","ك").replace("پ","ب").replace("ڤ","ف").replace("ظ","ض")
    return re.sub(r"\s+"," ", s).strip()

# ========= 1) كاشف "عاصمة دولة" =========
CAPITAL_PAT = re.compile(r"(?:ما|ماهي|ما هي)?\s*عاص(?:م(?:ة)?)\s+(.+?)\s*\?*$")
async def capital_via_restcountries(country: str) -> str | None:
    url = f"https://restcountries.com/v3.1/name/{quote(country)}?fields=capital,name,translations"
    try:
        async with httpx.AsyncClient(timeout=10) as cl:
            r = await cl.get(url)
            if r.status_code != 200:
                return None
            data = r.json()
            if isinstance(data, list) and data:
                cap = data[0].get("capital")
                if isinstance(cap, list) and cap:
                    return cap[0]
                if isinstance(cap, str):
                    return cap
    except Exception:
        return None
    return None

def detect_capital_question(q: str) -> str | None:
    qn = normalize_ar(q)
    m = CAPITAL_PAT.search(qn)
    if not m:
        return None
    country = m.group(1).strip(" ؟!.،")
    return country if country else None

# ========= 2) أستاذ الرياضيات (Sympy) =========
# حلول خطوة بخطوة مبسّطة (اشتقاق/تكامل/حل معادلة بسيطة)
from sympy import symbols, Eq, solve, sympify, diff, integrate
x = symbols('x')

def try_math_teacher(q: str) -> str | None:
    """
    أمثلة:
    - حل المعادلة: 2x+3=7
    - مشتق x^3 + 5x
    - تكامل x^2
    """
    text = normalize_ar(q).lower()
    try:
        if "مشتق" in text or "اشتقاق" in text:
            expr_str = text.replace("مشتق","").replace("اشتقاق","").strip()
            expr = sympify(expr_str, convert_xor=True)
            d = diff(expr, x)
            return f"المطلوب: مشتق {expr}\nالخطوة 1: نشتق الحدود.\nالنتيجة: {d}"
        if "تكامل" in text:
            expr_str = text.replace("تكامل","").strip()
            expr = sympify(expr_str, convert_xor=True)
            integ = integrate(expr, x)
            return f"المطلوب: تكامل {expr}\nالخطوة 1: نكامل الحدود.\nالنتيجة: {integ} + C"
        if "حل المعادلة" in text or "=" in text:
            # نحاول شكل a = b
            if "=" in text:
                left, right = text.split("=",1)
                left = sympify(left.replace("حل المعادلة","").strip(), convert_xor=True)
                right = sympify(right.strip(), convert_xor=True)
                eq = Eq(left, right)
                sol = solve(eq, x, dict=True)
                return f"المطلوب: حل {eq}\nالخطوات: نحول ونحل للمجهول x.\nالحل: {sol}"
    except Exception:
        return None
    return None

# ========= 3) بحث الويب متعدد المصادر =========
def _pack(title="", snippet="", link=""):
    return {"title": (title or "").strip(), "snippet": (snippet or "").strip(), "link": (link or "").strip()}

async def search_wikipedia(query: str, max_results: int = 5):
    out = []
    # نجرب العربية أولاً ثم الإنجليزية
    for api in [
        ("https://ar.wikipedia.org/w/api.php", "https://ar.wikipedia.org/wiki/"),
        ("https://en.wikipedia.org/w/api.php", "https://en.wikipedia.org/wiki/"),
    ]:
        url, base = api
        params = {"action":"query","list":"search","format":"json","srlimit":max_results,"srsearch":query,"utf8":1}
        try:
            async with httpx.AsyncClient(timeout=12) as cl:
                r = await cl.get(url, params=params)
                if r.status_code != 200: 
                    continue
                data = r.json()
                for hit in data.get("query",{}).get("search",[]):
                    title = hit.get("title","")
                    snippet = BeautifulSoup(hit.get("snippet",""), "lxml").get_text(" ")
                    link = f"{base}{title.replace(' ','_')}"
                    out.append(_pack(title, snippet, link))
        except Exception:
            continue
    return out

async def search_bing(query: str, max_results: int = 5):
    key = os.getenv("BING_API_KEY")
    if not key: return []
    url = "https://api.bing.microsoft.com/v7.0/search"
    headers = {"Ocp-Apim-Subscription-Key": key}
    params  = {"q": query, "count": max_results, "mkt": "en-US", "textDecorations": False}
    out = []
    try:
        async with httpx.AsyncClient(timeout=12) as cl:
            r = await cl.get(url, headers=headers, params=params)
            if r.status_code != 200: return []
            for it in r.json().get("webPages",{}).get("value",[]):
                out.append(_pack(it.get("name",""), it.get("snippet",""), it.get("url","")))
    except Exception:
        return []
    return out

async def search_brave(query: str, max_results: int = 5):
    key = os.getenv("BRAVE_API_KEY")
    if not key: return []
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {"Accept":"application/json","X-Subscription-Token":key}
    params  = {"q": query, "count": max_results, "safesearch": "moderate", "freshness": "month"}
    out = []
    try:
        async with httpx.AsyncClient(timeout=12) as cl:
            r = await cl.get(url, headers=headers, params=params)
            if r.status_code != 200: return []
            for it in r.json().get("web",{}).get("results",[]):
                out.append(_pack(it.get("title",""), it.get("description",""), it.get("url","")))
    except Exception:
        return []
    return out

async def search_serpapi(query: str, max_results: int = 5):
    key = os.getenv("SERPAPI_KEY")
    if not key: return []
    url = "https://serpapi.com/search.json"
    params = {"engine":"google","q":query,"num":max_results,"api_key":key}
    out = []
    try:
        async with httpx.AsyncClient(timeout=12) as cl:
            r = await cl.get(url, params=params)
            if r.status_code != 200: return []
            for it in r.json().get("organic_results", []):
                out.append(_pack(it.get("title",""), it.get("snippet",""), it.get("link","")))
    except Exception:
        return []
    return out

async def search_ddg(query: str, max_results: int = 6):
    # DuckDuckGo كـ fallback أخير (بدون مفاتيح)
    out = []
    try:
        from duckduckgo_search import DDGS
        with DDGS() as dd:
            for r in dd.text(query, max_results=max_results):
                out.append(_pack(r.get("title",""), r.get("body",""), r.get("href","")))
    except Exception:
        return []
    return out

def _dedupe(results: List[Dict], limit=10) -> List[Dict]:
    seen, out = set(), []
    for r in results:
        u = r.get("link","")
        if not u or u in seen: 
            continue
        seen.add(u)
        if r.get("title"): out.append(r)
        if len(out) >= limit: break
    return out

async def web_search(query: str, max_results: int = 6) -> List[Dict]:
    """Wikipedia → Bing → Brave → SerpAPI → DuckDuckGo (أخيرًا)"""
    all_results: List[Dict] = []

    # 1) Wikipedia أولاً
    try:
        all_results += await search_wikipedia(query, max_results=3)
    except Exception:
        pass

    # 2) Bing (بمفتاح)
    try:
        all_results += await search_bing(query, max_results=4)
    except Exception:
        pass

    # 3) Brave (بمفتاح)
    try:
        all_results += await search_brave(query, max_results=3)
    except Exception:
        pass

    # 4) SerpAPI (Google) (بمفتاح)
    try:
        all_results += await search_serpapi(query, max_results=4)
    except Exception:
        pass

    # 5) DuckDuckGo كاحتياطي
    if len(all_results) < 3:
        try:
            all_results += await search_ddg(query, max_results=6)
        except Exception:
            pass

    return _dedupe(all_results, limit=max_results)

# ========= 4) Deep Web (اختياري/معطّل افتراضيًا) =========
# ملاحظة أمان: للوصول الفعلي إلى .onion يلزم Tor Proxy؛ الكود هنا Stub آمن لا يعمل بدون إعدادات خاصة.
async def deepweb_search_stub(query: str) -> List[Dict]:
    if os.getenv("DEEPWEB_ENABLED","0") != "1":
        return []
    # هنا يمكن لاحقًا استخدام requests عبر socks5h إلى Tor—لكن نتركه مُعطّل افتراضيًا.
    return []

# ========= 5) تلخيص النتائج إلى نقاط + روابط =========
def _pick_lines(text: str, k: int = 2) -> List[str]:
    if not text: return []
    lines = [BeautifulSoup(text, "lxml").get_text(" ").strip() for _ in [1]]
    # تقسيم بسيط بالنقطة/الفاصلة/السطر
    parts = re.split(r"[\.!\n:\-–]+", lines[0])
    parts = [p.strip() for p in parts if 15 <= len(p.strip()) <= 220]
    return parts[:k]

def compose_web_answer(question: str, results: List[Dict]) -> Dict:
    bullets, links = [], []
    for r in results[:8]:
        t, s, u = r.get("title",""), r.get("snippet",""), r.get("link","")
        if u: links.append(u)
        if 15 <= len(t) <= 140: bullets.append(t.strip())
        bullets += _pick_lines(s, k=2)

    # إزالة التكرار
    clean, seen = [], set()
    for b in bullets:
        if b and b not in seen:
            seen.add(b); clean.append(b)
        if len(clean) >= 10: break

    if not clean:
        return {"answer": "بحثت ولم أجد نقاطًا واضحة كفاية. جرّب إعادة صياغة السؤال.", "links": links[:5]}

    head = f"سؤالك: {question}\n\nملخّص من مصادر متعددة:\n"
    body = "\n".join([f"• {b}" for b in clean])
    tail = ("\n\nروابط للاستزادة:\n" + "\n".join([f"- {u}" for u in links[:5]])) if links else ""
    return {"answer": head + body + tail, "links": links[:5]}

# ========= 6) الواجهة الموحدة الذكية =========
async def smart_answer(question: str) -> Tuple[str, Dict]:
    q = (question or "").strip()
    if not q:
        return "لم أستلم سؤالًا.", {"mode": "invalid"}

    # (أ) عواصم
    country = detect_capital_question(q)
    if country:
        cap = await capital_via_restcountries(country)
        if cap:
            return f"عاصمة {country} هي: **{cap}**.", {"mode": "capital", "country": country, "capital": cap}

    # (ب) رياضيات
    math_try = try_math_teacher(q)
    if math_try:
        return math_try, {"mode": "math"}

    # (ج) Deep Web (Stub) — لن يعيد نتائج إلا إذا فعّلته بمتغير البيئة
    deep_hits = await deepweb_search_stub(q)
    if deep_hits:
        pack = compose_web_answer(q, deep_hits)
        return pack["answer"], {"mode": "deepweb", "links": pack.get("links", [])}

    # (د) الويب العام
    results = await web_search(q, max_results=6)
    if results:
        pack = compose_web_answer(q, results)
        return pack["answer"], {"mode": "web", "links": pack.get("links", [])}

    return ("بحثت في المصادر ولم أجد إجابة واضحة. رجاءً أعد صياغة سؤالك "
            "أو حدّد كلمات أكثر دقة."), {"mode": "none"}
