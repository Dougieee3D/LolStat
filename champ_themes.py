"""
LoLStat champion themes: a theme for every champion and every skin, made from the skin's splash art.
Colors are picked automatically from the art, so new champions and skins work with no update.
Splash art is downloaded once from Riot's Data Dragon and kept on this PC.
"""

import colorsys
import io
import json
import os
import threading
import urllib.request

DD = "https://ddragon.leagueoflegends.com/cdn"
_lock = threading.Lock()


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "LoLStat"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def skins(version, alias, cache_dir):
    """All skins for a champion: [{id, num, name}], default first."""
    path = os.path.join(cache_dir, "skins", f"{alias}.json")
    try:
        with open(path, encoding="utf-8") as f:
            cached = json.load(f)
        if cached.get("version") == version:
            return cached["skins"]
    except Exception:
        cached = None
    try:
        d = json.loads(_get(f"{DD}/{version}/data/en_US/champion/{alias}.json"))["data"][alias]
        out = [{"id": int(s["id"]), "num": int(s["num"]), "name": "Default" if s["name"] == "default" else s["name"]}
               for s in d.get("skins", [])]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"version": version, "skins": out}, f)
        return out
    except Exception:
        return (cached or {}).get("skins") or [{"id": 0, "num": 0, "name": "Default"}]


def art_path(alias, num, cache_dir):
    """Local copy of a skin's splash art (downloaded the first time). None if unavailable."""
    path = os.path.join(cache_dir, "art", f"{alias}_{int(num)}.jpg")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    try:
        data = _get(f"{DD}/img/champion/splash/{alias}_{int(num)}.jpg", timeout=20)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path
    except Exception:
        return None


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def _hsv(h, s, v):
    return _hex([c * 255 for c in colorsys.hsv_to_rgb(h % 1.0, max(0, min(1, s)), max(0, min(1, v)))])


def _hue_gap(a, b):
    d = abs(a - b) % 1.0
    return min(d, 1 - d)


def palette_from_image(img):
    """Pick theme colors from a splash: a dark base tinted by the art, and its two boldest colors as accents."""
    im = img.convert("RGB").resize((160, 94))
    q = im.quantize(colors=20, method=0)
    pal = q.getpalette()[:60]
    counts = sorted(q.getcolors(), key=lambda c: -c[0])
    total = sum(c for c, _ in counts) or 1
    swatches = []
    for n, idx in counts:
        r, g, b = pal[idx * 3: idx * 3 + 3]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        swatches.append({"share": n / total, "h": h, "s": s, "v": v})

    # base hue: the most common colorful area (ignore near-greys)
    colorful = [w for w in swatches if w["s"] > 0.18 and w["v"] > 0.12] or swatches
    base = max(colorful, key=lambda w: w["share"])
    bh, bs = base["h"], min(0.55, max(0.25, base["s"]))

    # accents: bright, saturated and big enough to matter
    def score(w):
        return (w["s"] ** 1.2) * (w["v"] ** 0.8) * (w["share"] ** 0.35)
    cands = sorted([w for w in swatches if w["s"] > 0.22 and w["v"] > 0.30], key=score, reverse=True)
    a1 = cands[0] if cands else {"h": (bh + 0.08) % 1, "s": 0.6, "v": 0.9}
    a2 = (next((w for w in cands[1:] if _hue_gap(w["h"], a1["h"]) > 0.11), None)      # a clearly different color in the art
          or next((w for w in cands[1:] if _hue_gap(w["h"], a1["h"]) > 0.05), None)
          or next((w for w in sorted(swatches, key=lambda w: -w["share"]) if w["s"] > 0.12 and _hue_gap(w["h"], a1["h"]) > 0.05), None)
          or {"h": (a1["h"] + 0.09) % 1, "s": max(0.35, a1["s"] * 0.6), "v": 0.9})

    def accent(w):
        return _hsv(w["h"], max(0.5, min(0.85, w["s"])), max(0.82, min(0.98, w["v"] + 0.25)))

    return {
        "bg": _hsv(bh, bs, 0.075), "rail": _hsv(bh, bs, 0.055),
        "panel": _hsv(bh, bs * 0.85, 0.13), "raised": _hsv(bh, bs * 0.8, 0.19),
        "line": _hsv(bh, bs * 0.6, 0.27),
        "text": _hsv(bh, 0.06, 0.96), "muted": _hsv(bh, 0.16, 0.70),
        "accent": accent(a1), "accent2": accent(a2),
    }


def theme_for(version, champ_name, alias, num, cache_dir, skin_name=""):
    """Full theme for a champion skin (cached). Falls back to the default skin, then to fixed colors."""
    key = os.path.join(cache_dir, "themes", f"{alias}_{int(num)}.json")
    try:
        with open(key, encoding="utf-8") as f:
            t = json.load(f)
        if t.get("v") == 2:
            return t
    except Exception:
        pass
    path = art_path(alias, num, cache_dir) or (art_path(alias, 0, cache_dir) if num else None)
    colors = None
    if path:
        try:
            from PIL import Image
            with _lock:
                colors = palette_from_image(Image.open(path))
        except Exception:
            colors = None
    if not colors:
        colors = {"bg": "#0c1220", "rail": "#0a0f1b", "panel": "#131b2e", "raised": "#1a2440", "line": "#26314d",
                  "text": "#ece6d6", "muted": "#8e96ab", "accent": "#d9b871", "accent2": "#19c8b4"}
    name = skin_name if skin_name and skin_name != "Default" else champ_name
    t = dict(colors, v=2, name=name, champion=champ_name, alias=alias, num=int(num), skin=skin_name or "Default",
             art=bool(path), alpha=0.84, radius=14, overlay=0.9)
    if path:
        os.makedirs(os.path.dirname(key), exist_ok=True)
        with open(key, "w", encoding="utf-8") as f:
            json.dump(t, f)
    return t


def overlay_colors(t):
    return {"glass": t["panel"], "edge": t["line"], "text": t["text"], "muted": t["muted"],
            "accent": t["accent"], "accent2": t["accent2"], "alpha": t.get("overlay", 0.9)}
