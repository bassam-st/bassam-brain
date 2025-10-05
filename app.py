import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.engine import smart_search
from core.social import build_social_links, build_comment_links
from core.summarize import smart_summarize
from core.math_solver import explain_math_ar

app = FastAPI(title="Bassam v4.0 Full-AI")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "answer": None, "sources": [], "social_links": [],
         "comment_links": [], "q": "", "elapsed": None, "page": 1, "pages": 1,
         "math_mode": False}
    )

@app.post("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = Form(...),
    enable_social: str | None = Form(None),
    enable_comments: str | None = Form(None),
    enable_math: str | None = Form(None),
    page: int = Form(1),
):
    try:
        # أولوية وضع الرياضيات إن تم تفعيله
        if enable_math:
            answer = explain_math_ar(q)
            return templates.TemplateResponse(
                "index.html",
                {"request": request, "q": q, "answer": answer, "sources": [],
                 "social_links": build_social_links(q) if enable_social else [],
                 "comment_links": build_comment_links(q) if enable_comments else [],
                 "elapsed": None, "page": 1, "pages": 1, "math_mode": True}
            )

        # بحث ويب عادي
        result = await smart_search(q, page=page, per_page=10)
        answer = smart_summarize(q, result.texts)

        return templates.TemplateResponse(
            "index.html",
            {"request": request, "q": q, "answer": answer,
             "sources": result.sources,
             "social_links": build_social_links(q) if enable_social else [],
             "comment_links": build_comment_links(q) if enable_comments else [],
             "elapsed": result.elapsed_ms, "page": result.page, "pages": result.pages,
             "math_mode": False}
        )
    except Exception as e:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "q": q, "answer": f"حدث خطأ: {e}", "sources": [],
             "social_links": [], "comment_links": [], "elapsed": None,
             "page": 1, "pages": 1, "math_mode": False}
        )

@app.get("/health")
async def health():
    return {"ok": True}
