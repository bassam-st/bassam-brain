# ============================================================
# main_realtime_subtitles.py — Bassam Realtime Video Translator 🎬
# تطبيق بسام الذكي لترجمة الفيديوهات مباشرة إلى العربية ❤️
# ============================================================

import os, tempfile, subprocess, json, httpx, wave
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ============ إعداد المسارات الأساسية ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

app = FastAPI(title="Bassam Live Translator")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ============ صفحة البداية ============
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return HTMLResponse(
        "<h3 style='text-align:center;font-family:sans-serif'>✅ افتح <a href='/translate_video'>/translate_video</a> لتجربة الترجمة الحيّة 🎬</h3>"
    )

# ============ صفحة الترجمة ============
@app.get("/translate_video", response_class=HTMLResponse)
async def translate_page(request: Request):
    return templates.TemplateResponse("translate_video.html", {"request": request})

# ============ الترجمة باستخدام LibreTranslate ============
async def translate_to_arabic(text: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.post(
                "https://libretranslate.de/translate",
                json={"q": text, "source": "auto", "target": "ar"},
                headers={"Content-Type": "application/json"},
            )
            data = res.json()
            return data.get("translatedText", "")
    except Exception as e:
        return f"⚠️ خطأ أثناء الترجمة: {e}"

# ============ تحميل الصوت من الفيديو + استخراج الكلام ============
async def extract_audio_and_translate(video_url: str) -> str:
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = os.path.join(tmpdir, "audio.wav")

            # 🔹 تحميل الصوت فقط من الفيديو عبر yt-dlp
            cmd = [
                "yt-dlp",
                "-x", "--audio-format", "wav",
                "-o", audio_path,
                video_url,
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # 🔹 استخلاص النص بالصوت باستخدام vosk
            from vosk import Model, KaldiRecognizer

            model_path = os.path.join(BASE_DIR, "vosk-model-small-en-us-0.15")
            if not os.path.exists(model_path):
                return (
                    "⚠️ النموذج الصوتي VOSK غير موجود.<br>"
                    "حمّله من: <a href='https://alphacephei.com/vosk/models' target='_blank'>vosk-model-small-en-us-0.15</a>"
                )

            wf = wave.open(audio_path, "rb")
            rec = KaldiRecognizer(Model(model_path), wf.getframerate())
            rec.SetWords(True)
            results = []
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    if "text" in result:
                        results.append(result["text"])
            wf.close()

            text = ". ".join(results)
            if not text.strip():
                return "⚠️ لم يتم التعرف على أي كلام في الفيديو."

            # 🔹 ترجمة النص إلى العربية
            translated = await translate_to_arabic(text)
            return translated or "⚠️ لم يتم الحصول على ترجمة."
    except Exception as e:
        return f"⚠️ خطأ أثناء التحليل: {e}"

# ============ استقبال الرابط من المستخدم ============
@app.post("/translate_video", response_class=HTMLResponse)
async def translate_video(request: Request, video_url: str = Form(...)):
    translation = await extract_audio_and_translate(video_url)
    ctx = {"request": request, "video_url": video_url, "translation": translation}
    return templates.TemplateResponse("translate_video.html", ctx)
