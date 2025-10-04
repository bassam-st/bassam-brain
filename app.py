# Bassam Brain — الذكاء اللغوي الذاتي (تحليل + بحث + توليد)
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from core.search_web import web_search, fetch_page_text
from core.summarize import summarize_snippets
from core.llm_generate import generate_answer
import json, time

app = FastAPI(title="Bassam Brain – Smart Arabic AI")

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <h1>🤖 Bassam Brain – الذكاء العربي الذاتي</h1>
    <form method='post' action='/ask'>
      <textarea name='q' rows='4' cols='60' placeholder='اكتب سؤالك هنا...'></textarea><br>
      <button>🔍 إرسال</button>
    </form>
    """

@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request):
    form = await request.form()
    q = form.get("q", "").strip()

    if not q:
        return "<p>⚠️ الرجاء كتابة سؤال.</p>"

    # 1️⃣ بحث في الويب
    results = web_search(q, max_results=5)

    # 2️⃣ تلخيص النتائج
    summary = summarize_snippets(results)

    # 3️⃣ توليد الإجابة الذكية
    prompt = f"السؤال: {q}\n\nالملخص من الويب:\n{summary}\n\nالجواب بالعربية باختصار ووضوح:"
    final_answer = generate_answer(prompt)

    # 4️⃣ عرض النتيجة
    links_html = "<br>".join([f"<a href='{r['link']}' target='_blank'>{r['title']}</a>" for r in results])
    return f"""
    <div style='font-family:Tahoma;max-width:700px;margin:auto'>
      <h3>🧠 سؤالك:</h3>
      <p>{q}</p>
      <h3>💬 إجابة Bassam Brain:</h3>
      <p>{final_answer}</p>
      <details><summary>المصادر 🔗</summary>{links_html}</details>
    </div>
    """
