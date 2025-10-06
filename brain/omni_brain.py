<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>مساعدك بسام الذكي / ALSHOTAIMI</title>

  <!-- PWA (اختياري لو أضفناها لاحقًا) -->
  <link rel="manifest" href="/static/manifest.webmanifest">
  <meta name="theme-color" content="#0b0f19" />
  <link rel="apple-touch-icon" href="/static/icons/icon-192.png">
  <meta name="apple-mobile-web-app-capable" content="yes">

  <link rel="stylesheet" href="/static/style.css" />
  <style>
    body{font-family:system-ui,Tahoma; background:#0b0f19; color:#eaeef8; margin:0; padding:16px;}
    .container{max-width:980px; margin:0 auto;}
    .card{background:#101625; border:1px solid #182033; border-radius:16px; padding:16px; margin:12px 0;}
    .row{display:flex; gap:8px; flex-wrap:wrap;}
    input,button{border-radius:12px; border:1px solid #223; background:#0e1422; color:#eaeef8;}
    input{padding:10px 12px; flex:1; min-width:200px;}
    button{background:#7b6cff; border:0; padding:10px 16px; cursor:pointer;}
    .muted{color:#9bb1d0; font-size:13px}
    .answer{white-space:pre-wrap; line-height:1.8; margin-top:10px}
    .sources a{color:#7fb2ff; text-decoration:underline; word-break:break-all;}
    .badge{display:inline-block; background:#0d2037; border:1px solid #243555; padding:6px 10px; border-radius:10px; font-size:13px}
    h1{margin:0 0 6px}
  </style>
</head>
<body>
  <div class="container">
    <header class="card">
      <h1>مساعدك <b>بسام</b> الذكي / <span class="badge">ALSHOTAIMI</span></h1>
      <p class="muted">مرحبًا! أنا بسام لمساعدتك 👋 — اكتب سؤالك بالعربية وسأبحث وألخّص من مصادر موثوقة. الروابط تظهر بالأزرق وتفتح مباشرة.</p>
    </header>

    <!-- نموذج السؤال -->
    <section class="card">
      <form id="ask" class="row" autocomplete="off">
        <input id="user_name" placeholder="اسمك (اختياري)">
        <input id="q" placeholder="اكتب سؤالك هنا…" autofocus>
        <button type="submit">إرسال</button>
      </form>

      <div id="answer" class="answer"></div>
      <div id="sources" class="sources"></div>
    </section>

    <!-- ملاحظة للوحة المشرف -->
    <p class="muted" style="text-align:center">لوحة الإشراف: <code>/admin</code> — الإعدادات: <code>/admin/settings</code></p>
  </div>

  <script>
    // حفظ الاسم محليًا
    const el = (id)=>document.getElementById(id);
    try{
      const saved = localStorage.getItem("BASSAM_NAME") || "";
      if(saved) el("user_name").value = saved;
    }catch(e){}

    document.getElementById("ask").addEventListener("submit", async (e)=>{
      e.preventDefault();
      const q = el("q").value.trim();
      const user_name = el("user_name").value.trim();
      try{ localStorage.setItem("BASSAM_NAME", user_name); }catch(e){}

      if(!q){
        el("answer").textContent = "اكتب سؤالك أولًا.";
        el("sources").innerHTML = "";
        return;
      }

      el("answer").textContent = "… جاري التحليل والبحث وصياغة إجابة بشرية بالعربية";
      el("sources").innerHTML = "";

      try{
        const r = await fetch("/search", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({ q, user_name })
        });
        const j = await r.json();

        // نص الإجابة
        el("answer").textContent = j.answer || "لم أجد إجابة مناسبة الآن.";

        // المصادر (روابط زرقاء تفتح مباشرة)
        const src = j.sources || [];
        if(src.length){
          const ul = document.createElement("ul");
          src.forEach((s)=>{
            // قد تأتي ككائن {title, link} أو كسلسلة رابط فقط
            const url = s.link || s.url || s;
            const title = s.title || url;
            const li = document.createElement("li");
            const a = document.createElement("a");
            a.href = url; a.target="_blank"; a.rel="noopener";
            a.textContent = title;
            li.appendChild(a);
            ul.appendChild(li);
          });
          el("sources").innerHTML = "";
          el("sources").appendChild(ul);
        }else{
          el("sources").textContent = "—";
        }
      }catch(err){
        el("answer").textContent = "حدث خطأ أثناء البحث: " + err.message;
        el("sources").innerHTML = "";
      }
    });
  </script>
</body>
</html>
