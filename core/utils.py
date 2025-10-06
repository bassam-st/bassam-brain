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
