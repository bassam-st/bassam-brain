# ===========================
# Bassam v3.5 Pro — Smart Deep Search (Free)
# بحث ذكي، اجتماعي، وديب ويب — واجهة احترافية مجانية
# ===========================

import os, time, json, re, traceback
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.brain import smart_search
from core.utils import normalize_text

# إعداد المسارات
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title="Bassam الذكي — بحث عميق وتلخيص تلقائي")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/search")
async def do_search(request: Request):
    data = await request.json()
    q = normalize_text(data.get("q", "").strip())
    want_social = bool(data.get("want_social", False))

    if not q:
        return JSONResponse({"ok": False, "error": "يرجى كتابة سؤالك أولاً."})

    try:
        t0 = time.time()
        result = await smart_search(q, want_social=want_social)
        result["time_ms"] = int((time.time() - t0) * 1000)
        return JSONResponse({"ok": True, **result})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"ok": False, "error": str(e)})
