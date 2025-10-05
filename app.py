import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.engine import smart_search
from core.social import build_social_links
from core.summarize import smart_summarize

app = FastAPI(title="Bassam v4.0 Full-AI")

# Static & templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "answer": None,
            "sources": [],
            "social_links": [],
            "q": "",
            "elapsed": None,
            "page": 1,
            "pages": 1,
        },
    )

@app.post("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = Form(...),
    enable_social: str | None = Form(None),
    page: int = Form(1),
):
    try:
        # 1) Web search
        result = await smart_search(q, page=page, per_page=10)

        # 2) Summarize answer (من النصوص المتاحة)
        answer = smart_summarize(q, result.texts)

        # 3) Social (روابط قابلة للنقر فقط — بدون كشط)
        social_links = build_social_links(q) if enable_social else []

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "q": q,
                "answer": answer,
                "sources": result.sources,  # [{title,url,site}]
                "social_links": social_links,  # [(name,url)]
                "elapsed": result.elapsed_ms,
                "page": result.page,
                "pages": result.pages,
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "q": q,
                "answer": f"حدث خطأ: {str(e)}",
                "sources": [],
                "social_links": [],
                "elapsed": None,
                "page": 1,
                "pages": 1,
            },
        )

# صحة الخدمة
@app.get("/health")
async def health():
    return {"ok": True}
