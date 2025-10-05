# ==== app.py — Bassam الذكي ====
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.brain import smart_answer          # يجب أن يقبل force_social
from core.math_solver import explain_math_answer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title="Bassam الذكي — بحث عميق وذكاء شامل")

# مجلدات الواجهة
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/search")
async def search(request: Request):
    data = await request.json()
    q = data.get("q", "").strip()
    force_social = bool(data.get("force_social", False))
    if not q:
        return JSONResponse({"ok": False, "error": "empty_query"})
    try:
        answer, sources = await smart_answer(q, force_social=force_social)
        return JSONResponse({"ok": True, "answer": answer, "sources": sources})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})

@app.post("/solve_math")
async def solve_math(request: Request):
    data = await request.json()
    q = data.get("q", "").strip()
    if not q:
        return JSONResponse({"ok": False, "error": "empty_query"})
    try:
        solution = explain_math_answer(q)
        return JSONResponse({"ok": True, "solution": solution})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
