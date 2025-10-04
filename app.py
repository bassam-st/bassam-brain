# app.py — Bassam الذكي (النسخة الاحترافية الكاملة)
import os, traceback
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from core.brain import smart_answer  # العقل الذكي (البحث والتلخيص)

app = FastAPI(title="بسام الذكي — بحث عميق وتلخيص تلقائي")

# المسارات الثابتة
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# الصفحة الرئيسية
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# نقطة البحث الرئيسية
@app.post("/search")
async def search(q: str = Form(...), enable_social: bool = Form(False)):
    try:
        result = smart_answer(q, enable_social)
        return JSONResponse(result)
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({
            "ok": False,
            "answer": "",
            "sources": [],
            "mode": "error",
            "error": str(e)
        }, status_code=500)
