# app.py — Bassam Brain (واجهة ويب + API) متوافق مع core/brain.py
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pathlib import Path
import json, time, html

# استدعاء العقل المزدوج
from core.brain import smart_answer, save_to_knowledge, KB_FILE

app = FastAPI(title="Bassam Brain – Dual Mind")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
LOG_FILE = DATA_DIR / "log.jsonl"
FEED_FILE = DATA_DIR / "feedback_pool.jsonl"

# ======= أدوات مساعدة =======
def clamp(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n]

def render_bubble(answer_text: str, links=None) -> str:
    """
    يرسم "فقاعة" جواب جميلة مع روابط (إن وُجدت).
    """
    links = links or []
    safe_answer = html.escape(answer_text).replace("\n", "<br>")
    links_html = ""
    if links:
        items = "".join([f"<li><a href='{html.escape(u)}' target='_blank'>{html.escape(u)}</a></li>" for u in links])
        links_html = f"<div class='links'><b>روابط للاستزادة:</b><ul>{items}</ul></div>"

    return f"""
    <div class="bubble">
      <div class="badge">Bassam Brain</div>
      <div class="content">{safe_answer}</div>
      {links_html}
    </div>
    """

BASE_CSS = """
<style>
  :root {{
    --bg: #0b1220;        /* خلفية داكنة */
    --card: #121a2b;
    --text: #e8eefc;
    --muted: #9bb0d3;
    --accent: #3a86ff;
    --success: #28a745;
    --warning: #f59e0b;
  }}
  body {{
    margin: 0; padding: 0;
    background: var(--bg);
    font-family: system-ui, -apple-system, Segoe UI, Roboto, "Noto Kufi Arabic", Arial, sans-serif;
    color: var(--text);
    line-height: 1.6;
  }}
  .wrap {{
    max-width: 880px;
    margin: 24px auto;
    padding: 0 16px;
  }}
  h1 {{
    font-size: 24px; margin-bottom: 8px;
  }}
  .card {{
    background: var(--card);
    border: 1px solid #1e2a44;
    border-radius: 14px;
    padding: 16px;
    box-shadow: 0 8px 20px rgba(0,0,0,.25);
  }}
  textarea {{
    width: 100%; min-height: 120px; resize: vertical;
    border-radius: 10px; padding: 10px; border: 1px solid #2b395a;
    background: #0f1729; color: var(--text);
  }}
  button {{
    background: var(--accent); color: white; border: none;
    padding: 10px 16px; border-radius: 10px; cursor: pointer;
  }}
  button.secondary {{ background: #1f2a44; }}
  .bubble {{
    margin-top: 16px; padding: 16px;
    background: #0e1628; border: 1px solid #203055; border-radius: 14px;
  }}
  .bubble .badge {{
    display: inline-block; font-size: 12px; color: #cfe1ff;
    background: #1c2a48; padding: 3px 8px; border-radius: 999px; margin-bottom: 8px;
  }}
  .bubble .content {{ font-size: 16px; }}
  .bubble .links ul {{ padding-inline-start: 18px; margin-top: 6px; }}
  .muted {{ color: var(--muted); font-size: 13px; }}
  .actions {{ display:flex; gap:8px; flex-wrap: wrap; margin-top: 12px; }}
  a {{ color: #7fb0ff; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .footnote {{ margin-top: 10px; font-size: 12px; color: var(--muted); }}
</style>
"""

# ======= الصفحة الرئيسية =======
@app.get("/", response_class=HTMLResponse)
def home():
    return f"""
<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bassam Brain</title>
{BASE_CSS}
</head>
<body>
  <div class="wrap">
    <h1>🤖 Bassam Brain — العقل المزدوج</h1>
    <p class="muted">يسلّم السؤال، يحلّل، يبحث في الويب، يُلخّص ويُجيب. ويمكنه حفظ الإجابات الجيّدة في قاعدة المعرفة.</p>

    <div class="card">
      <form method="post" action="/ask">
        <textarea name="q" placeholder="اكتب سؤالك هنا... مثال: ما هي عاصمة فرنسا؟ أو: حل معادلة x^2 - 5x + 6 = 0"></textarea>
        <div class="actions">
          <button>إرسال</button>
        </div>
      </form>
    </div>
  </div>
</body>
</html>
    """

# ======= معالجة السؤال (نموذج HTML) =======
@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request):
    form = await request.form()
    q = clamp(form.get("q", ""), 2000)

    answer, meta = smart_answer(q)
    links = meta.get("links") if isinstance(meta, dict) else None

    # سجل التفاعل
    rec = {"ts": int(time.time()), "question": q, "answer": answer, "meta": meta}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # واجهة الحفظ إلى قاعدة المعرفة
    bubble = render_bubble(answer, links)
    return f"""
<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bassam Brain — Result</title>
{BASE_CSS}
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="muted">سؤالك:</div>
      <div class="bubble"><div class="content">{html.escape(q)}</div></div>

      <div style="margin-top:8px" class="muted">الجواب:</div>
      {bubble}

      <div class="actions">
        <form method="post" action="/save_to_knowledge">
          <input type="hidden" name="q" value="{html.escape(q)}">
          <input type="hidden" name="a" value="{html.escape(answer)}">
          <button class="secondary">✅ حفظ هذه الإجابة في قاعدة المعرفة</button>
        </form>
        <a href="/" class="secondary" style="padding:10px 16px;border-radius:10px;background:#1f2a44">◀ رجوع</a>
      </div>
      <div class="footnote">الوضع: {html.escape(str(meta.get('mode')) if isinstance(meta, dict) else 'n/a')}</div>
    </div>
  </div>
</body>
</html>
    """

# ======= حفظ إلى قاعدة المعرفة (من الواجهة) =======
@app.post("/save_to_knowledge", response_class=HTMLResponse)
async def save_to_knowledge_route(request: Request):
    form = await request.form()
    q = clamp(form.get("q", ""), 2000)
    a = clamp(form.get("a", ""), 8000)
    if not q or not a:
        return "<p>⚠️ الرجاء إدخال سؤال وجواب.</p><p><a href='/'>◀ رجوع</a></p>"

    save_to_knowledge(q, a)
    return "<p>✅ تم الحفظ في قاعدة المعرفة بنجاح.</p><p><a href='/'>◀ رجوع</a></p>"

# ======= واجهات API =======
@app.get("/ready")
def ready():
    return {"ok": True}

@app.post("/answer")
async def api_answer(request: Request):
    data = await request.json()
    q = clamp(data.get("question", ""), 2000)
    if not q:
        raise HTTPException(status_code=400, detail="ضع الحقل 'question'")
    answer, meta = smart_answer(q)

    # سجل
    rec = {"ts": int(time.time()), "question": q, "answer": answer, "meta": meta}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return JSONResponse({"ok": True, "answer": answer, "meta": meta})

# (اختياري) تصدير السجل/مجموعة التدريب
@app.get("/export/log")
def export_log():
    if not LOG_FILE.exists():
        LOG_FILE.write_text("", encoding="utf-8")
    return JSONResponse({"ok": True, "path": str(LOG_FILE)})

@app.get("/kb/path")
def kb_path():
    return {"kb_file": str(KB_FILE.resolve())}
