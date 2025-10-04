# ==== Bassam Brain — العقل المزدوج (نسخة قوية) ====

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import traceback
from core.brain import smart_answer

app = FastAPI(title="Bassam Brain — AI العقل المزدوج")

# ربط مجلد الستايل والقوالب
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request, q: str = Form(...)):
    try:
        # تشغيل العقل الذكي
        ans, meta = smart_answer(q)

        # تنسيق النتيجة في فقاعة أنيقة
        html = _render_result(q, ans, meta)
        return HTMLResponse(html)

    except Exception as e:
        traceback.print_exc()
        return HTMLResponse(f"<b>حدث خطأ:</b><br>{e}", status_code=500)


def _render_result(question: str, answer: str, meta: dict) -> str:
    """تنسيق الإجابة في فقاعة مرتبة وجميلة"""
    links_html = ""
    if meta.get("links"):
        links_html = "\n".join([f"🔗 <a href='{u}' target='_blank'>{u}</a>" for u in meta["links"]])

    pretty = (answer or "").strip()
    # ✅ إصلاح مشكلة الباك سلاش داخل f-string
    pretty_html = (
        pretty.replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )

    # ✅ الشكل النهائي لعرض الجواب
    return f"""
    <div style="background:#111827;color:#e5e7eb;border-radius:12px;padding:15px;margin:10px;font-size:17px;line-height:1.6;">
      <b style='color:#38bdf8;'>سؤالك:</b> {question}<br><br>
      <b style='color:#34d399;'>الجواب:</b><br>{pretty_html}<br>
      {'<hr style="border:0.5px solid #333;margin:10px 0;">'+links_html if links_html else ''}
      <div style='font-size:13px;color:#9ca3af;margin-top:6px;'>🧠 الوضع: {meta.get('mode','web')}</div>
    </div>
    """


# ✅ لتشغيل السيرفر في Render أو محلي
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
