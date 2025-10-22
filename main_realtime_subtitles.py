# ============================================================
# main_realtime_subtitles.py — Bassam Realtime Subtitles 🎬
# ترجمات فورية أثناء تشغيل الفيديو (سطر بسطر) + سقوط آمن للوضع البطيء
# ============================================================

import os, json, asyncio, subprocess, tempfile, wave
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import httpx

# ---------- مسارات أساسية ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

app = FastAPI(title="Bassam Realtime Subtitles")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# ---------- صفحة البداية ----------
@app.get("/", response_class=HTMLResponse)
async def root(_request: Request):
    return HTMLResponse("<h3 style='text-align:center;font-family:sans-serif'>افتح <a href='/translate_video_rt'>/translate_video_rt</a> للترجمة الحية 🎧</h3>")


# ---------- صفحة الريل تايم ----------
@app.get("/translate_video_rt", response_class=HTMLResponse)
async def translate_page(request: Request):
    return templates.TemplateResponse("translate_video_rt.html", {"request": request, "video_url": None})


@app.post("/translate_video_rt", response_class=HTMLResponse)
async def translate_page_post(request: Request, video_url: str = Form(...)):
    video_url = (video_url or "").strip()
    return templates.TemplateResponse("translate_video_rt.html", {"request": request, "video_url": video_url})


# ---------- ترجمة نص إلى العربية (LibreTranslate) ----------
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
            data = r.json()
            return data.get("translatedText", "") or ""
    except Exception as e:
        return f"[تعذّرت الترجمة: {e}]"


# ---------- محاولة استخراج رابط الصوت المباشر باستخدام yt-dlp ----------
def resolve_direct_audio_url(video_page_url: str) -> str | None:
    try:
        # نطلب فقط أفضل صوت
        cmd = [
            "yt-dlp", "-f", "bestaudio/best",
            "-g",  # اطبع الرابط المباشر فقط
            video_page_url
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        direct = (proc.stdout or "").strip().splitlines()
        if direct:
            return direct[-1].strip()
        return None
    except Exception:
        return None


# ---------- بث ترميزات (SSE) ----------
async def sse_event(data: dict) -> bytes:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


# ---------- RUNTIME: فوك-التعرّف الصوتي على دفق ffmpeg + ترجمة فورية ----------
async def stream_subtitles_sse(video_url: str) -> AsyncGenerator[bytes, None]:
    """
    يحاول بث الصوت عبر ffmpeg -> PCM 16k mono -> Vosk
    عند كل نتيجة نهائية يترجمها ويرسلها عبر SSE.
    """
    # 1) نحل رابط الصوت المباشر
    direct = resolve_direct_audio_url(video_url) or video_url

    # 2) افعل ffmpeg -> s16le mono 16k إلى stdout
    ffmpeg_cmd = [
        "ffmpeg",
        "-loglevel", "error",
        "-i", direct,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-f", "s16le",
        "pipe:1",
    ]

    try:
        # تأكد من وجود نموذج Vosk (صغير/إنجليزي كمثال؛ يمكن تبديله لاحقًا بالعربي)
        from vosk import Model, KaldiRecognizer  # noqa
    except Exception:
        # لا توجد vosk (أو لم تُثبت)، نرسل رسالة وننهي
        yield await sse_event({"type": "error", "msg": "مكتبة Vosk غير مثبتة. أضف vosk إلى requirements.txt ثم أعد النشر."})
        return

    model_path = os.path.join(BASE_DIR, "vosk-model-small-en-us-0.15")
    if not os.path.isdir(model_path):
        yield await sse_event({
            "type": "error",
            "msg": "نموذج VOSK غير موجود. حمّله وضعه بجانب المشروع: vosk-model-small-en-us-0.15"
        })
        return

    # شغّل ffmpeg
    try:
        proc = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        # ffmpeg غير متوفر -> سنسقط للوضع البطيء (يُنزل الصوت كاملًا ثم يترجمه دفعة واحدة)
        yield await sse_event({"type": "fallback", "msg": "ffmpeg غير متوفر — التحويل للوضع البطيء."})
        async for x in batch_translate_fallback(video_url):
            yield x
        return

    # حضّر Vosk
    from vosk import Model, KaldiRecognizer
    model = Model(model_path)
    rec = KaldiRecognizer(model, 16000)
    rec.SetWords(True)

    # نقرأ قطع الصوت من stdout ونمرّرها إلى Vosk
    chunk_size = 8000  # بايت
    sent_any = False
    try:
        while True:
            chunk = await proc.stdout.read(chunk_size)
            if not chunk:
                break

            if rec.AcceptWaveform(chunk):
                # نتيجة نهائية
                res = json.loads(rec.Result() or "{}")
                text = (res.get("text") or "").strip()
                if text:
                    sent_any = True
                    ar = await translate_to_ar(text)
                    yield await sse_event({"type": "final", "src": text, "ar": ar})

            else:
                # نتيجة جزئية (اختياري)
                pres = json.loads(rec.PartialResult() or "{}")
                ptxt = (pres.get("partial") or "").strip()
                if ptxt:
                    # يمكن إرسالها كـ "partial" لو حاب، الآن نتجنب الإزعاج
                    pass

        # ما تبقّى
        last = json.loads(rec.FinalResult() or "{}")
        ltxt = (last.get("text") or "").strip()
        if ltxt:
            ar = await translate_to_ar(ltxt)
            yield await sse_event({"type": "final", "src": ltxt, "ar": ar})

        if not sent_any:
            yield await sse_event({"type": "info", "msg": "لم يُلتقط كلام مفهوم من المصدر."})

    except Exception as e:
        yield await sse_event({"type": "error", "msg": f"تعذّر البث: {e}"})

    finally:
        try:
            if proc and proc.returncode is None:
                proc.kill()
        except Exception:
            pass

    # انتهاء البث
    yield await sse_event({"type": "done"})


# ---------- Fallback: تنزيل الصوت وترجمته دفعة واحدة ----------
async def batch_translate_fallback(video_url: str) -> AsyncGenerator[bytes, None]:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            audio_path = os.path.join(tmp, "audio.wav")
            # نحمل الصوت عبر yt-dlp إلى wav
            cmd = ["yt-dlp", "-x", "--audio-format", "wav", "-o", audio_path, video_url]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            from vosk import Model, KaldiRecognizer
            model_path = os.path.join(BASE_DIR, "vosk-model-small-en-us-0.15")
            if not os.path.isdir(model_path):
                yield await sse_event({"type": "error", "msg": "نموذج VOSK غير موجود."})
                return

            model = Model(model_path)
            wf = wave.open(audio_path, "rb")
            rec = KaldiRecognizer(model, wf.getframerate())
            rec.SetWords(True)
            text_parts = []
            while True:
                data = wf.readframes(4000)
                if not data:
                    break
                if rec.AcceptWaveform(data):
                    r = json.loads(rec.Result() or "{}")
                    if "text" in r:
                        text_parts.append(r["text"])
            wf.close()

            text = ". ".join([t for t in text_parts if t])
            if not text.strip():
                yield await sse_event({"type": "info", "msg": "لم يتم التعرف على كلام."})
                yield await sse_event({"type": "done"})
                return

            ar = await translate_to_ar(text)
            yield await sse_event({"type": "final", "src": text, "ar": ar})
            yield await sse_event({"type": "done"})
    except Exception as e:
        yield await sse_event({"type": "error", "msg": f"تعذّر الوضع البطيء: {e}"})


# ---------- endpoint: بث الترجمة عبر SSE ----------
@app.get("/sse_subs")
async def sse_subs(url: str):
    if not url:
        return PlainTextResponse("missing url", status_code=400)
    generator = stream_subtitles_sse(url)
    return StreamingResponse(generator, media_type="text/event-stream")
