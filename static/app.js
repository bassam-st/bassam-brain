// static/app.js — Bassam v4 (Ask via /api/ask + OCR + PWA + "عرض المزيد")
function $(s, r=document){ return r.querySelector(s); }
function el(t, c){ const x = document.createElement(t); if(c) x.className=c; return x; }

// PWA install button (يظهر تلقائيًا)
let deferredPrompt;
window.addEventListener("beforeinstallprompt", (e)=>{
  e.preventDefault(); deferredPrompt = e;
  const btn = document.createElement("button");
  btn.textContent = "📱 تثبيت تطبيق بسام الذكي";
  btn.className = "install-btn";
  document.body.appendChild(btn);
  btn.addEventListener("click", async ()=>{
    btn.style.display = "none";
    deferredPrompt.prompt(); await deferredPrompt.userChoice; deferredPrompt = null;
  });
});

// Service Worker (سلامة)
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(()=>{});
}

function setExpandables(box, btn){
  if(!box || !btn) return;
  btn.addEventListener('click', ()=>{
    const expanded = box.classList.toggle('expanded');
    box.classList.toggle('collapsed', !expanded);
    btn.textContent = expanded ? 'إخفاء' : 'عرض المزيد';
  });
}

function renderBullets(bullets){
  const box = $('#summaryBox'); if(!box) return;
  box.innerHTML = '';
  const ul = el('ul','sumText');
  (bullets||[]).forEach(b=>{ const li = el('li'); li.textContent=b; ul.appendChild(li); });
  box.appendChild(ul); box.appendChild(el('div','summary-fade'));
  box.classList.add('collapsed'); box.classList.remove('expanded');
  setExpandables(box, $('#toggleSummary'));
}

function renderResults(results){
  const box = $('#resultsBox'); if(!box) return;
  box.innerHTML = '';
  const ul = el('ul','results');
  (results||[]).forEach(r=>{
    const li = el('li');
    const a = el('a'); a.href=r.link; a.target='_blank'; a.textContent=r.title || r.link;
    const sm = el('small'); sm.textContent = r.snippet || '';
    const em = el('em'); em.textContent = r.source || '';
    li.appendChild(a); li.appendChild(sm); li.appendChild(em);
    ul.appendChild(li);
  });
  box.appendChild(ul); box.appendChild(el('div','summary-fade'));
  box.classList.add('collapsed'); box.classList.remove('expanded');
  setExpandables(box, $('#toggleResults'));
}

function ensureLLMCard(){
  let card = document.getElementById('llmCard');
  if(card) return card;
  card = el('section','card'); card.id='llmCard';
  const h = el('h3'); h.textContent = 'إجابة الذكاء (GPT-4o mini)';
  const ans = el('div'); ans.id='llmAnswer'; ans.style.whiteSpace='pre-wrap';
  const src = el('div'); src.id='llmSources';
  card.appendChild(h); card.appendChild(ans); card.appendChild(src);
  document.body.insertBefore(card, $('.footer'));
  return card;
}

async function askLLM(q){
  ensureLLMCard();
  $('#llmAnswer').textContent = '… جارِ التوليد';
  $('#llmSources').innerHTML = '';
  try{
    const r = await fetch('/api/ask', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ q })
    });
    const data = await r.json();
    if(!data.ok) throw new Error(data.error || 'failed');
    renderBullets(data.bullets);
    renderResults(data.results);
    $('#llmAnswer').textContent = data.answer || '—';
    const box = $('#llmSources');
    if(data.sources?.length){
      const h = el('h4'); h.textContent = 'المراجع:';
      const list = el('ul'); list.style.paddingInlineStart='20px';
      data.sources.forEach(u=>{
        const li = el('li'); const a = el('a'); a.href=u; a.target='_blank'; a.textContent=u;
        li.appendChild(a); list.appendChild(li);
      });
      box.appendChild(h); box.appendChild(list);
    }
  }catch(e){
    $('#llmAnswer').textContent = '⚠️ حدث خطأ أثناء توليد الإجابة.';
    console.error(e);
  }
}

// ربط نموذج البحث ليستخدم /api/ask (بدون ريفرش)
(function initAsk(){
  const form = $('#searchForm'); if(!form) return;
  form.addEventListener('submit', (e)=>{
    e.preventDefault();
    const q = ($('#q')?.value || '').trim();
    if(!q) return;
    askLLM(q);
  });
})();

// OCR: إدراج نص من صورة إلى مربع البحث
(function initOCR(){
  const btn = $('#imgBtn'), pick = $('#imgPick'), input = $('#q');
  if(!btn || !pick || !input) return;
  btn.onclick = ()=> pick.click();
  pick.onchange = async ()=>{
    if(!pick.files[0]) return;
    try{
      $('#llmAnswer') && ($('#llmAnswer').textContent = '… قراءة النص من الصورة');
      const { data:{ text } } = await Tesseract.recognize(pick.files[0], 'ara+eng');
      input.value = (input.value + ' ' + text).trim();
    }catch(err){ console.error(err); }
  };
})();
