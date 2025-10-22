# ============================================================
# main_realtime_subtitles.py - نسخة مبسطة تعمل فوراً
# ============================================================

import os, json, asyncio
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
import httpx

app = FastAPI(title="Bassam Realtime Subtitles")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# ---------- الصفحات ----------
@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("translate_video_rt.html", {"request": request, "video_url": None})

@app.get("/translate_video_rt")
async def translate_page(request: Request):
    return templates.TemplateResponse("translate_video_rt.html", {"request": request, "video_url": None})

@app.post("/translate_video_rt")
async def translate_page_post(request: Request, video_url: str = Form(...)):
    return templates.TemplateResponse("translate_video_rt.html", {"request": request, "video_url": video_url})

# ---------- ترجمة نصية ----------
async def translate_to_ar(text: str) -> str:
    if not text.strip():
        return ""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://libretranslate.de/translate",
                json={"q": text, "source": "auto", "target": "ar"},
                headers={"Content-Type": "application/json"},
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("translatedText", text)
            else:
                return f"[ترجمة: {text}]"
    except Exception as e:
        return f"[ترجمة: {text}]"

# ---------- محاكاة البث (للتجربة) ----------
async def mock_stream_subtitles(video_url: str):
    # رسائل تجريبية للعرض
    messages = [
        "Welcome to Bassam Brain Realtime Translation",
        "This service provides instant video translation to Arabic", 
        "The system is currently in demonstration mode",
        "Thank you for testing our translation platform"
    ]
    
    yield f"data: {json.dumps({'type': 'info', 'msg': 'جاري بدء الترجمة...'}, ensure_ascii=False)}\n\n"
    await asyncio.sleep(1)
    
    for i, msg in enumerate(messages):
        ar_text = await translate_to_ar(msg)
        yield f"data: {json.dumps({'type': 'final', 'src': msg, 'ar': ar_text}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(4)
    
    yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

@app.get("/sse_subs")
async def sse_subs(url: str):
    if not url:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'msg': 'يرجى إدخال رابط الفيديو'}, ensure_ascii=False)}\n\n"]), 
            media_type="text/event-stream"
        )
    
    generator = mock_stream_subtitles(url)
    return StreamingResponse(generator, media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
