"""
Case 2 - CLOUD version of the District movie alert bot
------------------------------------------------------
Runs on GitHub Actions every ~10 minutes, even when your PC is off.
Watches District for Avengers: Doomsday bookings in Kurnool (17 Dec) and
sends a phone notification through the ntfy app when they open.

The ntfy channel name comes from the GitHub secret NTFY_TOPIC, so it is not
visible in the code. State is kept in state.json in the repository.

MODE (set when you run it by hand from the Actions tab):
    normal   - regular check (what the schedule runs)
    test     - send a test notification to your phone
    dry-run  - show what it sees on District, no alerts
    reset    - forget the baseline/alerts (next run starts fresh)
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

# ============================== SETTINGS ===================================

MOVIE     = "Avengers: Doomsday"
SHOW_DATE = "2026-12-17"
CITY_URL  = ("https://www.district.in/movies/"
             "avengers-doomsday-movie-tickets-in-kurnool-MV176735"
             "?fromdate=" + SHOW_DATE)
THEATRE   = "SVC"
WANT      = "English 3D, first show, 2 centre seats"

# ===========================================================================

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
MODE       = os.environ.get("MODE", "normal").strip().lower() or "normal"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "state.json")
IST        = timezone(timedelta(hours=5, minutes=30))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def now_ist():
    return datetime.now(IST)


def log(msg):
    print(f"{now_ist():%Y-%m-%d %H:%M:%S} IST  {msg}", flush=True)


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


def signals(html):
    t = html.lower()
    return {
        "svc":          len(re.findall(r"\bsvc\b", t)),
        "filling_fast": t.count("filling fast"),
        "almost_full":  t.count("almost full"),
        "available":    len(re.findall(r"\bavailable\b", t)),
        "3d":           len(re.findall(r"\b3d\b", t)),
        "seat_layout":  t.count("seat-layout") + t.count("seatlayout"),
    }


def bookings_open(now, base):
    keys = ("filling_fast", "almost_full", "available", "seat_layout")
    return any(now[k] > base.get(k, 0) for k in keys)


def notify(title, body, urgent=True):
    """Push notification to the ntfy app on your phone."""
    if not NTFY_TOPIC:
        log("NTFY_TOPIC secret is missing - add it in repo Settings > Secrets")
        return False
    req = urllib.request.Request(
        "https://ntfy.sh/" + NTFY_TOPIC,
        data=body.encode("utf-8"),
        headers={"Title": title,                      # ASCII only
                 "Priority": "urgent" if urgent else "default",
                 "Tags": "movie_camera" if urgent else "warning",
                 "Click": CITY_URL})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        log(f"Phone notification sent: {title}")
        return True
    except Exception as e:
        log(f"Phone notification FAILED: {e}")
        return False


def alert(headline):
    body = (f"{headline}\n\n{MOVIE} - {SHOW_DATE}\nWant: {WANT}\n\n"
            f"Tap to open District.\nThen tell Claude: \"book the Avengers tickets\"")
    notify("Movie booking alert", body)


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(s):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1, sort_keys=True)
        f.write("\n")


def main():
    log(f"Mode: {MODE}")

    if MODE == "reset":
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        log("State cleared - next run takes a fresh baseline.")
        return

    if MODE == "test":
        ok = notify("Movie bot TEST",
                    "Cloud movie alert bot is working. You'll get an alert "
                    "like this when Kurnool bookings open.", urgent=False)
        sys.exit(0 if ok else 1)

    if now_ist().date().isoformat() > SHOW_DATE:
        log("Show date has passed - you can disable the workflow.")
        return

    state = load_state()

    try:
        html = fetch(CITY_URL)
    except Exception as e:
        log(f"Couldn't reach District: {e}")
        if MODE == "normal" and not state.get("error_sent"):
            notify("Movie bot: District unreachable",
                   f"The cloud bot couldn't load District ({e}). It will keep "
                   "trying; your PC bot is unaffected.", urgent=False)
            state["error_sent"] = True
            save_state(state)
        if MODE == "dry-run":
            sys.exit(1)
        return

    now = signals(html)
    if state.get("error_sent"):
        state["error_sent"] = False

    if "baseline" not in state:
        state.update({"baseline": now, "open_sent": False, "svc_sent": False})
        save_state(state)
        log(f"Baseline saved: {now}")
        if MODE != "dry-run":
            return

    base = state["baseline"]
    is_open = bookings_open(now, base)
    svc_listed = now["svc"] > base.get("svc", 0)

    if MODE == "dry-run":
        log(f"Baseline : {base}")
        log(f"Now      : {now}")
        log(f"Kurnool bookings open : {is_open}")
        log(f"SVC listed            : {svc_listed}")
        save_state(state)
        return

    if svc_listed and not state.get("svc_sent"):
        alert(f"{THEATRE} Kurnool is now selling {MOVIE} tickets!")
        state["svc_sent"] = state["open_sent"] = True
    elif is_open and not state.get("open_sent"):
        alert(f"{MOVIE} bookings are OPEN in Kurnool (SVC not seen yet)")
        state["open_sent"] = True
    else:
        log(f"No change. open={is_open} svc={svc_listed}")
    save_state(state)


if __name__ == "__main__":
    main()
