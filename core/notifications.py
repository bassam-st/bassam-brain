import os, json, datetime as dt, httpx
from pathlib import Path

APP_ID  = os.getenv("ONESIGNAL_APP_ID", "")
RESTKEY = os.getenv("ONESIGNAL_REST_API_KEY", "")
PUBLIC  = os.getenv("PUBLIC_BASE_URL", "")

_SENT_FILE = Path("/tmp/sent_pushes.json")

def _load_sent():
    if _SENT_FILE.exists():
        try:
            return json.loads(_SENT_FILE.read_text("utf-8"))
        except Exception:
            return {}
    return {}

def _save_sent(data):
    try:
        _SENT_FILE.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    except Exception:
        pass

def _send(payload):
    headers = {"Authorization": f"Basic {RESTKEY}",
               "Content-Type": "application/json; charset=utf-8"}
    with httpx.Client(timeout=20) as client:
        r = client.post("https://api.onesignal.com/notifications",
                        headers=headers, json=payload)
        return (r.status_code in (200, 201)), r.text

def send_push(title, body, url_path="/"):
    url = url_path if url_path.startswith("http") else (PUBLIC.rstrip("/") + url_path)
    payload = {
        "app_id": APP_ID,
        "included_segments": ["Subscribed Users"],
        "headings": {"ar": title},
        "contents": {"ar": body},
        "url": url
    }
    return _send(payload)

def send_test_push(title, body, url="/"):
    return send_push(title, body, url)

def make_daily_digest(matches, today_str, tz_name):
    if not matches:
        return None
    lines = []
    for m in matches:
        hhmm = m["kickoff"].strftime("%H:%M")
        lines.append(f"{hhmm}  {m['home']} × {m['away']}  ({m['league']})")
    return {"title": f"مباريات اليوم ({today_str} – {tz_name})",
            "body": "\n".join(lines[:10])}

def maybe_send_once(kind_key, unique_key, title, body, url="/"):
    sent = _load_sent()
    today = dt.date.today().isoformat()
    sent.setdefault(today, {})
    key = f"{kind_key}:{unique_key}"
    if key in sent[today]:
        return False, "duplicate-suppressed"
    ok, resp = send_push(title, body, url)
    if ok:
        sent[today][key] = True
        _save_sent(sent)
    return ok, resp
