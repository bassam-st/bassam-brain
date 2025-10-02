import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# llama.cpp (Python bindings)
from llama_cpp import Llama

# إعدادات قليلة الذاكرة (مهمة على Render Free)
MODEL_PATH = os.getenv("MODEL_PATH", "models/model.gguf")
N_CTX      = int(os.getenv("N_CTX", "512"))   # خفّضها إذا واجهت OOM (256 مثلاً)
N_THREADS  = int(os.getenv("N_THREADS", "1")) # 1 لتقليل CPU
N_BATCH    = int(os.getenv("N_BATCH", "16"))

# تأكد أن الملف موجود (يُنزَّل في خطوة البناء)
if not os.path.exists(MODEL_PATH):
    raise RuntimeError(f"Model file not found: {MODEL_PATH}. Did build step download it?")

llm = Llama(
    model_path=MODEL_PATH,
    n_ctx=N_CTX,
    n_threads=N_THREADS,
    n_batch=N_BATCH,
    use_mmap=True,
    use_mlock=False,
    verbose=False,
)

app = FastAPI(title="Bassam Brain (Free)")

class Ask(BaseModel):
    question: str
    extra: str | None = None
    max_new_tokens: int = 180
    temperature: float = 0.8
    top_p: float = 0.9

PROMPT_WITH = """[سؤال]
{q}

[مُدخل إضافي]
{x}

[أجب بإيجاز ووضوح]:"""
PROMPT_NO = """[سؤال]
{q}

[أجب بإيجاز ووضوح]:"""

@app.get("/live")
def live(): return {"ok": True}

@app.get("/ready")
def ready():
    return {"ok": True, "model": os.path.basename(MODEL_PATH), "n_ctx": N_CTX}

@app.post("/generate")
def generate(body: Ask):
    prompt = (PROMPT_WITH.format(q=body.question, x=(body.extra or "").strip())
              if (body.extra and body.extra.strip()) else
              PROMPT_NO.format(q=body.question))
    out = llm(
        prompt,
        max_tokens=body.max_new_tokens,
        temperature=body.temperature,
        top_p=body.top_p,
        repeat_penalty=1.1,
        stop=["</s>"],
    )
    text = (out["choices"][0]["text"] or "").strip()
    if "[أجب بإيجاز ووضوح]:" in text:
        text = text.split("[أجب بإيجاز ووضوح]:", 1)[-1].strip()
    return JSONResponse({"ok": True, "answer": text})
