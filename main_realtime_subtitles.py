<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>الترجمة الحيّة للفيديو</title>
  <link rel="stylesheet" href="/static/style.css"/>
  <!-- hls.js لتشغيل m3u8 على المتصفحات التي لا تدعمه -->
  <script src="https://cdn.jsdelivr.net/npm/hls.js@1"></script>
  <style>
    body{background:#0b0f19;color:#e5e7eb;font-family:system-ui,-apple-system,Segoe UI,Roboto,"Noto Naskh Arabic UI","Noto Kufi Arabic",Tahoma,Arial,sans-serif}
    .wrap{max-width:920px;margin:28px auto;padding:0 14px}
    h1{display:flex;gap:10px;align-items:center;margin:10px 0 18px}
    .card{background:#121826;border-radius:16px;padding:16px;box-shadow:0 10px 30px rgba(0,0,0,.25)}
    .row{display:flex;gap:10px;flex-wrap:wrap}
    input[type="url"]{flex:1;min-width:260px;padding:12px 14px;border:none;border-radius:12px;background:#0f1421;color:#fff}
    button{padding:12px 16px;border:none;border-radius:12px;background:#7c3aed;color:#fff;font-weight:700;cursor:pointer}
    button:hover{background:#6d28d9}
    #player{margin-top:14px}
    video{width:100%;max-height:60vh;background:#000;border-radius:12px}
    .status{margin-top:10px;color:#98a2b3}
    .subs{margin-top:12px;background:#0f1220;border:1px solid #2a2f45;border-radius:12px;padding:10px;min-height:48px;line-height:1.8}
    .line{display:block;font-size:18px}
    .note{margin-top:8px;color:#a1a1aa;font-size:13px}
    .err{color:#fda4af}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>🎧 الترجمة الحيّة للفيديو</h1>

    <div class="card">
      <p>ألصق رابط فيديو (YouTube / Twitch / MP4 / M3U8) ثم اضغط “ابدأ”.</p>
      <form id="f" class="row">
        <button type="submit">ابدأ</button>
        <input id="url" type="url" placeholder="https://…" required/>
      </form>
      <div id="status" class="status"></div>

      <div id="player"></div>
      <div id="subs" class="subs"></div>
      <div class="note">
        إن لم يظهر الفيديو داخل الصفحة، ستجد زر “فتح في تبويب جديد”. ستظل الترجمة الحيّة تعمل هنا.
      </div>
    </div>
  </div>

<script>
const $ = s => document.querySelector(s);
const log = (m, cls='') => { const el = $('#status'); el.className = 'status ' + cls; el.textContent = m||''; };
const esc = s => (s||'').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

async function start(e){
  e.preventDefault();
  const videoUrl = $('#url').value.trim();
  if(!videoUrl) return;

  log('جارٍ بدء الجلسة…');

  // 1) ابدأ جلسة الترجمة الحيّة في الباك-إند
  let sid = null;
  try{
    const fd = new FormData(); fd.append('video_url', videoUrl);
    const sres = await fetch('/rt/start', { method:'POST', body: fd });
    const sj = await sres.json();
    if(sj && sj.ok && sj.sid){
      sid = sj.sid;
      log('متصل… يتم الاستماع للصوت وترجمته');
    }else{
      log('تعذر بدء جلسة الترجمة: ' + (sj && sj.error ? sj.error : ''), 'err');
    }
  }catch(err){
    log('تعذر بدء جلسة الترجمة: ' + (err?.message||String(err)), 'err');
  }

  // 2) واجهة المشغّل + رابط خارجي دائمًا
  $('#player').innerHTML =
    '<div style="padding:10px;background:#0f1220;border:1px solid #2a2f45;border-radius:10px;margin-bottom:10px">' +
    'رابط الفيديو الأصلي: <a target="_blank" href="'+videoUrl+'">فتح في تبويب جديد</a>' +
    '</div>' +
    '<div id="inner"></div>';

  // 3) حاول استخراج رابط تشغيل مباشر
  let playable = null, resolveErr = null;
  try{
    const r = await fetch('/resolve?video_url=' + encodeURIComponent(videoUrl));
    const j = await r.json();
    if(j.ok && j.url){ playable = j.url; }
    else resolveErr = j.error || 'لم يتم العثور على رابط تشغيل مباشر';
  }catch(err){ resolveErr = err?.message || String(err); }

  // 4) شغّل داخل الصفحة (MP4/HLS). استخدم hls.js إذا كان m3u8.
  const box = $('#inner');
  if(playable){
    if(playable.includes('.m3u8') && window.Hls && Hls.isSupported()){
      box.innerHTML = '<video id="vid" controls autoplay playsinline></video>';
      const videoEl = $('#vid');
      const hls = new Hls({maxBufferLength:30});
      hls.loadSource(playable);
      hls.attachMedia(videoEl);
      hls.on(Hls.Events.ERROR, (e,data)=>{ log('مشكلة تشغيل HLS: '+(data?.details||''), 'err'); });
    }else{
      box.innerHTML = '<video id="vid" src="'+playable+'" controls autoplay playsinline></video>';
    }
  }else{
    box.innerHTML =
      '<div style="padding:10px;border-radius:10px;border:1px dashed #475569;color:#98a2b3">' +
      'تعذّر تشغيل الفيديو داخل الصفحة. السبب: ' + esc(resolveErr||'غير معروف') +
      '<br/>يمكنك المشاهدة في التبويب الخارجي، وستبقى الترجمة الحيّة هنا.' +
      '</div>';
  }

  // 5) استقبل سطور الترجمة عبر WebSocket
  if(sid){
    try{
      const wsProto = (location.protocol === 'https:') ? 'wss' : 'ws';
      const ws = new WebSocket(wsProto + '://' + location.host + '/ws/' + sid);
      ws.onmessage = ev => {
        try{
          const d = JSON.parse(ev.data);
          if(d.type === 'line'){
            $('#subs').innerHTML = '<span class="line">' + esc(d.ar || d.src || '') + '</span>';
          }else if(d.type === 'error'){
            log('خطأ: ' + d.error, 'err');
          }else if(d.type === 'done'){
            log('انتهى البث.');
          }
        }catch(e){}
      };
      ws.onclose = ()=> log('انتهى الاتصال');
    }catch(err){
      log('WebSocket فشل: ' + (err?.message||String(err)), 'err');
    }
  }
}

document.getElementById('f').addEventListener('submit', start);
</script>
</body>
</html>
