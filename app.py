# app.py — Bassam Brain (Dual Intelligence: Local + Web)
import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.brain import ask_brain

app = FastAPI(title="Bassam الذكي — بحث وتحليل عميق (عقل مزدوج)")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/ask")
async def ask(request: Request, q: str = Form(...)):
    try:
        result = await ask_brain(q)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)})
