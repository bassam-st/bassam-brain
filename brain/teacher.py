# brain/teacher.py
from __future__ import annotations
from typing import List, Dict
from bs4 import BeautifulSoup
import requests, re

HEADERS = {"User-Agent":"Mozilla/5.0"}

def _clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for s in soup(["script","style","noscript"]): s.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    return text

def fetch_page(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.ok and "text" in r.headers.get("Content-Type",""):
            return _clean_text(r.text)[:12000]
    except Exception:
        pass
    return ""

def distill_knowledge(text: str, max_lines: int = 10) -> List[str]:
    # قَطِّع النص إلى جمل، خُذ أهم الجمل (بدائية لكنها فعّالة كبداية)
    sents = re.split(r"(?<=[.!؟:])\s+", text)
    uniq = []
    for s in sents:
        s = s.strip()
        if len(s) >= 40 and s not in uniq:
            uniq.append(s)
        if len(uniq) >= max_lines: break
    return uniq

def learn_from_urls(urls: List[str]) -> List[Dict]:
    out = []
    for u in urls:
        text = fetch_page(u)
        if not text: continue
        facts = distill_knowledge(text)
        for f in facts:
            out.append({"content": f, "source": u, "tags": []})
    return out
