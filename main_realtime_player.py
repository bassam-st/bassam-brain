# main_realtime_player.py — Bassam Realtime Subtitle Player (FastAPI + WebSocket)
# يلزم: ffmpeg موجود في النظام + yt-dlp + vosk + httpx
# يقوم بتنزيل نموذج Vosk تلقائياً إن لم يكن موجوداً (en-US صغير) ويستخدم LibreTranslate للترجمة إلى العربية.

import os, asyncio, json, uuid, re, shutil, tarfile, subprocess, tempfile
from typing import Dict, Optional
from urllib.parse import urlparse, parse_qs

import httpx
from fastapi import FastAPI, Request, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ====== مسارات أساسية
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR    = os.path.join(BASE_DIR, "static")
MODEL_DIR     = os.path.join(BASE_DIR, "models")
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

# ====== تطبيق FastAPI
app = FastAPI(title="Bassam Realtime Subtitle Player")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ====== إعدادات الترجمة و النماذج
LIBRE_TRANSLATE_URL = os.getenv("LIBRE_TRANSLATE_URL", "https://libretranslate.de/translate")
VOSK_MODEL_NAME = os.getenv("VOSK_MODEL_NAME", "vosk-model-small-en-us-0.15")
VOSK_TARBALL_URL = os.getenv(
    "VOSK_TARBALL_URL",
    "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"  # المرايا أحياناً tar.gz أو zip
)

def unzip_any(src_path: str, dst_dir: str):
    # يدعم zip أو tar.gz
    if src_path.endswith(".zip"):
        import zipfile
        with zipfile.ZipFile(src_path, "r") as zf:
            zf.extractall(dst_dir)
    else:
        with tarfile.open(src_path, "r:*") as tf:
            tf.extractall(dst_dir)

async def ensure_vosk_model() -> str:
    """تحميل نموذج Vosk إذا لم يوجد"""
    target_path = os.path.join(MODEL_DIR, VOSK_MODEL_NAME)
    if os.path.isdir(target_path) and os.path.exists(os.path.join(target_path, "am", "mfinal.mat")):
        return target_path

    # إن لم يوجد: نزّل ثم فك الضغط
    archive_path = os.path.join(MODEL_DIR, os.path.basename(VOSK_TARBALL_URL))
    if not os.path.exists(archive_path):
        print(f"[VOSK] downloading model from {VOSK_TARBALL_URL} ...")
        async with httpx.AsyncClient(timeout=None) as cli:
            r = await cli.get(VOSK_TARBALL_URL)
            r.raise_for_status()
            with open(archive_path, "wb") as f:
                f.write(r.content)
    os.makedirs(MODEL_DIR, exist_ok=True)
    print("[VOSK] extracting model...")
    unzip_any(archive_path, MODEL_DIR)
    # قد يختلف اسم المجلد بعد الفك، نبحث عن مجلد بداخله conf/am
    for name in os.listdir(MODEL_DIR):
        p = os.path.join(MODEL_DIR, name)
        if os.path.isdir(p) and os.path.exists(os.path.join(p, "am")):
            return p
    return target_path

# ====== إدارة جلسات الويب سوكِت
class Hub:
    def __init__(self):
        self.clients: Dict[str, WebSocket] = {}
    async def add(self, sid: str, ws: WebSocket):
        await ws.accept()
        self.clients[sid] = ws
    async def send(self, sid: str, data: Dict):
        ws = self.clients.get(sid)
        if not ws: return
        try:
            await ws.send_text(json.dumps(data, ensure_ascii=False))
        except Exception:
            pass
    def remove(self, sid: str):
        self.clients.pop(sid, None)

hub = Hub()

# ====== صفحات
@app.get("/", response_class=HTMLResponse)
async def home():
    # صفحة بسيطة فيها رابط للترجمة الحية
    return HTMLResponse('<meta charset="utf-8"/><div style="padding:24px;font-family:sans-serif">افتح <a href="/translate_video_rt">/translate_video_rt</a> للترجمة الحيّة 🎧</div>')

@app.get("/translate_video_rt", response_class=HTMLResponse)
async def translate_page(request: Request, video_url: Optional[str] = None):
    return templates.TemplateResponse("realtime_player.html", {"request": request, "video_url": video_url or ""})

# ====== نقطة بدء الجلسة: ترجع sid ونبدأ بث التفريغ والترجمة عبر WS
@app.post("/rt/start")
async def start_rt(video_url: str = Form(...)):
    if not video_url:
        return JSONResponse({"ok": False, "error": "no_url"}, status_code=400)

    # أنشئ معرّف جلسة
    sid = uuid.uuid4().hex

    # شغّل المهمة بالخلفية
    asyncio.create_task(run_realtime_pipeline(sid, video_url.strip()))
    return {"ok": True, "sid": sid}

# ====== WebSocket للعميل ليستقبل الجُمل لحظيًّا
@app.websocket("/ws/{sid}")
async def ws_subtitles(ws: WebSocket, sid: str):
    try:
        await hub.add(sid, ws)
        while True:
            # لا نتوقع رسائل من العميل، لكن نحافظ على الاتصال
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        hub.remove(sid)

# ====== دوال مساعدة
def build_ytdlp_audio_cmd(video_url: str):
    """
    استخدم yt-dlp لاستخراج مسار الصوت وبثه إلى ffmpeg عبر stdout
    ثم نحول إلى PCM s16le mono 16kHz ليتوافق مع Vosk
    """
    ytdlp = ["yt-dlp", "-f", "bestaudio/best", "-o", "-", video_url]
    ffmpeg = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", "pipe:0",
        "-ac", "1", "-ar", "16000",
        "-f", "s16le", "pipe:1"
    ]
    return ytdlp, ffmpeg

async def translate_to_ar(text: str) -> str:
    payload = {"q": text, "source": "auto", "target": "ar", "format": "text"}
    try:
        async with httpx.AsyncClient(timeout=30) as cli:
            r = await cli.post(LIBRE_TRANSLATE_URL, json=payload)
            r.raise_for_status()
            data = r.json()
            return data.get("translatedText", "") or text
    except Exception:
        # فشل الخادم المجاني—أعد النص الأصلي كتدبير احتياطي
        return text

def youtube_embed_url(url: str) -> Optional[str]:
    try:
        u = urlparse(url)
        if "youtube.com" in u.netloc or "youtu.be" in u.netloc:
            vid = None
            if "youtube.com" in u.netloc:
                qs = parse_qs(u.query)
                vid = (qs.get("v") or [None])[0]
            else:
                # youtu.be/<id>
                vid = u.path.strip("/").split("/")[0]
            if vid:
                return f"https://www.youtube.com/embed/{vid}?autoplay=1"
    except Exception:
        pass
    return None

# ====== المهمة الأساسية: تنزيل الصوت -> تفريغ Vosk -> ترجمة -> بث عبر WS
async def run_realtime_pipeline(sid: str, video_url: str):
    model_path = await ensure_vosk_model()

    # تجهير أنبوبين: ytdlp | ffmpeg -> stdout PCM
    ytdlp_cmd, ffmpeg_cmd = build_ytdlp_audio_cmd(video_url)

    y = await asyncio.create_subprocess_exec(
        *ytdlp_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    f = await asyncio.create_subprocess_exec(
        *ffmpeg_cmd, stdin=y.stdout, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    # استيراد Vosk داخليًا بعد توفر النموذج
    from vosk import Model, KaldiRecognizer
    model = Model(model_path)
    rec = KaldiRecognizer(model, 16000)
    rec.SetWords(True)

    await hub.send(sid, {"type": "meta", "msg": "listening", "embed": youtube_embed_url(video_url) or ""})

    try:
        # نقرأ من stdout الخاص بـ ffmpeg chunks صغيرة
        while True:
            chunk = await f.stdout.read(4000)
            if not chunk:
                break
            if rec.AcceptWaveform(chunk):
                res = json.loads(rec.Result())
                text = res.get("text", "").strip()
                if text:
                    ar = await translate_to_ar(text)
                    await hub.send(sid, {"type": "line", "src": text, "ar": ar})
        # آخر جزء
        final = json.loads(rec.FinalResult())
        ftxt = (final.get("text") or "").strip()
        if ftxt:
            far = await translate_to_ar(ftxt)
            await hub.send(sid, {"type": "line", "src": ftxt, "ar": far})
    except Exception as e:
        await hub.send(sid, {"type": "error", "error": str(e)})
    finally:
        try:
            if f.returncode is None:
                f.terminate()
        except Exception:
            pass
        try:
            if y.returncode is None:
                y.terminate()
        except Exception:
            pass
        await hub.send(sid, {"type": "done"})
