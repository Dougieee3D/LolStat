"""
LoLStat: League of Legends companion for Windows
------------------------------------------------
Runs on your Windows PC next to the League client. When a match pops, it
accepts it for you through the League client's local API (the same one
companion apps use). It also serves a small control page your
phone can open over Wi-Fi: see status, toggle auto-accept, accept/decline.

Auto-accept, phone remote, ARAM Mayhem builds and augment ranks, in-game overlay.
Run:   python lolstat.py            (app window + overlay; needs pywebview)
       python lolstat.py --console  (no window)
"""

import base64
import http.client
import io
import json
import os
import re
import secrets
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# ---------------- Settings ----------------
WEB_PORT = 5005          # port the phone page is served on
POLL_SECONDS = 0.5       # backup check of the client (League also pushes changes to LoLStat as they happen)
ACCEPT_DELAY = 0         # seconds to wait before accepting (0 = instant)
LOCKFILE_PATHS = [       # fallback if the client process can't be read
    r"C:\Riot Games\League of Legends\lockfile",
    r"D:\Riot Games\League of Legends\lockfile",
]
from lolstat_assets import APP_NAME, APP_VERSION, LOGO_40, LOGO_64, RIOT_NOTICE
import ui_pages

_APPDATA = os.environ.get("APPDATA") or os.path.expanduser("~")
DATA_DIR = os.path.join(_APPDATA, "LoLStat")
if not os.path.isdir(DATA_DIR) and os.path.isdir(os.path.join(_APPDATA, "LoLAutoAccept")):
    try:  # keep the phone link and saved data from the old "LoL Auto-Accept" app
        import shutil
        shutil.copytree(os.path.join(_APPDATA, "LoLAutoAccept"), DATA_DIR)
    except Exception:
        pass
os.makedirs(DATA_DIR, exist_ok=True)
KEY_FILE = os.path.join(DATA_DIR, "phone_key.txt")
# ------------------------------------------

SSL_CTX = ssl._create_unverified_context()  # the client uses a self-signed cert
lock = threading.Lock()
current_lcu = None
state = {
    "enabled": True,
    "connected": False,
    "phase": "Unknown",
    "ready_check": False,
    "accepted_count": 0,
    "last_accepted": None,
}


LOG_LINES = []


def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    LOG_LINES.append(line)
    del LOG_LINES[:-200]
    if sys.stdout:
        print(line, flush=True)


def load_key():
    """A secret key so only your phone (with the link) can control this."""
    try:
        with open(KEY_FILE) as f:
            key = f.read().strip()
            if key:
                return key
    except OSError:
        pass
    key = secrets.token_urlsafe(8)
    with open(KEY_FILE, "w") as f:
        f.write(key)
    return key


def find_credentials():
    """Get the client's port + password from its process, or its lockfile."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Process -Filter \"name='LeagueClientUx.exe'\").CommandLine"],
            capture_output=True, text=True, timeout=10,
            creationflags=0x08000000,  # don't flash a window
        ).stdout
        port = re.search(r"--app-port=(\d+)", out)
        token = re.search(r"--remoting-auth-token=([^\s\"]+)", out)
        if port and token:
            return port.group(1), token.group(1)
    except Exception:
        pass
    for path in LOCKFILE_PATHS:
        try:
            with open(path) as f:
                parts = f.read().split(":")
            return parts[2], parts[3]
        except Exception:
            continue
    return None


class LCU:
    """The League client's local API. Each thread keeps one open connection (no new handshake per request)."""
    def __init__(self, port, token):
        self.port = int(port)
        self.base = f"https://127.0.0.1:{port}"
        self.auth = "Basic " + base64.b64encode(f"riot:{token}".encode()).decode()
        self._local = threading.local()

    def _conn(self, fresh=False):
        c = getattr(self._local, "conn", None)
        if fresh or c is None:
            if c is not None:
                try:
                    c.close()
                except Exception:
                    pass
            c = http.client.HTTPSConnection("127.0.0.1", self.port, context=SSL_CTX, timeout=3)
            self._local.conn = c
        return c

    def req(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else (b"" if method in ("POST", "PATCH", "PUT") else None)
        headers = {"Authorization": self.auth, "Accept": "application/json", "Content-Type": "application/json"}
        for attempt in (0, 1):
            try:
                c = self._conn(fresh=attempt == 1)
                c.request(method, path, body=data, headers=headers)
                resp = c.getresponse()
                raw = resp.read()
                break
            except (http.client.HTTPException, ConnectionError, OSError):
                if attempt:
                    raise
        if resp.status >= 400:
            raise urllib.error.HTTPError(self.base + path, resp.status, resp.reason, resp.headers, io.BytesIO(raw))
        return json.loads(raw) if raw else None


# ---------------------------------------------------------------- push events from the League client
_wake = threading.Event()          # wakes the main loop the moment League reports a change
LCU_EVENTS = ["OnJsonApiEvent_lol-gameflow_v1_gameflow-phase", "OnJsonApiEvent_lol-matchmaking_v1_ready-check",
              "OnJsonApiEvent_lol-champ-select_v1_session", "OnJsonApiEvent_lol-end-of-game_v1_eog-stats-block",
              "OnJsonApiEvent_lol-lobby_v2_lobby", "OnJsonApiEvent_lol-matchmaking_v1_search"]
_events = {"connected": False, "count": 0, "last": ""}


class LcuEvents(threading.Thread):
    """A tiny WebSocket client for the League client's event stream (no extra packages needed)."""
    def __init__(self, lcu, on_event):
        super().__init__(daemon=True)
        self.lcu, self.on_event, self.alive = lcu, on_event, True

    def run(self):
        while self.alive and current_lcu is self.lcu:
            try:
                self._session()
            except Exception:
                pass
            _events["connected"] = False
            time.sleep(2)

    def _send(self, sock, text, opcode=1):
        payload = text.encode() if isinstance(text, str) else text
        mask = os.urandom(4)
        n = len(payload)
        head = bytes([0x80 | opcode]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + n.to_bytes(2, "big")
                                          if n < 65536 else bytes([0x80 | 127]) + n.to_bytes(8, "big"))
        sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def _session(self):
        raw = socket.create_connection(("127.0.0.1", self.lcu.port), timeout=5)
        sock = SSL_CTX.wrap_socket(raw, server_hostname="127.0.0.1")
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall((f"GET / HTTP/1.1\r\nHost: 127.0.0.1:{self.lcu.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nAuthorization: {self.lcu.auth}\r\n\r\n").encode())
        f = sock.makefile("rb")
        status = f.readline()
        if b" 101 " not in status:
            raise ConnectionError(status)
        while f.readline() not in (b"\r\n", b"\n", b""):
            pass
        for ev in LCU_EVENTS:
            self._send(sock, json.dumps([5, ev]))
        sock.settimeout(None)
        _events["connected"] = True
        buf = b""
        while self.alive and current_lcu is self.lcu:
            h = f.read(2)
            if len(h) < 2:
                return
            op, n = h[0] & 0x0F, h[1] & 0x7F
            if n == 126:
                n = int.from_bytes(f.read(2), "big")
            elif n == 127:
                n = int.from_bytes(f.read(8), "big")
            mask = f.read(4) if h[1] & 0x80 else None
            data = f.read(n)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if op == 8:
                return
            if op == 9:
                self._send(sock, data, opcode=10)
                continue
            if op in (0, 1, 2):
                buf += data
                if not h[0] & 0x80:
                    continue
                msg, buf = buf, b""
                try:
                    m = json.loads(msg)
                except ValueError:
                    continue
                if isinstance(m, list) and len(m) >= 3 and m[0] == 8 and isinstance(m[2], dict):
                    _events["count"] += 1
                    _events["last"] = m[2].get("uri", "")
                    try:
                        self.on_event(m[2])
                    except Exception:
                        pass


_accept = {"t": 0}


def accept_now(source=""):
    """Accept a ready check once (the push event and the backup check can both see it)."""
    if time.time() - _accept["t"] < 3:
        return False
    _accept["t"] = time.time()
    if ACCEPT_DELAY:
        time.sleep(ACCEPT_DELAY)
    accept()
    with lock:
        state["accepted_count"] += 1
        state["last_accepted"] = datetime.now().strftime("%I:%M:%S %p")
    log("Match found! Accepted." + (f" ({source})" if source else ""))
    return True


def on_lcu_event(ev):
    uri, data = ev.get("uri", ""), ev.get("data")
    if uri == "/lol-matchmaking/v1/ready-check" and isinstance(data, dict):
        if state.get("enabled") and data.get("state") == "InProgress" and data.get("playerResponse") == "None":
            threading.Thread(target=accept_now, daemon=True).start()
    elif uri == "/lol-lobby/v2/lobby":
        _party["t"] = 0
    _wake.set()


def accept():
    lcu = current_lcu
    if lcu:
        lcu.req("POST", "/lol-matchmaking/v1/ready-check/accept")


def decline():
    lcu = current_lcu
    if lcu:
        lcu.req("POST", "/lol-matchmaking/v1/ready-check/decline")


def worker():
    global current_lcu
    waiting_logged = False
    while True:
        if current_lcu is None:
            creds = find_credentials()
            if not creds:
                with lock:
                    state.update(connected=False, phase="Client closed", ready_check=False)
                if not waiting_logged:
                    log("Waiting for the League client to open...")
                    waiting_logged = True
                time.sleep(3)
                continue
            current_lcu = LCU(*creds)
            LcuEvents(current_lcu, on_lcu_event).start()
            waiting_logged = False

        try:
            phase = current_lcu.req("GET", "/lol-gameflow/v1/gameflow-phase")
            rc = None
            if phase == "ReadyCheck":
                rc = current_lcu.req("GET", "/lol-matchmaking/v1/ready-check")
            qinfo = None
            if phase in ("Matchmaking", "Lobby", "ReadyCheck"):
                try:
                    qs = current_lcu.req("GET", "/lol-lobby/v2/lobby/matchmaking/search-state") or {}
                    pen = max([int(e.get("penaltyTimeRemaining") or 0) for e in qs.get("errors") or []] or [0])
                    srch = current_lcu.req("GET", "/lol-matchmaking/v1/search") if phase == "Matchmaking" else {}
                    srch = srch or {}
                    qinfo = {"in_queue": phase == "Matchmaking", "time": round(srch.get("timeInQueue") or 0),
                             "estimate": round(srch.get("estimatedQueueTime") or 0), "penalty": pen,
                             "queue_id": ((srch.get("queueId") or 0))}
                except Exception:
                    qinfo = None
            on_phase_change(state.get("phase"), phase)

            with lock:
                newly = not state["connected"]
                if newly:
                    log("Connected to the League client.")
                    threading.Thread(target=catch_up, daemon=True).start()
            if newly and mayhem:
                try:   # read augment cards in the client's language
                    mayhem.set_locale((current_lcu.req("GET", "/riotclient/region-locale") or {}).get("locale"))
                except Exception:
                    pass
            with lock:
                state.update(connected=True, phase=phase or "None", ready_check=phase == "ReadyCheck", queue=qinfo)
                enabled = state["enabled"]

            if mayhem:   # live champ select for the app: your champion, bench, swaps
                if phase == "ChampSelect":
                    try:
                        sess = current_lcu.req("GET", "/lol-champ-select/v1/session")
                        pick_ids = None
                        try:   # ARAM champion cards: during your pick, only your cards are pickable
                            pick_ids = current_lcu.req("GET", "/lol-champ-select/v1/pickable-champion-ids")
                        except Exception:
                            pass
                        mayhem.on_champ_select(sess, pick_ids)
                    except urllib.error.HTTPError:
                        pass
                elif mayhem.champ_select is not None:
                    mayhem.on_champ_select(None)

            sync_party(phase)
            sync_item_sets(phase)
            sync_spells(phase)
            sync_runes(phase)
            sync_eog(phase)

            if (enabled and rc and rc.get("state") == "InProgress"
                    and rc.get("playerResponse") == "None"):
                accept_now()
        except urllib.error.HTTPError:
            pass  # client is up but that endpoint isn't ready yet
        except Exception:
            if state["connected"]:
                log("Lost connection to the client.")
            current_lcu = None
            with lock:
                state.update(connected=False, phase="Client closed", ready_check=False)
        # sleep until League pushes a change (or the backup check is due); never spin faster than 10x a second
        time.sleep(0.15)
        in_game = state.get("phase") == "InProgress"
        _wake.wait((4 if in_game else 2) if _events["connected"] else (2 if in_game else 1))
        _wake.clear()


PAGE = """<!doctype html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#0a1428">
<title>LoLStat</title>
<style>
  * { box-sizing: border-box; }
  body { margin:0; font-family: system-ui, sans-serif; background:#0a1428; color:#f0e6d2;
         min-height:100vh; display:flex; flex-direction:column; align-items:center; padding:24px 16px; }
  h1 { font-size:20px; letter-spacing:2px; color:#c8aa6e; margin:8px 0 24px; text-transform:uppercase; }
  .card { width:100%; max-width:420px; background:#091428; border:1px solid #463714;
          border-radius:12px; padding:20px; margin-bottom:16px; }
  .row { display:flex; justify-content:space-between; align-items:center; margin:8px 0; }
  .dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:8px; background:#666; }
  .on { background:#0acf83; } .off { background:#e84057; }
  .phase { font-size:28px; font-weight:700; text-align:center; margin:12px 0; }
  .muted { color:#a09b8c; font-size:14px; }
  button { width:100%; padding:18px; font-size:18px; font-weight:700; border-radius:10px;
           border:2px solid #c8aa6e; background:#1e2328; color:#f0e6d2; margin-top:10px; }
  button.primary { background:#0ac8b9; border-color:#0ac8b9; color:#0a1428; }
  button.danger { border-color:#e84057; color:#e84057; }
  #found { display:none; border-color:#0ac8b9; animation: pulse 1s infinite; }
  @keyframes pulse { 50% { box-shadow: 0 0 24px #0ac8b9; } }
</style></head>
<body>
  <h1>LoLStat</h1>

  <div class="card">
    <div class="row"><span><span id="pcDot" class="dot"></span><span id="pc">Connecting to PC...</span></span></div>
    <div class="phase" id="phase">—</div>
    <div class="row muted"><span>Accepted this session</span><span id="count">0</span></div>
    <div class="row muted"><span>Last accepted</span><span id="last">—</span></div>
  </div>

  <div class="card" id="found">
    <div class="phase">MATCH FOUND</div>
    <button class="primary" onclick="act('/accept')">Accept</button>
    <button class="danger" onclick="act('/decline')">Decline</button>
  </div>

  <a href="/app" id="fullApp" style="color:#c8aa6e;margin:0 0 14px;font-weight:700">Open the full LoLStat app on your phone</a>
  <div class="card">
    <div class="row"><span>Auto-accept</span><span id="autoTxt">—</span></div>
    <button id="toggle" onclick="act('/toggle')">Toggle</button>
  </div>

<script>
const KEY = new URLSearchParams(location.search).get('key') || '';
document.getElementById('fullApp').href = '/app?key=' + encodeURIComponent(KEY);
const NAMES = { None:'In client', Lobby:'In lobby', Matchmaking:'In queue', ReadyCheck:'Match found!',
  ChampSelect:'Champ select', GameStart:'Loading in', InProgress:'In game', WaitingForStats:'Post game',
  PreEndOfGame:'Post game', EndOfGame:'Post game', Reconnect:'Reconnect needed' };
let wasFound = false;

async function api(path, method) {
  const r = await fetch(path + '?key=' + encodeURIComponent(KEY), { method: method || 'GET' });
  if (!r.ok) throw new Error(r.status);
  return r.json();
}
async function act(path) { try { render(await api(path, 'POST')); } catch (e) {} }

function render(s) {
  document.getElementById('pcDot').className = 'dot on';
  document.getElementById('pc').textContent = s.connected ? 'PC + League client connected' : 'PC online — League client closed';
  document.getElementById('phase').textContent = NAMES[s.phase] || s.phase;
  document.getElementById('count').textContent = s.accepted_count;
  document.getElementById('last').textContent = s.last_accepted || '—';
  document.getElementById('autoTxt').innerHTML =
    '<span class="dot ' + (s.enabled ? 'on' : 'off') + '"></span>' + (s.enabled ? 'ON' : 'OFF');
  const btn = document.getElementById('toggle');
  btn.textContent = s.enabled ? 'Turn auto-accept OFF' : 'Turn auto-accept ON';
  btn.className = s.enabled ? 'danger' : 'primary';
  document.getElementById('found').style.display = s.ready_check ? 'block' : 'none';
  if (s.ready_check && !wasFound && navigator.vibrate) navigator.vibrate([300, 150, 300]);
  wasFound = s.ready_check;
}
async function refresh() {
  try { render(await api('/status')); }
  catch (e) {
    document.getElementById('pcDot').className = 'dot off';
    document.getElementById('pc').textContent = 'Can\\'t reach PC (same Wi-Fi? app running?)';
  }
}
refresh(); setInterval(refresh, 1000);
</script>
</body></html>
"""


# ---------------------------------------------------------------- settings
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
settings = {"overlay": True, "scan": True, "panel_open": False, "itemsets": True, "spells": True, "runes": True,
            "theme_follow": False,
            # quality of life
            "notify": True, "dnd": False, "dnd_ranked": True, "perf_mode": True, "close_to_tray": False,
            "start_hidden": False, "show_on_league": True, "notify_friends": True, "hotkey_mods": "ctrl+shift", "hotkey_key": "L",
            "goal_type": "", "goal_target": 0, "favorites": [], "pinned": {}, "fav_itemsets": False,
            "pick_list": [], "ban_list": [], "text_scale": 1.0, "colorblind": False, "reduce_motion": False,
            # fun
            "tilt_guard": True, "tilt_lock": False, "tilt_losses": 3, "tilt_minutes": 10, "reactive": True,
            # launch
            "showdown_best_of": 3, "showdown_auto": True,
            "overlay_look": "app", "panel_size": 0.85, "overlay_alpha": 0.9,
            "update_check": True, "update_auto": False, "itemsets_clean_others": True,
            "live_build_on": True, "panel_page": "builds", "ov_show_steps": True, "ov_show_buynow": True,
            "ov_show_kda": False, "ov_show_cs": False, "ov_show_csmin": False, "ov_show_kp": False, "ov_show_gold": False,
            "ov_show_level": False, "ov_show_augments": False,
            "clips_on": False, "clip_quality": "high", "clip_before": 12, "clip_after": 5, "clip_sound": True,
            "clip_full_game": False, "clip_max_gb": 20, "clip_kills": True, "clip_multikills": True, "clip_deaths": False,
            "clip_assists": False, "clip_objectives": True, "clip_aces": True, "clip_game_end": True,
            "onboarded": False, "last_version": "", "safe_mode": False, "_safe_saved": {},
            "spell_d": "Smart", "spell_f": "Smart", "badge_up": 0.10, "badge_size": 1.0, "theme": "dark"}
try:
    with open(SETTINGS_FILE, encoding="utf-8") as _f:
        _old = json.load(_f)
    if isinstance(_old, dict) and "onboarded" not in _old:      # upgrading from 3.x: skip setup, show What's new
        _old.update(onboarded=True, last_version="3.2.0")
    if isinstance(_old, dict) and not _old.get("_close_quits"):   # closing the window now quits LoLStat completely
        _old.update(close_to_tray=False, _close_quits=True)
    settings.update(_old)
except Exception:
    pass


def save_settings():
    try:
        tmp = SETTINGS_FILE + ".tmp"           # write then swap: a crash never wipes your settings
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(settings, f)
        os.replace(tmp, SETTINGS_FILE)
    except Exception:
        pass


mayhem = None          # MayhemService, created in main()
LOGO_PNG = base64.b64decode(LOGO_64)


def qr_svg(text):
    try:
        import io
        import qrcode
        import qrcode.image.svg
        buf = io.BytesIO()
        qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, border=1).save(buf)
        return buf.getvalue()
    except Exception:
        return (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text x="50" y="50" '
                b'font-size="8" text-anchor="middle">QR needs the qrcode package</text></svg>')


def diagnostics():
    m = mayhem
    lines = [f"{APP_NAME} {APP_VERSION}", f"Windows: {sys.getwindowsversion().major if hasattr(sys, 'getwindowsversion') else '?'}",
             f"League client: {'connected' if state.get('connected') else 'not connected'}, phase {state.get('phase')}"]
    if m:
        live = m.live or {}
        lines += [f"Live game: {'yes' if m.live else 'no'}, mode {live.get('mode')!r}, champion {live.get('champion')}",
                  f"Client language: {m.locale}, localized names: {len(m.local_names)}",
                  f"Card reading: {m.scanner_status}",
                  f"Reader details: {json.dumps(m.reader_info)}",
                  f"In-game overlay: {m.overlay_status}",
                  f"Hotkeys: {m.hotkey_status}",
                  f"Item sets: {_itemsets.get('status')}",
                  f"Runes: {_runes.get('status')}, mode {m.mode}",
                  f"Champ select: {json.dumps(getattr(m, 'cs_debug', {}))}",
                  f"Overlay setting: {settings.get('overlay')}, card reading setting: {settings.get('scan')}",
                  f"Game data: patch {m.data.get('patch')}, {m.data_status}"]
    try:
        import ctypes
        lines.append(f"Screen: {ctypes.windll.user32.GetSystemMetrics(0)}x{ctypes.windll.user32.GetSystemMetrics(1)}, "
                     f"display scale {ctypes.windll.user32.GetDpiForSystem() / 96:.2f}")
    except Exception:
        pass
    lines.append("Recent log:")
    lines += LOG_LINES[-15:]
    return "\n".join(lines)


# ---------------------------------------------------------------- instant screen updates
# The app asks "anything new since <hash>?" and the answer waits until something really changes
# (checked every 50 ms), so a change shows on screen right away without the page re-drawing constantly.
_ui = {"json": "", "hash": "", "t": 0}
_ui_cond = threading.Condition()


def _ui_refresh():
    s = json.dumps(full_state())
    h = format(hash(s) & 0xFFFFFFFF, "x")
    with _ui_cond:
        _ui["t"] = time.time()
        if h != _ui["hash"]:
            _ui.update(json=s, hash=h)
            _ui_cond.notify_all()


def ui_pump():
    while True:
        try:
            _ui_refresh()
        except Exception:
            pass
        game = mayhem is not None and mayhem.live is not None
        time.sleep((0.5 if settings.get("perf_mode") else 0.25) if game else 0.1)


def ui_state(since=""):
    if time.time() - _ui["t"] > 1:              # the pump isn't running (tests): build it now
        _ui_refresh()
    with _ui_cond:
        if since and since == _ui["hash"]:
            _ui_cond.wait_for(lambda: _ui["hash"] != since, timeout=4)
        s, h = _ui["json"], _ui["hash"]
    return s[:-1] + f', "_h": "{h}"}}'


def full_state():
    with lock:
        a = dict(state)
    return {
        "app": {"name": APP_NAME, "version": APP_VERSION, "notice": RIOT_NOTICE},
        "accept": a,
        "settings": dict(settings),
        "mayhem": mayhem.state() if mayhem else {},
        "log": [l for l in LOG_LINES if "Phone remote:" not in l][-8:],
        "goal": goal_progress(), "dnd_active": is_dnd(), "showdown": showdown.summary(),
            "clips": clips.view() if clips else None,
            "update": updater.view() if updater else None, "tilt_lock": tilt_locked(),
        "onboarded": bool(settings.get("onboarded")), "show_whatsnew": bool(settings.get("onboarded")) and settings.get("last_version") != APP_VERSION,
        "my_champs": {c["champion"]: [c["games"], c["wr"]] for c in (insights_data().get("champions") or [])},
        "snapshots": SNAP_DIR,
    }


def do_action(body):
    act = body.get("action")
    if act == "toggle_accept" and settings.get("safe_mode") and not state.get("enabled"):
        mayhem.notify("Safe mode is on. Turn it off in Settings to use automation again.")
    elif act == "toggle_accept":
        with lock:
            state["enabled"] = not state["enabled"]
            log(f"Auto-accept turned {'ON' if state['enabled'] else 'OFF'}.")
    elif act == "setting":
        name = body.get("name")
        if settings.get("safe_mode") and name in SAFE_KEYS and not settings.get(name):
            mayhem.notify("Safe mode is on. Turn it off in Settings to use automation again.")
            return
        if name in settings:
            settings[name] = not settings[name]
            save_settings()
            log(f"{name} turned {'on' if settings[name] else 'off'}.")
    elif act == "refresh_data":
        threading.Thread(target=mayhem.refresh_data, daemon=True).start()
    elif act == "add_aug":
        mayhem.add_augment(str(body.get("id")))
    elif act == "remove_aug":
        mayhem.remove_augment(str(body.get("id")))
    elif act == "clear_augs":
        mayhem.clear_augments()
    elif act == "dismiss_unconfirmed":
        mayhem.dismiss_unconfirmed()
    elif act == "set_champion":
        mayhem.set_champion(body.get("name", ""))
    elif act == "set_enemy":
        mayhem.set_enemy(int(body.get("i", -1)), body.get("name", ""))
    elif act == "swap":
        try:
            mayhem.swap_bench(body.get("name", ""))
        except Exception as e:
            mayhem.notify(f"Couldn't swap: {e}")
    elif act == "reroll":
        try:
            mayhem.reroll()
        except Exception as e:
            mayhem.notify(f"Couldn't reroll: {e}")
    elif str(act or "").startswith("sd_"):
        showdown_action(act, body)
    elif act == "show_window":
        show_main_force()
    elif act == "quit":
        threading.Thread(target=lambda: (time.sleep(0.3), quit_app()), daemon=True).start()
    elif act == "finish_onboarding":
        for k, v in (body.get("auto") or {}).items():
            if k == "accept":
                with lock:
                    state["enabled"] = bool(v)
            elif k in settings and isinstance(v, bool):
                settings[k] = v
        settings["onboarded"] = True
        settings["last_version"] = APP_VERSION
        save_settings()
    elif act == "seen_whatsnew":
        settings["last_version"] = APP_VERSION
        save_settings()
    elif act == "safe_mode":
        set_safe_mode(not settings.get("safe_mode"))
        mayhem.notify("Safe mode on: all automation is paused" if settings["safe_mode"] else "Safe mode off: your automation is back")
    elif act == "cleanup":
        try:
            n = cleanup_client()
            mayhem.notify(f"Removed {n} LoLStat item sets and rune pages from League")
        except Exception as e:
            mayhem.notify(f"Couldn't clean up: {e}. Open League and try again.")
    elif act == "end_break":
        _tilt["lock_until"] = 0
        mayhem.notify("Break ended. Good luck!")
    elif act == "mini":
        toggle_mini()
    elif act == "backup":
        try:
            fp = make_backup()
            mayhem.notify(f"Backup saved to Documents\\LoLStat Backups")
        except Exception as e:
            mayhem.notify(f"Couldn't make a backup: {e}")
    elif act == "favorite":
        name = body.get("name", "")
        favs = settings.setdefault("favorites", [])
        if name in favs:
            favs.remove(name)
        elif name in mayhem.data["champions"]:
            favs.append(name)
        save_settings()
        if settings.get("fav_itemsets"):
            threading.Thread(target=lambda: _safe(write_favorite_sets), daemon=True).start()
    elif act == "pin_build":
        settings.setdefault("pinned", {})[body.get("name", "")] = int(body.get("index") or 0)
        save_settings()
        _itemsets["sig"] = None
    elif act == "list_edit":
        lst = settings.setdefault(body.get("list"), []) if body.get("list") in ("pick_list", "ban_list") else None
        name = body.get("name", "")
        if lst is not None and name in mayhem.data["champions"]:
            if body.get("remove"):
                if name in lst:
                    lst.remove(name)
            elif name not in lst:
                lst.append(name)
            save_settings()
    elif act == "goal":
        settings["goal_type"] = body.get("type", "")
        settings["goal_target"] = int(body.get("target") or 0)
        save_settings()
    elif act == "fav_sets_now":
        threading.Thread(target=lambda: mayhem.notify(f"Saved {_safe(write_favorite_sets) or 0} item sets for your favorites"), daemon=True).start()
    elif act == "journal":
        archive.set_note(body.get("id"), body.get("mood"), body.get("text"))
        _ins["sig"] = None
    elif act == "sync_archive":
        threading.Thread(target=sync_archive, args=(True,), daemon=True).start()
    elif act == "refresh_profile":
        threading.Thread(target=refresh_profile, args=(True,), daemon=True).start()
    elif act == "replay":
        gid = body.get("id")
        try:
            meta = lcu_call("GET", f"/lol-replays/v1/metadata/{gid}") or {}
            st = meta.get("state")
            src = {"componentType": "replay-button_match-history"}
            if st == "watch":
                lcu_call("POST", f"/lol-replays/v1/rofls/{gid}/watch", src)
                mayhem.notify("Opening the replay in League")
            elif st in ("download", "checking", "retry-download", "lost"):
                lcu_call("POST", f"/lol-replays/v1/rofls/{gid}/download", src)
                mayhem.notify("Replay downloading. Click again when it's done to watch.")
            else:
                mayhem.notify(f"Replay not available ({st or 'unknown'}). Replays only work for the current patch.")
        except Exception as e:
            mayhem.notify(f"Couldn't open replay: {e}")
    elif act == "ban":
        try:
            mayhem.ban(body.get("name", ""))
        except Exception as e:
            mayhem.notify(f"Couldn't ban: {e}")
    elif act == "pick":
        try:
            mayhem.pick(body.get("name", ""))
        except Exception as e:
            mayhem.notify(f"Couldn't lock in: {e}")
    elif act == "snapshot":
        if reader and reader.ocr:
            threading.Thread(target=reader.snapshot, daemon=True).start()
        else:
            mayhem.notify("Card reading isn't running: " + (mayhem.scanner_status or "unknown"))
    elif act == "pick_aug":
        mayhem.manual_pick(str(body.get("id")))
    elif act == "set_value":
        name, value = body.get("name"), body.get("value")
        if name == "champ_theme" and isinstance(value, dict):
            t = champ_theme(value.get("champion", ""), int(value.get("num") or 0), value.get("skin", ""))
            if t:
                apply_champ_theme(t)
                settings["theme_follow"] = False
                save_settings()
            return
        if name in ("clip_quality", "clip_before", "clip_after", "clip_max_gb"):
            settings[name] = value if name == "clip_quality" else max(1, min(200, float(value)))
            if name == "clip_quality" and clips and clips.proc:
                log("Clips: the new quality starts with your next game")
            save_settings()
            return
        if name in ("badge_up", "badge_size", "theme", "custom_theme", "overlay_theme", "spell_d", "spell_f",
                    "hotkey_mods", "hotkey_key", "text_scale", "tilt_losses", "tilt_minutes",
                    "overlay_look", "panel_size", "overlay_alpha"):
            if name == "panel_size":
                value = max(0.6, min(1.5, float(value)))
            if name == "overlay_alpha":
                value = max(0.5, min(1.0, float(value)))
            settings[name] = value
            if name == "overlay_look":
                _follow["key"] = None          # re-check the champion skin right away
            save_settings()
            if name in ("spell_d", "spell_f"):
                _spells["sig"] = None
    elif act == "test_overlay":
        mayhem.test_until = time.time() + 15
        mayhem.notify("Test overlay: look at your screen for the LoLStat button, panel and three sample letters (15 seconds).")
    elif act == "itemsets_clean":
        def run():
            try:
                n = clean_other_item_sets()
                mayhem.notify(f"Removed {n} item set{'s' if n != 1 else ''} from other apps. Yours are kept." if n
                              else "No item sets from other apps found.")
            except Exception as e:
                mayhem.notify(f"Couldn't clean up item sets: {e}")
        threading.Thread(target=run, daemon=True).start()
    elif act == "update_check":
        if updater:
            threading.Thread(target=updater.check, daemon=True).start()
    elif act == "update_install":
        if updater:
            updater.install()
    elif act == "update_later":
        if updater:
            updater.later()
            save_settings()
    elif act == "panel_page":
        settings["panel_page"] = "live" if body.get("value") == "live" else "builds"
        save_settings()
    elif act == "clip_delete":
        if clips:
            clips.delete(body.get("path", ""))
    elif act in ("clip_folder", "clip_show"):
        try:
            if act == "clip_show" and clips and clips.resolve(body.get("path", "")):
                subprocess.Popen(["explorer", "/select,", clips.resolve(body["path"])])
            else:
                os.makedirs(clips.folder(), exist_ok=True)
                os.startfile(clips.folder())
        except Exception:
            pass
    elif act == "clip_save":
        if clips:
            clips.save_last(int(body.get("seconds") or 30))
    elif act == "open_snapshots":
        os.makedirs(SNAP_DIR, exist_ok=True)
        try:
            os.startfile(SNAP_DIR)
        except Exception:
            pass
    elif act == "accept":
        accept()
    elif act == "decline":
        decline()


class Handler(BaseHTTPRequestHandler):
    def _ok_key(self):
        q = parse_qs(urlparse(self.path).query)
        return q.get("key", [""])[0] == KEY

    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass        # the page closed or reloaded while waiting for an update

    def _status(self):
        with lock:
            return json.dumps(state)

    def _send_file(self, p, ctype):
        """Serve a file with Range support, so the clip player can seek."""
        size = os.path.getsize(p)
        start, end = 0, size - 1
        rng = self.headers.get("Range", "")
        m = re.match(r"bytes=(\d*)-(\d*)", rng)
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
        try:
            self.send_response(206 if m and rng else 200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if m and rng:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            with open(p, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/logo.png":
            return self._send(200, LOGO_PNG, "image/png")
        if not self._ok_key():
            return self._send(403, "Wrong or missing key. Use the link shown in LoLStat.", "text/plain")
        if path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif path == "/app":
            self._send(200, ui_pages.APP_HTML, "text/html; charset=utf-8")
        elif path == "/mini":
            self._send(200, ui_pages.MINI_HTML, "text/html; charset=utf-8")
        elif path == "/overlay":
            self._send(200, ui_pages.OVERLAY_HTML, "text/html; charset=utf-8")
        elif path == "/status":
            self._send(200, self._status())
        elif path == "/api/state":
            h = parse_qs(urlparse(self.path).query).get("h", [""])[0]
            self._send(200, ui_state(h))
        elif path == "/api/augments":
            self._send(200, json.dumps(mayhem.augments_list()))
        elif path == "/api/champions":
            self._send(200, json.dumps(mayhem.champions_list()))
        elif path == "/api/champion":
            q = parse_qs(urlparse(self.path).query)
            self._send(200, json.dumps(mayhem.champion_page(q.get("name", [""])[0], q.get("mode", ["sr"])[0])))
        elif path == "/api/player":
            import lcu_stats
            q = parse_qs(urlparse(self.path).query)
            try:
                data = lcu_stats.player_profile(lcu_call, mayhem.champ_name, q.get("riot", [None])[0], q.get("puuid", [None])[0])
            except Exception as e:
                data = {"error": str(e) if state.get("connected") else "Open League to look up players."}
            self._send(200, json.dumps(data))
        elif path == "/api/friends":
            import lcu_stats
            try:
                data = lcu_stats.friends(lcu_call)
            except Exception:
                data = []
            self._send(200, json.dumps(data))
        elif path == "/api/clips":
            self._send(200, json.dumps({"clips": clips.list() if clips else [], "recorder": clips.view() if clips else {}}))
        elif path in ("/clip", "/clipthumb"):
            p = clips.resolve(parse_qs(urlparse(self.path).query).get("f", [""])[0]) if clips else None
            if not p:
                return self._send(404, "Not found", "text/plain")
            return self._send_file(p, "image/jpeg" if p.endswith(".jpg") else "video/mp4")
        elif path == "/api/showdown":
            self._send(200, json.dumps(showdown.view(int(settings.get("showdown_best_of", 3)))))
        elif path == "/api/challenges":
            q = parse_qs(urlparse(self.path).query)
            self._send(200, json.dumps(challenges_data(q.get("champ", [None])[0])))
        elif path == "/api/items":
            self._send(200, json.dumps(sorted([mayhem.item_view({"id": k, "name": v["name"], "gold": v["gold"], "boots": v["boots"]})
                                               for k, v in mayhem.data["items"].items() if v.get("sr", True)], key=lambda x: x["name"])))
        elif path == "/api/insights":
            self._send(200, json.dumps(insights_data()))
        elif path == "/api/journey":
            q = parse_qs(urlparse(self.path).query)
            self._send(200, json.dumps(insights.journey(archive.list(), q.get("champ", [""])[0]) or {}))
        elif path == "/api/friends_board":
            self._send(200, json.dumps(friends_board()))
        elif path == "/api/skins":
            q = parse_qs(urlparse(self.path).query)
            self._send(200, json.dumps(skin_list(q.get("champ", [""])[0])))
        elif path == "/api/champ_theme":
            q = parse_qs(urlparse(self.path).query)
            t = champ_theme(q.get("champ", [""])[0], int(q.get("num", ["0"])[0] or 0), q.get("skin", [""])[0])
            self._send(200, json.dumps(t or {"error": "Unknown champion"}))
        elif path == "/api/art":
            q = parse_qs(urlparse(self.path).query)
            alias = re.sub(r"[^A-Za-z0-9]", "", q.get("alias", [""])[0])
            num = int(q.get("num", ["0"])[0] or 0)
            fp = champ_themes.art_path(alias, num, DATA_DIR) or (champ_themes.art_path(alias, 0, DATA_DIR) if num else None)
            if fp:
                self.send_response(200)
                data = open(fp, "rb").read()
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                self.wfile.write(data)
            else:
                self._send(404, "{}")
        elif path == "/api/profile":
            self._send(200, json.dumps(_profile["data"] or {"empty": True, "connected": bool(state.get("connected"))}))
        elif path == "/api/scout":
            self._send(200, json.dumps({"players": _scout["players"], "status": _scout["status"],
                                        "live": bool(mayhem and mayhem.live)}))
        elif path == "/api/reader.jpg":
            self._send(200, mayhem.preview[0] or LOGO_PNG, "image/jpeg" if mayhem.preview[0] else "image/png")
        elif path == "/api/diagnostics":
            self._send(200, diagnostics(), "text/plain; charset=utf-8")
        elif path == "/api/qr.svg":
            self._send(200, qr_svg(PHONE_URL), "image/svg+xml")
        else:
            self._send(404, "{}")

    def do_POST(self):
        if not self._ok_key():
            return self._send(403, "{}")
        path = urlparse(self.path).path
        if path in ("/api/buildlab", "/api/compare"):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            try:
                if path == "/api/buildlab":
                    c = mayhem.data["champions"].get(body.get("champ", ""))
                    prof = (mayhem.champ_ranks.get(c["key"]) or eng_champion_ranks(c["key"])) if c else None
                    res = fun.build_lab(body.get("champ", ""), body.get("items", []), body.get("enemies", []), mayhem.data,
                                        (prof or {}).get("items"))
                else:
                    res = fun.compare_items(body.get("champ", ""), body.get("a"), body.get("b"), body.get("enemies", []), mayhem.data)
            except Exception as e:
                res = {"error": str(e)}
            return self._send(200, json.dumps(res))
        if path == "/api/restore":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                count = restore_backup(base64.b64decode(body.get("data", "").split(",")[-1]))
                mayhem.notify(f"Backup restored ({count} files)")
                return self._send(200, json.dumps({"ok": True, "files": count}))
            except Exception as e:
                return self._send(200, json.dumps({"error": str(e)}))
        if path == "/api/save_card":           # stats card image -> Pictures\LoLStat, then show it
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                png = base64.b64decode(body.get("png", "").split(",")[-1])
                folder = os.path.join(os.path.expanduser("~"), "Pictures", "LoLStat")
                os.makedirs(folder, exist_ok=True)
                safe = re.sub(r"[^A-Za-z0-9_-]+", "_", body.get("name", "stats"))[:40]
                fp = os.path.join(folder, f"{safe}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
                open(fp, "wb").write(png)
                try:
                    subprocess.Popen(["explorer", "/select,", fp])
                except Exception:
                    pass
                mayhem.notify(f"Stats card saved to Pictures\\LoLStat")
                return self._send(200, json.dumps({"saved": fp}))
            except Exception as e:
                return self._send(200, json.dumps({"error": str(e)}))
        try:
            if path == "/api/action":
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                do_action(body)
                return self._send(200, json.dumps(full_state()))
            if path == "/toggle":
                with lock:
                    state["enabled"] = not state["enabled"]
                    log(f"Auto-accept turned {'ON' if state['enabled'] else 'OFF'} from phone.")
            elif path == "/accept":
                accept(); log("Accepted from phone.")
            elif path == "/decline":
                decline(); log("Declined from phone.")
            else:
                return self._send(404, "{}")
        except Exception as e:
            log(f"Action failed: {e}")
        self._send(200, self._status())

    def log_message(self, *args):
        pass


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # no data is actually sent
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


KEY = load_key()
PHONE_URL = f"http://{local_ip()}:{WEB_PORT}/?key={KEY}"
LOCAL = f"http://127.0.0.1:{WEB_PORT}"
OVERLAY_TITLE = "LoLStat Overlay"


def lcu_call(method, path, body=None):
    lcu = current_lcu
    if not lcu:
        raise RuntimeError("League client isn't connected")
    return lcu.req(method, path, body)


SNAP_DIR = os.path.join(DATA_DIR, "snapshots")

# ---------------------------------------------------------------- item sets in the League client
import uuid
ITEMSET_PREFIX = "lolstat-"
ITEMSET_UIDS = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"lolstat-itemset-{n}")) for n in range(3)]
_itemsets = {"sig": None, "written": False, "status": "nothing saved yet"}


def _is_ours(x):
    uid = str(x.get("uid", ""))
    return uid in ITEMSET_UIDS or uid.startswith(ITEMSET_PREFIX) or str(x.get("title", "")).startswith("LoLStat - ")


# item sets other build apps leave behind, recognised by the app name they put first in the title
# (or in the id / file name). Sets you made yourself never match and are never touched.
_OTHER_APP = re.compile(r"^[\s\[\(]*(u\.?gg|blitz(\.gg)?|mobalytics|op\.?gg|porofessor|probuilds|lolalytics|metasrc|"
                        r"champion\.?gg|deeplol|lolvvv|league ?of ?graphs|iten|itemsetter|championify|ugg)\b", re.I)


def _is_other_app(x, filename=""):
    if _is_ours(x):
        return False
    for v in (x.get("title"), x.get("uid"), re.sub(r"[_\-.]+", " ", filename.rsplit(".", 1)[0])):
        if v and _OTHER_APP.search(str(v)):
            return True
    return False


ROLE_NAME = {"top": "Top", "jungle": "Jungle", "middle": "Mid", "bottom": "ADC", "utility": "Support"}
STYLE_NAME = {"MAX DAMAGE": "Max damage", "AUGMENT OVERDRIVE": "Overdrive", "NEVER BEEN DONE": "Off-meta",
              "COUNTER-DAMAGE": "Counter-damage"}


def set_title(champ, mode, role, style="", main=True):
    """Item set name, e.g. "LoLStat Jinx ADC"."""
    where = {"mayhem": "ARAM Mayhem", "aram": "ARAM"}.get(mode) or ROLE_NAME.get(role, "")
    t = f"LoLStat {champ} {where}".strip()
    return t if main else f"{t} - {STYLE_NAME.get(style, style.title())}"


def ugg_blocks(builds, idx, mode, role, champ):
    """Item set blocks, laid out the familiar way:
    Starting Items, Core Items (in buy order, boots included), Fourth / Fifth / Sixth Item Options,
    Situational Items, Consumables & Trinkets."""
    b = builds[idx]
    g = b.get("guide") or {}
    def ids(items):
        counts = {}
        for it in items:
            counts[str(it["id"])] = counts.get(str(it["id"]), 0) + 1
        return [{"id": i, "count": n} for i, n in counts.items()]
    blocks = []
    if (g.get("start") or {}).get("items"):
        blocks.append({"type": "Starting Items", "items": ids(g["start"]["items"])})
    items = b["items"]
    # core = three buys: first item, boots, second item (or three items when the build skips boots)
    if b.get("boots"):
        core, first_opt = [items[0], b["boots"]] + items[1:2], 2
    else:
        core, first_opt = items[:3], 3
    blocks.append({"type": "Core Items", "items": [{"id": str(i["id"]), "count": 1} for i in core]})
    taken = {str(i["id"]) for i in core}
    others = [o for o in builds if o is not b]
    names = ["Fourth Item Options", "Fifth Item Options", "Sixth Item Options"]
    for n, name in enumerate(names):
        k = first_opt + n
        if k >= len(items) and not any(len(o["items"]) > k for o in others):
            break
        cands = [x["items"][k] for x in [b] + others if len(x["items"]) > k]
        cands += [x["items"][j] for x in [b] + others for j in (k + 1, k - 1) if first_opt <= j < len(x["items"])]
        opts = []
        for it in cands:
            if str(it["id"]) not in taken and len(opts) < 3:
                taken.add(str(it["id"]))
                opts.append(it)
        if opts:
            blocks.append({"type": name, "items": ids(opts)})
    situ = g.get("situational") or []
    extra = [x for x in situ if x["situation"] != "Boots swap"] + [x for x in situ if x["situation"] == "Boots swap"]
    extra = [x for x in extra if str(x["id"]) not in taken]
    if extra:
        blocks.append({"type": "Situational Items", "items": ids(extra[:6])})
    ch = mayhem.data["champions"].get(champ, {})
    dmg = (g and __import__("build_guide").build_dmg(b, mayhem.data, ch)) if ch else "ad"
    elixir = "2138" if "Tank" in ch.get("classes", []) else "2139" if dmg == "ap" else "2140"
    if mode == "sr":
        trinket = "3364" if role in ("jungle", "utility") else "3363" if role == "bottom" else "3364"
        cons = ["2003", "2055", elixir, trinket]
    else:
        cons = ["2003", elixir]
    blocks.append({"type": "Consumables & Trinkets", "items": [{"id": i, "count": 1} for i in cons]})
    return blocks


def o_ok(build, k):
    return 0 <= k < len(build["items"]) and k >= 3


def guide_blocks(guide):
    """The item set, step by step: start, first back, core, boots, end game, situational swaps."""
    def ids(items):
        counts = {}
        for it in items:
            counts[str(it["id"])] = counts.get(str(it["id"]), 0) + 1
        return [{"id": i, "count": n} for i, n in counts.items()]
    blocks = []
    st = guide.get("start") or {}
    if st.get("items"):
        blocks.append({"type": "1. Start", "items": ids(st["items"])})
    fb = guide.get("first_back") or {}
    if fb.get("items"):
        blocks.append({"type": "2. First back (buy from the left)", "items": ids(fb["items"])})
    if guide.get("core"):
        blocks.append({"type": "3. Core - rush the first item", "items": ids(guide["core"])})
    if guide.get("boots") and guide["boots"].get("item"):
        blocks.append({"type": "4. Boots - " + guide["boots"]["note"].rstrip(".").lower().replace("finish these", "finish"),
                       "items": ids([guide["boots"]["item"]])})
    if guide.get("late"):
        blocks.append({"type": "5. End game", "items": ids(guide["late"])})
    swaps = [x for x in guide.get("situational") or [] if x["situation"] != "Boots swap"]
    for x in swaps[:5]:
        when = x["when"].replace("Buy it now: ", "BUY NOW - ").replace("Buy if ", "if ")
        blocks.append({"type": f"Situational: {x['situation']} ({when})"[:90], "items": ids([x])})
    bs = [x for x in guide.get("situational") or [] if x["situation"] == "Boots swap"]
    if bs:
        blocks.append({"type": "Situational: swap boots (Steelcaps vs AD, Mercury's vs AP/CC)", "items": ids(bs)})
    return blocks


def _full_block(b):
    return dict({"hideIfSummonerSpell": "", "showIfSummonerSpell": "", "recMath": False,
                 "minSummonerLevel": -1, "maxSummonerLevel": -1}, **b)


_install = {"dir": None}


def _league_dir():
    """League's install folder (the one with Config\\), asked from the client."""
    if not _install["dir"]:
        d = lcu_call("GET", "/data-store/v1/install-dir")
        if isinstance(d, str) and os.path.isdir(d):
            _install["dir"] = d
    return _install["dir"]


def _set_files_dir(alias):
    base = _league_dir()
    return os.path.join(base, "Config", "Champions", alias, "Recommended") if base else None


def _write_set_files(champ, sets):
    """Write the sets as League item set files: Config\\Champions\\<Champion>\\Recommended\\LoLStat_N.json."""
    alias = mayhem.data["champions"][champ].get("alias") or champ
    _remove_set_files()
    folder = _set_files_dir(alias)
    if not folder:
        raise RuntimeError("couldn't find League's install folder")
    os.makedirs(folder, exist_ok=True)
    for n, st in enumerate(sets):
        f = {"title": st["title"], "type": "custom", "map": "any", "mode": "any", "priority": False, "sortrank": n,
             "champion": alias, "blocks": st["blocks"]}
        with open(os.path.join(folder, f"LoLStat_{n + 1}.json"), "w", encoding="utf-8") as fh:
            json.dump(f, fh)
    _itemsets["files"] = folder


def _remove_set_files():
    """Delete LoLStat's item set files from every champion folder (yours are never touched)."""
    base = _install["dir"]
    if not base:
        try:
            base = _league_dir()
        except Exception:
            base = None
    root = os.path.join(base, "Config", "Champions") if base else None
    n = 0
    if root and os.path.isdir(root):
        for champ_dir in os.listdir(root):
            rec = os.path.join(root, champ_dir, "Recommended")
            if os.path.isdir(rec):
                for fn in os.listdir(rec):
                    if fn.startswith("LoLStat_") and fn.endswith(".json"):
                        try:
                            os.remove(os.path.join(rec, fn))
                            n += 1
                        except OSError:
                            pass
    return n


def _remove_other_app_files():
    """Delete item set files other apps wrote into League's Config folder. Only files whose name or title
    starts with another app's name; every other file (including ones you made) stays."""
    try:
        base = _install["dir"] or _league_dir()
    except Exception:
        base = None
    cfg = os.path.join(base, "Config") if base else None
    if not cfg or not os.path.isdir(cfg):
        return 0
    folders = [os.path.join(cfg, "Global", "Recommended")]
    champs = os.path.join(cfg, "Champions")
    if os.path.isdir(champs):
        folders += [os.path.join(champs, c, "Recommended") for c in os.listdir(champs)]
    n = 0
    for rec in folders:
        if not os.path.isdir(rec):
            continue
        for fn in os.listdir(rec):
            if not fn.lower().endswith(".json") or fn.startswith("LoLStat_"):
                continue
            fp = os.path.join(rec, fn)
            try:
                with open(fp, encoding="utf-8", errors="replace") as fh:
                    data = json.load(fh)
            except Exception:
                data = {}
            if _is_other_app(data if isinstance(data, dict) else {}, fn):
                try:
                    os.remove(fp)
                    n += 1
                except OSError:
                    pass
    return n


def clean_other_item_sets():
    """Remove other apps' item sets now: from your account's sets in the client and from League's files."""
    n = _remove_other_app_files()
    try:
        path, me = _set_path()
        cur = lcu_call("GET", path) or {}
        sets = cur.get("itemSets", [])
        keep = [x for x in sets if not _is_other_app(x)]
        if len(keep) != len(sets):
            lcu_call("PUT", path, {"accountId": cur.get("accountId", me.get("accountId")), "itemSets": keep,
                                   "timestamp": int(time.time() * 1000)})
            n += len(sets) - len(keep)
    except Exception as e:
        if not n:
            raise RuntimeError("open the League client first") from e
    log(f"Removed {n} item set{'s' if n != 1 else ''} made by other apps. Yours are kept." if n
        else "No item sets from other apps found. Yours are untouched.")
    return n


def _set_path():
    me = lcu_call("GET", "/lol-summoner/v1/current-summoner") or {}
    return f"/lol-item-sets/v1/item-sets/{me['summonerId']}/sets", me


def _put_sets(make_ours):
    """Replace only LoLStat's sets; the player's own sets stay exactly as they are."""
    path, me = _set_path()
    cur = lcu_call("GET", path) or {}
    clean = settings.get("itemsets_clean_others", True)
    keep = [x for x in cur.get("itemSets", []) if not _is_ours(x) and not (clean and _is_other_app(x))]
    gone = len(cur.get("itemSets", [])) - len(keep) - len([x for x in cur.get("itemSets", []) if _is_ours(x)])
    if gone:
        log(f"Removed {gone} item set{'s' if gone != 1 else ''} other apps left in your client (yours are kept).")
    ours = make_ours()
    body = {"accountId": cur.get("accountId", me.get("accountId")), "itemSets": keep + ours,
            "timestamp": int(time.time() * 1000)}
    lcu_call("PUT", path, body)
    back = lcu_call("GET", path) or {}               # read back: did the client really keep them?
    saved = [x for x in back.get("itemSets", []) if _is_ours(x)]
    if len(saved) != len(ours):
        raise RuntimeError(f"client kept {len(saved)} of {len(ours)} sets")


def write_item_sets():
    champ = mayhem.current_champion()
    builds = mayhem.builds()
    if not champ or not builds:
        return
    pin = (settings.get("pinned") or {}).get(champ)
    if pin is not None and 0 <= int(pin) < len(builds):        # your pinned build goes first
        builds = [builds[int(pin)]] + [b for i, b in enumerate(builds) if i != int(pin)]
    mayhem.remember_set_builds(champ, builds)                 # the game shows exactly these, in this order
    sig = json.dumps([champ, [[b["boots"]["id"] if b["boots"] else ""] + [i["id"] for i in b["items"]] for b in builds]])
    if sig == _itemsets["sig"]:
        return
    key = mayhem.data["champions"][champ]["key"]
    short = {"MAX DAMAGE": "Max damage", "AUGMENT OVERDRIVE": "Overdrive", "NEVER BEEN DONE": "Off-meta"}

    sr = mayhem.mode == "sr"
    role = (mayhem.champ_select or {}).get("role", "")

    def ours():
        sets = []
        for n, b in enumerate(builds):
            if b.get("guide"):
                blocks = ugg_blocks(builds, n, mayhem.mode, role, champ)
                sets.append({"title": set_title(champ, mayhem.mode, role if sr else "", b["style"], main=(n == 0)),
                             "uid": ITEMSET_UIDS[n], "type": "custom", "map": "any", "mode": "any",
                             "associatedMaps": [], "associatedChampions": [int(key)], "blocks": [_full_block(x) for x in blocks],
                             "preferredItemSlots": [], "sortrank": n, "startedFrom": "blank"})
                continue
            blocks = []
            if sr and role == "utility":
                blocks.append({"type": "Support start", "items": [{"id": "3865", "count": 1}, {"id": "2003", "count": 2}]})
            if b["boots"]:
                blocks.append({"type": "Boots", "items": [{"id": str(b["boots"]["id"]), "count": 1}]})
            blocks.append({"type": "Build order (LoLStat)", "items": [{"id": str(i["id"]), "count": 1} for i in b["items"]]})
            sets.append({"title": f"LoLStat - {short.get(b['style'], b['style'].title())} ({champ})",
                         "uid": ITEMSET_UIDS[n], "type": "custom", "map": "any", "mode": "any",
                         # every map: ARAM Mayhem and the newer ARAM maps don't use Howling Abyss's old map number
                         "associatedMaps": [], "associatedChampions": [int(key)], "blocks": [_full_block(x) for x in blocks],
                         "preferredItemSlots": [], "sortrank": n, "startedFrom": "blank"})
        return sets
    errors = []
    if settings.get("itemsets_clean_others", True) and not _itemsets.get("files_cleaned"):
        _itemsets["files_cleaned"] = True                  # once per session: League's files from other apps
        try:
            k = _remove_other_app_files()
            if k:
                log(f"Removed {k} item set file{'s' if k != 1 else ''} other apps left in League's folder.")
        except Exception:
            pass
    try:
        _put_sets(ours)
    except Exception as e:
        errors.append(e)
    try:                       # backup: League's own item set files, which the game reads when it loads
        _write_set_files(champ, ours())
    except Exception as e:
        log(f"Couldn't write item set files: {e}")
        if errors:
            raise errors[0]
    if errors:
        log(f"Item sets: the client refused them ({errors[0]}), saved as League files instead")
    _itemsets.update(sig=sig, written=True, status=f"saved 3 sets for {champ} at {datetime.now().strftime('%I:%M:%S %p')}")
    mayhem.notify(f"3 item sets saved to your client for {champ}")


def clear_item_sets():
    if _itemsets["written"]:
        try:
            _put_sets(lambda: [])
        finally:
            _remove_set_files()
        _itemsets.update(sig=None, written=False)
        log("Removed LoLStat item sets after the game.")


SPELLS = {"Flash": 4, "Ignite": 14, "Exhaust": 3, "Heal": 7, "Barrier": 21, "Ghost": 6,
          "Cleanse": 1, "Clarity": 13, "Mark": 32, "Smite": 11, "Teleport": 12}
_runes = {"sig": None, "status": "nothing imported yet"}
_spells = {"sig": None}
_eog = {"done": None}


def smart_spells(champ, aram, role=""):
    c = mayhem.data["champions"].get(champ, {})
    assassin = "Slayer" in c.get("classes", []) or "Assassin" in c.get("subclasses", [])
    melee = c.get("range", 550) <= 300
    if aram:
        return ("Ignite", "Flash") if assassin or (melee and "Fighter" in c.get("classes", [])) else ("Mark", "Flash")
    if role == "jungle":
        return ("Smite", "Flash")
    if role == "bottom":
        return ("Heal", "Flash")
    if role == "top" and not assassin:
        return ("Teleport", "Flash")
    return ("Ignite", "Flash")   # mid, support and assassins: the damage pick


def sync_runes(phase):
    """Import a damage rune page for your champion (Summoner's Rift and ARAM; Mayhem has no runes)."""
    if not mayhem or not settings.get("runes", True) or phase != "ChampSelect" or mayhem.mode == "mayhem":
        return
    champ = mayhem.current_champion()
    page = mayhem.rune_page(champ) if champ else None
    if not page:
        return
    sig = (champ, tuple(page["selectedPerkIds"]))
    if sig == _runes["sig"]:
        return
    _runes["sig"] = sig
    try:
        import runes
        runes.apply_page(lcu_call, page)
        _runes["status"] = f"imported {page['keystone']} page for {champ}"
        mayhem.notify(f"Rune page imported: {page['keystone']} ({page['primary']} + {page['secondary']})")
    except Exception as e:
        _runes["status"] = f"failed: {e}"
        mayhem.notify(f"Couldn't import runes: {e}")


def sync_spells(phase):
    """Set your summoner spells in champ select (Smart picks damage spells for your champion)."""
    if not mayhem or not settings.get("spells", True) or phase != "ChampSelect":
        if phase != "ChampSelect":
            _spells["sig"] = None
        return
    cs = mayhem.champ_select or {}
    champ = mayhem.current_champion()
    if not champ:
        return
    aram = mayhem.mode in ("aram", "mayhem")
    d, f = settings.get("spell_d", "Smart"), settings.get("spell_f", "Smart")
    sd, sf = smart_spells(champ, aram, cs.get("role", ""))
    d = sd if d == "Smart" else d
    f = sf if f == "Smart" else f
    if d == f:
        f = "Flash" if d != "Flash" else sf
    sig = (champ, d, f)
    if sig == _spells["sig"]:
        return
    try:
        lcu_call("PATCH", "/lol-champ-select/v1/session/my-selection",
                 {"spell1Id": SPELLS[d], "spell2Id": SPELLS[f]})
        _spells["sig"] = sig
        mayhem.notify(f"Summoner spells set: {d} + {f}")
    except Exception as e:
        _spells["sig"] = sig
        log(f"Couldn't set spells: {e}")


# ---------------------------------------------------------------- quality of life
_windows = {"main": None, "mini": None, "main_hidden": False, "mini_on": False}
_qol = {"ranked_dnd": False, "last_phase": None, "friend_status": {}}


SAFE_KEYS = ["itemsets", "spells", "runes", "overlay", "scan", "tilt_lock", "fav_itemsets", "theme_follow"]


def set_safe_mode(on):
    """Safe mode: every automation off (remembering how you had them), for troubleshooting."""
    if on and not settings.get("safe_mode"):
        settings["_safe_saved"] = {k: settings.get(k) for k in SAFE_KEYS}
        settings["_safe_saved"]["accept"] = state.get("enabled")
        for k in SAFE_KEYS:
            settings[k] = False
        with lock:
            state["enabled"] = False
        settings["safe_mode"] = True
    elif not on and settings.get("safe_mode"):
        saved = settings.get("_safe_saved") or {}
        for k in SAFE_KEYS:
            if k in saved:
                settings[k] = saved[k]
        with lock:
            state["enabled"] = bool(saved.get("accept", True))
        settings["safe_mode"] = False
    save_settings()


def cleanup_client():
    """Remove everything LoLStat added to the League client: its item sets and its rune page."""
    removed = 0
    path, me = _set_path()
    cur = lcu_call("GET", path) or {}
    sets = cur.get("itemSets", [])
    keep = [x for x in sets if not (_is_ours(x) or str(x.get("uid", "")).startswith("lolstat-fav-"))]
    if len(keep) != len(sets):
        lcu_call("PUT", path, {"accountId": cur.get("accountId", me.get("accountId")), "itemSets": keep,
                               "timestamp": int(time.time() * 1000)})
        removed += len(sets) - len(keep)
    for pg in lcu_call("GET", "/lol-perks/v1/pages") or []:
        if str(pg.get("name", "")).startswith("LoLStat") and pg.get("isEditable", True):
            lcu_call("DELETE", f"/lol-perks/v1/pages/{pg['id']}")
            removed += 1
    try:
        removed += _remove_set_files()
    except Exception:
        pass
    _itemsets.update(sig=None, written=False)
    _runes["sig"] = None
    return removed


def run_cleanup_cli():
    """LoLStat.exe --cleanup (used by the uninstaller): connect to League for up to 15 s and clean up."""
    global current_lcu
    for _ in range(15):
        creds = find_credentials()
        if creds:
            current_lcu = LCU(*creds)
            try:
                n = cleanup_client()
                print(f"Removed {n} LoLStat item sets and rune pages.")
            except Exception as e:
                print(f"Cleanup failed: {e}")
            return
        time.sleep(1)
    print("League isn't open, nothing to clean up.")


def is_dnd():
    return bool(settings.get("dnd") or _qol["ranked_dnd"])


def on_phase_change(old, new):
    if old == new:
        return
    _qol["last_phase"] = new
    if new == "Matchmaking" and tilt_locked():
        try:
            lcu_call("DELETE", "/lol-lobby/v2/lobby/matchmaking/search")
            notify_user("Tilt guard", f"Break time: queue opens again in {tilt_locked() // 60 + 1} minutes. You can end the break in LoLStat.")
        except Exception as e:
            log(f"Tilt guard: {e}")
    if new == "ReadyCheck":
        notify_user("Match found", "Accepting now" if state.get("enabled") else "Your match is ready")
    if new in ("ChampSelect", "InProgress") and settings.get("dnd_ranked"):
        try:
            q = (lcu_call("GET", "/lol-gameflow/v1/session") or {}).get("gameData", {}).get("queue", {}).get("id")
            _qol["ranked_dnd"] = q in (420, 440)
        except Exception:
            pass
    if new in ("None", "Lobby", "EndOfGame") and _qol["ranked_dnd"]:
        _qol["ranked_dnd"] = False
    if old in (None, "Client closed") and new not in (None, "Client closed") and settings.get("show_on_league"):
        show_main()                                   # League opened: bring LoLStat up


def show_main():
    w = _windows.get("main")
    if w and _windows.get("main_hidden"):
        try:
            w.show()
            _windows["main_hidden"] = False
        except Exception:
            pass


def toggle_mini():
    w = _windows.get("mini")
    if not w:
        return
    try:
        if _windows["mini_on"]:
            w.hide()
        else:
            w.show()
        _windows["mini_on"] = not _windows["mini_on"]
    except Exception:
        pass


BACKUP_FILES = ["showdown.json", "settings.json", "history.json", "lp_history.json", "journal.json", "friends_board.json",
                "phone_key.txt", "lp_log.json"]


def make_backup():
    import zipfile
    folder = os.path.join(os.path.expanduser("~"), "Documents", "LoLStat Backups")
    os.makedirs(folder, exist_ok=True)
    fp = os.path.join(folder, f"LoLStat-backup-{datetime.now().strftime('%Y-%m-%d-%H%M')}.zip")
    with zipfile.ZipFile(fp, "w", zipfile.ZIP_DEFLATED) as z:
        for name in os.listdir(DATA_DIR):
            if name in BACKUP_FILES or name.startswith("archive"):
                z.write(os.path.join(DATA_DIR, name), name)
        z.writestr("lolstat-backup.txt", f"{APP_NAME} {APP_VERSION} backup {datetime.now().isoformat()}")
    try:
        subprocess.Popen(["explorer", "/select,", fp])
    except Exception:
        pass
    return fp


def restore_backup(raw):
    import io
    import zipfile
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = z.namelist()
    if "lolstat-backup.txt" not in names:
        raise RuntimeError("that file isn't a LoLStat backup")
    n = 0
    for name in names:
        if (name in BACKUP_FILES or (name.startswith("archive") and name.endswith(".json"))) and "/" not in name and "\\" not in name:
            with open(os.path.join(DATA_DIR, name), "wb") as f:
                f.write(z.read(name))
            n += 1
    try:
        settings.update(json.load(open(SETTINGS_FILE, encoding="utf-8")))
    except Exception:
        pass
    global archive
    archive = insights.Archive(DATA_DIR, log)
    _ins["sig"] = None
    try:
        showdown.data.update(json.load(open(showdown.path, encoding="utf-8")))
    except Exception:
        pass
    return n


def write_favorite_sets():
    """Keep LoLStat's 3 item sets for every favorite champion in the client (all maps)."""
    favs = [c for c in settings.get("favorites", []) if c in mayhem.data["champions"]][:20]
    if not favs:
        return 0
    path, me = _set_path()
    cur = lcu_call("GET", path) or {}
    keep = [x for x in cur.get("itemSets", []) if not str(x.get("uid", "")).startswith("lolstat-fav-")]
    sets = []
    for champ in favs:
        c = mayhem.data["champions"][champ]
        prof = mayhem.champ_ranks.get(c["key"]) or {}
        builds = mayhem_engine_builds(champ, prof)
        for n, b in enumerate(builds):
            g = mayhem.guide_view(b, champ, "sr")
            if g:
                b["guide"] = g
                blocks = ugg_blocks([dict(x, guide=x.get("guide") or g) for x in builds], n, "sr", "", champ)
            else:
                blocks = []
                if b["boots"]:
                    blocks.append({"type": "Boots", "items": [{"id": str(b["boots"]["id"]), "count": 1}]})
                blocks.append({"type": "Build order (LoLStat)", "items": [{"id": str(i["id"]), "count": 1} for i in b["items"]]})
            sets.append({"title": set_title(champ, "sr", "", b["style"], main=(n == 0)), "uid": f"lolstat-fav-{c['key']}-{n}",
                         "type": "custom", "map": "any", "mode": "any", "associatedMaps": [],
                         "associatedChampions": [int(c["key"])], "blocks": [_full_block(x) for x in blocks], "preferredItemSlots": [],
                         "sortrank": n, "startedFrom": "blank"})
    lcu_call("PUT", path, {"accountId": cur.get("accountId", me.get("accountId")), "itemSets": keep + sets,
                           "timestamp": int(time.time() * 1000)})
    return len(sets)


def mayhem_engine_builds(champ, prof):
    import mayhem_engine as _eng
    return _eng.make_builds(champ, [], [], mayhem.data, champ_items=(prof or {}).get("items"), mode="sr")


def goal_progress():
    gt, target = settings.get("goal_type"), int(settings.get("goal_target") or 0)
    if not gt or target <= 0:
        return None
    ses = ((_profile.get("data") or {}).get("session")) or {}
    now = {"wins": ses.get("wins", 0), "games": ses.get("games", 0),
           "lp": max(list((ses.get("lp") or {}).values()) or [0])}.get(gt, 0)
    return {"type": gt, "target": target, "now": now, "done": now >= target}


# ---------------------------------------------------------------- fun: challenges, build lab, tilt guard
import fun
_tilt = {"alerted": None, "lock_until": 0}


def eng_champion_ranks(key):
    import mayhem_engine as _e
    r = _e.champion_ranks(DATA_DIR, key)
    if r:
        mayhem.champ_ranks[key] = r
    return r


def grade_of_aug(x):
    """Grade for an augment id or name."""
    if not mayhem:
        return ""
    aid = x if str(x) in mayhem.data["augments"] else next((k for k, a in mayhem.data["augments"].items() if a["name"] == x), None)
    return mayhem.grade(aid)[0] if aid else ""


def challenges_data(champ=None):
    gs = archive.list()
    ch = fun.challenge_for()
    champ = champ or (mayhem.current_champion() if mayhem else "") or ((insights.champions_list(gs) or [{}])[0].get("champion"))
    build = fun.chaos_build(champ, mayhem.data, "sr" if mayhem.mode == "sr" else "aram", ch) if champ else None
    view = lambda b: {"style": b["style"], "boots": mayhem.item_view(b["boots"]) if b["boots"] else None,
                      "items": [mayhem.item_view(i) for i in b["items"]]} if b else None
    return {"challenge": {"name": ch["name"], "desc": ch["desc"], "week": fun.week_key()},
            "champion": champ, "build": view(build), "chaos_games": fun.chaos_games(gs, mayhem.data)[:10],
            "missions": fun.missions(gs, mayhem.data, mayhem.history, grade_of_aug),
            "collection": fun.collection(mayhem.data, mayhem.history, grade_of_aug)}


def check_tilt():
    if not settings.get("tilt_guard"):
        return
    gs = archive.list()
    n = fun.tilt_check(gs, int(settings.get("tilt_losses") or 3))
    if n and gs and _tilt["alerted"] != gs[0]["id"]:
        _tilt["alerted"] = gs[0]["id"]
        mins = int(settings.get("tilt_minutes") or 10)
        if settings.get("tilt_lock"):
            _tilt["lock_until"] = time.time() + mins * 60
            notify_user("Tilt guard", f"{n} losses in a row. Queue is paused for {mins} minutes. Grab some water.")
        else:
            notify_user("Tilt guard", f"{n} losses in a row. A {mins} minute break usually helps.")


def tilt_locked():
    return max(0, int(_tilt["lock_until"] - time.time()))


# ---------------------------------------------------------------- friends leaderboard (automatic)
FRIENDS_FILE = os.path.join(DATA_DIR, "friends_board.json")
_friends = {"list": [], "cards": {}, "status": "Open League and your friends' stats load here by themselves.", "t": 0}
try:
    _friends["cards"] = json.load(open(FRIENDS_FILE, encoding="utf-8"))
except Exception:
    pass
FRIEND_REFRESH_MIN = 20          # each friend's stats are refreshed this often


def friends_loop():
    """Keeps every friend's rank and recent stats up to date, quietly, a few friends at a time."""
    import lcu_stats
    while True:
        try:
            if state.get("connected") and mayhem:
                _friends["list"] = lcu_stats.friends(lcu_call)
                prev = _qol["friend_status"]
                for f in _friends["list"]:
                    key = f.get("puuid") or f["name"]
                    if prev and prev.get(key) == "offline" and f["status"] != "offline" and settings.get("notify_friends", True):
                        notify_user("Friend online", f"{f['name'].split('#')[0]} is online")
                _qol["friend_status"] = {f.get("puuid") or f["name"]: f["status"] for f in _friends["list"]}
                if mayhem.live and settings.get("perf_mode", True):
                    time.sleep(20)
                    continue
                me = _profile.get("data") or {}
                if me.get("puuid"):        # you're on the board too
                    _friends["cards"]["__me__"] = {"name": me.get("name"), "puuid": me["puuid"], "me": True,
                        "solo": next((r for r in me.get("ranks", []) if r["type"] == "RANKED_SOLO_5x5"), None),
                        "flex": next((r for r in me.get("ranks", []) if r["type"] == "RANKED_FLEX_SR"), None),
                        "summary": me.get("summary") or {}, "streak": me.get("streak", 0),
                        "top": (me.get("champions") or [{}])[0].get("champion") if me.get("champions") else None,
                        "rank_score": -1, "updated": int(time.time())}
                    s = _friends["cards"]["__me__"]["solo"]
                    if s and s.get("tier") not in ("", "NONE"):
                        _friends["cards"]["__me__"]["rank_score"] = lcu_stats._lp_score(s)
                now = time.time()
                stale = [f for f in _friends["list"][:120]
                         if now - (_friends["cards"].get(f.get("puuid") or f["name"], {}).get("updated") or 0) > FRIEND_REFRESH_MIN * 60]
                stale.sort(key=lambda f: (f["status"] == "offline", f["name"].lower()))   # online friends first
                for i, f in enumerate(stale[:12]):
                    try:
                        card = lcu_stats.friend_card(lcu_call, mayhem.champ_name, f)
                        if card:
                            _friends["cards"][card["puuid"]] = card
                    except Exception:
                        _friends["cards"][f.get("puuid") or f["name"]] = {"name": f["name"], "puuid": f.get("puuid"),
                                                                          "error": True, "updated": int(now)}
                    time.sleep(1.2)
                done = sum(1 for f in _friends["list"] if (f.get("puuid") or f["name"]) in _friends["cards"])
                _friends["status"] = (f"{len(_friends['list'])} friends · stats for {done} · keeps updating by itself"
                                      if _friends["list"] else "No friends found in your League client.")
                try:
                    json.dump(_friends["cards"], open(FRIENDS_FILE, "w", encoding="utf-8"))
                except Exception:
                    pass
        except Exception as e:
            _friends["status"] = f"Friends: {e}"
        time.sleep(20)


def friends_board():
    rows = []
    live = {f.get("puuid") or f["name"]: f for f in _friends["list"]}
    for key, f in live.items():
        c = dict(_friends["cards"].get(key) or {"name": f["name"], "puuid": f.get("puuid"), "loading": True})
        c.update(status=f["status"], playing=f["playing"],
                 champ=mayhem.champ_name(int(f["champ_id"])) if str(f.get("champ_id") or "").isdigit() and mayhem else "",
                 queue=f.get("queue", ""))
        rows.append(c)
    me = _friends["cards"].get("__me__")
    if me:
        rows.append(dict(me, status="chat", playing=state.get("phase", "")))
    return {"friends": rows, "status": _friends["status"]}


# ---------------------------------------------------------------- champion themes
import champ_themes
_follow = {"key": None}


def owned_skins(champ):
    """Skin ids you own for a champion (from the League client), or None when the client isn't open."""
    c = mayhem.data["champions"].get(champ)
    if not c or not state.get("connected"):
        return None
    try:
        me = lcu_call("GET", "/lol-summoner/v1/current-summoner") or {}
        rows = lcu_call("GET", f"/lol-champions/v1/inventories/{me['summonerId']}/champions/{c['key']}/skins") or []
        return {int(r["id"]) for r in rows if (r.get("ownership") or {}).get("owned") or r.get("owned")}
    except Exception:
        return None


def skin_list(champ):
    c = mayhem.data["champions"].get(champ)
    if not c:
        return {"skins": [], "owned_known": False}
    sk = champ_themes.skins(mayhem.data.get("patch", ""), c["alias"], DATA_DIR)
    own = owned_skins(champ)
    rows = [dict(x, owned=(own is not None and (x["num"] == 0 or x["id"] in own))) for x in sk]
    return {"skins": rows, "owned_known": own is not None, "alias": c["alias"]}


def champ_theme(champ, num, skin_name=""):
    c = mayhem.data["champions"].get(champ)
    if not c:
        return None
    if not skin_name:
        skin_name = next((x["name"] for x in champ_themes.skins(mayhem.data.get("patch", ""), c["alias"], DATA_DIR)
                          if x["num"] == int(num)), "")
    return champ_themes.theme_for(mayhem.data.get("patch", ""), champ, c["alias"], int(num), DATA_DIR, skin_name)


def apply_champ_theme(t):
    settings["champ_theme"] = t
    settings["theme"] = "champ"
    if settings.get("overlay_look", "app") in ("app", "skin"):     # a look picked just for the overlay stays
        settings["overlay_theme"] = champ_themes.overlay_colors(t)
    save_settings()


def theme_follow_loop():
    """'Match my champion': switch the theme to the champion and skin you're playing."""
    while True:
        try:
            skin_overlay = settings.get("overlay_look") == "skin"
            if (settings.get("theme_follow") or skin_overlay) and mayhem:
                champ, num = None, 0
                cs = mayhem.champ_select
                if mayhem.live:
                    champ, num = mayhem.live.get("champion"), int(mayhem.live.get("skin") or 0)
                elif cs and cs.get("champion"):
                    champ, num = cs["champion"], int(cs.get("skin_id") or 0) % 1000
                if champ and (champ, num) != _follow["key"]:
                    _follow["key"] = (champ, num)
                    t = champ_theme(champ, num)
                    if t and settings.get("theme_follow"):
                        apply_champ_theme(t)
                        mayhem.notify(f"Theme matched to {t['name']}")
                    elif t:                                  # only the in-game overlay matches the skin
                        settings["overlay_theme"] = champ_themes.overlay_colors(t)
                        save_settings()
        except Exception as e:
            log(f"Theme: {e}")
        time.sleep(2)


# ---------------------------------------------------------------- profile + live scouting
_profile = {"data": None, "t": 0, "busy": False}
_scout = {"key": None, "players": [], "status": "Scouting starts when your game loads."}


def refresh_profile(force=False):
    import lcu_stats
    if _profile["busy"] or not state.get("connected") or not mayhem:
        return
    if mayhem.live and settings.get("perf_mode", True) and not force:
        return
    if not force and time.time() - _profile["t"] < 90:
        return
    _profile["busy"] = True
    try:
        _profile["data"] = lcu_stats.profile(lcu_call, mayhem.champ_name, DATA_DIR)
        _profile["t"] = time.time()
        archive.record_lp(_profile["data"].get("ranks"))
    except Exception as e:
        log(f"Profile: {e.__class__.__name__}: {e}")
    finally:
        _profile["busy"] = False


def run_scout(key, players):
    import lcu_stats
    _scout.update(key=key, players=[], status="Scouting players...")
    out = []
    for p in players:
        if _scout["key"] != key:
            return
        try:
            out.append(lcu_stats.scout_player(lcu_call, p, mayhem.champ_name))
        except Exception as e:
            out.append({"name": p.get("riotId"), "champion": p.get("champion"), "team": p.get("team"), "tags": [f"Unavailable"]})
        _scout["players"] = list(out)
    _scout["status"] = f"Scouted {len(out)} players at {datetime.now().strftime('%I:%M %p')}"


# ---------------------------------------------------------------- insights (local game archive)
import insights
archive = insights.Archive(DATA_DIR, log)
_ins = {"cache": None, "sig": None, "syncing": False, "last_sync": 0, "pending_coach": None}


def sync_archive(force=False):
    if _ins["syncing"] or not state.get("connected") or not mayhem:
        return
    if not force and time.time() - _ins["last_sync"] < 120:
        return
    if mayhem.live and settings.get("perf_mode", True) and not force:
        return                                   # don't load the client mid-game
    _ins["syncing"] = True
    try:
        deep = force or not _ins.get("deep_done")         # first sync of the session goes further back
        for _ in range(12 if deep else 3):
            if not archive.sync(lcu_call, mayhem.champ_name, max_new=10):
                break
        _ins["last_sync"] = time.time()
        _ins["deep_done"] = True
        check_tilt()
        gid = _ins.get("pending_coach")
        if gid and str(gid) in archive.games:
            make_coach(gid)
            _ins["pending_coach"] = None
    except Exception as e:
        log(f"Archive: {e}")
    finally:
        _ins["syncing"] = False


def make_coach(gid):
    g = archive.games.get(str(gid))
    if not g:
        return
    try:
        tl = lcu_call("GET", f"/lol-match-history/v1/game-timelines/{gid}")
    except Exception:
        tl = None
    archive.coach = insights.coach(g, archive.list(), tl)
    _ins["sig"] = None
    t = archive.coach["tips"]
    notify_user("Post-game recap ready", archive.coach["headline"])


def insights_data():
    friends = {f.get("puuid") for f in _friends["list"] if f.get("puuid")}
    sig = (archive.version, len(friends), len(archive.lp), len(archive.notes), id(archive.coach))
    if _ins["sig"] == sig and _ins["cache"]:
        out = dict(_ins["cache"])
    else:
        gs = archive.list()
        if not archive.coach and gs:
            archive.coach = insights.coach(gs[0], gs)
        cur, best = insights.streaks(gs)
        out = {"overview": insights.overview(gs), "streak": cur, "best_streak": best,
               "records": insights.records(gs), "badges": insights.badges(gs),
               "people": insights.people(gs, friends, archive.puuid), "habits": insights.habits(gs),
               "champions": insights.champions_list(gs), "highlights": insights.highlights(gs),
               "season": insights.season(gs), "lp": archive.lp[-400:], "coach": archive.coach,
               "notes": archive.notes,
               "recent": [{"id": g["id"], "when": g["when"], "champ": g["me"]["champ"], "win": g["me"]["win"],
                           "queue": g["queue"], "k": g["me"]["k"], "d": g["me"]["d"], "a": g["me"]["a"]} for g in gs[:30]]}
        _ins.update(cache=out, sig=sig)
        out = dict(out)
    out.update(count=len(archive.games), syncing=_ins["syncing"], connected=bool(state.get("connected")),
               name=(_profile.get("data") or {}).get("name", ""))
    return out


def _safe(fn):
    try:
        return fn()
    except Exception as e:
        log(f"{fn.__name__}: {e}")
        return None


def notify_user(title, text):
    """Windows notification (if the tray is running) plus the in-app notice."""
    if mayhem:
        mayhem.notify(text if not title else f"{title}: {text}")
    try:
        if not is_dnd() and _tray.get("icon") and settings.get("notify", True):
            _tray["icon"].notify(text, title or APP_NAME)
    except Exception:
        pass


_tray = {"icon": None}


def stats_loop():
    while True:
        try:
            refresh_profile()
            sync_archive()
            live = mayhem.live if mayhem else None
            if live and live.get("players"):
                key = mayhem.game_key
                if key and key != _scout["key"] and state.get("connected"):
                    threading.Thread(target=run_scout, args=(key, live["players"]), daemon=True).start()
            elif not live and _scout["key"]:
                _scout.update(key=None, status="Scouting starts when your game loads.")
        except Exception as e:
            log(f"Stats: {e}")
        time.sleep(5)


def sync_eog(phase, catch_up=False):
    if not mayhem or (phase not in ("EndOfGame", "PreEndOfGame", "WaitingForStats") and not catch_up):
        return
    try:
        eog = lcu_call("GET", "/lol-end-of-game/v1/eog-stats-block")
        if eog and catch_up and "_last_eog" not in settings:      # first run with this version: just remember it
            settings["_last_eog"] = eog.get("gameId")
            save_settings()
            return
        if eog and eog.get("gameId") != _eog["done"] and eog.get("gameId") != settings.get("_last_eog"):
            _eog["done"] = eog.get("gameId")
            settings["_last_eog"] = eog.get("gameId")          # remembered, so a restart never counts it twice
            save_settings()
            if catch_up:
                log("Found a game that ended while LoLStat was closed")
            mayhem.record_game(eog)
            threading.Thread(target=showdown_on_eog, args=(eog,), daemon=True).start()
            _ins["pending_coach"] = eog.get("gameId")
            threading.Thread(target=refresh_profile, args=(True,), daemon=True).start()
            threading.Thread(target=lambda: (time.sleep(8), sync_archive(True)), daemon=True).start()
    except Exception:
        pass


# ---------------------------------------------------------------- Party Showdown (Fun tab)
import showdown as showdown_mod
showdown = showdown_mod.Showdown(DATA_DIR, notify=lambda t: notify_user("Party Showdown", t), log=log)
_party = {"t": 0, "me": None, "names": {}}


def _riot_name(d):
    for k in ("riotIdGameName", "gameName", "summonerName", "displayName"):
        if d.get(k):
            return str(d[k])
    return ""


def _name_for(puuid):
    """Riot ID game name for a puuid (cached)."""
    if puuid in _party["names"]:
        return _party["names"][puuid]
    name = ""
    try:
        name = _riot_name(lcu_call("GET", f"/lol-summoner/v2/summoners/puuid/{puuid}") or {})
    except Exception:
        pass
    if name:
        _party["names"][puuid] = name
    return name or "Player"


def sync_party(phase):
    """Keep track of who's in your party, so their damage can be read after the game."""
    if phase not in ("Lobby", "Matchmaking", "ReadyCheck", "ChampSelect", "GameStart") or time.time() - _party["t"] < 6:
        return
    _party["t"] = time.time()
    try:
        if not _party["me"]:
            _party["me"] = (lcu_call("GET", "/lol-summoner/v1/current-summoner") or {}).get("puuid")
        lob = lcu_call("GET", "/lol-lobby/v2/lobby") or {}
        members = []
        for m in lob.get("members") or []:
            pu = m.get("puuid")
            if pu:
                nm = _riot_name(m)
                if nm:
                    _party["names"][pu] = nm
                members.append({"puuid": pu, "name": nm or _name_for(pu)})
        showdown.set_party(members, _party["me"])
    except Exception:
        pass


def _game_players(eog):
    """Every player's damage from the end-of-game screen, falling back to match history."""
    players = {}
    for t in eog.get("teams") or []:
        for p in t.get("players") or []:
            pu = p.get("puuid")
            if not pu:
                continue
            st = p.get("stats") or {}
            players[pu] = {"puuid": pu, "name": _riot_name(p) or _party["names"].get(pu, ""),
                           "champion": p.get("championName") or (mayhem.champ_name(p.get("championId")) if mayhem else "") or "",
                           "damage": int(st.get("TOTAL_DAMAGE_DEALT_TO_CHAMPIONS") or 0),
                           "k": int(st.get("CHAMPIONS_KILLED") or 0), "d": int(st.get("NUM_DEATHS") or 0), "a": int(st.get("ASSISTS") or 0)}
    if len(players) < 2 and eog.get("gameId"):     # older end-of-game screens without player IDs
        for _ in range(12):                      # match history can take a little while to show a new game
            try:
                g = lcu_call("GET", f"/lol-match-history/v1/games/{eog['gameId']}") or {}
                ids = {i["participantId"]: i.get("player") or {} for i in g.get("participantIdentities") or []}
                for part in g.get("participants") or []:
                    pl = ids.get(part.get("participantId")) or {}
                    pu, st = pl.get("puuid"), part.get("stats") or {}
                    if pu and pu not in players:
                        players[pu] = {"puuid": pu, "name": _riot_name(pl), "damage": int(st.get("totalDamageDealtToChampions") or 0),
                                       "champion": mayhem.champ_name(part.get("championId")) if mayhem else "",
                                       "k": int(st.get("kills") or 0), "d": int(st.get("deaths") or 0), "a": int(st.get("assists") or 0)}
                if players:
                    break
            except Exception:
                pass
            time.sleep(5)
    return list(players.values())


def catch_up():
    """Run when LoLStat connects: pick up anything that happened while it was closed."""
    time.sleep(3)
    try:
        sync_eog(None, catch_up=True)          # the last game's results, if League still has them
    except Exception:
        pass
    s = showdown.data.get("series")
    if not s or s.get("winner"):
        return
    try:                                        # showdown games you played while LoLStat was closed
        done = {str(r.get("game_id")) for r in s["rounds"]}
        res = lcu_call("GET", "/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex=9") or {}
        games = [g for g in ((res.get("games") or {}).get("games") or [])
                 if str(g.get("gameId")) not in done and (g.get("gameCreation") or 0) / 1000 > s.get("started", 0) - 60]
        found = 0
        for g in sorted(games, key=lambda g: g.get("gameCreation") or 0):
            full = lcu_call("GET", f"/lol-match-history/v1/games/{g['gameId']}") or {}
            ids = {i["participantId"]: i.get("player") or {} for i in full.get("participantIdentities") or []}
            players = []
            for part in full.get("participants") or []:
                pl, st = ids.get(part.get("participantId")) or {}, part.get("stats") or {}
                if pl.get("puuid"):
                    players.append({"puuid": pl["puuid"], "name": _riot_name(pl), "champion": mayhem.champ_name(part.get("championId")) if mayhem else "",
                                    "damage": int(st.get("totalDamageDealtToChampions") or 0),
                                    "k": int(st.get("kills") or 0), "d": int(st.get("deaths") or 0), "a": int(st.get("assists") or 0)})
            mine = {p["puuid"] for p in s["players"]}
            if sum(1 for p in players if p["puuid"] in mine) < 2:
                continue                                   # a game without your showdown party
            if showdown.on_game({"game_id": full.get("gameId") or g["gameId"], "length": int(full.get("gameDuration") or 0),
                                 "mode": full.get("gameMode", ""), "players": players}, auto_start=False):
                found += 1
            if (showdown.data.get("series") or {}).get("winner"):
                break
        if found:
            log(f"Party Showdown: caught up on {found} game(s) played while LoLStat was closed")
    except Exception as e:
        log(f"Party Showdown couldn't catch up: {e}")


def showdown_on_eog(eog):
    if not settings.get("showdown_auto", True) and not showdown.data.get("series"):
        return
    try:
        game = {"game_id": eog.get("gameId"), "length": int(eog.get("gameLength") or 0),
                "mode": eog.get("gameMode", ""), "players": _game_players(eog)}
        showdown.on_game(game, auto_start=settings.get("showdown_auto", True), best_of=int(settings.get("showdown_best_of", 3)))
    except Exception as e:
        log(f"Party Showdown couldn't read the game: {e}")


def showdown_action(act, body):
    try:
        if act == "sd_start":
            pl = body.get("players") or showdown.party
            showdown.start(pl, int(body.get("best_of") or settings.get("showdown_best_of", 3)))
        elif act == "sd_best_of":
            n = 5 if int(body.get("n") or 3) >= 5 else 3
            settings["showdown_best_of"] = n
            save_settings()
            msg = showdown.set_best_of(n)
            if msg and mayhem:
                mayhem.notify(msg)
        elif act == "sd_extend":
            settings["showdown_best_of"] = 5
            save_settings()
            showdown.extend()
        elif act == "sd_rematch":
            showdown.rematch()
        elif act == "sd_end":
            showdown.end()
        elif act == "sd_undo":
            showdown.undo()
        elif act == "sd_give":
            showdown.give_round(int(body.get("round", -1)), body.get("puuid"))
        elif act == "sd_count":
            showdown.count_anyway(int(body.get("round", -1)))
        elif act == "sd_remove":
            showdown.remove_player(body.get("puuid"))
        elif act == "sd_clear_history":
            with showdown.lock:
                showdown.data["history"] = []
                showdown._save()
    except Exception as e:
        if mayhem:
            mayhem.notify(f"Party Showdown: {e}")


def sync_item_sets(phase):
    if not mayhem or not settings.get("itemsets", True):
        return
    try:
        if phase in ("ChampSelect", "GameStart"):
            write_item_sets()
        elif phase in ("WaitingForStats", "PreEndOfGame", "EndOfGame") and settings.get("itemsets_cleanup", False):
            clear_item_sets()
    except Exception as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        msg = f"{e.__class__.__name__}: {getattr(e, 'code', '')} {e} {detail}".strip()
        if _itemsets.get("last_err") != msg:
            _itemsets["last_err"] = msg
            mayhem.notify(f"Couldn't save item sets: {msg[:120]}")
        _itemsets["status"] = "failed: " + msg
        _itemsets["sig"] = None
reader = None


def message_box(text):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, APP_NAME, 0x40)
    except Exception:
        print(text)


def start_tray():
    """System tray icon: open, mini mode, quick toggles, quit. Also used for Windows notifications."""
    try:
        import io
        import pystray
        from PIL import Image
    except Exception as e:
        log(f"Tray icon unavailable: {e}")
        return
    icon_img = Image.open(io.BytesIO(LOGO_PNG))

    def toggle(name):
        def f(icon, item):
            if name == "accept":
                with lock:
                    state["enabled"] = not state["enabled"]
            else:
                settings[name] = not settings.get(name)
                save_settings()
        return f

    def checked(name):
        return lambda item: bool(state.get("enabled") if name == "accept" else settings.get(name))
    menu = pystray.Menu(
        pystray.MenuItem("Open LoLStat", lambda i, it: show_main_force(), default=True),
        pystray.MenuItem("Mini mode", lambda i, it: toggle_mini()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Auto-accept", toggle("accept"), checked=checked("accept")),
        pystray.MenuItem("In-game overlay", toggle("overlay"), checked=checked("overlay")),
        pystray.MenuItem("Do not disturb", toggle("dnd"), checked=checked("dnd")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit LoLStat", lambda i, it: threading.Thread(target=quit_app, daemon=True).start()))
    icon = pystray.Icon("LoLStat", icon_img, APP_NAME, menu)
    _tray["icon"] = icon
    try:
        icon.run_detached()
    except Exception:
        threading.Thread(target=icon.run, daemon=True).start()


def quit_app():
    """Close everything: windows, tray icon, overlay, background work. Nothing is left in Task Manager."""
    try:
        save_settings()
    except Exception:
        pass
    try:
        if _tray.get("icon"):
            _tray["icon"].visible = False
            _tray["icon"].stop()
    except Exception:
        pass
    try:
        for k in ("mini", "main"):
            if _windows.get(k):
                _windows[k].destroy()
    except Exception:
        pass
    os._exit(0)


def show_main_force():
    w = _windows.get("main")
    if w:
        try:
            w.show()
            w.restore()
        except Exception:
            pass
        _windows["main_hidden"] = False


def run_windows():
    import webview
    w, h = 1320, 860
    try:   # fit the window to this screen (laptops to ultrawides), in the same units pywebview uses
        scr = webview.screens[0]
        w, h = min(w, int(scr.width * 0.92)), min(h, int(scr.height * 0.88))
    except Exception:
        pass
    start_hidden = bool(settings.get("start_hidden")) and "--show" not in sys.argv
    x = y = None
    saved = settings.get("_win") or {}
    try:   # come back where you left the window, if that spot is still on one of your screens
        if saved.get("w", 0) >= 900 and saved.get("h", 0) >= 560:
            w, h = int(saved["w"]), int(saved["h"])
        sx, sy = saved.get("x"), saved.get("y")
        if sx is not None and any(s.x - 50 <= sx <= s.x + s.width - 200 and s.y - 10 <= sy <= s.y + s.height - 100 for s in webview.screens):
            x, y = int(sx), int(sy)
    except Exception:
        pass
    main_win = webview.create_window(APP_NAME, f"{LOCAL}/app?key={KEY}", width=w, height=h, x=x, y=y,
                                     min_size=(900, 560), background_color="#0c1220", hidden=start_hidden)

    def remember(**kw):
        g = settings.setdefault("_win", {})
        g.update({k: int(v) for k, v in kw.items() if v is not None})
        if not _windows.get("_save_soon"):
            _windows["_save_soon"] = True
            threading.Timer(1.5, lambda: (_windows.update(_save_soon=False), save_settings())).start()
    try:
        main_win.events.resized += lambda width, height: remember(w=width, h=height)
        main_win.events.moved += lambda x, y: remember(x=x, y=y)
    except Exception:
        pass
    _windows["main"], _windows["main_hidden"] = main_win, start_hidden
    try:
        mini = webview.create_window(f"{APP_NAME} Mini", f"{LOCAL}/mini?key={KEY}", width=300, height=380,
                                     on_top=True, resizable=False, hidden=True, background_color="#0c1220")
        _windows["mini"] = mini
        mini.events.closing += lambda: (toggle_mini(), False)[1]   # closing the mini window just hides it
    except Exception as e:
        log(f"Mini window unavailable: {e}")

    def on_closing():
        if settings.get("close_to_tray", False) and _tray.get("icon"):
            main_win.hide()
            _windows["main_hidden"] = True
            if not settings.get("_tray_tip_shown"):
                settings["_tray_tip_shown"] = True
                save_settings()
                notify_user("", "LoLStat is still running in the tray. Right-click the icon to quit.")
            return False                       # keep running in the tray
        return True

    def on_closed():
        threading.Thread(target=quit_app, daemon=True).start()     # closing the window quits LoLStat completely
        time.sleep(3)
        os._exit(0)
    main_win.events.closing += on_closing
    main_win.events.closed += on_closed
    start_tray()
    webview.start(gui="edgechromium" if sys.platform == "win32" else None)


def run_fallback():
    """No WebView2: open the app in the browser and keep a tiny window to quit."""
    import webbrowser
    webbrowser.open(f"{LOCAL}/app?key={KEY}")
    try:
        import tkinter as tk
        root = tk.Tk()
        root.title(APP_NAME)
        root.configure(bg="#0c1220")
        tk.Label(root, text="LoLStat is running", bg="#0c1220", fg="#d9b871",
                 font=("Segoe UI", 14, "bold")).pack(padx=30, pady=(20, 6))
        tk.Button(root, text="Open dashboard", command=lambda: webbrowser.open(f"{LOCAL}/app?key={KEY}")).pack(pady=4)
        tk.Button(root, text="Quit LoLStat", command=lambda: os._exit(0)).pack(pady=(4, 20))
        root.mainloop()
    except Exception:
        while True:
            time.sleep(3600)


clips = None
updater = None

_mutex = {"h": None}


def single_instance():
    """Only one LoLStat at a time. Opening it again brings the running one to the front."""
    if sys.platform != "win32" or "--console" in sys.argv:
        return True
    try:
        import ctypes
        _mutex["h"] = ctypes.windll.kernel32.CreateMutexW(None, False, "LoLStatSingleInstance")
        if ctypes.windll.kernel32.GetLastError() != 183:        # 183 = already exists
            return True
    except Exception:
        return True
    try:
        req = urllib.request.Request(f"{LOCAL}/api/action?key={KEY}", data=json.dumps({"action": "show_window"}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=3).read()
    except Exception:
        pass
    return False


def _crash_log(kind, exc_type, exc, tb):
    try:
        import traceback
        with open(os.path.join(DATA_DIR, "crash.log"), "a", encoding="utf-8") as f:
            f.write(f"\n--- {datetime.now():%Y-%m-%d %H:%M:%S} {kind} (LoLStat {APP_VERSION})\n")
            f.write("".join(traceback.format_exception(exc_type, exc, tb)))
    except Exception:
        pass


def main():
    global mayhem
    sys.excepthook = lambda t, e, tb: _crash_log("crash", t, e, tb)
    threading.excepthook = lambda a: _crash_log(f"thread {getattr(a.thread, 'name', '')}", a.exc_type, a.exc_value, a.exc_traceback)
    if "--cleanup" in sys.argv:
        run_cleanup_cli()
        return
    if "--safe" in sys.argv:
        set_safe_mode(True)
    try:   # crisp windows and matching screen coordinates on high-DPI displays
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    if not single_instance():
        return
    try:   # full speed while minimized or in the tray, so cards are read the instant they appear
        import screen_reader as _boost
        _boost.boost_process()
    except Exception:
        pass
    try:
        server = ThreadingHTTPServer(("0.0.0.0", WEB_PORT), Handler)
    except OSError:
        message_box("LoLStat is already running. Check your taskbar.")
        return
    from mayhem_service import MayhemService
    mayhem = MayhemService(DATA_DIR, log, settings)
    global updater
    try:
        import updater as updater_mod
        updater = updater_mod.Updater(APP_VERSION, settings, log, lambda t: notify_user("LoLStat update", t),
                                      lambda: threading.Thread(target=quit_app, daemon=True).start())
        if "--test" not in sys.argv:
            updater.start()
    except Exception as e:
        log(f"Updates unavailable: {e}")
    global clips
    try:
        import clips as clips_mod
        import screen_reader as _sr
        clips = clips_mod.ClipRecorder(DATA_DIR, settings, log, lambda t: notify_user("LoLStat clips", t),
                                       window=lambda: _sr.league_window())
        mayhem.on_snapshot = clips.on_snapshot
        mayhem.save_clip = lambda: clips.save_last(30)
    except Exception as e:
        log(f"Clips unavailable: {e}")
    mayhem.start()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=ui_pump, daemon=True).start()
    threading.Thread(target=stats_loop, daemon=True).start()
    threading.Thread(target=theme_follow_loop, daemon=True).start()
    threading.Thread(target=friends_loop, daemon=True).start()
    global reader
    mayhem.lcu_call = lcu_call
    try:
        from screen_reader import ScreenReader
        reader = ScreenReader(mayhem, settings, log, SNAP_DIR)
        reader.start()
    except Exception as e:
        log(f"Screen reader didn't start: {e}")
    try:
        from ingame_overlay import InGameLayer
        InGameLayer(mayhem, settings, save_settings,
                    (reader.snapshot if reader else (lambda: None)),
                    LOGO_64, os.path.join(DATA_DIR, "icons"), log).start()
    except Exception as e:
        log(f"In-game overlay didn't start: {e}")
    log(f"Phone remote: {PHONE_URL}")

    if "--console" in sys.argv:
        print(f"Running. App: {LOCAL}/app?key={KEY}   Phone: {PHONE_URL}")
        while True:
            time.sleep(3600)
    try:
        run_windows()
    except Exception as e:
        log(f"App window unavailable ({e}); opening in your browser.")
        run_fallback()


if __name__ == "__main__":
    main()
