# main_realtime_subtitles.py
# 🎬 مشروع بسام الذكي - ترجمة الفيديوهات مباشرة إلى العربية

import os, tempfile, subprocess, json, httpx, asyncio
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# إعداد المسارات
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

app = FastAPI(title="Bassam Realtime Translator 🎧")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# الصفحة الرئيسية
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return HTMLResponse(
        "<h3 style='text-align:center;font-family:sans-serif;'>🎧 افتح <a href='/translate_video_rt'>صفحة الترجمة الحية</a></h3>"
    )

# صفحة الترجمة
@app.get("/translate_video_rt", response_class=HTMLResponse)
async def translate_page(request: Request):
    return templates.TemplateResponse("translate_video_rt.html", {"request": request})

# تحميل الصوت من الفيديو واستخراج النص
async def extract_audio(video_url: str):
    """تحميل الفيديو وتحويل الصوت إلى ملف wav"""
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.wav")
        cmd = [
            "yt-dlp", "-x", "--audio-format", "wav",
            "-o", audio_path, video_url
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if not os.path.exists(audio_path):
            raise RuntimeError("لم يتم استخراج الصوت من الفيديو.")
        return audio_path

# التعرف على الكلام عبر Vosk (مجاني وذاتي)
async def recognize_speech(audio_path: str):
    """تحويل الصوت إلى نص باستخدام نموذج Vosk"""
    from vosk import Model, KaldiRecognizer
    import wave

    model_path = os.path.join(BASE_DIR, "vosk-model-small-en-us-0.15")
    if not os.path.exists(model_path):
        return "⚠️ نموذج Vosk غير موجود. نزّله من https://alphacephei.com/vosk/models"

    wf = wave.open(audio_path, "rb")
    rec = KaldiRecognizer(Model(model_path), wf.getframerate())
    rec.SetWords(True)

    result_text = ""
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            result = json.loads(rec.Result())
            result_text += " " + result.get("text", "")
    final = json.loads(rec.FinalResult())
    result_text += " " + final.get("text", "")
    return result_text.strip()

# الترجمة إلى العربية باستخدام واجهة LibreTranslate المجانية
async def translate_to_arabic(text: str):
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.post(
                "https://libretranslate.de/translate",
                json={"q": text, "source": "auto", "target": "ar"},
                headers={"Content-Type": "application/json"}
            )
            data = res.json()
            return data.get("translatedText", "⚠️ لم يتم الترجمة")
    except Exception as e:
        return f"❌ خطأ في الترجمة: {e}"

# نقطة API لتشغيل الترجمة
@app.post("/api/translate_video")
async def translate_video(request: Request, video_url: str = Form(...)):
    try:
        audio_path = await extract_audio(video_url)
        original_text = await recognize_speech(audio_path)
        translated_text = await translate_to_arabic(original_text)
        return JSONResponse({
            "original": original_text,
            "translated": translated_text
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# لتشغيل التطبيق محليًا
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_realtime_subtitles:app", host="0.0.0.0", port=5000, reload=True)
