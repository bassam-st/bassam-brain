import asyncio
from fastapi import Query

@app.get("/resolve")
async def resolve_playable(video_url: str = Query(...)):
    """
    يعيد رابط تشغيل مباشر (mp4/m3u8) إن أمكن باستخدام yt-dlp.
    يوضح الخطأ بوضوح إن فشل.
    """
    try:
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
             "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        cmd = [
            "yt-dlp",
            "-g",
            "-f", "bv*+ba/best",       # دمج أفضل فيديو+صوت إن أمكن
            "--no-check-certificates",
            "--user-agent", ua,
            "--referer", video_url,
            video_url,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            return {"ok": False, "error": (err.decode() or "yt-dlp failed")}
        urls = [x.strip() for x in out.decode().splitlines() if x.strip()]
        if not urls:
            return {"ok": False, "error": "no playable urls"}
        # اختر m3u8 إن وجد، وإلا خذ آخر رابط
        best = None
        for u in urls:
            if ".m3u8" in u:
                best = u
        if not best:
            best = urls[-1]
        return {"ok": True, "url": best, "debug": {"count": len(urls)}}
    except Exception as e:
        return {"ok": False, "error": str(e)}
