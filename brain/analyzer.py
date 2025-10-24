# brain/analyzer.py
from __future__ import annotations
import re
from typing import Dict, List

AR_QUESTION_PAT = r"(كيف|ما|ماذا|ليش|لماذا|متى|أين|كم|هل)\b"
CODE_HINT_PAT = r"(كود|code|python|js|javascript|بايثون|جافاسكربت|sql|bash)"
MATH_HINT_PAT = r"(مشتق|تكامل|مصفوف|معادلة|deriv|integral|matrix|solve)"

def detect_language(text: str) -> str:
    return "ar" if re.search(r"[\u0600-\u06FF]", text) else "en"

def is_question(text: str) -> bool:
    return "؟" in text or "?" in text or bool(re.search(AR_QUESTION_PAT, text))

def extract_intent(text: str) -> str:
    t = text.lower()
    if re.search(CODE_HINT_PAT, t): return "code"
    if re.search(MATH_HINT_PAT, t): return "math"
    if any(w in t for w in ["خلاصة","لخص","ملخص","summary","summarize"]): return "summarize"
    if any(w in t for w in ["ابحث","search","ما هو","ماهي","ماهو"]): return "search"
    return "qa"  # سؤال/جواب عام

def key_phrases(text: str, max_k: int = 8) -> List[str]:
    words = re.findall(r"[A-Za-z\u0600-\u06FF0-9]{3,}", text)
    stop = set(["ماهو","ماهي","هذا","هذه","ذلك","التي","الذي","and","the","for","with","من","في","على","عن"])
    uniq = []
    for w in words:
        w2 = w.lower()
        if w2 not in stop and w2 not in uniq:
            uniq.append(w2)
        if len(uniq) >= max_k: break
    return uniq

def sentiment(text: str) -> str:
    neg = ["سيء","سئ","غلط","خطأ","كذب","زفت","زعلان","كره","bad","wrong","hate"]
    pos = ["ممتاز","جميل","رائع","حلو","تمام","جيد","great","good","love"]
    score = sum(w in text for w in pos) - sum(w in text for w in neg)
    return "positive" if score>0 else "negative" if score<0 else "neutral"

def analyze_query(text: str) -> Dict:
    return {
        "lang": detect_language(text),
        "is_question": is_question(text),
        "intent": extract_intent(text),
        "key_phrases": key_phrases(text),
        "sentiment": sentiment(text),
    }
