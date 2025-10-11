# main.py — Bassam Brain Notifications + FastAPI App

import os
import time
import datetime as dt
import threading
import requests
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Bassam Brain — Match Notifications")

# ===== إعداد مفاتيح OneSignal =====
ONESIGNAL_APP_ID = os.getenv("ONESIGNAL_APP_ID")
ONESIGNAL_REST_KEY = os.getenv("ONESIGNAL_REST_KEY")
ONESIGNAL_API_URL = "https://onesignal.com/api/v1/notifications"

def send_push(title: str, body: str, url: str | None = None):
    """
    يرسل إشعار Web Push إلى جميع المشتركين.
    """
    if not ONESIGNAL_APP_ID or not ONESIGNAL_REST_KEY:
        return {"error": "❌ مفاتيح OneSignal غير موجودة في Render!"}

    payload = {
        "app_id": ONESIGNAL_APP_ID,
        "headings": {"en": title, "ar": title},
        "contents": {"en": body, "ar": body},
        "included_segments": ["All"],  # يرسل لجميع المشتركين
    }
    if url:
        payload["url"] = url

    headers = {
        "Authorization": f"Basic {ONESIGNAL_REST_KEY}",
        "Content-Type": "application/json; charset=utf-8",
    }

    try:
        res = requests.post(ONESIGNAL_API_URL, json=payload, headers=headers, timeout=30)
        res.raise_for_status()
        print("✅ تم إرسال الإشعار:", title)
        return res.json()
    except Exception as e:
        print("❌ خطأ في الإرسال:", e)
        return {"error": str(e)}

# ===== بيانات نموذج الإرسال اليدوي =====
class Broadcast(BaseModel):
    title: str
    body: str
    url: str | None = None

# ===== مسارات إدارية =====
@app.post("/admin/push-broadcast")
def push_broadcast(data: Broadcast):
    """
    إرسال إشعار يدوي بعنوان ومحتوى مخصص.
    """
    return send_push(data.title, data.body, data.url)

@app.get("/admin/push-test")
def push_test():
    """
    اختبار سريع: إرسال إشعار بسيط لتجربة النظام.
    """
    return send_push(
        "اختبار الإشعارات 🔔",
        "تم إرسال إشعار تجريبي من Bassam Brain بنجاح ✅",
        "https://bassam-brain.onrender.com/"
    )

# ===== نظام الإشعارات التلقائية للمباريات =====
sent_notifications = set()

def check_and_notify_matches():
    """
    تحقق من مباريات اليوم وأرسل الإشعارات قبل 30 دقيقة وعند البداية.
    (يمكن لاحقًا ربطها بجدول حقيقي من API)
    """
    sample_matches = [
        {
            "home": "الهلال",
            "away": "النصر",
            "kickoff": dt.datetime.utcnow().replace(second=0, microsecond=0) + dt.timedelta(minutes=35),
            "url": "https://bassam-brain.onrender.com/",
            "id": "match-123"
        }
    ]

    now = dt.datetime.utcnow().replace(second=0, microsecond=0)

    for match in sample_matches:
        kickoff = match["kickoff"]
        match_id = match["id"]
        title = f"⚽ {match['home']} × {match['away']}"

        # قبل المباراة بـ30 دقيقة
        if kickoff - now == dt.timedelta(minutes=30) and f"{match_id}-before" not in sent_notifications:
            body = f"⏰ المباراة تبدأ بعد 30 دقيقة ({kickoff.time().strftime('%H:%M')} UTC)"
            send_push(title, body, match["url"])
            sent_notifications.add(f"{match_id}-before")

        # عند بداية المباراة
        if kickoff == now and f"{match_id}-start" not in sent_notifications:
            body = "🔥 انطلقت المباراة الآن! شاهد التفاصيل مباشرة."
            send_push(title, body, match["url"])
            sent_notifications.add(f"{match_id}-start")

def scheduler_loop():
    """
    يشغل الجدولة التلقائية كل دقيقة.
    """
    while True:
        try:
            check_and_notify_matches()
        except Exception as e:
            print("scheduler error:", e)
        time.sleep(60)

def start_scheduler():
    """
    بدء تشغيل الثريد الخلفي للجدولة.
    """
    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()

@app.on_event("startup")
def on_startup():
    start_scheduler()
    print("✅ تم تشغيل نظام الإشعارات التلقائية بنجاح")

@app.get("/")
def home():
    return JSONResponse({
        "message": "👋 Bassam Brain Notifications تعمل الآن بنجاح",
        "status": "ready",
        "onesignal_app_id": ONESIGNAL_APP_ID[:8] + "...",
    })
