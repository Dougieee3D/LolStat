"""LoLStat clips: automatic highlight recording.

While you're in a game, the screen is recorded into a short rolling buffer (2-second pieces, hardware
encoded). League's live game data says when kills, multikills, deaths, aces and objectives happen; the
seconds around them are cut from the buffer into a video (with game sound) in Videos\\LoLStat.
Back-to-back moments merge into one clip. Nothing is uploaded anywhere.
"""
import collections
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave
from datetime import datetime

SEG = 2                     # seconds per buffer piece
BUFFER_SECONDS = 150        # how much is kept while nothing happens
MAX_CLIP = 90               # longest automatic clip (merged moments)
MERGE_GAP = 4               # moments this close together become one clip

KINDS = {   # kind: (setting, default on, label)
    "kill": ("clip_kills", True, "Kill"),
    "multikill": ("clip_multikills", True, "Multikill"),
    "death": ("clip_deaths", False, "Death"),
    "assist": ("clip_assists", False, "Assist"),
    "objective": ("clip_objectives", True, "Objective"),
    "ace": ("clip_aces", True, "Ace"),
    "end": ("clip_game_end", True, "Game end"),
}
MULTI = {2: "Double kill", 3: "Triple kill", 4: "Quadra kill", 5: "Penta kill"}
RANK = ["Penta kill", "Quadra kill", "Triple kill", "Double kill", "Ace", "Baron steal", "Dragon steal",
        "Herald steal", "Victory", "Defeat", "Kill", "Baron", "Dragon", "Rift Herald", "Turret", "Death", "Assist", "Saved clip"]
QUALITY = {   # setting: (height, fps, Mbps)
    "smooth": (720, 30, 6),
    "high": (1080, 60, 14),
    "max": (0, 60, 24),        # 0 = the game's own resolution
}
ENCODERS = ["h264_nvenc", "h264_amf", "h264_qsv", "h264_mf", "libx264", "mpeg4"]
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def find_ffmpeg():
    """ffmpeg.exe ships next to LoLStat.exe (or inside the bundle); PATH as a last resort."""
    names = ["ffmpeg.exe", "ffmpeg"] if sys.platform == "win32" else ["ffmpeg"]
    roots = [os.path.dirname(sys.executable), getattr(sys, "_MEIPASS", ""), os.path.dirname(os.path.abspath(__file__))]
    for r in roots:
        for n in names:
            p = os.path.join(r, n)
            if r and os.path.isfile(p):
                return p
    return shutil.which("ffmpeg")


def _run(args, timeout=30):
    return subprocess.run(args, capture_output=True, timeout=timeout, creationflags=NO_WINDOW)


class AudioLoop:
    """Game sound (what you hear) kept in memory for the last few minutes, via WASAPI loopback."""

    def __init__(self, seconds, log):
        self.seconds, self.log = seconds, log
        self.chunks = collections.deque()       # (wall time at chunk start, bytes)
        self.rate, self.channels, self.width = 48000, 2, 2
        self.stream = self.pa = None
        self.lock = threading.Lock()
        self.full = None                        # wave writer when the whole game is kept

    def start(self):
        try:
            import pyaudiowpatch as pyaudio
        except Exception:
            return False
        try:
            self.pa = pyaudio.PyAudio()
            dev = self.pa.get_default_wasapi_loopback()
            self.rate, self.channels = int(dev["defaultSampleRate"]), max(1, min(2, int(dev["maxInputChannels"])))
            self.stream = self.pa.open(format=pyaudio.paInt16, channels=self.channels, rate=self.rate, input=True,
                                       input_device_index=dev["index"], frames_per_buffer=1024,
                                       stream_callback=self._cb)
            self.stream.start_stream()
            return True
        except Exception as e:
            self.log(f"Clips: game sound unavailable ({e})")
            self.stop()
            return False

    def _cb(self, data, frames, info, status):
        self.push(data, time.time() - frames / self.rate)
        try:
            import pyaudiowpatch as pyaudio
            return (None, pyaudio.paContinue)
        except Exception:
            return (None, 0)

    def push(self, data, t):
        with self.lock:
            self.chunks.append((t, data))
            while self.chunks and self.chunks[0][0] < time.time() - self.seconds:
                self.chunks.popleft()
            if self.full:
                self.full.writeframes(data)

    def keep_all(self, path):
        with self.lock:
            self.full = wave.open(path, "wb")
            self.full.setnchannels(self.channels)
            self.full.setsampwidth(self.width)
            self.full.setframerate(self.rate)
            self.full_start = time.time()

    def stop_all(self):
        with self.lock:
            if self.full:
                self.full.close()
                self.full = None

    def write(self, path, t0, t1):
        """Sound from wall time t0 to t1 as a WAV (silence where nothing was captured)."""
        frame = self.channels * self.width
        n = max(0, int((t1 - t0) * self.rate))
        out = bytearray(n * frame)
        with self.lock:
            chunks = list(self.chunks)
        for t, data in chunks:
            start = int(round((t - t0) * self.rate))
            frames = len(data) // frame
            a, b = max(0, start), min(n, start + frames)
            if a < b:
                out[a * frame:b * frame] = data[(a - start) * frame:(b - start) * frame]
        with wave.open(path, "wb") as w:
            w.setnchannels(self.channels)
            w.setsampwidth(self.width)
            w.setframerate(self.rate)
            w.writeframes(bytes(out))
        return any(out)

    def stop(self):
        try:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
            if self.pa:
                self.pa.terminate()
        except Exception:
            pass
        self.stream = self.pa = None
        self.stop_all()


class ClipRecorder:
    def __init__(self, data_dir, settings, log, notify, window=None):
        self.settings, self.log, self.notify = settings, log, notify
        self.window = window or (lambda: None)  # -> (hwnd, (l, t, r, b)) of the League game window
        self.ffmpeg = find_ffmpeg()
        self.buf = os.path.join(tempfile.gettempdir(), "LoLStat-clip-buffer")
        self.proc = None
        self.segments = []                      # [path, wall start, wall end]
        self.t0 = None
        self.queue = []                         # clips waiting for their last seconds to be recorded
        self.pending = None
        self.game = None
        self.seen = set()
        self.status = "Off"
        self.error = ""
        self.saved = 0
        self.lock = threading.RLock()
        self.audio = AudioLoop(BUFFER_SECONDS + 30, log)
        self.input_override = None              # tests: replace the screen capture input
        threading.Thread(target=self._loop, daemon=True).start()

    # ------------------------------------------------------------------ settings
    def on(self):
        return bool(self.settings.get("clips_on")) and bool(self.ffmpeg)

    def folder(self):
        return self.settings.get("clips_dir") or os.path.join(os.path.expanduser("~"), "Videos", "LoLStat")

    def quality(self):
        return QUALITY.get(self.settings.get("clip_quality", "high"), QUALITY["high"])

    # ------------------------------------------------------------------ encoder
    def encoder(self):
        """Pick the fastest video encoder that works on this PC (graphics card first). Remembered."""
        enc = self.settings.get("clip_encoder")
        if enc:
            return enc
        for e in ENCODERS:
            try:
                r = _run([self.ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                          "color=c=black:s=1280x720:r=30", "-t", "0.5", "-c:v", e, "-f", "null", "-"], 20)
                if r.returncode == 0:
                    self.settings["clip_encoder"] = e
                    self.log(f"Clips: using the {e} video encoder")
                    return e
            except Exception:
                continue
        return "mpeg4"

    def _enc_args(self, enc, fps, mbps):
        b = [f"-b:v", f"{mbps}M", "-maxrate", f"{int(mbps * 1.5)}M", "-bufsize", f"{mbps * 2}M", "-g", str(fps)]
        extra = {"h264_nvenc": ["-preset", "p4", "-rc", "vbr"],
                 "h264_amf": ["-quality", "speed", "-rc", "vbr_peak"],
                 "h264_qsv": ["-preset", "veryfast"],
                 "h264_mf": ["-hw_encoding", "1"],
                 "libx264": ["-preset", "veryfast", "-tune", "zerolatency"],
                 "mpeg4": ["-q:v", "4"]}.get(enc, [])
        return ["-c:v", enc] + extra + b + ["-pix_fmt", "yuv420p"]

    def _capture_args(self, rect, fps, height):
        if self.input_override:
            return self.input_override(rect, fps, height)
        l, t, r, b = rect
        w, h = (r - l) // 2 * 2, (b - t) // 2 * 2
        scale = f",scale=-2:{height}:flags=bilinear" if height and h > height else ""
        mon, ox, oy = self._monitor(rect)
        # Desktop Duplication (works with games); GDI as the fallback
        dda = (f"ddagrab=output_idx={mon}:framerate={fps}:offset_x={ox}:offset_y={oy}:video_size={w}x{h}:draw_mouse=1,"
               f"hwdownload,format=bgra{scale}")
        if self.settings.get("clip_capture") == "gdi":
            return ["-f", "gdigrab", "-framerate", str(fps), "-offset_x", str(l), "-offset_y", str(t),
                    "-video_size", f"{w}x{h}", "-draw_mouse", "1", "-i", "desktop"] + (["-vf", scale[1:]] if scale else [])
        return ["-f", "lavfi", "-i", dda]

    @staticmethod
    def _monitor(rect):
        """Which screen the game is on, and where the game sits on it."""
        try:
            import ctypes
            from ctypes import wintypes
            mons = []
            cb = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

            def add(h, dc, r, p):
                mons.append((r.contents.left, r.contents.top, r.contents.right, r.contents.bottom))
                return 1
            ctypes.windll.user32.EnumDisplayMonitors(None, None, cb(add), 0)
            cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
            # DXGI lists the primary screen first
            mons.sort(key=lambda m: (m[0] != 0 or m[1] != 0))
            for i, m in enumerate(mons):
                if m[0] <= cx < m[2] and m[1] <= cy < m[3]:
                    return i, max(0, rect[0] - m[0]), max(0, rect[1] - m[1])
        except Exception:
            pass
        return 0, max(0, rect[0]), max(0, rect[1])

    # ------------------------------------------------------------------ recording
    def start(self, rect):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                return True
            shutil.rmtree(self.buf, ignore_errors=True)
            os.makedirs(self.buf, exist_ok=True)
            h, fps, mbps = self.quality()
            enc = self.encoder()
            if enc == "mpeg4":
                fps = min(fps, 30)
            cmd = ([self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y"] + self._capture_args(rect, fps, h)
                   + self._enc_args(enc, fps, mbps) + ["-an", "-f", "segment", "-segment_time", str(SEG),
                   "-segment_format", "mpegts", "-reset_timestamps", "1",
                   "-segment_list", os.path.join(self.buf, "list.csv"), "-segment_list_type", "csv",
                   "-segment_list_flags", "+live", os.path.join(self.buf, "seg_%06d.ts")])
            try:
                self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                             stderr=subprocess.PIPE, creationflags=NO_WINDOW)
            except Exception as e:
                self.error = f"couldn't start recording: {e}"
                self.status = "Error"
                return False
            self.segments, self.t0, self._csv_pos = [], None, 0
            self._started = time.time()
            if self.settings.get("clip_sound", True):
                self.audio.start()
            self.status = "Recording"
            self.error = ""
            threading.Thread(target=self._watch_proc, args=(self.proc, cmd), daemon=True).start()
            return True

    def _watch_proc(self, proc, cmd):
        err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
        proc.wait()
        if proc is self.proc and self.game and time.time() - self._started < 8 and proc.returncode not in (0, 255):
            # the screen capture didn't work on this PC: try the other capture method once
            self.log(f"Clips: recording stopped ({err.strip()[:200]})")
            if self.settings.get("clip_capture") != "gdi":
                self.settings["clip_capture"] = "gdi"
                self.proc = None
                _, rect = self.window() or (None, None)
                if rect:
                    self.start(rect)
                    return
            self.error = "Recording doesn't work on this PC: " + (err.strip().splitlines() or ["unknown error"])[-1][:160]
            self.status = "Error"

    def stop(self):
        with self.lock:
            p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                p.stdin.write(b"q")
                p.stdin.flush()
                p.wait(5)
            except Exception:
                p.kill()
        self.audio.stop()
        self.status = "Ready" if self.on() else "Off"

    def _read_segments(self):
        """New pieces from the segment list, with the wall-clock time each one covers."""
        p = os.path.join(self.buf, "list.csv")
        try:
            with open(p, encoding="utf-8") as f:
                f.seek(self._csv_pos)
                data = f.read()
        except OSError:
            return
        if not data.endswith("\n"):
            data = data[:data.rfind("\n") + 1]
        self._csv_pos += len(data.encode("utf-8"))
        for line in data.splitlines():
            parts = line.split(",")
            if len(parts) < 3:
                continue
            name, a, b = parts[0], float(parts[1]), float(parts[2])
            path = os.path.join(self.buf, name)
            try:
                written = os.path.getmtime(path)
            except OSError:
                written = time.time()
            # first piece: the recording's start time on the wall clock; later pieces keep the same base
            if self.t0 is None:
                self.t0 = written - b
            else:
                self.t0 = min(self.t0, written - b) if written - b > self.t0 - 1 else self.t0
            self.segments.append([path, self.t0 + a, self.t0 + b])

    def _prune(self):
        if self.settings.get("clip_full_game"):
            return
        keep_from = time.time() - BUFFER_SECONDS
        for c in self.queue + ([self.pending] if self.pending else []):
            keep_from = min(keep_from, c["start"] - SEG)
        old = [s for s in self.segments if s[2] < keep_from]
        for s in old:
            try:
                os.remove(s[0])
            except OSError:
                pass
        self.segments = [s for s in self.segments if s[2] >= keep_from]

    # ------------------------------------------------------------------ what happened in the game
    def on_snapshot(self, snap):
        """Called with every live game update (or None when no game is running)."""
        if not self.on():
            if self.proc:
                self.stop()
            self.status = "Off" if not self.ffmpeg else ("Ready" if self.settings.get("clips_on") else "Off")
            return
        if not snap:
            if self.game:
                self._game_over()
            self.status = "Ready"
            return
        now = time.time()
        gd = snap.get("gameData") or {}
        gtime = float(gd.get("gameTime") or 0)
        ap = snap.get("activePlayer") or {}
        me = {str(ap.get(k, "")).split("#")[0].lower() for k in ("riotIdGameName", "riotId", "summonerName") if ap.get(k)}
        champ = next((p.get("championName") for p in snap.get("allPlayers") or []
                      if str(p.get("riotIdGameName") or p.get("riotId") or p.get("summonerName") or "").split("#")[0].lower() in me), "")
        team = next((p.get("team") for p in snap.get("allPlayers") or []
                     if str(p.get("riotIdGameName") or p.get("riotId") or p.get("summonerName") or "").split("#")[0].lower() in me), "")
        events = (snap.get("events") or {}).get("Events") or []
        if not self.game:
            got = self.window()
            if not got or not got[1]:
                return
            stamp = datetime.now()
            self.game = {"champion": champ or "Game", "started": now - gtime, "team": team,
                         "folder": os.path.join(self.folder(), f"{stamp:%Y-%m-%d %H-%M} {champ or 'Game'}"), "count": 0}
            self.seen = {e.get("EventID") for e in events}     # things that happened before recording started
            self.start(got[1])
        if self.proc is None:
            return
        for e in events:
            eid = e.get("EventID")
            if eid in self.seen:
                continue
            self.seen.add(eid)
            for kind, label in self._classify(e, me, team):
                if self.settings.get(KINDS[kind][0], KINDS[kind][1]):
                    t = now - max(0.0, gtime - float(e.get("EventTime") or gtime))
                    self.moment(t, label, kind)

    @staticmethod
    def _classify(e, me, team):
        name = e.get("EventName", "")
        who = lambda k: str(e.get(k, "")).split("#")[0].lower() in me
        out = []
        if name == "ChampionKill":
            if who("KillerName"):
                out.append(("kill", "Kill"))
            elif who("VictimName"):
                out.append(("death", "Death"))
            elif any(str(a).split("#")[0].lower() in me for a in e.get("Assisters") or []):
                out.append(("assist", "Assist"))
        elif name == "Multikill" and who("KillerName"):
            out.append(("multikill", MULTI.get(int(e.get("KillStreak") or 2), "Multikill")))
        elif name == "Ace" and (str(e.get("AcingTeam", "")) == team or who("Acer")):
            out.append(("ace", "Ace"))
        elif name in ("BaronKill", "DragonKill", "HeraldKill") and (who("KillerName") or str(e.get("Stolen")) == "True"):
            base = {"BaronKill": "Baron", "DragonKill": "Dragon", "HeraldKill": "Rift Herald"}[name]
            stolen = str(e.get("Stolen")) == "True" and who("KillerName")
            if who("KillerName"):
                out.append(("objective", (base.replace("Rift ", "") + " steal") if stolen else base))
        elif name == "TurretKilled" and who("KillerName"):
            out.append(("objective", "Turret"))
        elif name == "GameEnd":
            out.append(("end", "Victory" if str(e.get("Result", "")).lower().startswith("win") else "Defeat"))
        return out

    def moment(self, t, label, kind="kill", before=None, after=None):
        """Something worth keeping happened at wall time t."""
        b = float(before if before is not None else self.settings.get("clip_before", 12))
        a = float(after if after is not None else self.settings.get("clip_after", 5))
        if kind == "end":
            b, a = 8, 4
        with self.lock:
            p = self.pending
            if p and t - b <= p["end"] + MERGE_GAP and max(p["end"], t + a) - p["start"] <= MAX_CLIP:
                p["end"] = max(p["end"], t + a)
                p["labels"].append(label)
                p["kinds"].add(kind)
            else:
                if p:
                    self.queue.append(p)
                self.pending = {"start": t - b, "end": t + a, "labels": [label], "kinds": {kind}}

    def save_last(self, seconds=30):
        """The 'save the last 30 seconds' hotkey."""
        if not self.proc:
            self.notify("Clips: not recording right now. Turn on clips and be in a game.")
            return
        now = time.time()
        with self.lock:
            self.queue.append({"start": now - seconds, "end": now, "labels": ["Saved clip"], "kinds": {"manual"}})
        self.notify(f"Saving the last {int(seconds)} seconds…")

    # ------------------------------------------------------------------ cutting clips
    def _loop(self):
        while True:
            try:
                if self.proc:
                    self._read_segments()
                    now = time.time()
                    with self.lock:
                        if self.pending and now > self.pending["end"] + MERGE_GAP:
                            self.queue.append(self.pending)
                            self.pending = None
                        ready = [c for c in self.queue if self.segments and self.segments[-1][2] >= c["end"]]
                        self.queue = [c for c in self.queue if c not in ready]
                    for c in ready:
                        self._cut(c)
                    self._prune()
            except Exception as e:
                self.log(f"Clips: {e}")
            time.sleep(0.4)

    @staticmethod
    def _title(labels):
        kills = labels.count("Kill")
        best = min(labels, key=lambda l: RANK.index(l) if l in RANK else 99)
        if best == "Kill" and kills > 1:
            return f"{kills} kills"
        return best

    def _cut(self, c, name=None, folder=None):
        segs = [s for s in self.segments if s[2] > c["start"] and s[1] < c["end"]]
        if not segs or not self.game:
            return None
        folder = folder or self.game["folder"]
        os.makedirs(folder, exist_ok=True)
        title = self._title(c["labels"])
        gt = max(0, c["end"] - (self.settings.get("clip_after", 5)) - self.game["started"])
        base = name or f"{int(gt // 60):02d}-{int(gt % 60):02d} {title}"
        out = os.path.join(folder, re.sub(r'[<>:"/\\|?*]', "", base) + ".mp4")
        n = 2
        while os.path.exists(out):
            out = os.path.join(folder, f"{base} ({n}).mp4")
            n += 1
        lst = os.path.join(self.buf, f"cut_{int(time.time() * 1000)}.txt")
        with open(lst, "w", encoding="utf-8") as f:
            for s in segs:
                f.write("file '" + s[0].replace("\\", "/").replace("'", "'\\''") + "'\n")
        t0, t1 = segs[0][1], segs[-1][2]
        wav = lst[:-4] + ".wav"
        has_sound = self.audio.stream is not None or self.audio.chunks
        if has_sound:
            has_sound = self.audio.write(wav, t0, t1) or True
        cmd = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst]
        if has_sound:
            cmd += ["-i", wav, "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "160k", "-shortest"]
        cmd += ["-c:v", "copy", "-movflags", "+faststart", out]
        r = _run(cmd, 120)
        for p in (lst, wav):
            try:
                os.remove(p)
            except OSError:
                pass
        if r.returncode != 0 or not os.path.exists(out):
            self.log(f"Clips: couldn't save a clip ({r.stderr.decode('utf-8', 'replace')[-200:]})")
            return None
        thumb = out[:-4] + ".jpg"
        _run([self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(0.0, (t1 - t0) - (self.settings.get('clip_after', 5)) - 1):.1f}",
              "-i", out, "-frames:v", "1", "-vf", "scale=480:-2", thumb], 30)
        info = {"title": title, "moments": c["labels"], "champion": self.game["champion"], "game_time": round(gt),
                "seconds": round(t1 - t0, 1), "created": time.time(), "file": os.path.basename(out),
                "thumb": os.path.basename(thumb) if os.path.exists(thumb) else "", "manual": "manual" in c["kinds"]}
        with open(out[:-4] + ".json", "w", encoding="utf-8") as f:
            json.dump(info, f)
        self.saved += 1
        self.game["count"] += 1
        if "manual" in c["kinds"] or not self.settings.get("clip_quiet"):
            self.notify(f"Clip saved: {title}")
        self._limit_storage()
        return out

    def _game_over(self):
        """Game ended: finish the clips still waiting, keep the full game if asked, stop recording."""
        g = self.game
        end = time.time() + 1
        deadline = time.time() + 12
        while time.time() < deadline and (self.pending or self.queue) and self.proc:
            if self.segments and self.segments[-1][2] >= min([c["end"] for c in self.queue] + ([self.pending["end"]] if self.pending else []) or [end]):
                break
            time.sleep(0.3)
        with self.lock:
            if self.pending:
                self.queue.append(self.pending)
                self.pending = None
            waiting, self.queue = self.queue, []
        self.stop()
        self._read_segments()
        for c in waiting:
            self._cut(c)
        if self.settings.get("clip_full_game") and self.segments:
            self._cut({"start": self.segments[0][1], "end": self.segments[-1][2], "labels": ["Full game"], "kinds": {"full"}},
                      name="Full game")
        if g and g["count"]:
            self.notify(f"{g['count']} clip{'s' if g['count'] != 1 else ''} saved from this game. Open them in Clips.")
        self.game = None
        shutil.rmtree(self.buf, ignore_errors=True)

    def _limit_storage(self):
        """Keep the clips folder under the size limit by removing the oldest automatic clips."""
        try:
            limit = float(self.settings.get("clip_max_gb", 20)) * 1024 ** 3
            files = []
            for d, _, fs in os.walk(self.folder()):
                for f in fs:
                    if f.endswith(".mp4"):
                        p = os.path.join(d, f)
                        files.append((os.path.getmtime(p), os.path.getsize(p), p))
            total = sum(s for _, s, _ in files)
            for _, size, p in sorted(files):
                if total <= limit:
                    break
                for ext in (".mp4", ".jpg", ".json"):
                    try:
                        os.remove(p[:-4] + ext)
                    except OSError:
                        pass
                total -= size
        except Exception:
            pass

    # ------------------------------------------------------------------ for the app
    def list(self, limit=300):
        out = []
        root = self.folder()
        for d, _, fs in os.walk(root):
            for f in fs:
                if f.endswith(".json"):
                    try:
                        with open(os.path.join(d, f), encoding="utf-8") as fh:
                            c = json.load(fh)
                    except Exception:
                        continue
                    if not os.path.exists(os.path.join(d, c.get("file", ""))):
                        continue
                    rel = os.path.relpath(os.path.join(d, c["file"]), root).replace("\\", "/")
                    c.update(path=rel, game=os.path.basename(d),
                             thumb=(os.path.relpath(os.path.join(d, c["thumb"]), root).replace("\\", "/") if c.get("thumb") else ""),
                             mb=round(os.path.getsize(os.path.join(d, c["file"])) / 1e6, 1))
                    out.append(c)
        out.sort(key=lambda c: -c.get("created", 0))
        return out[:limit]

    def resolve(self, rel):
        """A clip path from the app, only ever inside the clips folder."""
        root = os.path.realpath(self.folder())
        p = os.path.realpath(os.path.join(root, rel))
        return p if p.startswith(root + os.sep) and os.path.isfile(p) else None

    def delete(self, rel):
        p = self.resolve(rel)
        if not p:
            return False
        for ext in (".mp4", ".jpg", ".json"):
            try:
                os.remove(p[:-4] + ext)
            except OSError:
                pass
        try:
            os.rmdir(os.path.dirname(p))       # empty game folder
        except OSError:
            pass
        return True

    def view(self):
        return {"on": bool(self.settings.get("clips_on")), "available": bool(self.ffmpeg), "status": self.status,
                "error": self.error, "recording": bool(self.proc), "encoder": self.settings.get("clip_encoder", ""),
                "this_game": (self.game or {}).get("count", 0), "folder": self.folder(),
                "sound": self.audio.stream is not None}
