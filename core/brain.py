# core/brain.py
from __future__ import annotations
from typing import List, Dict, Tuple
import re
from rapidfuzz import fuzz
from .search_engines import google_search, bing_search, wikipedia_search, ddg_fallback, social_search_links

AR_DIAC  = re.compile(r'[\u064B-\u0652]')
TOKEN_RE = re.compile(r'[A-Za-z\u0621-\u064A0-9]+')

def _norm(s: str) -> str:
    s = s or ""
    s = AR_DIAC.sub("", s)
    s = s.replace("أ","ا").replace("إ","ا").replace("آ","ا").replace("ى","ي").replace("ة","ه")
    return re.sub(r"\s+"," ", s).strip()

def _clean_lines(text: str, max_lines: int = 2) -> List[str]:
    if not text: return []
    lines = [l.strip(" .\t\r\n") for l in text.splitlines()] or [text.strip()]
    lines = [l for l in lines if 15 <= len(l) <= 220]
    seen, out = set(), []
    for l in lines:
        if l in seen: continue
        seen.add(l); out.append(l)
        if len(out) >= max_lines: break
    return out

def _summarize(results: List[Dict], question: str) -> str:
    bullets, links = [], []
    for r in results[:8]:
        if r.get("link"): links.append(r["link"])
        t = r.get("title","").strip()
        s = r.get("snippet","").strip()
        if 12 <= len(t) <= 120: bullets.append(t)
        bullets += _clean_lines(s, 1)
    # إزالة التكرار
    seen, clean = set(), []
    for b in bullets:
        if b and b not in seen:
            seen.add(b); clean.append(b)
        if len(clean) >= 10: break
    head = f"سؤالك: {question}\n\nملخّص من عدة مصادر:\n"
    body = "\n".join(f"• {b}" for b in clean) if clean else "• لم أعثر على نقاط واضحة كفاية."
    if links:
        body += "\n\nروابط للاستزادة:\n" + "\n".join(f"- {u}" for u in links[:6])
    return head + body

async def smart_answer(question: str, force_social: bool = False) -> Tuple[str, Dict]:
    q = (question or "").strip()
    if not q:
        return "لم أستلم سؤالًا.", {"mode": "invalid"}

    # إذا طلب المستخدم اسم شخص/شركة -> أعرض روابط السوشال
    if force_social or re.search(r"(تويتر|فيسبوك|انستقرام|سناب|يوتيوب|لينكد(?:إن)?|حساب|username|@)", q):
        name = _norm(re.sub(r"(تويتر|فيسبوك|انستقرام|سناب|يوتيوب|لينكد.?ان|حساب)","",q)).strip()
        if len(name) < 2: name = q
        links = social_search_links(name)
        txt = "بحث اجتماعي سريع (اختر المنصة):\n" + "\n".join([f"- {k}: {v}" for k,v in links.items()])
        return txt, {"mode":"social", "name": name}

    # ترتيب: Google -> Bing -> Wikipedia -> DDG (fallback)
    results: List[Dict] = []
    for fn in (google_search, bing_search, wikipedia_search, ddg_fallback):
        try:
            part = await fn(q, 6) if fn != wikipedia_search else await fn(q, 4)
        except Exception:
            part = []
        results.extend(part)
        if len(results) >= 6:
            break

    if not results:
        return "لم أصل لنتائج كافية الآن. جرّب إعادة الصياغة أو حدّد كلمات أكثر.", {"mode":"none"}

    return _summarize(results, q), {"mode":"web", "sources": [r.get("link") for r in results[:6] if r.get("link")]}
