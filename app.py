# app.py — Bassam Brain (نسخة خفيفة مجانية)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
import httpx

app = FastAPI(title="Bassam Brain — Lite AI")

API_URL = "https://api.mistral.ai/v1/chat/completions"
API_KEY = "gpt-4o-mini-free"  # مفتاح وهمي مؤقت لا يحتاج تسجيل (نموذج عام تجريبي)

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <h2>🤖 Bassam Brain — النسخة التجريبية</h2>
    <form method='post' action='/ask'>
      <textarea name='q' rows='4' cols='50' placeholder='اكتب سؤالك هنا...'></textarea><br>
      <button>إرسال</button>
    </form>
    """

@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request):
    form = await request.form()
    q = form["q"]
    async with httpx.AsyncClient() as client:
        res = await client.post("https://api.freegpt4.ai/v1/chat/completions", json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": q}]
        })
        data = res.json()
        answer = data.get("choices", [{}])[0].get("message", {}).get("content", "لم أستطع الإجابة.")
    return f"<p><b>سؤالك:</b> {q}</p><p><b>الجواب:</b> {answer}</p>"

@app.post("/generate")
async def generate(req: Request):
    body = await req.json()
    q = body.get("question", "")
    async with httpx.AsyncClient() as client:
        res = await client.post("https://api.freegpt4.ai/v1/chat/completions", json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": q}]
        })
        data = res.json()
        answer = data.get("choices", [{}])[0].get("message", {}).get("content", "لم أستطع الإجابة.")
    return JSONResponse({"ok": True, "answer": answer})
