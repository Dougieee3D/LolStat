"""
LoLStat in-game layer (Windows): native see-through windows drawn over League.

  - Grade letters that float right above each augment card (clicks pass through them)
  - A small LoLStat button you can drag anywhere; click it (or Ctrl+Shift+L) to open or
    close a sleek panel with your builds, augments and card grades
  - Ctrl+Shift+S saves a snapshot of what LoLStat sees (for fixing card reading)

None of these windows take focus from the game, and all are hidden from screen
capture so LoLStat never reads its own text.
"""

import base64
import json
import os
import sys
import threading
import time
import urllib.request

KEY = "#010203"            # transparent color key
GLASS, EDGE = "#111318", "#2b2f3a"
TEXT, MUTED, DIM = "#ece6d6", "#8e96ab", "#5f6880"
GOLD, TEAL = "#d9b871", "#19c8b4"
GRADE = {"S+": "#f6d27a", "S": "#ff9a3c", "A": "#3ad08f", "B": "#4aa3ff", "C": "#8e96ab", "D": "#ff5d6c"}
TIER = {"Silver": "#c3cbd6", "Gold": "#e7c35f", "Prismatic": "#c98cff"}
PANEL_W = 300            # design width; shown at panel_size (drag the corner or Ctrl+wheel to resize)
STYLES = ["Max", "Overdrive", "Off-meta"]


def _style(top, click_through=False):
    """Never steal focus; optionally let clicks pass through; keep out of screen capture."""
    try:
        import ctypes
        u = ctypes.windll.user32
        hwnd = int(top.wm_frame(), 16)
        ex = u.GetWindowLongW(hwnd, -20)
        ex |= 0x08000000 | 0x80 | 0x8          # NOACTIVATE | TOOLWINDOW | TOPMOST
        if click_through:
            ex |= 0x80000 | 0x20               # LAYERED | TRANSPARENT
        u.SetWindowLongW(hwnd, -20, ex)
        u.SetWindowDisplayAffinity(hwnd, 0x11)
    except Exception:
        pass


def system_scale():
    """Windows display scaling (1.0 at 100%, 1.5 at 150%...)."""
    try:
        import ctypes
        return max(1.0, ctypes.windll.user32.GetDpiForSystem() / 96)
    except Exception:
        return 1.0


def monitor_area(x, y):
    """Work area (left, top, right, bottom) of the monitor containing a point."""
    try:
        import ctypes
        from ctypes import wintypes

        class MI(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        u = ctypes.windll.user32
        mon = u.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 2)   # nearest monitor
        mi = MI()
        mi.cbSize = ctypes.sizeof(MI)
        u.GetMonitorInfoW(mon, ctypes.byref(mi))
        r = mi.rcWork
        return r.left, r.top, r.right, r.bottom
    except Exception:
        return 0, 0, 1920, 1080


class Scaled:
    """Canvas wrapper: draw in 'design pixels', shown at k times size, fonts in exact pixels."""

    def __init__(self, cv, k):
        self.cv, self.k = cv, k

    def _f(self, font):
        fam, size, *rest = font
        return (fam, -max(6, round(size * 4 / 3 * self.k)), *rest)

    def _c(self, args):
        return [a * self.k for a in args]

    def create_polygon(self, pts, **kw):
        if "width" in kw:
            kw["width"] = max(1, kw["width"] * self.k)
        return self.cv.create_polygon(self._c(pts), **kw)

    def create_text(self, x, y, **kw):
        if "font" in kw:
            kw["font"] = self._f(kw["font"])
        return self.cv.create_text(x * self.k, y * self.k, **kw)

    def create_line(self, *xy, **kw):
        if "width" in kw:
            kw["width"] = max(1, kw["width"] * self.k)
        return self.cv.create_line(*self._c(xy), **kw)

    def create_rectangle(self, *xy, **kw):
        return self.cv.create_rectangle(*self._c(xy), **kw)

    def create_oval(self, *xy, **kw):
        if "width" in kw:
            kw["width"] = max(1, kw["width"] * self.k)
        return self.cv.create_oval(*self._c(xy), **kw)

    def create_image(self, x, y, **kw):
        return self.cv.create_image(x * self.k, y * self.k, **kw)

    def delete(self, *a):
        return self.cv.delete(*a)

    def itemconfigure(self, *a, **kw):
        return self.cv.itemconfigure(*a, **kw)

    def configure(self, **kw):
        if "height" in kw:
            kw["height"] = int(kw["height"] * self.k)
        if "width" in kw:
            kw["width"] = int(kw["width"] * self.k)
        return self.cv.configure(**kw)


def _round(cv, x0, y0, x1, y1, r, **kw):
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
           x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return cv.create_polygon(pts, smooth=True, **kw)


class InGameLayer(threading.Thread):
    def __init__(self, service, settings, save_settings, snapshot, logo_png_b64, icon_dir, log):
        super().__init__(daemon=True)
        self.svc, self.settings, self.save_settings = service, settings, save_settings
        self.snapshot, self.logo_b64, self.icon_dir, self.log = snapshot, logo_png_b64, icon_dir, log
        self.open = bool(settings.get("panel_open", False))
        self.toggle_req = False
        self.build_idx = 0
        self.icons = {}
        self.badges = []
        self.visible = False

    # ------------------------------------------------------------ setup
    def run(self):
        if sys.platform != "win32":
            return
        try:
            import tkinter as tk
            self.tk = tk
            threading.Thread(target=self._hotkeys, daemon=True).start()
            self.root = tk.Tk()
            self.root.withdraw()
            self.root.tk.call("tk", "scaling", 96 / 72)    # we size everything ourselves
            self.k = system_scale()
            self._panel_sig = None
            self._make_button()
            self._make_panel()
            self.root.after(300, self._tick)
            self.root.after(300, self._fast)
            self.svc.overlay_status = f"running (display scale {self.k:.2f})"
            self.root.mainloop()
        except Exception as e:
            self.svc.overlay_status = f"failed: {e.__class__.__name__}: {e}"
            self.log(f"In-game overlay unavailable: {e}")

    def _top(self, w, h, x, y, alpha=1.0):
        t = self.tk.Toplevel(self.root)
        t.overrideredirect(True)
        t.geometry(f"{w}x{h}+{int(x)}+{int(y)}")
        t.configure(bg=KEY)
        t.attributes("-transparentcolor", KEY)
        t.attributes("-topmost", True)
        t.attributes("-alpha", alpha)
        return t

    def _default_spot(self):
        try:   # right edge of the screen League is on
            from screen_reader import league_window
            _, rect = league_window()
        except Exception:
            rect = None
        if rect:
            l, t, r, b = rect
        else:
            l, t, r, b = monitor_area(0, 0)
        return r - int(80 * self.k), t + int((b - t) * 0.18)

    def _make_button(self):
        dx, dy = self._default_spot()
        x, y = self.settings.get("ov_x", dx), self.settings.get("ov_y", dy)
        ml, mt, mr, mb = monitor_area(x, y)          # keep it on a screen if monitors changed
        if not (ml - 10 <= x <= mr - 20 and mt - 10 <= y <= mb - 20):
            x, y = dx, dy
        B = int(52 * self.k)
        self.btn = self._top(B, B, x, y, 0.96)
        raw = self.tk.Canvas(self.btn, width=B, height=B, bg=KEY, highlightthickness=0, bd=0)
        raw.pack()
        cv = Scaled(raw, self.k)
        self.btn_ring = cv.create_oval(2, 2, 50, 50, fill=GLASS, outline=GOLD, width=2)
        try:
            self.logo = self.tk.PhotoImage(data=self.logo_b64)
            want = 34 * self.k
            k = max(1, round(self.logo.width() / want))
            self.logo_small = self.logo.subsample(k, k) if k > 1 else self.logo
            cv.create_image(26, 26, image=self.logo_small)
        except Exception:
            cv.create_text(26, 26, text="LS", fill=GOLD, font=("Segoe UI", 13, "bold"))
        self.btn_dot = cv.create_oval(38, 6, 47, 15, fill=TEAL, outline=GLASS, width=2, state="hidden")
        self.btn_cv = cv
        self._draggable(raw, self.btn, on_click=self._toggle, save=True)
        self.btn.withdraw()
        self.root.after(100, lambda: _style(self.btn))

    def _ps(self):
        try:
            return max(0.6, min(1.5, float(self.settings.get("panel_size", 0.85))))
        except Exception:
            return 0.85

    def _make_panel(self):
        self.pk = self.k * self._ps()
        self.panel = self._top(int(PANEL_W * self.pk), 200, 0, 0, 0.90)
        self.raw_cv = self.tk.Canvas(self.panel, width=int(PANEL_W * self.pk), height=200, bg=KEY,
                                     highlightthickness=0, bd=0)
        self.raw_cv.pack()
        self.cv = Scaled(self.raw_cv, self.pk)
        self._rs = {}
        self.raw_cv.bind("<ButtonPress-1>", self._panel_press)
        self.raw_cv.bind("<B1-Motion>", self._panel_drag)
        self.raw_cv.bind("<ButtonRelease-1>", self._panel_release)
        self.raw_cv.bind("<Control-MouseWheel>", self._panel_wheel)
        self.panel.withdraw()
        self.root.after(100, lambda: _style(self.panel))
        self.hit = []     # clickable areas: (x0, y0, x1, y1, action)

    def _draggable(self, widget, win, on_click=None, save=False):
        st = {}

        def press(e):
            st.update(x=e.x_root, y=e.y_root, wx=win.winfo_x(), wy=win.winfo_y(), moved=False)

        def motion(e):
            dx, dy = e.x_root - st["x"], e.y_root - st["y"]
            if abs(dx) + abs(dy) > 4:
                st["moved"] = True
            if st["moved"]:
                win.geometry(f"+{st['wx'] + dx}+{st['wy'] + dy}")
                self._place_panel()

        def release(e):
            if st.get("moved"):
                if save:
                    self.settings["ov_x"], self.settings["ov_y"] = win.winfo_x(), win.winfo_y()
                    self.save_settings()
            elif on_click:
                on_click()
        widget.bind("<ButtonPress-1>", press)
        widget.bind("<B1-Motion>", motion)
        widget.bind("<ButtonRelease-1>", release)

    # ------------------------------------------------------------ hotkeys
    MODS = {"ctrl": 0x0002, "shift": 0x0004, "alt": 0x0001, "win": 0x0008}

    def _hotkeys(self):
        """Overlay toggle hotkey (changeable in Settings) and the snapshot hotkey. Re-registers on change."""
        try:
            import ctypes
            from ctypes import wintypes
            u = ctypes.windll.user32
            msg = wintypes.MSG()
            current = None
            while True:
                want = (str(self.settings.get("hotkey_mods", "ctrl+shift")).lower(),
                        str(self.settings.get("hotkey_key", "L"))[:1].upper() or "L")
                if want != current:
                    u.UnregisterHotKey(None, 1)
                    u.UnregisterHotKey(None, 2)
                    mods = 0x4000
                    for m in want[0].split("+"):
                        mods |= self.MODS.get(m.strip(), 0)
                    got = []
                    label = "+".join(x.strip().title() for x in want[0].split("+") if x.strip())
                    if u.RegisterHotKey(None, 1, mods, ord(want[1])):
                        got.append(f"Overlay: {label}+{want[1]}")
                    else:
                        got.append(f"Overlay: {label}+{want[1]} is taken by another app, pick another key")
                    snap_mods = 0x0002 | 0x0004 | 0x4000
                    if u.RegisterHotKey(None, 2, snap_mods, ord("S")) or u.RegisterHotKey(None, 2, 0x0001 | 0x0004 | 0x4000, ord("S")):
                        got.append("snapshot ready")
                    self.svc.hotkey_status = ", ".join(got)
                    current = want
                while u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):     # PM_REMOVE
                    if msg.message == 0x0312:       # WM_HOTKEY
                        if msg.wParam == 1:
                            self.toggle_req = True
                        elif msg.wParam == 2:
                            threading.Thread(target=self._snap, daemon=True).start()
                time.sleep(0.05)
        except Exception as e:
            self.svc.hotkey_status = f"failed: {e}"
            self.log(f"Hotkeys unavailable: {e}")

    def _snap(self):
        try:
            folder = self.snapshot()
            self.svc.notify("Snapshot saved. Open it from Settings in the LoLStat app.")
            return folder
        except Exception as e:
            self.log(f"Snapshot failed: {e}")

    def _toggle(self):
        self.open = not self.open
        self._panel_sig = None
        self.settings["panel_open"] = self.open
        self.save_settings()
        self._sync()

    # ------------------------------------------------------------ loop
    def _tick(self):
        try:
            if self.toggle_req:
                self.toggle_req = False
                self._toggle()
            self._apply_theme()
            self.state = self.svc.state()
            testing = time.time() < self.svc.test_until
            if testing:
                self.state = self._test_state(self.state)
                if not getattr(self, "_was_testing", False):
                    self.open = True
            elif getattr(self, "_was_testing", False):
                self.open = bool(self.settings.get("panel_open", False))
            self._was_testing = testing
            want = bool(testing or (self.settings.get("overlay", True) and self.state.get("live")))
            if want != self.visible:
                self.visible = want
            self._sync()
            self._draw_badges()
            if self.visible and self.open:
                self._draw_panel()
            self.btn.attributes("-topmost", True)
        except Exception as e:
            self.log(f"Overlay: {e}")
        self.root.after(350, self._tick)

    def _fast(self):
        """Letters on the cards: redraw the moment the cards change (rerolls), not on the next full tick."""
        try:
            v = getattr(self.svc, "offer_ver", 0)
            if v != getattr(self, "_offer_ver", None):
                self._offer_ver = v
                self.state = self.svc.state()
                self._draw_badges()             # the builds panel doesn't depend on the cards
        except Exception as e:
            self.log(f"Overlay: {e}")
        self.root.after(60, self._fast)

    def _test_state(self, st):
        """Sample cards in the middle of the screen League is on (or the main screen)."""
        try:
            from screen_reader import league_window
            _, rect = league_window()
        except Exception:
            rect = None
        rect = rect or monitor_area(0, 0)
        l, t, r, b = rect
        H, cx = b - t, (l + r) / 2
        st = dict(st)
        aug = list(self.svc.data["augments"])[:3]
        cards = [dict(self.svc.aug_view(a), grade=g) for a, g in zip(aug, ["A", "S+", "B"])]
        st["offer"] = {"cards": cards, "best": 1, "rect": rect,
                       "pos": [(cx + (i - 1) * 0.245 * H, t + 0.40 * H) for i in range(3)]}
        st["live"] = True
        return st

    def _apply_theme(self):
        """Use the colors and see-through level picked in the app's theme settings."""
        global GLASS, EDGE, TEXT, MUTED, GOLD, TEAL
        t = self.settings.get("overlay_theme") or {}
        try:
            self._rescale()
        except Exception:
            pass
        sig = repr(t) + repr(self.settings.get("overlay_alpha"))
        if sig == getattr(self, "_theme_sig", None):
            return
        self._theme_sig = sig
        GLASS = t.get("glass", "#111318")
        EDGE = t.get("edge", "#2b2f3a")
        TEXT = t.get("text", "#ece6d6")
        MUTED = t.get("muted", "#8e96ab")
        GOLD = t.get("accent", "#d9b871")
        TEAL = t.get("accent2", "#19c8b4")
        try:
            self.panel.attributes("-alpha", float(self.settings.get("overlay_alpha") or t.get("alpha", 0.90)))
            self.btn_cv.itemconfigure(self.btn_ring, fill=GLASS, outline=GOLD)
        except Exception:
            pass

    def _sync(self):
        if self.visible:
            self.btn.deiconify()
            _style(self.btn)
            st = getattr(self, "state", {}) or {}
            self.btn_cv.itemconfigure(self.btn_dot, state="normal" if st.get("offer") else "hidden")
            if self.open:
                self.panel.deiconify()
                self._place_panel()
            else:
                self.panel.withdraw()
        else:
            self.btn.withdraw()
            self.panel.withdraw()

    def _place_panel(self):
        try:
            bx, by = self.btn.winfo_x(), self.btn.winfo_y()
            ml, mt, mr, mb = monitor_area(bx, by)
            pw, ph = int(PANEL_W * self.pk), self.panel.winfo_height()
            bw = int(60 * self.k)
            x = bx - pw - int(8 * self.k) if bx + bw + pw > mr else bx + bw
            y = max(mt, min(by, mb - ph - 8))
            self.panel.geometry(f"+{x}+{y}")
        except Exception:
            pass

    # ------------------------------------------------------------ grade letters over the cards
    def _draw_badges(self):
        st = self.state or {}
        offer = st.get("offer") if self.visible else None
        pos = (offer or {}).get("pos") or []
        cards = (offer or {}).get("cards") or []
        want = len(pos) if offer and len(pos) == len(cards) else 0
        while len(self.badges) > want:
            self.badges.pop().destroy()
        rect = (offer or {}).get("rect")
        H = (rect[3] - rect[1]) if rect else 1080
        kb = max(0.6, min(2.6, H / 1080))     # letters grow with the game's resolution
        for i in range(want):
            c, p = cards[i], pos[i]
            x, y = p[0], p[1]
            top = p[2] if len(p) > 2 else None
            g = c.get("grade") or "–"
            best = i == offer.get("best")
            kb2 = kb
            w, h = int(120 * kb2), int(84 * kb2)
            if top is not None:                       # found the card's top edge: sit right above it
                bx, by = x - w / 2, top - h + 0.012 * H
            else:                                     # couldn't see the edge: a safe spot above the name
                bx, by = x - w / 2, y - h - 0.16 * H
            by = max((rect[1] if rect else 0), by)
            if i >= len(self.badges) or getattr(self.badges[i], "kb", None) != kb2:
                if i < len(self.badges):
                    self.badges[i].destroy()
                t = self._top(w, h, bx, by, 1.0)
                raw = self.tk.Canvas(t, width=w, height=h, bg=KEY, highlightthickness=0, bd=0)
                raw.pack()
                t.cv, t.kb = Scaled(raw, kb2), kb2
                if i < len(self.badges):
                    self.badges[i] = t
                else:
                    self.badges.append(t)
                self.root.after(50, lambda t=t: _style(t, click_through=True))
            t = self.badges[i]
            t.geometry(f"+{int(bx)}+{int(by)}")
            cv = t.cv
            cv.delete("all")
            col = GRADE.get(g, DIM)
            _round(cv, 22, 20, 98, 78, 16, fill=GLASS, outline=col, width=3)
            cv.create_text(60, 49, text=g, fill=col, font=("Segoe UI Black", 26 if len(g) < 2 else 22))
            if best:
                _round(cv, 30, 2, 90, 24, 8, fill=GOLD, outline="")
                cv.create_text(60, 13, text="BEST", fill="#1a1405", font=("Segoe UI", 9, "bold"))

    # ------------------------------------------------------------ panel
    def _icon(self, url):
        if not url:
            return None
        if url in self.icons:
            return self.icons[url]
        self.icons[url] = None
        threading.Thread(target=self._fetch_icon, args=(url,), daemon=True).start()
        return None

    def _fetch_icon(self, url):
        try:
            os.makedirs(self.icon_dir, exist_ok=True)
            path = os.path.join(self.icon_dir, url.rsplit("/", 1)[-1])
            if not os.path.exists(path):
                with urllib.request.urlopen(url, timeout=10) as r:
                    open(path, "wb").write(r.read())
            self.root.after(0, lambda: self._load_icon(url, path))
        except Exception:
            pass

    def _load_icon(self, url, path):
        try:
            img = self.tk.PhotoImage(file=path)
            k = max(1, round(img.width() / (24 * getattr(self, "pk", self.k))))
            self.icons[url] = img.subsample(k, k) if k > 1 else img
        except Exception:
            pass

    # ---- resizing: drag the bottom-right corner, or Ctrl + mouse wheel
    def _set_panel_scale(self, ps, save=False):
        ps = max(0.6, min(1.5, ps))
        self.settings["panel_size"] = round(ps, 3)
        self._rescale()
        if save:
            self.save_settings()

    def _rescale(self):
        pk = self.k * self._ps()
        if abs(pk - getattr(self, "pk", 0)) < 1e-3:
            return
        self.pk = pk
        self.cv.k = pk
        self.raw_cv.configure(width=int(PANEL_W * pk))
        self.icons = {}                    # reload icons at the new size
        self._panel_sig = None
        self._draw_panel(force=True)
        self._place_panel()

    def _panel_press(self, e):
        ex, ey = e.x / self.pk, e.y / self.pk
        h = getattr(self, "_panel_h", 0)
        if ex >= PANEL_W - 22 and ey >= h - 22:           # the resize grip
            self._rs = {"x": e.x_root, "w": PANEL_W * self.pk}
        else:
            self._rs = {}

    def _panel_drag(self, e):
        if self._rs:
            w = self._rs["w"] + (e.x_root - self._rs["x"])
            self._set_panel_scale(w / (PANEL_W * self.k))

    def _panel_release(self, e):
        if self._rs:
            self._rs = {}
            self.save_settings()
            return
        self._panel_click(e)

    def _panel_wheel(self, e):
        self._set_panel_scale(self._ps() + (0.05 if e.delta > 0 else -0.05), save=True)

    def _panel_click(self, e):
        ex, ey = e.x / self.pk, e.y / self.pk
        for x0, y0, x1, y1, action in self.hit:
            if x0 <= ex <= x1 and y0 <= ey <= y1:
                action()
                self._draw_panel(force=True)
                return

    def _set_build(self, i):
        self.build_idx = i

    def _draw_panel(self, force=False):
        st = self.state or {}
        sig = json.dumps([(st.get("champion") or {}).get("name"), st.get("builds_locked"), self.build_idx,
                          [[b.get("style"), [i.get("id") for i in b.get("items") or []]] for b in st.get("builds") or []]])
        if not force and sig == getattr(self, "_panel_sig", None):
            return                      # nothing changed: leave the panel exactly as it is
        self._panel_sig = sig
        cv, W = self.cv, PANEL_W
        cv.delete("all")
        self.hit = []
        items = []
        y = 16
        # builds only, and they stay the same all game (they match your item sets)
        champ = (st.get("champion") or {}).get("name", "LoLStat")
        items.append(("text", 16, y, champ, TEXT, ("Segoe UI Semibold", 11), "w"))
        if st.get("builds_locked"):
            items.append(("text", W - 40, y, "locked for this game", MUTED, ("Segoe UI", 7), "e"))
        items.append(("close", W - 20, y))
        y += 20
        builds = st.get("builds") or []
        if builds:
            self.build_idx = min(self.build_idx, len(builds) - 1)
            items.append(("tabs", y, len(builds))); y += 28
            b = builds[self.build_idx]
            g = b.get("guide")
            owned = set()           # the panel never changes mid-game, so no "owned" marks either
            head = lambda t: items.append(("text", 18, y + 6, t, GOLD if t.startswith("Buy now") else MUTED, ("Segoe UI Semibold", 8), "w"))
            if g:
                def short(xs, room=44):
                    t = ", ".join(x["name"] for x in xs)
                    return t if len(t) <= room else t[:room - 1].rstrip(", ") + "…"
                if g["start"]["items"] and not owned:
                    head("Start: " + short(g["start"]["items"])); y += 16
                    if g["first_back"]["items"]:
                        head("First back: " + short(g["first_back"]["items"], 38)); y += 16
                    y += 4
                head("Core - rush the first item"); y += 16
                for it in g["core"]:
                    items.append(("item", y, dict(it, why=("Rush first. " if it.get("rush") else "") + it.get("why", "")))); y += 30
                if g["boots"] and g["boots"]["item"]:
                    head("Boots - " + g["boots"]["note"].lower().replace("finish these ", "")); y += 16
                    items.append(("item", y, g["boots"]["item"])); y += 30
                if g["late"]:
                    head("End game"); y += 16
                    for it in g["late"]:
                        items.append(("item", y, it)); y += 30
                urgent = [x for x in g["situational"] if x.get("urgent")][:2] or g["situational"][:1]
                if urgent:
                    head(("Buy now" if urgent[0].get("urgent") else "Situational")); y += 16
                    for x in urgent:
                        items.append(("item", y, dict(x, why=x["situation"] + ": " + x["when"].replace("Buy it now: ", "")))); y += 30
            else:
                rows = ([b["boots"]] if b.get("boots") else []) + b["items"]
                for it in rows:
                    items.append(("item", y, it)); y += 30
            y += 6
        else:
            items.append(("text", 18, y, "Builds show once your champion is known.", MUTED, ("Segoe UI", 9), "w")); y += 22
        y += 6
        H = y
        self._panel_h = H
        self.panel.geometry(f"{int(W * self.pk)}x{int(H * self.pk)}")
        cv.configure(height=H)
        _round(cv, 1, 1, W - 1, H - 1, 14, fill=GLASS, outline=EDGE, width=1)
        for d in (6, 10, 14):                               # resize grip (drag it, or Ctrl + mouse wheel)
            cv.create_line(W - d, H - 4, W - 4, H - d, fill=MUTED, width=1)
        for it in items:
            k = it[0]
            if k == "text":
                _, x, yy, t, col, font, anchor = it
                cv.create_text(x, yy, text=t, fill=col, font=font, anchor=anchor)
            elif k == "close":
                _, x, yy = it
                cv.create_text(x, yy, text="—", fill=MUTED, font=("Segoe UI", 11, "bold"))
                self.hit.append((x - 12, yy - 10, x + 12, yy + 10, self._toggle))
            elif k == "card":
                _, yy, c, best = it
                _round(cv, 12, yy, W - 12, yy + 34, 10, fill="#181b22", outline=GOLD if best else EDGE)
                cv.create_rectangle(12, yy + 8, 15, yy + 26, fill=TIER.get(c["tier"], DIM), outline="")
                cv.create_text(24, yy + 11, text=c["name"], fill=TEXT, font=("Segoe UI Semibold", 10), anchor="w")
                sub = (f"Combo with {c['combo']}" if c.get("combo") else
                       f"{c['gpick'] * 100:.1f}% picked" if c.get("gpick") is not None else "")
                cv.create_text(24, yy + 25, text=sub, fill=MUTED, font=("Segoe UI", 8), anchor="w")
                g = c.get("grade") or "–"
                col = GRADE.get(g, DIM)
                _round(cv, W - 62, yy + 6, W - 20, yy + 28, 7, fill=col, outline="")
                cv.create_text(W - 41, yy + 17, text=g, fill="#0c1220", font=("Segoe UI Black", 11))
            elif k == "tabs":
                _, yy, n = it
                x = 14
                for i in range(n):
                    label = STYLES[i] if i < len(STYLES) else f"Build {i + 1}"
                    tw = 10 + 6.3 * len(label)
                    on = i == self.build_idx
                    if on:
                        _round(cv, x, yy, x + tw, yy + 22, 8, fill=EDGE, outline="")
                    cv.create_text(x + tw / 2, yy + 11, text=label, fill=TEXT if on else MUTED,
                                   font=("Segoe UI Semibold" if on else "Segoe UI", 9))
                    self.hit.append((x, yy, x + tw, yy + 22, lambda i=i: self._set_build(i)))
                    x += tw + 4
            elif k == "item":
                _, yy, itm = it
                ic = self._icon(itm.get("icon"))
                if ic:
                    cv.create_image(28, yy + 12, image=ic)
                else:
                    _round(cv, 16, yy, 40, yy + 24, 6, fill=EDGE, outline="")
                cv.create_text(48, yy + 6, text=itm["name"], fill=TEXT,
                               font=("Segoe UI Semibold", 9), anchor="w")
                why = itm.get("why", "")
                why = why if len(why) < 50 else why[:48] + "…"
                cv.create_text(48, yy + 19, text=why, fill=MUTED, font=("Segoe UI", 7), anchor="w")
            elif k == "chip":
                _, x, yy, c, wtxt = it
                _round(cv, x, yy, x + wtxt, yy + 22, 7, fill="#181b22", outline=EDGE)
                g = c.get("grade") or "–"
                _round(cv, x + 3, yy + 3, x + 27, yy + 19, 5, fill=GRADE.get(g, DIM), outline="")
                cv.create_text(x + 15, yy + 11, text=g, fill="#0c1220", font=("Segoe UI Black", 8))
                cv.create_text(x + 31, yy + 11, text=c["name"], fill=TEXT, font=("Segoe UI", 8), anchor="w")
