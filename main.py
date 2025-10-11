# main.py
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx

# ===== إعداد مفاتيح OneSignal =====
ONESIGNAL_APP_ID = os.getenv(
    "ONESIGNAL_APP_ID",
    "81c7fcd0-8dbe-4486-9f9e-7a80e461f5d1"  # App ID
)

# ↓↓↓ ضع هنا الـ REST API KEY (القيمة السرّية الطويلة التي تبدأ بـ os_v2_app_)
ONESIGNAL_REST_API_KEY = os.getenv(
    "ONESIGNAL_REST_API_KEY",
    "os_v2_app_qhd7zuenxzcinh46pkaoiypv2h4d4ozpcsuedgnz3hzev4lmm5fepsqeykluuw6cj5stzrluiw6gdu2ujliagiscsqxsdmfngvwfoty"
)

# ===== تطبيق FastAPI =====
app = FastAPI(title="Bassam Brain")

# ملفات الستاتك والقوالب
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# الصفحة الرئيسية
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "onesignal_app_id": ONESIGNAL_APP_ID})


# Service Worker مسار قصير للجذر /sw.js حتى لا يظهر 404
@app.get("/sw.js")
async def sw_proxy():
    sw_path = "static/sw.js"
    if not os.path.exists(sw_path):
        raise HTTPException(status_code=404, detail="sw.js not found")
    return FileResponse(sw_path, media_type="application/javascript")


# صحة التكامل
@app.get("/admin/health")
async def health():
    return {
        "message": "👋 Bassam Brain Notifications تعمل الآن بنجاح",
        "status": "ready",
        "onesignal_app_id": f"{ONESIGNAL_APP_ID[:8]}..."
    }


# اختبار إرسال إشعار (GET بسيط)
@app.get("/admin/push-test")
async def push_test():
    url = "https://onesignal.com/api/v1/notifications"
    headers = {
        # ملاحظة: v1 يحتاج Basic <REST_KEY>. استخدم المفتاح السري (الطويل الذي يبدأ os_v2_app_)
        "Authorization": f"Basic {ONESIGNAL_REST_API_KEY}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {
        "app_id": ONESIGNAL_APP_ID,
        "included_segments": ["Subscribed Users"],
        "headings": {"en": "Bassam Brain"},
        "contents": {"en": "Push test ✅ من لوحة الإدارة"},
        "url": "https://bassam-brain.onrender.com/",
        "chrome_web_icon": "https://bassam-brain.onrender.com/static/icons/icon-192.png",
    }

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, headers=headers, json=payload)
        if r.status_code >= 400:
            raise HTTPException(status_code=500, detail=f"OneSignal error: {r.status_code} {r.text}")
        return {"ok": True, "onesignal_response": r.json()}
