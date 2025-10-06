# core/utils.py — Bassam الذكي / ALSHOTAIMI v13.6

import os, re, csv, time

# إنشاء المجلدات إذا لم تكن موجودة
def ensure_dirs(*paths):
    for path in paths:
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)

# 🔒 الكلمات المحظورة (محتوى إباحي / مخل)
HARAM_KEYWORDS = [
    "sex","xxx","porn","nude","fuck","pussy","dick","anal","gay",
    "سكس","اباحي","افلام اباحيه","ممثله اباحيه","ممثلات اباحيات","جماع","عاريه","مواقع اباحيه",
    "عاري","صدرها","مؤخرتها","فرجها","قضيب","نيك","طيز","ممارسة","لواط","شذوذ","اغراء"
]

# ✅ الفحص إن كان السؤال مخالفًا
def is_haram_query(text: str) -> bool:
    text = text.lower().strip()
    for kw in HARAM_KEYWORDS:
        if kw in text:
            return True
    return False

# 📜 تسجيل المحادثات
def log_conversation(ip, user_name, question, answer):
    path = os.path.join("logs", "conversations.csv")
    file_exists = os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "ip", "user_name", "question", "answer"])
        writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), ip, user_name, question, answer])

# 🚫 تسجيل المحظورات (Blocks)
def log_block(ip, user_name, question, reason="محتوى مخالف"):
    path = os.path.join("logs", "blocks.csv")
    file_exists = os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "ip", "user_name", "question", "reason"])
        writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), ip, user_name, question, reason])
# === ترجمة تلقائية إلى العربية عند الحاجة ===
from typing import Optional
try:
    from langdetect import detect
    from deep_translator import GoogleTranslator
except Exception:
    # في حال لم تُثبَّت المكتبات بعد أثناء البيلد
    detect = None
    GoogleTranslator = None

def ensure_arabic(text: Optional[str]) -> str:
    """
    يعيد النص كما هو إذا كان عربيًا،
    وإلا يترجمه تلقائيًا إلى العربية.
    في حال حدوث خطأ، يعيد النص الأصلي بدون كسر.
    """
    if not text:
        return ""
    try:
        if detect is None or GoogleTranslator is None:
            return text  # أول تشغيل قبل التثبيت
        lang = detect(text)
        if lang != "ar":
            return GoogleTranslator(source="auto", target="ar").translate(text)
        return text
    except Exception as e:
        print("translation error:", e)
        return text
