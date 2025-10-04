from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from core.brain import smart_answer, save_to_knowledge

app = FastAPI(title="Bassam Brain")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "q": "", "ans": None, "meta": None}
    )

@app.post("/ask", response_class=HTMLResponse)
async def ask(
    request: Request,
    q: str = Form(""),
    save_answer: str = Form(None),
    last_answer: str = Form("")
):
    ans, meta = smart_answer(q)
    # حفظ اختياري للقاعدة
    if save_answer == "on" and q.strip() and last_answer.strip():
        save_to_knowledge(q, last_answer)

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "q": q, "ans": ans, "meta": meta}
    )

# للعودة من زر "رجوع"
@app.post("/back")
async def back():
    return RedirectResponse("/", status_code=303)
