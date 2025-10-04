# app.py
# =========================================================
# FastAPI + Jinja2 — واجهة تطبيق "بسام الذكي"
# =========================================================

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from jinja2 import Environment, FileSystemLoader, select_autoescape
import asyncio

from core.brain import smart_answer

app = FastAPI(title="Bassam Brain Pro v3.5", version="3.5")

# السماح بواجهة المتصفح
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# القوالب
env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml"])
)

@app.get("/", response_class=HTMLResponse)
async def index():
    tpl = env.get_template("index.html")
    return tpl.render()

@app.post("/search")
async def search(q: str = Form(...), social: str = Form("off")):
    try:
        force_social = (social == "on")
        data = await smart_answer(q.strip(), force_social=force_social)
        return JSONResponse(data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=422)

# ملاحظة: لا تنشئ main.py — مدخل التشغيل هو app:app
# أمر التشغيل على Render:
# uvicorn app:app --host 0.0.0.0 --port $PORT
