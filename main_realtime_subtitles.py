# === أضف أعلى الملف إن لزم ===
import asyncio

# === أضف هذا المسار كما هو (لا يستبدل شيئًا آخر) ===
from fastapi import Query

@app.get("/resolve")
async def resolve_playable(video_url: str = Query(...)):
    """
    يحاول استخراج رابط تشغيل مباشر (mp4/m3u8) باستخدام yt-dlp.
    يرجع {"ok": True, "url": "..."} إذا نجح، أو ok=False مع سبب الخطأ.
    """
    try:
        # --get-url يطبع روابط التشغيل النهائية (قد تكون عدة أسطر)
        cmd = ["yt-dlp", "-g", video_url]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            return {"ok": False, "error": (err.decode() or "yt-dlp failed")}
        urls = [x.strip() for x in out.decode().splitlines() if x.strip()]
        if not urls:
            return {"ok": False, "error": "no urls"}
        playable = urls[-1]  # غالبًا آخر سطر هو فيديو (أو m3u8)
        return {"ok": True, "url": playable}
    except Exception as e:
        return {"ok": False, "error": str(e)}
