# app.py
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os, asyncio

from core.brain import smart_answer

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "answer": None, "meta": None})

@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request, q: str = Form(...), social: str = Form("0")):
    ans, meta = await smart_answer(q, force_social = (social=="1"))
    return templates.TemplateResponse("index.html", {"request": request, "answer": ans, "meta": meta, "q": q})
