"""Updates: check GitHub for a newer LoLStat, download it, verify it and install it quietly, then reopen.

The installer runs silently (no screens) after LoLStat closes, and reopens LoLStat on the new version.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

REPO = "Dougieee3D/LolStat"            # where releases are published
API = f"https://api.github.com/repos/{REPO}/releases/latest"
CHECK_EVERY = 6 * 3600
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:3]) or (0,)


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "LoLStat-updater", "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


class Updater:
    def __init__(self, version, settings, log, notify, quit_app):
        self.version, self.settings, self.log, self.notify, self.quit_app = version, settings, log, notify, quit_app
        self.state = {"status": "idle", "latest": "", "notes": "", "pct": 0, "error": "", "checked": 0}
        self.release = None
        self.lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        time.sleep(8)                               # let the app open first
        while True:
            if self.settings.get("update_check", True) and self.state["status"] in ("idle", "latest", "error", "available"):
                self.check()
            time.sleep(CHECK_EVERY)

    def check(self):
        with self.lock:
            if self.state["status"] in ("downloading", "installing"):
                return self.view()
            self.state.update(status="checking", error="")
        try:
            with _get(API) as r:
                rel = json.load(r)
            latest = str(rel.get("tag_name", "")).lstrip("v")
            assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets") or []}
            notes = (rel.get("body") or "").split("\n---")[0].strip()
            self.state["checked"] = time.time()
            if latest and version_tuple(latest) > version_tuple(self.version) and "LoLStat-Setup.exe" in assets:
                self.release = {"version": latest, "setup": assets["LoLStat-Setup.exe"], "sums": assets.get("SHA256SUMS.txt")}
                self.state.update(status="available", latest=latest, notes=notes)
                if self.settings.get("update_auto"):
                    self.install()
                elif self.settings.get("update_seen") != latest:
                    self.notify(f"LoLStat {latest} is ready. Open LoLStat to update.")
            else:
                self.state.update(status="latest", latest=latest or self.version, notes="")
        except Exception as e:
            self.state.update(status="error", error=f"Couldn't check for updates ({e.__class__.__name__})")
        return self.view()

    def install(self):
        """Download, verify, then close LoLStat and let the installer update it quietly and reopen it."""
        with self.lock:
            if self.state["status"] in ("downloading", "installing") or not self.release:
                return
            self.state.update(status="downloading", pct=0, error="")
        threading.Thread(target=self._install, daemon=True).start()

    def _install(self):
        rel = self.release
        try:
            path = os.path.join(tempfile.gettempdir(), f"LoLStat-Setup-{rel['version']}.exe")
            h = hashlib.sha256()
            with _get(rel["setup"], 60) as r, open(path, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if total:
                        self.state["pct"] = int(done * 100 / total)
            if rel.get("sums"):
                with _get(rel["sums"]) as r:
                    want = r.read().decode("utf-8", "replace").split()[0].lower()
                if want != h.hexdigest():
                    os.remove(path)
                    raise RuntimeError("the download didn't match its checksum")
            self.state.update(status="installing", pct=100)
            self.log(f"Installing LoLStat {rel['version']}…")
            if sys.platform == "win32":
                # wait for LoLStat to close, then update quietly; the installer reopens LoLStat when it's done
                cmd = (f'cmd /c ping -n 3 127.0.0.1 >nul & "{path}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART '
                       f'/CLOSEAPPLICATIONS /RESTARTAPPLICATIONS')
                subprocess.Popen(cmd, creationflags=NO_WINDOW | 0x00000008, close_fds=True)   # DETACHED_PROCESS
                time.sleep(0.5)
                self.quit_app()
        except Exception as e:
            self.state.update(status="error", error=f"Update failed: {e}")
            self.log(f"Update failed: {e}")

    def later(self):
        self.settings["update_seen"] = self.state.get("latest")
        if self.state["status"] == "available":
            self.state["status"] = "later"

    def view(self):
        v = dict(self.state)
        v["current"] = self.version
        return v
