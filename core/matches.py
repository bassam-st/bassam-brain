import os, httpx, datetime as dt
from dateutil import tz
from urllib.parse import quote

LEAGUE_NAME_BY_ID = {
    "4328": "English Premier League",
    "4335": "Spanish La Liga",
    "4332": "Italian Serie A",
    "4331": "German Bundesliga",
    "4334": "French Ligue 1",
    "4480": "Saudi Pro League",
    "4790": "UEFA Champions League",
}

TZ_NAME = os.getenv("TIMEZONE", "Asia/Qatar")
LOCAL_TZ = tz.gettz(TZ_NAME)

def _parse_ts(date_str: str, time_str: str):
    t = (time_str or "00:00:00").split("+")[0]
    utc_dt = dt.datetime.fromisoformat(f"{date_str}T{t}")
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=tz.UTC)
    return utc_dt.astimezone(LOCAL_TZ)

def fetch_today_matches():
    today = dt.date.today().strftime("%Y-%m-%d")
    ids = [x.strip() for x in os.getenv("LEAGUE_IDS", "").split(",") if x.strip()]
    matches = []
    with httpx.Client(timeout=20) as client:
        for lid in ids:
            name = LEAGUE_NAME_BY_ID.get(lid)
            if not name:
                continue
            url = f"https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d={today}&l={quote(name)}"
            try:
                data = client.get(url).json()
            except Exception:
                continue
            for e in (data or {}).get("events", []) or []:
                home, away = e.get("strHomeTeam"), e.get("strAwayTeam")
                date_str   = e.get("dateEvent")
                time_str   = e.get("strTime") or "00:00:00"
                kickoff    = _parse_ts(date_str, time_str)
                league     = e.get("strLeague") or name
                deeplink_q = quote(f"{home} vs {away}")
                click_url  = f"/deeplink?match={deeplink_q}"
                matches.append({
                    "id": e.get("idEvent"),
                    "league": league,
                    "home": home, "away": away,
                    "kickoff": kickoff,
                    "venue": e.get("strVenue") or "",
                    "click_url": click_url
                })
    matches.sort(key=lambda x: x["kickoff"])
    return matches, today, TZ_NAME
