# app.py — Bassam Brain Pro (Starter)
# واجهة ويب + API تعتمد على "العقل المزدوج" في core/brain.py

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
import json, time, pathlib, os
from core.brain import smart_answer  # <- العقل

app = FastAPI(title="Bassam Brain Pro")

# تخزين بسيط للتعلّم لاحقًا
DATA_DIR = pathlib.Path("data"); DATA_DIR.mkdir(exist_ok=True)
LOG_FILE = DATA_DIR / "log.jsonl"

# ---------- صفحة رئيسية بسيطة (كل الإجابة داخل فقاعة) ----------
HTML_INDEX = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Bassam Brain Pro</title>
<style>
  body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", "Helvetica Neue", Arial; background:#0B1220; color:#E6EDF3; margin:0; }
  .wrap { max-width:860px; margin:28px auto; padding:0 16px; }
  h1 { font-size:26px; margin:0 0 18px; }
  form { background:#0F172A; padding:16px; border-radius:16px; box-shadow: 0 10px 30px rgba(0,0,0,.25); }
  textarea { width:100%; min-height:120px; border-radius:12px; border:1px solid #1F2937; background:#0B1220; color:#E6EDF3; padding:12px; font-size:16px; }
  button { margin-top:12px; padding:10px 16px; border:none; border-radius:10px; background:#2563EB; color:white; font-weight:600; cursor:pointer; }
  .bubble { margin-top:16px; background:#111827; border:1px solid #1F2937; border-radius:16px; padding:16px 18px; line-height:1.7; white-space:pre-wrap; }
  .meta { margin-top:8px; font-size:13px; color:#93A4B3; }
  a { color:#60A5FA; text-decoration:none; }
  a:hover { text-decoration:underline; }
  .note { font-size:13px; color:#9CA3AF; margin-top:8px; }
</style>
</head>
<body>
  <div class="wrap">
    <h1>🤖 Bassam Brain <small style="font-size:16px;color:#93A4B3">Pro</small></h1>
    <form method="post" action="/ask">
      <textarea name="q" placeholder="اكتب سؤالك هنا… مثال: ما عاصمة ألمانيا؟ أو حل المعادلة: 2x+3=7"></textarea>
      <button>إرسال</button>
      <div class="note">
        المحركات المستخدمة: Wikipedia ⇢ Bing ⇢ Brave ⇢ SerpAPI ⇢ DuckDuckGo (الأخير كاحتياطي).<br/>
        يمكنك إضافة مفاتيح البيئة في Render: <code>BING_API_KEY</code>, <code>BRAVE_API_KEY</code>, <code>SERPAPI_KEY</code>.
      </div>
    </form>
    {RESULT}
  </div>
</body>
</html>
"""

def _render_result(question: str, answer: str, meta: dict) -> str:
    links_html = ""
    if meta.get("links"):
        links_html = "\n\n🔗 مصادر:\n" + "\n".join([f"- {u}" for u in meta["links"]])
    pretty = (answer or "").strip()
    return f"""
    <div class="bubble">
      <div><b>سؤالك:</b> {question}</div>
      <div style="margin-top:10px"><b>الجواب:</b><br>{pretty.replace("<","&lt;").replace(">","&gt;").replace("\\n","<br>")}</div>
      {'<div class="meta" style="margin-top:10px">'+links_html.replace("\\n","<br>")+'</div>' if links_html else ''}
      <div class="meta">وضع: {meta.get('mode','web')}</div>
    </div>
    """

@app.get("/", response_class=HTMLResponse)
def home():
    return HTML_INDEX.replace("{RESULT}", "")

@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request):
    form = await request.form()
    q = (form.get("q") or "").strip()
    if not q:
        return HTML_INDEX.replace("{RESULT}", '<div class="bubble">⚠️ رجاءً اكتب سؤالًا.</div>')
    answer, meta = await smart_answer(q)

    # سجّل للتعلّم لاحقًا
    rec = {"ts": int(time.time()), "q": q, "answer": answer, "meta": meta}
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False)+"\n")

    return HTML_INDEX.replace("{RESULT}", _render_result(q, answer, meta))

# ---------- JSON API ----------
@app.post("/answer", response_class=JSONResponse)
async def answer_api(request: Request):
    data = await request.json()
    q = (data.get("question") or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="ضع حقل 'question'")
    answer, meta = await smart_answer(q)

    rec = {"ts": int(time.time()), "q": q, "answer": answer, "meta": meta}
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False)+"\n")

    return {"ok": True, "answer": answer, "meta": meta}

@app.get("/ready")
def ready():
    return {"ok": True}
