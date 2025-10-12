# bassam_agent.py — ملف واحد: وكيل بشري + ذاكرة + واجهة ويب + PWA
import os, re, json, sqlite3, hashlib, io, csv, uuid, traceback
from datetime import datetime
from typing import List, Dict, Optional

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import httpx
from duckduckgo_search import DDGS

# ---------- إعداد مفاتيح / بيئة ----------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY","").strip()
LLM_MODEL = os.getenv("LLM_MODEL","gpt-4o-mini").strip()  # عدّل لِما يتوفر عندك
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "093589")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "bassam-secret")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/") if os.getenv("PUBLIC_BASE_URL") else ""
SERPER_API_KEY = os.getenv("SERPER_API_KEY","").strip()  # اختياري للبحث في Google عبر Serper

# ---------- مسارات المشروع ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data"); os.makedirs(DATA_DIR, exist_ok=True)
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads"); os.makedirs(UPLOADS_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "bassam.db")
MEM_DB = os.path.join(DATA_DIR, "memory.db")

# ---------- تطبيق FastAPI + ملفات ثابتة بسيطة ----------
app = FastAPI(title="Bassam Agent (Human-like)")
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")  # لو عندك مجلد static خارجي

# ---------- OpenAI عميل اختياري ----------
try:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except Exception:
    client = None

# ===================== قواعد بيانات: سجلات + ذاكرة شخصية =====================
def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            type TEXT NOT NULL,      -- ask | search | image
            query TEXT,
            file_name TEXT,
            engine_used TEXT,
            ip TEXT, ua TEXT
        );
        """)
init_db()

def log_event(t:str, ip:str, ua:str, query:Optional[str]=None, engine:Optional[str]=None, file_name:Optional[str]=None):
    with db() as con:
        con.execute("INSERT INTO logs(ts,type,query,file_name,engine_used,ip,ua) VALUES(?,?,?,?,?,?,?)",
                    (datetime.utcnow().isoformat(timespec="seconds")+"Z", t, query, file_name, engine, ip, ua))

def mdb() -> sqlite3.Connection:
    con = sqlite3.connect(MEM_DB)
    con.row_factory = sqlite3.Row
    return con

def init_memory():
    with mdb() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS chats(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            role TEXT NOT NULL,          -- user | assistant
            text TEXT NOT NULL
        );""")
        con.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS chats_fts USING fts5(text, content='chats', content_rowid='id');""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS memories(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            score REAL DEFAULT 1.0
        );""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS style_profile(
            id INTEGER PRIMARY KEY CHECK (id=1),
            persona TEXT, tone TEXT, prompts TEXT
        );""")
init_memory()

def remember_chat(role:str, text:str):
    t = (text or "").strip()
    if not t: return
    with mdb() as con:
        cur = con.execute("INSERT INTO chats(ts,role,text) VALUES(?,?,?)",
                          (datetime.utcnow().isoformat(timespec="seconds")+"Z", role, t))
        rid = cur.lastrowid
        con.execute("INSERT INTO chats_fts(rowid,text) VALUES(?,?)",(rid,t))

def recent_history(n:int=12) -> List[Dict]:
    with mdb() as con:
        rows = con.execute("SELECT * FROM chats ORDER BY id DESC LIMIT ?",(n,)).fetchall()
    return [dict(r) for r in rows][::-1]

def search_memories_like(q:str, limit:int=6)->List[str]:
    q = (q or "").strip()
    if not q: return []
    with mdb() as con:
        rows = con.execute("SELECT text FROM chats_fts WHERE chats_fts MATCH ? LIMIT ?", (q,limit)).fetchall()
    return [r["text"] for r in rows]

# استخراج ذكريات (تفضيلات/حقائق) مبسّط
PREF_PATTERNS = [
    (r"\b(احب|أحب)\b\s+(.+)", "like"),
    (r"\bافضل\b\s+(.+)", "prefer"),
    (r"\bلا\s*احب\b\s+(.+)", "dislike"),
    (r"\b(اسكن|أعيش|انا من)\b\s+(.+)", "location"),
    (r"\b(وظيفتي|عملي|مجالي)\b\s+(.+)", "job"),
    (r"\b(اسمي)\b\s+(.+)", "name"),
]

def _clean_phrase(t:str)->str:
    t = re.sub(r"[\"'،,.!?؟]+$","", t.strip()); return t[:140]

def mine_memories_from_text(text:str)->List[Dict]:
    out=[]
    for pat,key in PREF_PATTERNS:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            val = _clean_phrase(m.group(len(m.groups())))
            if val: out.append({"key":key,"value":val,"score":1.0})
    return out

def mine_new_memories(limit_scan:int=60)->int:
    with mdb() as con:
        rows = con.execute("SELECT * FROM chats ORDER BY id DESC LIMIT ?",(limit_scan,)).fetchall()
    added=0; seen=set()
    for r in rows:
        if r["role"]!="user": continue
        for m in mine_memories_from_text(r["text"]):
            sig=f"{m['key']}::{m['value']}"
            if sig in seen: continue
            seen.add(sig)
            with mdb() as con:
                ex = con.execute("SELECT 1 FROM memories WHERE key=? AND value=?",(m["key"],m["value"])).fetchone()
                if not ex:
                    con.execute("INSERT INTO memories(ts,key,value,score) VALUES(?,?,?,?)",
                                (datetime.utcnow().isoformat(timespec="seconds")+"Z", m["key"], m["value"], m["score"]))
                    added+=1
    return added

def derive_style_profile():
    rows = recent_history(30)
    exclam = sum(t["text"].count("!") for t in rows if t["role"]=="user")
    emojis = sum(sum(t["text"].count(e) for e in ["😂","😍","😊","😅"]) for t in rows if t["role"]=="user")
    tone = "مرح وودّي" if exclam+emojis>8 else ("حماسي وودّي" if exclam>2 else "هادئ وودّي")
    persona = "مساعد عربي يشبه البشر، يرد بإيجاز ووضوح وبنبرة " + tone
    prompts = {"opener":"تمام! هذا ملخص سريع ثم الإجابة:","closer":"لو تحب أحفظ هذه المعلومة للمرة الجاية قل: احفظ."}
    with mdb() as con:
        con.execute("INSERT OR REPLACE INTO style_profile(id,persona,tone,prompts) VALUES(1,?,?,?)",
                    (persona,tone,json.dumps(prompts,ensure_ascii=False)))
    return {"persona":persona,"tone":tone,"prompts":prompts}

def get_style_profile()->Dict:
    with mdb() as con:
        r = con.execute("SELECT persona,tone,prompts FROM style_profile WHERE id=1").fetchone()
    if not r: return derive_style_profile()
    return {"persona":r["persona"],"tone":r["tone"],"prompts":json.loads(r["prompts"] or "{}")}

def simple_emotion(t:str)->str:
    t=(t or "").strip()
    if any(w in t for w in ["😍","❤","حب","احب","ممتاز","رائع","جميل","تمام"]): return "😊"
    if any(w in t for w in ["😡","غاضب","سيء","مزعل"]): return "😟"
    if any(w in t for w in ["😢","حزين","زعلان"]): return "😢"
    if any(w in t for w in ["😂","هههه","😅"]): return "😄"
    return "🙂"

# ===================== بحث ويب (DDG / Serper) =====================
async def search_google_serper(q:str, num:int=6)->List[Dict]:
    if not SERPER_API_KEY: raise RuntimeError("SERPER_API_KEY غير مضبوط")
    url="https://google.serper.dev/search"
    headers={"X-API-KEY":SERPER_API_KEY,"Content-Type":"application/json"}
    payload={"q":q,"num":num,"hl":"ar"}
    async with httpx.AsyncClient(timeout=25) as cl:
        r=await cl.post(url,headers=headers,json=payload); r.raise_for_status()
        data=r.json()
    out=[]
    for it in (data.get("organic",[]) or [])[:num]:
        out.append({"title":it.get("title"),"link":it.get("link"),"snippet":it.get("snippet"),"source":"Google"})
    return out

def search_duckduckgo(q:str,num:int=6)->List[Dict]:
    out=[]
    with DDGS() as ddgs:
        for r in ddgs.text(q, region="xa-ar", safesearch="moderate", max_results=num):
            out.append({"title":r.get("title"),"link":r.get("href") or r.get("url"),
                        "snippet":r.get("body"),"source":"DuckDuckGo"})
            if len(out)>=num: break
    return out

def _clean(txt:str)->str:
    txt=(txt or "").strip()
    return re.sub(r"[^\w\s\u0600-\u06FF]"," ", txt)

def make_bullets(snips:List[str], max_items:int=8)->List[str]:
    text=" ".join(_clean(s) for s in snips if s).strip()
    parts=re.split(r"[.!؟\n]", text); cleaned=[]; seen=set()
    for p in parts:
        p=re.sub(r"\s+"," ",p).strip(" -•،,")
        if len(p.split())>=4:
            key=p[:80]
            if key not in seen:
                seen.add(key); cleaned.append(p)
        if len(cleaned)>=max_items: break
    return cleaned

async def smart_search(q:str,num:int=6)->Dict:
    try:
        if SERPER_API_KEY:
            try:
                res=await search_google_serper(q,num); used="Google"
            except Exception:
                res=search_duckduckgo(q,num); used="DuckDuckGo"
        else:
            res=search_duckduckgo(q,num); used="DuckDuckGo"
        return {"ok":True,"used":used,"results":res,"bullets":make_bullets([r.get("snippet") for r in res],8)}
    except Exception as e:
        return {"ok":False,"used":None,"results":[],"error":str(e)}

# ===================== وكيل “بشري” بسيط =====================
HUMAN_SYSTEM_PROMPT = (
    "أنت مساعد عربي يشبه البشر: ودود، ذكي، عملي. "
    "أجب بإيجاز واضح، وإذا احتجت معلومة خارجية اطلب البحث وستصيغ الناتج بلغة بشرية. "
    "لا تكشف التفكير الداخلي. إن لم تكن واثقًا قل لا أعلم."
)

async def agent_reply(user_text:str)->str:
    """
    1) حفظ السؤال في الذاكرة
    2) تقرير: هل نبحث أم نجيب مباشرة
    3) صياغة رد “بشري”، مع الاستفادة من الذاكرة + أسلوب المستخدم
    """
    remember_chat("user", user_text)
    style = get_style_profile()
    mem_hits = search_memories_like(user_text, limit=5)

    # قرار بسيط: هل نحتاج بحث؟
    need_search = any(k in user_text for k in ["ما هو","من هو","كيف","متى","أخبار","خبر","سعر","نتيجة","معنى","تعريف"])
    tool_data = None
    if need_search:
        s = await smart_search(user_text, num=6)
        tool_data = s
        # لعرض المصادر داخل الرد

    # لو معك مفتاح LLM — استعمله للرد بصياغة بشرية
    if client:
        user_msg = (
            f"سؤال المستخدم:\n{user_text}\n\n"
            f"سياق شخصي (قد يفيد):\n- " + "\n- ".join(mem_hits) + "\n\n"
        )
        if tool_data and tool_data.get("ok"):
            sources = "\n".join([f"- {r['title']}: {r['link']}" for r in tool_data["results"][:5]])
            user_msg += f"ملخص بحث مختصر (للاستئناس):\n" + " • ".join(tool_data.get("bullets",[])[:4]) + "\n"
            user_msg += f"مصادر:\n{sources}\n\n"
        try:
            resp = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role":"system","content": HUMAN_SYSTEM_PROMPT + " نبرة: " + (style.get("tone") or "ودّي")},
                    {"role":"user","content": user_msg},
                    {"role":"user","content":"اكتب الرد النهائي فقط، نقاط قصيرة إن لزم، واذكر أهم مصدرين إذا كان هناك بحث."}
                ],
                temperature=0.4,
                max_tokens=600
            )
            answer = (resp.choices[0].message.content or "").strip()
        except Exception as e:
            answer = f"تعذر استخدام النموذج حالياً ({e}). هذا ملخّص سريع: " + " • ".join((tool_data or {}).get("bullets",[])[:4])
    else:
        # وضع احتياطي محلي
        emo = simple_emotion(user_text)
        if tool_data and tool_data.get("ok"):
            bullets = tool_data.get("bullets",[])
            srcs = tool_data.get("results",[])
            top = " • ".join(bullets[:4]) if bullets else "بحثت ووجدت لك نقاطًا مفيدة."
            links = "\n".join([f"- {r['title']}: {r['link']}" for r in srcs[:3]])
            answer = f"{emo} ملخص سريع: {top}\nمصادر:\n{links}" if links else f"{emo} {top}"
        else:
            answer = f"{emo} تمام! أحكي لي أكثر عن سؤالك أو أعطني مثالًا أدق علشان أفيدك سريعًا."

    remember_chat("assistant", answer)
    # تعلّم يومي بسيط
    try:
        added = mine_new_memories(limit_scan=40)
        if len(recent_history(1)) % 10 == 0:
            derive_style_profile()
    except Exception:
        pass

    return answer

# ===================== واجهات API + صفحة المحادثة =====================
@app.get("/", response_class=HTMLResponse)
def home():
    # صفحة محادثة بسيطة + زر تثبيت (PWA)
    return HTML_CHAT

@app.post("/api/ask")
async def api_ask(request: Request):
    data = await request.json()
    q = (data.get("q") or "").strip()
    if not q: return JSONResponse({"ok":False,"error":"no_query"}, status_code=400)
    ans = await agent_reply(q)
    ip = request.client.host if request.client else "?"
    ua = request.headers.get("user-agent","?")
    log_event("ask", ip, ua, query=q, engine=f"Agent:{LLM_MODEL if client else 'heuristic'}")
    return {"ok":True,"answer":ans,"bullets":make_bullets([ans],6)}

@app.post("/api/learn/mine")
def api_learn_mine():
    n = mine_new_memories(limit_scan=100)
    return {"ok":True,"added":n}

@app.post("/api/learn/rebuild-style")
def api_learn_style():
    prof = derive_style_profile()
    return {"ok":True,"profile":prof}

# ---------- PWA: manifest + service worker ----------
@app.get("/static/pwa/manifest.json")
def manifest():
    return JSONResponse({
        "name":"بسام — وكيل بشري",
        "short_name":"Bassam",
        "start_url":"/",
        "display":"standalone",
        "background_color":"#0b0f19",
        "theme_color":"#7c3aed",
        "icons":[
            {"src":"/static/icons/icon-192.png","sizes":"192x192","type":"image/png"},
            {"src":"/static/icons/icon-512.png","sizes":"512x512","type":"image/png"},
        ]
    })

@app.get("/sw.js")
def sw_js():
    return HTMLResponse(SW_JS, media_type="application/javascript")

# ============= HTML + JS (مضمّن) =============
HTML_CHAT = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>بسام — وكيل يشبه البشر</title>
<meta name="theme-color" content="#7c3aed">
<link rel="manifest" href="/static/pwa/manifest.json"/>
<link rel="apple-touch-icon" href="/static/icons/icon-192.png"/>
<style>
:root{--bg:#0b0f19;--card:#121826;--pri:#7c3aed;--muted:#98a2b3}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:#e5e7eb;
font-family:system-ui,-apple-system,Segoe UI,Roboto,"Noto Naskh Arabic UI","Noto Kufi Arabic",Tahoma,Arial,sans-serif}
a{color:#c4b5fd;text-decoration:none} .wrap{max-width:860px;margin:0 auto;padding:16px}
.card{background:#121826;border-radius:16px;padding:14px 12px;box-shadow:0 10px 30px rgba(0,0,0,.25);margin:16px 0}
.row{display:flex;gap:8px;flex-wrap:wrap}
input[type=text]{flex:1;min-width:220px;padding:12px 14px;border:none;border-radius:12px;background:#0f1421;color:#fff}
button{padding:12px 16px;border:none;border-radius:12px;background:var(--pri);color:#fff;font-weight:700;cursor:pointer}
button:hover{opacity:.92}
.msg{padding:10px 12px;border-radius:12px;margin:8px 0;white-space:pre-wrap;line-height:1.7}
.user{background:#0f1421} .bot{background:#0f1220;border:1px solid #2a2f45}
.footer{color:var(--muted);text-align:center;margin:24px 0}
.install{position:fixed;right:12px;bottom:12px;background:#7c3aed;color:#fff;border:none;border-radius:12px;padding:10px 14px;font-weight:700}
</style>
</head>
<body>
<div class="wrap">
  <h2>بسام — يرد كنبرة بشرية ويتعلّم يوميًا</h2>
  <div id="chat" class="card"></div>
  <form class="card row" onsubmit="return sendMsg()">
    <input id="q" type="text" placeholder="اكتب سؤالك..." required />
    <button type="submit">أرسل</button>
  </form>
  <div class="footer">© 2025 • يدعم PWA — ثبّت من زر الأسفل إن ظهر</div>
</div>

<script>
// PWA install button (beforeinstallprompt)
let deferredPrompt=null;
window.addEventListener("beforeinstallprompt",(e)=>{
  e.preventDefault(); deferredPrompt=e;
  const b=document.createElement("button"); b.className="install"; b.textContent="📱 تثبيت بسام";
  b.onclick=async()=>{
    b.style.display="none"; deferredPrompt.prompt();
    await deferredPrompt.userChoice; deferredPrompt=null;
  };
  document.body.appendChild(b);
});
// SW
if ("serviceWorker" in navigator){ navigator.serviceWorker.register("/sw.js"); }

const chat = document.getElementById('chat');
function addMsg(txt, who){
  const d=document.createElement('div');
  d.className='msg '+(who||'bot'); d.textContent=txt; chat.appendChild(d); chat.scrollTop=chat.scrollHeight;
}
addMsg("مرحبًا! أنا بسام — اسألني أي شيء 🙂", "bot");

async function sendMsg(){
  const inp = document.getElementById('q'); const t = inp.value.trim(); if(!t) return false;
  addMsg(t,"user"); inp.value=""; 
  try{
    const r = await fetch('/api/ask',{method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({q:t})});
    const j = await r.json();
    if(j.ok){ addMsg(j.answer || "تمام 🙂","bot"); } else { addMsg("عذرًا، لم أفهم الطلب.","bot"); }
  }catch(e){ addMsg("حدث خطأ أثناء الاتصال بالخادم.","bot"); }
  return false;
}
</script>
</body>
</html>
"""

SW_JS = """
self.addEventListener("install", e=>self.skipWaiting());
self.addEventListener("activate", e=>self.clients.claim());
self.addEventListener("fetch", ()=>{});
"""

# ============ نقطة صحّة ============
@app.get("/healthz")
def health(): return {"ok":True}
