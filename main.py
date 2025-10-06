import os
os.makedirs("uploads", exist_ok=True)
os.makedirs("cache", exist_ok=True)
# main.py — Bassam الذكي / ALSHOTAIMI v13.6
import os, json, time, traceback, re
from typing import Optional, List, Dict
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# استيراد الملفات الداخلية
from core.search import deep_search
from core.utils import ensure_dirs, is_haram_query, log_conversation, log_block
from brain.omni_brain import summarize_answer

# إنشاء المسارات
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
CACHE_DIR = os.path.join(BASE_DIR, "cache")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
CONFIGS_DIR = os.path.join(BASE_DIR, "configs")

# إنشاء المجلدات إن لم تكن موجودة
ensure_dirs(TEMPLATES_DIR, STATIC_DIR, UPLOADS_DIR, CACHE_DIR, LOGS_DIR, CONFIGS_DIR)

app = FastAPI(title="Bassam الذكي — ALSHOTAIMI v13.6")

# إعداد القوالب والملفات الثابتة
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# تحميل الإعدادات
SETTINGS_FILE = os.path.join(CONFIGS_DIR, "settings.json")
DEFAULT_SETTINGS = {
    "welcome_message": "مرحبًا أنا بسام لمساعدتك 👋",
    "bank_account": "",
    "subscription_price": "5 دولار شهريًا",
    "ads_enabled": True,
    "ads_text": "احصل على النسخة المدفوعة لمميزات إضافية!",
    "admin_password": "093589"
}
if not os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_SETTINGS, f, ensure_ascii=False, indent=2)

def load_settings():
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_settings(data):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    settings = load_settings()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "welcome": settings["welcome_message"],
        "ads_enabled": settings["ads_enabled"],
        "ads_text": settings["ads_text"],
        "subscription_price": settings["subscription_price"]
    })

@app.post("/search")
async def do_search(request: Request):
    data = await request.json()
    q = data.get("q", "").strip()
    user_name = data.get("user_name", "مستخدم مجهول")
    ip = request.client.host

    # التحقق من الأسئلة المخالفة
    if is_haram_query(q):
        log_block(ip, user_name, q, reason="محتوى مخالف")
        return JSONResponse({"ok": True, "answer": "🚫 لا تنسَ أن الله يراك", "sources": []})

    try:
        results = await deep_search(q)
        answer = summarize_answer(results)
        log_conversation(ip, user_name, q, answer)
        return JSONResponse({"ok": True, "answer": answer, "sources": results})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"ok": False, "error": str(e)})

# لوحة الإشراف
@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    settings = load_settings()
    return templates.TemplateResponse("admin.html", {"request": request, "settings": settings})

@app.post("/admin/login")
async def admin_login(request: Request):
    form = await request.form()
    password = form.get("password", "")
    settings = load_settings()
    admin_pass = os.getenv("ADMIN_PASSWORD", settings["admin_password"])
    if password == admin_pass:
        resp = RedirectResponse("/admin/dashboard", status_code=302)
        resp.set_cookie("admin_auth", password)
        return resp
    return RedirectResponse("/admin?error=1", status_code=302)

@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    settings = load_settings()
    auth = request.cookies.get("admin_auth")
    admin_pass = os.getenv("ADMIN_PASSWORD", settings["admin_password"])
    if auth != admin_pass:
        return RedirectResponse("/admin", status_code=302)

    # قراءة السجلات
    conversations = []
    blocks = []
    conv_file = os.path.join(LOGS_DIR, "conversations.csv")
    block_file = os.path.join(LOGS_DIR, "blocks.csv")
    if os.path.exists(conv_file):
        with open(conv_file, "r", encoding="utf-8") as f:
            conversations = f.readlines()
    if os.path.exists(block_file):
        with open(block_file, "r", encoding="utf-8") as f:
            blocks = f.readlines()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "settings": settings,
        "conversations": conversations,
        "blocks": blocks
    })

@app.post("/admin/settings")
async def save_admin_settings(request: Request):
    data = await request.form()
    settings = load_settings()
    for k in ["welcome_message", "bank_account", "subscription_price", "ads_text"]:
        if k in data:
            settings[k] = data[k]
    settings["ads_enabled"] = "ads_enabled" in data
    save_settings(settings)
    return RedirectResponse("/admin/dashboard", status_code=302)
