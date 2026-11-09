"""
LoLStat screen reader: spots ARAM Mayhem augment cards on screen and the one you click.

It only looks at the League game window, only during a Mayhem game and only while
League is the active window. It reads the card names with Windows' built-in text
recognition (Windows.Media.Ocr), the same engine as the Snipping Tool's text
actions. Nothing is saved or sent anywhere.
"""

import difflib
import re
import sys
import threading
import time

SCAN_SECONDS = 0.3       # between reads while looking for new augment cards
SCAN_FAST = 0.15         # between reads while cards are on screen (rerolls show quickly, game stays smooth)
SCAN_CLICK = 0.03        # back to back: right after a level-up or at game start (cards are likely)
LEVEL_BURST = 6.0        # seconds of back-to-back searching after each level-up
FAST_AFTER_CLICK = 1.2   # how long to read at the click pace
CLICK_POLL_SECONDS = 0.025
# part of the game window that's read (fractions of width/height): nearly all of it
REGION = (0.03, 0.04, 0.97, 0.90)
SCAN_BAND = (0.04, 0.14, 0.96, 0.86)   # where augment card names can be while looking for new cards
SLOT_W, SLOT_H = 0.19, 0.085           # one card's name box, as a share of the game window

# The ARAM Mayhem card screen, measured from real games. Everything scales with the game window's
# height and is centred horizontally, so it fits any screen (16:9, 21:9, 4K...). s = League HUD scale.
CARD_DX = 0.3407      # card centres: middle of the screen, and this far either side (x height)
CARD_EDGE = 0.138     # card frame: this far left/right of a card's centre
CARD_EDGE_YS = (0.23, 0.20, 0.17)   # rows where the gold frame is checked (above the screen middle)
CARD_TOP = 0.32       # top of the cards, above the screen middle (for the grade letters)
NAME_Y = 0.087        # card names: this far above the screen middle
NAME_W, NAME_H = 0.26, 0.05
NAME_ZOOM = 3         # names are small (about 13 px at 1080p): enlarge before reading
FALLBACK_SECONDS = 2.0  # whole-screen search when the frames aren't where expected (unusual HUD scale)
SLOT_TEXT_H = 72                       # name boxes are enlarged to this height before reading
SLOT_POLL = 0.04                       # how often the name boxes are checked for changes (cheap)
SLOT_REREAD = 0.7                      # read the boxes at least this often, even if nothing seems to change


def norm(s):
    # letters and digits in any language (so German, Korean, Chinese... names work too)
    return re.sub(r"[\W_]+", "", (s or "").lower())


# ---------------------------------------------------------------- text -> augments (pure, testable)
class AugmentMatcher:
    def __init__(self, names):
        self.update(names)

    def update(self, names):
        """names: {id: name} or a list of (id, name) pairs (several languages allowed)."""
        pairs = names.items() if isinstance(names, dict) else names
        sig = id(names), len(pairs) if hasattr(pairs, "__len__") else 0
        if getattr(self, "_sig", None) == sig:
            return
        self._sig = sig
        self.by_norm = {}
        for aid, name in pairs:
            n = norm(name)
            if n:
                self.by_norm.setdefault(n, aid)
        self.keys = list(self.by_norm)

    def lookup(self, text):
        n = norm(text)
        cjk = any(ord(ch) > 0x2E80 for ch in n)
        if len(n) < (2 if cjk else 3):
            return None
        if n in self.by_norm:
            return self.by_norm[n]
        if len(n) < (4 if cjk else 6):   # short names must match exactly
            return None
        hit = difflib.get_close_matches(n, self.keys, n=1, cutoff=0.80)
        if hit:
            return self.by_norm[hit[0]]
        # the name may be glued to nearby text ("PRISMATICTWINFIRE"): look for a long name inside
        inside = [k for k in self.keys if len(k) >= (4 if cjk else 8) and k in n and len(n) <= len(k) + 14]
        return self.by_norm[max(inside, key=len)] if inside else None

    @staticmethod
    def segments(lines):
        """Split OCR lines into chunks wherever there's a big horizontal gap (separate cards)."""
        segs = []
        for words in lines:
            words = sorted(words, key=lambda w: w["x"])
            if not words:
                continue
            h = max(1.0, sum(w["h"] for w in words) / len(words))
            cur = [words[0]]
            for w in words[1:]:
                prev = cur[-1]
                if w["x"] - (prev["x"] + prev["w"]) > 1.6 * h:
                    segs.append(cur)
                    cur = [w]
                else:
                    cur.append(w)
            segs.append(cur)
        out = []
        for s in segs:
            x0 = min(w["x"] for w in s)
            x1 = max(w["x"] + w["w"] for w in s)
            y0 = min(w["y"] for w in s)
            y1 = max(w["y"] + w["h"] for w in s)
            out.append({"text": " ".join(w["text"] for w in s), "x": (x0 + x1) / 2, "y": (y0 + y1) / 2,
                        "h": y1 - y0, "w": x1 - x0})
        return out

    def find_offer(self, lines, img_h, min_cards=2):
        """Return [(augment id, x, y), ...] left to right for the cards on screen, or []."""
        segs = self.segments(lines)
        hits = []
        used = set()
        for i, s in enumerate(segs):
            aid = self.lookup(s["text"])
            if aid:
                hits.append((aid, s["x"], s["y"]))
                used.add(i)
        # long names can wrap onto two lines: try joining a chunk with the one right below it
        for i, a in enumerate(segs):
            if i in used:
                continue
            for j, b in enumerate(segs):
                if j == i or j in used:
                    continue
                if 0 < b["y"] - a["y"] < 2.2 * max(a["h"], 1) and abs(b["x"] - a["x"]) < max(a["w"], b["w"]):
                    aid = self.lookup(a["text"] + " " + b["text"])
                    if aid:
                        hits.append((aid, (a["x"] + b["x"]) / 2, a["y"]))
                        used.update((i, j))
                        break
        # keep one hit per augment, then the biggest group sitting on the same row
        seen, uniq = set(), []
        for h in hits:
            if h[0] not in seen:
                seen.add(h[0])
                uniq.append(h)
        best = []
        for h in uniq:
            row = [g for g in uniq if abs(g[2] - h[2]) < 0.12 * img_h]
            if len(row) > len(best):
                best = row
        if len(best) < min_cards:
            return []
        best.sort(key=lambda g: g[1])
        # cards are spread across the screen; drop hits bunched up on top of each other
        spread = []
        for g in best:
            if not spread or g[1] - spread[-1][1] > 0.14 * img_h:
                spread.append(g)
        return spread[:3] if len(spread) >= min_cards else []


# ---------------------------------------------------------------- offer + click tracking (pure, testable)
MISS_SECONDS = 1.2     # ...and for at least this long (reads are fast now, a blink isn't "cards gone")
MISS_LIMIT = 4          # empty frames in a row before the card screen counts as closed (rerolls animate)


class OfferTracker:
    """Turns noisy per-frame detections into offer/pick events. Handles rerolls: a card that changes
    in place updates that slot, and a click on a reroll button is never taken as a pick."""

    def __init__(self):
        self.current = None      # {"ids": [...], "xs": [...], "ys": [...], "since": t}
        self.pending = None
        self.pending_n = 0
        self.miss = 0
        self.first_miss = 0
        self.clicks = []

    def click(self, x, y, t):
        if self.current:
            self.clicks.append((x, y, t))

    def _confirm(self, key):
        if self.pending == key:
            self.pending_n += 1
        else:
            self.pending, self.pending_n = key, 1
        return self.pending_n >= 1      # names only match real augments, so one clean read is enough

    def _event(self):
        c = self.current
        return ("offer", list(c["ids"]), list(zip(c["xs"], c["ys"])))

    def frame(self, cards, t, force=False):
        """cards: [(id, screen_x, screen_y)]; returns a list of events."""
        ev = []
        if cards:
            self.miss = 0
            cur = self.current
            if cur:
                if set(c[0] for c in cards) <= set(cur["ids"]):
                    return ev                                   # same cards (some maybe missed this frame)
                ids, xs, ys = list(cur["ids"]), list(cur["xs"]), list(cur["ys"])
                gap = (max(xs) - min(xs)) / (len(xs) - 1) if len(xs) > 1 else 300
                row_y = sum(ys) / len(ys)
                for aid, x, y in cards:
                    if aid in ids or abs(y - row_y) > max(60, 0.6 * gap):
                        continue
                    k = min(range(len(xs)), key=lambda i: abs(xs[i] - x))
                    if abs(xs[k] - x) < 0.5 * gap:              # rerolled card in the same spot
                        ids[k], xs[k], ys[k] = aid, x, y
                    elif len(ids) < 3:                          # a card that wasn't read before
                        ids.append(aid); xs.append(x); ys.append(y)
                order = sorted(range(len(ids)), key=lambda i: xs[i])
                ids, xs, ys = [ids[i] for i in order], [xs[i] for i in order], [ys[i] for i in order]
                if ids != cur["ids"] and self._confirm(tuple(ids)):
                    self.current = {"ids": ids, "xs": xs, "ys": ys, "since": t}
                    self.clicks = []                            # that click was a reroll, not a pick
                    self.pending, self.pending_n = None, 0
                    ev.append(self._event())
                return ev
            if len(cards) >= 2 and self._confirm(tuple(c[0] for c in cards)):
                self.current = {"ids": [c[0] for c in cards], "xs": [c[1] for c in cards],
                                "ys": [c[2] for c in cards], "since": t}
                self.clicks = []
                self.pending, self.pending_n = None, 0
                ev.append(self._event())
            return ev
        self.pending, self.pending_n = None, 0
        if self.current:
            if self.miss == 0:
                self.first_miss = t
            self.miss += 1
            if self.miss >= MISS_LIMIT and (force or t - self.first_miss >= MISS_SECONDS):                         # cards really gone: which one was clicked?
                cur = self.current
                self.current = None
                pick = None
                recent = [c for c in self.clicks if c[2] <= self.first_miss + 0.3 and c[2] >= self.first_miss - 4]
                if recent:
                    xs = cur["xs"]
                    gap = (max(xs) - min(xs)) / (len(xs) - 1) if len(xs) > 1 else 400
                    x, y, _ = recent[-1]
                    k = min(range(len(xs)), key=lambda i: abs(xs[i] - x))
                    if abs(xs[k] - x) < 0.6 * gap:
                        pick = cur["ids"][k]
                self.clicks = []
                self.miss = 0
                ev.append(("pick", pick, cur["ids"]))
        return ev


# ---------------------------------------------------------------- Windows plumbing
def _win():
    import ctypes
    from ctypes import wintypes
    return ctypes, wintypes


def league_window():
    """(hwnd, (l, t, r, b)) for the game window, or (None, None)."""
    ctypes, wintypes = _win()
    u = ctypes.windll.user32
    hwnd = u.FindWindowW("RiotWindowClass", None)
    if not hwnd or u.IsIconic(hwnd):
        return None, None
    r = wintypes.RECT()
    u.GetClientRect(hwnd, ctypes.byref(r))          # the game picture only, without a title bar
    pt = wintypes.POINT(0, 0)
    u.ClientToScreen(hwnd, ctypes.byref(pt))
    w, h = r.right - r.left, r.bottom - r.top
    if w < 400 or h < 300:
        return None, None
    return hwnd, (pt.x, pt.y, pt.x + w, pt.y + h)


def client_window():
    """(hwnd, rect) of the League client (champ select lives there), or (None, None)."""
    ctypes, wintypes = _win()
    u = ctypes.windll.user32
    hwnd = u.FindWindowW("RCLIENT", None)
    if not hwnd or u.IsIconic(hwnd) or not u.IsWindowVisible(hwnd):
        return None, None
    r = wintypes.RECT()
    u.GetClientRect(hwnd, ctypes.byref(r))
    pt = wintypes.POINT(0, 0)
    u.ClientToScreen(hwnd, ctypes.byref(pt))
    w, h = r.right - r.left, r.bottom - r.top
    if w < 600 or h < 350:
        return None, None
    return hwnd, (pt.x, pt.y, pt.x + w, pt.y + h)


def foreground_is(hwnd):
    ctypes, _ = _win()
    return ctypes.windll.user32.GetForegroundWindow() == hwnd


def game_visible(hwnd, rect):
    """True when the middle of the screen shows League (not another window like our app on top)."""
    ctypes, wintypes = _win()
    u = ctypes.windll.user32
    l, t, r, b = rect
    for fx, fy in ((0.5, 0.45), (0.3, 0.45), (0.7, 0.45)):
        pt = wintypes.POINT(int(l + (r - l) * fx), int(t + (b - t) * fy))
        w = u.WindowFromPoint(pt)
        root = u.GetAncestor(w, 2) if w else 0          # GA_ROOT
        if root == hwnd:
            return True
    return False


def exclude_hwnd_from_capture(hwnd):
    try:
        ctypes, _ = _win()
        return bool(ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x11))
    except Exception:
        return False


def exclude_from_capture(title):
    """Keep our overlay out of screenshots so we never read our own text."""
    try:
        ctypes, _ = _win()
        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if hwnd:
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x11)  # WDA_EXCLUDEFROMCAPTURE
            return True
    except Exception:
        pass
    return False


class WindowsOcr:
    def __init__(self, lang_tag="en-US"):
        self.mod = None
        for prefix in ("winsdk", "winrt"):
            try:
                ocr = __import__(f"{prefix}.windows.media.ocr", fromlist=["OcrEngine"])
                img = __import__(f"{prefix}.windows.graphics.imaging",
                                 fromlist=["SoftwareBitmap", "BitmapPixelFormat"])
                crypt = __import__(f"{prefix}.windows.security.cryptography", fromlist=["CryptographicBuffer"])
                glob = __import__(f"{prefix}.windows.globalization", fromlist=["Language"])
                self.mod = (ocr, img, crypt, glob)
                break
            except Exception:
                continue
        if not self.mod:
            raise RuntimeError("Windows text recognition isn't available")
        ocr, _, _, glob = self.mod
        eng = None
        try:
            lang = glob.Language(lang_tag)
            if ocr.OcrEngine.is_language_supported(lang):
                eng = ocr.OcrEngine.try_create_from_language(lang)
        except Exception:
            eng = None
        self.engine = eng or ocr.OcrEngine.try_create_from_user_profile_languages()
        if not self.engine:
            raise RuntimeError("no text-recognition language installed (Windows Settings > Language)")
        self.lang_tag = lang_tag

    def read(self, pil_img):
        """Lines of words: [[{text, x, y, w, h}, ...], ...] in image pixels."""
        import asyncio
        ocr, img, crypt, _ = self.mod
        im = pil_img.convert("RGBA")
        try:
            maxd = int(ocr.OcrEngine.max_image_dimension)
        except Exception:
            maxd = 2600
        k = 1.0
        if max(im.width, im.height) > maxd:            # very wide screens: shrink to what the engine accepts
            k = maxd / max(im.width, im.height)
            im = im.resize((int(im.width * k), int(im.height * k)))
        buf = crypt.CryptographicBuffer.create_from_byte_array(im.tobytes())
        bmp = img.SoftwareBitmap(img.BitmapPixelFormat.RGBA8, im.width, im.height)
        bmp.copy_from_buffer(buf)

        async def go():
            return await self.engine.recognize_async(bmp)
        res = asyncio.run(go())
        lines = []
        for line in res.lines:
            words = []
            for w in line.words:
                r = w.bounding_rect
                words.append({"text": w.text, "x": r.x / k, "y": r.y / k, "w": r.width / k, "h": r.height / k})
            lines.append(words)
        return lines


TARGET_H = 940   # read every screen at about the same text size (1080p-like), whatever its resolution


def card_top(img, ix, iy, H):
    """Find the top edge of the card whose name sits at (ix, iy) in img: the strongest brightness
    change in a narrow band above the name (card frame vs. darker background). None if unsure."""
    from PIL import ImageOps
    bw = max(12, int(0.07 * H))
    y0, y1 = max(0, int(iy - 0.55 * H)), max(0, int(iy - 0.03 * H))
    if y1 - y0 < 20 or ix - bw < 0 or ix + bw > img.width:
        return None
    band = ImageOps.grayscale(img.crop((int(ix - bw), y0, int(ix + bw), y1)))
    n = max(20, (y1 - y0) // 2)
    prof = list(band.resize((1, n)).getdata())          # average brightness of each row
    best, bt = 0, None
    lo = max(3, n // 12)
    for t in range(lo, n - lo):
        above = sum(prof[max(0, t - lo):t]) / (t - max(0, t - lo))
        below = sum(prof[t:t + lo]) / lo
        d = abs(below - above)
        if d > best:
            best, bt = d, t
    if bt is None or best < 18:                          # no clear edge
        return None
    return y0 + bt * (y1 - y0) / n


def _sig(img):
    """A tiny fingerprint of an image, to notice the moment a card changes."""
    from PIL import ImageOps
    return list(ImageOps.grayscale(img).resize((32, 8)).getdata())


def _changed(a, b, limit=7.0):
    if not a or not b or len(a) != len(b):
        return True
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a) > limit


def slot_strip(crops, zoom=None):
    """Enlarge and contrast-boost each card's name box (dark text on white reads best), stack them
    into one image. Returns (image, [(y0, y1), ...]) so each line read can be traced back to its card."""
    from PIL import Image, ImageOps
    parts, spans, y = [], [], 0
    for c in crops:
        g = ImageOps.autocontrast(ImageOps.grayscale(c), cutoff=1)
        k = zoom or SLOT_TEXT_H / max(1, g.height)
        g = ImageOps.invert(g.resize((max(1, int(g.width * k)), max(1, int(g.height * k))), Image.LANCZOS))
        parts.append(g)
        spans.append((y, y + g.height))
        y += g.height + 24
    w = max(p.width for p in parts) if parts else 1
    out = Image.new("L", (w, max(1, y)), 255)
    for p, (y0, _) in zip(parts, spans):
        out.paste(p, (0, y0))
    return out.convert("RGB"), spans


def _prep(img, mode):
    """mode 0: as is; 1: grayscale, stretched contrast, enlarged (helps small or stylized text)."""
    from PIL import ImageOps
    if mode == 0:
        return img, 1.0
    g = ImageOps.autocontrast(ImageOps.grayscale(img), cutoff=1)
    if g.height >= 600:                   # big enough already: enlarging only slows the read down
        return g.convert("RGB"), 1.0
    k = 1.6
    return g.resize((int(g.width * k), int(g.height * k))).convert("RGB"), k


class ScreenReader:
    def __init__(self, service, settings, log, snap_dir):
        self.svc, self.settings, self.log, self.snap_dir = service, settings, log, snap_dir
        self.matcher = AugmentMatcher(service.match_names())
        self.tracker = OfferTracker()
        self._wake = threading.Event()
        self._burst_until = 0
        self._slot_sigs = []        # fingerprint of each card's name box when it was last read
        self._slot_read_t = 0
        self._slot_last_ok = True
        self._full_mode = 0
        self.ocr = None
        self.last_text = ""
        self.last_img = None
        self.last_box = None

    def start(self):
        if sys.platform != "win32":
            self._status("Screen reading works on Windows only")
            return
        try:
            self.ocr = WindowsOcr()
        except Exception as e:
            self._status(f"Screen reading unavailable: {e}")
            self.log(self.svc.scanner_status)
            return
        threading.Thread(target=self._scan_loop, daemon=True).start()
        threading.Thread(target=self._click_loop, daemon=True).start()

    def _status(self, s):
        self.svc.scanner_status = s

    def _check_lang(self):
        """Read cards in the game's language (German client -> German OCR), English as backup."""
        want = (self.svc.locale or "en_US").replace("_", "-")
        if self.ocr and self.ocr.lang_tag != want and getattr(self, "_lang_tried", None) != want:
            self._lang_tried = want
            try:
                self.ocr = WindowsOcr(want)
                self.log(f"Reading cards in {want}.")
            except Exception:
                pass

    def _read(self, img):
        """Whole-screen search (fallback): contrast-boosted, since plain reads miss the card names."""
        pim, k = _prep(img, 1)
        lines = self.ocr.read(pim)
        texts = [" | ".join(" ".join(w["text"] for w in ln) for ln in lines)]
        cards = self.matcher.find_offer(lines, pim.height, 1 if self.tracker.current else 2)
        return [(aid, x / k, y / k) for aid, x, y in cards], texts

    # ---- fast path: the card screen sits in a known place, so check for the cards' gold frames
    # (a few pixels, almost free) and read only the three name spots, enlarged.
    def _scale(self):
        try:
            return max(0.6, min(1.4, float(self.settings.get("card_scale", 1.0))))
        except Exception:
            return 1.0

    def _layout(self, rect):
        l, t, r, b = rect
        W, H = r - l, b - t
        s = self._scale()
        cx, mid = l + W / 2, t + H / 2
        xs = [cx + k * CARD_DX * s * H for k in (-1, 0, 1)]
        return {"H": H, "s": s, "xs": xs, "name_y": mid - NAME_Y * s * H, "top": mid - CARD_TOP * s * H,
                "edge": CARD_EDGE * s * H, "edge_ys": [mid - f * s * H for f in CARD_EDGE_YS],
                "nw": NAME_W * s * H, "nh": NAME_H * s * H}

    def _fast_cards(self, ImageGrab, rect):
        """Returns how many card frames are on screen (0-3), and reads the names when needed."""
        L = self._layout(rect)
        x0 = int(L["xs"][0] - L["edge"] - 6)
        x1 = int(L["xs"][2] + L["edge"] + 6)
        y0 = int(min(L["edge_ys"]) - 4)
        y1 = int(L["name_y"] + L["nh"] / 2 + 4)
        band = ImageGrab.grab(bbox=(x0, y0, x1, y1), all_screens=True).convert("RGB")
        px = band.load()
        frames = 0
        for x in L["xs"]:
            edge = [max(px[int(x + sgn * L["edge"] - x0), int(yy - y0)]) for sgn in (-1, 1) for yy in L["edge_ys"]]
            inside = [max(px[int(x + d * L["H"] * L["s"] - x0), int(L["edge_ys"][1] - y0)]) for d in (-0.08, 0.08)]
            if sum(edge) / len(edge) > 140 and sum(inside) / len(inside) < 100:
                frames += 1
        self._frames = frames
        if frames < 2:
            return frames
        boxes = [(int(x - L["nw"] / 2), int(L["name_y"] - L["nh"] / 2), int(x + L["nw"] / 2), int(L["name_y"] + L["nh"] / 2))
                 for x in L["xs"]]
        crops = [band.crop((b[0] - x0, b[1] - y0, b[2] - x0, b[3] - y0)) for b in boxes]
        sigs = [_sig(c) for c in crops]
        now = time.time()
        moved = len(sigs) != len(self._slot_sigs) or any(_changed(a, b, 5.0) for a, b in zip(sigs, self._slot_sigs))
        if not moved and self._slot_last_ok and now - self._slot_read_t < SLOT_REREAD:
            return frames
        strip, spans = slot_strip(crops, zoom=max(1.2, NAME_ZOOM * 1080 / max(1, L["H"])))
        lines = self.ocr.read(strip)
        texts = [""] * 3
        for ln in lines:
            for w in ln:
                cy = w["y"] + w["h"] / 2
                for i, (a, b) in enumerate(spans):
                    if a - 6 <= cy <= b + 6:
                        texts[i] = (texts[i] + " " + w["text"]).strip()
        cards = []
        for i, txt in enumerate(texts):
            aid = self.matcher.lookup(txt)
            if not aid:                              # extra words read next to the name: try each line alone
                for ln in lines:
                    if ln and spans[i][0] - 6 <= ln[0]["y"] + ln[0]["h"] / 2 <= spans[i][1] + 6:
                        aid = self.matcher.lookup(" ".join(w["text"] for w in ln))
                        if aid:
                            break
            if aid:
                cards.append((aid, L["xs"][i], L["name_y"]))
        self._slot_sigs, self._slot_read_t = sigs, now
        self._slot_last_ok = len(cards) == 3
        self._fast_top = L["top"]
        self.last_text = " | ".join(texts)
        self.svc.reader_info = dict(getattr(self.svc, "reader_info", {}) or {}, last_scan=time.strftime("%H:%M:%S"),
                                    cards_matched=[self.svc.aug_names.get(a, a) for a, _, _ in cards], card_frames=frames,
                                    text_seen=self.last_text[:400], mode="reading the card names", hud_scale=round(L["s"], 3))
        if cards:
            if len(cards) >= 2 and not self.settings.get("card_layout_ok"):
                self.settings["card_layout_ok"] = True      # found the quick way: the backup search isn't needed
            for e in self.tracker.frame(cards, now):
                self._handle(e)
        return frames

    def _calibrate(self, cards, rect):
        """The whole-screen search found cards somewhere else: learn where (League HUD scale)."""
        if len(cards) < 2:
            return
        l, t, r, b = rect
        H = b - t
        xs = sorted(x for _, x, _ in cards)
        gap = (xs[-1] - xs[0]) / (len(xs) - 1) if len(cards) == 3 else None
        if gap is None:
            gap = xs[1] - xs[0]
            if gap > 1.5 * CARD_DX * H:              # the middle one was missed
                gap /= 2
        s = max(0.6, min(1.4, gap / (CARD_DX * H)))
        if abs(s - self._scale()) > 0.02:
            self.settings["card_scale"] = round(s, 3)
            self.log(f"Augment cards: adjusted to your HUD scale ({s:.2f}).")

    def _slot_boxes(self, rect):
        """Name boxes to watch: the known cards, plus where a card that wasn't read yet must be."""
        cur = self.tracker.current
        l, t, r, b = rect
        W, H = r - l, b - t
        pts = list(zip(cur["xs"], cur["ys"]))
        if len(pts) == 2:                        # only 2 of 3 read: the third is between them or beside them
            (xa, ya), (xb, yb) = sorted(pts)
            gap, y = xb - xa, (ya + yb) / 2
            for x in ((xa + xb) / 2, xa - gap, xb + gap):
                if l + SLOT_W * W / 2 <= x <= r - SLOT_W * W / 2 and min(abs(x - xa), abs(x - xb)) > SLOT_W * W * 0.6:
                    pts.append((x, y))
        return [(int(x - SLOT_W * W / 2), int(y - SLOT_H * H / 2), int(x + SLOT_W * W / 2), int(y + SLOT_H * H / 2))
                for x, y in pts]

    def _watch_slots(self, ImageGrab, rect):
        """Cards are up: watch just their name boxes. Read them the moment one changes (a reroll),
        and at least every SLOT_REREAD seconds. Returns True if a read happened."""
        boxes = self._slot_boxes(rect)
        x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
        band = ImageGrab.grab(bbox=(x0, y0, x1, y1), all_screens=True)
        crops = [band.crop((b[0] - x0, b[1] - y0, b[2] - x0, b[3] - y0)) for b in boxes]
        sigs = [_sig(c) for c in crops]
        moved = len(sigs) != len(self._slot_sigs) or any(_changed(a, b) for a, b in zip(sigs, self._slot_sigs))
        now = time.time()
        if not moved and self._slot_last_ok and now - self._slot_read_t < SLOT_REREAD:
            return False
        strip, spans = slot_strip(crops)
        lines = self.ocr.read(strip)
        texts = [""] * len(boxes)
        for ln in lines:
            for w in ln:
                cy = w["y"] + w["h"] / 2
                for i, (a, b) in enumerate(spans):
                    if a - 6 <= cy <= b + 6:
                        texts[i] = (texts[i] + " " + w["text"]).strip()
        cards = []
        for i, txt in enumerate(texts):
            aid = self.matcher.lookup(txt)
            if not aid:                              # the name may share the box with other words
                for ln in lines:
                    if ln and spans[i][0] - 6 <= ln[0]["y"] + ln[0]["h"] / 2 <= spans[i][1] + 6:
                        aid = self.matcher.lookup(" ".join(w["text"] for w in ln))
                        if aid:
                            break
            if aid:
                bx = boxes[i]
                cards.append((aid, (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2))
        self._slot_sigs, self._slot_read_t = sigs, now
        self._slot_last_ok = len(cards) >= min(3, len(boxes))
        self.last_text = " | ".join(texts)
        self.svc.reader_info = dict(getattr(self.svc, "reader_info", {}) or {}, last_scan=time.strftime("%H:%M:%S"),
                                    cards_matched=[self.svc.aug_names.get(a, a) for a, _, _ in cards],
                                    text_seen=self.last_text[:400], mode="watching the cards' name boxes")
        for e in self.tracker.frame(cards, now):
            self._handle(e)
        return True

    def _tops(self, pos, box):
        """Card top edges (screen y) for the letters; the cards share one height, so use the median."""
        img, rect = self.last_img, self.game_rect
        if img is None or not rect:
            return [None] * len(pos)
        H = rect[3] - rect[1]
        found = [card_top(img, x - box[0], y - box[1], H) for x, y in pos]
        offs = sorted((y - box[1]) - t for (x, y), t in zip(pos, found) if t is not None)
        if not offs:
            return [None] * len(pos)
        off = offs[len(offs) // 2]
        return [y - off for x, y in pos]

    def _emit(self, cards, box, band=False):
        cards = [(aid, box[0] + x, box[1] + y) for aid, x, y in cards]
        for e in self.tracker.frame(cards, time.time()):
            self._handle(e, box, band)

    def _handle(self, e, box=None, band=True):
        if True:
            if e[0] == "offer":
                self._slot_sigs = []                 # new cards: start watching their name boxes fresh
                old = getattr(self, "_known_tops", None) or []
                tops = [None] * len(e[2]) if band or box is None else self._tops(e[2], box)
                if box is None and getattr(self, "_fast_top", None) is not None:
                    tops = [self._fast_top] * len(e[2])     # the cards' top edge, from the known layout
                for i, (x, y) in enumerate(e[2]):        # same slot as before (a reroll): same card top
                    if tops[i] is None and old:
                        ox, oy, ot = min(old, key=lambda o: abs(o[0] - x))
                        if abs(ox - x) < 80 and ot is not None:
                            tops[i] = ot + (y - oy)
                if any(t is not None for t in tops):
                    self._known_tops = [(x, y, t) for (x, y), t in zip(e[2], tops)]
                pos = [(x, y, t) for (x, y), t in zip(e[2], tops)]
                self.svc.on_offer(e[1], pos=pos, game_rect=self.game_rect)
            elif e[0] == "pick":
                self.svc.on_pick(e[1], e[2])

    def _scan_loop(self):
        from PIL import ImageGrab, ImageStat
        self.game_rect = None
        while True:
            try:
                live = self.svc.live
                if not self.settings.get("scan", True):
                    self._status("Off (turned off in Settings)")
                elif not live:
                    cs = self.svc.champ_select
                    if cs and not cs.get("locked") and not (self.svc.cs_debug or {}).get("cards"):
                        self._scan_client(ImageGrab)
                        time.sleep(0.6)
                        continue
                    self._status("Waiting for a game")
                else:
                    hwnd, rect = league_window()
                    self.game_rect = rect
                    if not hwnd:
                        self._status("Can't find the League game window")
                    elif not (foreground_is(hwnd) or game_visible(hwnd, rect)):
                        self._status("Paused: another window is covering League")
                    else:
                        self.matcher.update(self.svc.match_names())
                        self._check_lang()
                        frames = self._fast_cards(ImageGrab, rect)
                        now = time.time()
                        if frames >= 2:                  # cards are up: keep reading their names
                            self._status("Reading augment cards")
                            self._wake.wait(SLOT_POLL)
                            self._wake.clear()
                            continue
                        if self.tracker.current:         # cards gone: settles the pick
                            for e in self.tracker.frame([], now):
                                self._handle(e)
                            self._slot_sigs = []
                        perf = 1.5 if self.settings.get("perf_mode") else 1
                        lv, gt = int(live.get("level") or 0), float(live.get("time") or 0)
                        if lv > getattr(self, "_last_level", lv) or gt < 75:
                            self._burst_until = max(self._burst_until, now + LEVEL_BURST)
                        self._last_level = lv
                        if (self.settings.get("card_layout_ok") or now - getattr(self, "_fallback_t", 0) < FALLBACK_SECONDS
                                or str(live.get("mode", "")).upper() != "KIWI"):
                            self._status("Watching for augment cards")
                            self._wake.wait(0.03 if now < self._burst_until else 0.1 * perf)
                            self._wake.clear()
                            continue
                        self._fallback_t = now           # whole-screen search, in case the HUD is scaled differently
                        l, t, r, b = rect
                        W, H = r - l, b - t
                        box = (l + int(W * SCAN_BAND[0]), t + int(H * SCAN_BAND[1]),
                               l + int(W * SCAN_BAND[2]), t + int(H * SCAN_BAND[3]))
                        full_h = int(H * (REGION[3] - REGION[1]))
                        band = False
                        img = ImageGrab.grab(bbox=box, all_screens=True)
                        self.last_img, self.last_box = img, box
                        if sum(ImageStat.Stat(img.convert("L")).mean) < 2:
                            self._status("Can't see the game: set League's Window Mode to Borderless")
                        else:
                            scale = max(0.45, min(2.0, TARGET_H / full_h))
                            if abs(scale - 1) > 0.05:
                                img = img.resize((int(img.width * scale), int(img.height * scale)))
                            cards, texts = self._read(img)
                            self.last_text = texts[-1] if texts else ""
                            self._preview(img, cards)
                            self.svc.reader_info = {
                                "ocr_language": getattr(self.ocr, "lang_tag", "?"),
                                "game_area": rect, "read_size": f"{img.width}x{img.height}",
                                "last_scan": time.strftime("%H:%M:%S"),
                                "cards_matched": [self.svc.aug_names.get(a, a) for a, _, _ in cards],
                                "text_seen": (texts[0] if texts else "")[:400],
                            }
                            cards = [(a, x / scale, y / scale) for a, x, y in cards]
                            self._status("Reading augment cards" if cards else "Watching for augment cards")
                            if cards:
                                self._calibrate([(a, box[0] + x, box[1] + y) for a, x, y in cards], rect)
                            self._emit(cards, box, band)
                            perf = 1.5 if self.settings.get("perf_mode") else 1
                            lv, gt = int(live.get("level") or 0), float(live.get("time") or 0)
                            if lv > getattr(self, "_last_level", lv) or gt < 75:
                                self._burst_until = max(self._burst_until, time.time() + LEVEL_BURST)
                            self._last_level = lv
                            if time.time() < self._burst_until:
                                pause = SCAN_CLICK
                            elif self.tracker.current is not None:
                                pause = SCAN_FAST * perf
                            else:
                                pause = SCAN_SECONDS * perf
                            self._wake.wait(pause)
                            self._wake.clear()
                            continue
                if self.tracker.current:            # left the screen: settle any open offer
                    evs = []
                    for _ in range(MISS_LIMIT):
                        evs += self.tracker.frame([], time.time(), force=True)
                    for e in evs:
                        if e[0] == "pick":
                            self.svc.on_pick(e[1], e[2])
            except Exception as e:
                self._status(f"Screen reading error: {e.__class__.__name__}: {e}")
            time.sleep(1.2)

    def _scan_client(self, ImageGrab):
        """Champ select: read your champion cards off the League client window."""
        hwnd, rect = client_window()
        if not hwnd:
            self._status("Champ select: League client window not visible")
            return
        if not hasattr(self, "champ_matcher"):
            self.champ_matcher = AugmentMatcher({})
        names = {n: n for n in self.svc.data["champions"]}
        self.champ_matcher.update(names)
        img = ImageGrab.grab(bbox=rect, all_screens=True)
        scale = max(0.6, min(2.0, 900 / img.height))
        if abs(scale - 1) > 0.05:
            img = img.resize((int(img.width * scale), int(img.height * scale)))
        for mode in (0, 1):
            pim, k = _prep(img, mode)
            found = self.champ_matcher.find_offer(self.ocr.read(pim), pim.height)
            if found:
                self.svc.screen_cards = ([n for n, _, _ in found], time.time())
                self._status("Champ select: reading your champion cards")
                return
        self._status("Champ select: watching for your champion cards")

    def _preview(self, img, cards):
        """Small live picture of what's being read, with each recognized card marked (for the app)."""
        try:
            import io
            from PIL import ImageDraw
            k = 960 / img.width
            pv = img.convert("RGB").resize((960, max(1, int(img.height * k))))
            d = ImageDraw.Draw(pv)
            for aid, x, y in cards:
                g = self.svc.grade(aid)[0] or "?"
                cx, cy = x * k, y * k
                d.rounded_rectangle([cx - 90, cy - 16, cx + 90, cy + 16], 8, outline=(25, 200, 180), width=3)
                d.rectangle([cx - 90, cy - 40, cx - 40, cy - 18], fill=(217, 184, 113))
                d.text((cx - 84, cy - 38), g, fill=(12, 18, 32))
            buf = io.BytesIO()
            pv.save(buf, "JPEG", quality=70)
            self.svc.preview = (buf.getvalue(), time.time())
        except Exception:
            pass

    def snapshot(self):
        """Save what LoLStat sees right now (whole game window + the text it read). Returns the folder."""
        import os
        from PIL import ImageGrab
        os.makedirs(self.snap_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        hwnd, rect = league_window() if sys.platform == "win32" else (None, None)
        img = ImageGrab.grab(bbox=rect, all_screens=True) if rect else (self.last_img or ImageGrab.grab(all_screens=True))
        img.save(os.path.join(self.snap_dir, f"LoLStat-{stamp}.png"))
        lines_txt = ""
        found = []
        if self.ocr:
            try:
                for mode in (0, 1):
                    pim, k = _prep(img, mode)
                    lines = self.ocr.read(pim)
                    lines_txt += f"--- pass {mode} ---\n" + "\n".join(" ".join(w["text"] for w in ln) for ln in lines) + "\n"
                    found += [self.svc.aug_names.get(a, a) for a, _, _ in self.matcher.find_offer(lines, pim.height)]
            except Exception as e:
                lines_txt += f"OCR error: {e}\n"
        lines_txt = f"Screen: {img.width}x{img.height}, OCR language: {getattr(self.ocr, 'lang_tag', '?')}, game locale: {self.svc.locale}\n" + lines_txt
        with open(os.path.join(self.snap_dir, f"LoLStat-{stamp}.txt"), "w", encoding="utf-8") as f:
            f.write(f"Status: {self.svc.scanner_status}\nGame window: {rect}\nCards matched: {found}\n"
                    f"Mode: {(self.svc.live or {}).get('mode')}\n\n{lines_txt}")
        self.log(f"Snapshot saved ({len(found)} cards matched).")
        return self.snap_dir

    def _click_loop(self):
        ctypes, wintypes = _win()
        u = ctypes.windll.user32
        was_down = False
        pt = wintypes.POINT()
        while True:
            down = bool(u.GetAsyncKeyState(0x01) & 0x8000)
            if down and not was_down and self.tracker.current:
                u.GetCursorPos(ctypes.byref(pt))
                self.tracker.click(pt.x, pt.y, time.time())
                self._burst_until = time.time() + FAST_AFTER_CLICK
                self._wake.set()                     # read the screen right now (a reroll is coming)
            was_down = down
            time.sleep(CLICK_POLL_SECONDS)
