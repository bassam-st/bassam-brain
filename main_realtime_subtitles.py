# ============================================================
# main_realtime_full.py — Bassam Realtime Universal Translator
# ============================================================
# يدعم الترجمة الفورية لأي فيديو (YouTube / Twitter / TikTok / MP4 ...)
# عبر استخراج الصوت -> تفريغ النص -> ترجمة -> عرض مترجم حي.
# ============================================================

import os, asyncio, tempfile, subprocess, json, re, wave
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx
from vosk import Model, KaldiRecognizer
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

app = FastAPI(title="Bassam Realtime Universal Translator")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# نموذج الصوت المحلي (Vosk)
MODEL_PATH = os.path.join(BASE_DIR, "vosk-model-small-en-us-0.15")

# تحميل نموذج Vosk مرة واحدة عند التشغيل
if not os.path.exists(MODEL_PATH):
    print("⚠️ يرجى تنزيل نموذج Vosk من:")
    print("👉 https://alphacephei.com/vosk/models")
    print("ثم ضع المجلد داخل المشروع.")
model = Model(MODEL_PATH)

# ترجمة عبر LibreTranslate
async def translate_to_ar(text: str):
    if not text.strip():
        return ""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.post(
                "https://libretranslate.de/translate",
                json={"q": text, "source": "auto", "target": "ar"},
                headers={"Content-Type": "application/json"},
            )
            data = res.json()
            return data.get("translatedText", text)
    except Exception:
        return text

# استخراج الصوت من الفيديو
def extract_audio(video_url: str, out_path: str):
    cmd = [
        "yt-dlp",
        "-f", "bestaudio",
        "--extract-audio",
        "--audio-format", "wav",
        "--audio-quality", "0",
        "-o", out_path,
        video_url,
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

# تفريغ الصوت باستخدام Vosk
def transcribe_audio(path: str):
    rec = KaldiRecognizer(model, 16000)
    results = []
    with wave.open(path, "rb") as wf:
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                part = json.loads(rec.Result())
                if "text" in part:
                    results.append(part["text"])
        final = json.loads(rec.FinalResult())
        if "text" in final:
            results.append(final["text"])
    return results

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return HTMLResponse(
        '<h2 style="text-align:center">افتح <a href="/translate_full">/translate_full</a> لمشاهدة الترجمة الفورية 🎧</h2>'
    )

@app.get("/translate_full", response_class=HTMLResponse)
async def page(request: Request):
    return templates.TemplateResponse("translate_full.html", {"request": request})

@app.post("/api/full_translate")
async def full_translate(request: Request):
    data = await request.json()
    url = data.get("url", "").strip()
    if not url:
        return JSONResponse({"ok": False, "error": "missing_url"})

    tmpdir = tempfile.TemporaryDirectory()
    audio_path = os.path.join(tmpdir.name, "audio.%(ext)s")
    status = "جاري التحميل..."

    # 1️⃣ استخراج الصوت
    extract_audio(url, audio_path)
    wav_file = os.path.join(tmpdir.name, "audio.wav")
    if not os.path.exists(wav_file):
        return JSONResponse({"ok": False, "error": "download_failed"})

    # 2️⃣ تفريغ النص
    status = "جاري التفريغ..."
    transcript = transcribe_audio(wav_file)

    # 3️⃣ الترجمة للعربية
    status = "جاري الترجمة..."
    joined = ". ".join(transcript)
    ar_text = await translate_to_ar(joined)

    return JSONResponse({"ok": True, "status": status, "text_ar": ar_text})
