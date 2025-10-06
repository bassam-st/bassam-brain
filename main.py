import os, json, time, uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, UploadFile, File, Depends, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from duckduckgo_search import DDGS
import httpx

# --- إعداد مجلدات العمل ---
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
UPLOADS_DIR = STATIC_DIR / "uploads"
CACHE_DIR = BASE_DIR / "cache"
for p in [STATIC_DIR, TEMPLATES_DIR, UPLOADS_DIR, CACHE_DIR]:
    p.mkdir(parents=True, exist_ok=True)

LOG_FILE = CACHE_DIR / "logs.jsonl"

# --- إعدادات بسيطة ---
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "093589")  # طلبك
SERPER_API_KEY = os.getenv("SERPER_API_KEY")             # بحث Google (اختياري)

app = FastAPI(title="Bassam Smart Search")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ----------------- أدوات مساعدة -----------------
def log_event(event: dict) -> None:
    """تسجيل أي حدث كسطر JSONL لسهولة القراءة لاحقًا في لوحة الإدارة."""
    event["ts"] = int(time.time())
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def admin_required(request: Request):
    token = request.cookies.get("admin_auth")
    if token != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


async def google_search_serper(query: str, max_results: int = 8):
    if not SERPER_API_KEY:
        return None  # ما في مفتاح -> نرجع None علشان نستعمل DuckDuckGo
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {"q": query, "gl": "sa", "hl": "ar"}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    results = []
    for item in (data.get("organic", []) or [])[:max_results]:
        results.append({
            "title": item.get("title"),
            "snippet": item.get("snippet"),
            "link": item.get("link"),
            "source": "Google"
        })
    return results


def ddg_web_search(query: str, max_results: int = 8):
    out = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, region="xa-ar", max_results=max_results):
            out.append({
                "title": r.get("title"),
                "snippet": r.get("body"),
                "link": r.get("href"),
                "source": "DuckDuckGo"
            })
    return out


# ----------------- الصفحات -----------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = Form(...),
    include_prices: Optional[bool] = Form(False),
):
    # 1) نحاول Google (Serper) إن توفر مفتاح، وإلا DuckDuckGo
    google = await google_search_serper(q)
    results = google if google else ddg_web_search(q)

    # (اختياري) فلترة بسيطة لو فعل المستخدم "روابط الأسعار"
    if include_prices:
        results = [r for r in results if any(k in (r.get("snippet") or "").lower() for k in ["price", "سعر", "ريال", "درهم", "دولار", "$"]) or
                   any(k in (r.get("title") or "").lower() for k in ["price", "سعر", "ريال", "درهم", "دولار", "$"])]

    # Log
    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
    log_event({"type": "text_search", "q": q, "ip": client_ip, "results": len(results)})

    return templates.TemplateResponse("results.html", {
        "request": request,
        "q": q,
        "results": results,
        "used": "Google" if google else "DuckDuckGo"
    })


# --- رفع صورة + إنشاء روابط بحث العدسة ---
@app.post("/search_image", response_class=HTMLResponse)
async def search_image(request: Request, image: UploadFile = File(...)):
    # تحفظ الصورة
    ext = (image.filename or "").split(".")[-1].lower()
    if ext not in ["jpg", "jpeg", "png", "webp", "gif"]:
        ext = "jpg"
    file_id = f"{uuid.uuid4().hex}.{ext}"
    save_path = UPLOADS_DIR / file_id
    data = await image.read()
    save_path.write_bytes(data)

    # رابط عام للصورة (لتمريره إلى عدسات طرف ثالث)
    base_url = str(request.base_url).rstrip("/")
    public_url = f"{base_url}/static/uploads/{file_id}"

    # نجهز روابط قفز للبحث بالصور
    links = {
        "Google Lens": f"https://lens.google.com/uploadbyurl?url={public_url}",
        "Bing Visual Search": f"https://www.bing.com/images/searchbyimage?cbir=sbi&imgurl={public_url}",
        "Yandex": f"https://yandex.com/images/search?rpt=imageview&url={public_url}",
    }

    # Log
    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
    log_event({"type": "image_search", "file": file_id, "ip": client_ip})

    return templates.TemplateResponse("image_result.html", {
        "request": request,
        "img_url": public_url,
        "links": links
    })


# ----------------- لوحة الإدارة -----------------
@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    # لو معاه كوكي صحيحة يدخّل، وإلا يظهر نموذج الدخول
    token = request.cookies.get("admin_auth")
    if token == ADMIN_PASSWORD:
        # اقرأ آخر 500 سطر مثلًا
        rows = []
        if LOG_FILE.exists():
            with LOG_FILE.open("r", encoding="utf-8") as f:
                for line in f.readlines()[-500:]:
                    try:
                        rows.append(json.loads(line))
                    except:
                        pass
        rows.reverse()
        return templates.TemplateResponse("admin.html", {"request": request, "rows": rows, "ok": True})
    else:
        return templates.TemplateResponse("admin.html", {"request": request, "ok": False})


@app.post("/admin/login")
def admin_login(password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        resp = RedirectResponse(url="/admin", status_code=302)
        # كوكي بسيطة (ليست نظام JWT) – تكفي للوحة البسيطة
        resp.set_cookie("admin_auth", ADMIN_PASSWORD, httponly=True, max_age=60*60*6)
        return resp
    return RedirectResponse(url="/admin", status_code=302)


@app.post("/admin/clear", dependencies=[Depends(admin_required)])
def admin_clear():
    if LOG_FILE.exists():
        LOG_FILE.unlink()
    return RedirectResponse(url="/admin", status_code=302)
