"""
LoLStat fun: Chaos mode weekly challenges, daily and weekly missions, the augment collection,
the build lab (with item vs item comparisons) and tilt guard. All computed from your own games.
"""

from datetime import date, datetime, timedelta

import mayhem_engine as eng

# ------------------------------------------------------------------ Chaos mode
CHALLENGES = [
    {"id": "glass", "name": "Glass cannon", "desc": "Only items with no armor, magic resist or health.",
     "rule": lambda it: not ({"armor", "mr", "hp"} & set(it["stats"]))},
    {"id": "onhit", "name": "On-hit everything", "desc": "Only items with on-hit effects or attack speed.",
     "rule": lambda it: "onhit" in it["feats"] or "as" in it["stats"]},
    {"id": "tankdmg", "name": "Tanky damage", "desc": "Every item must give health. Win with sheer bulk.",
     "rule": lambda it: "hp" in it["stats"]},
    {"id": "barefoot", "name": "Barefoot", "desc": "No boots. Five damage items and nothing else.",
     "rule": lambda it: True, "no_boots": True},
    {"id": "crit", "name": "Crit or bust", "desc": "Only items with critical strike chance.",
     "rule": lambda it: "crit" in it["stats"]},
    {"id": "vamp", "name": "Vampire", "desc": "Only items with life steal, omnivamp or healing effects.",
     "rule": lambda it: bool({"ls", "omni"} & set(it["stats"]))},
    {"id": "haste", "name": "Spell spam", "desc": "Only items with 15 or more ability haste.",
     "rule": lambda it: it["stats"].get("haste", 0) >= 15},
    {"id": "offtype", "name": "Wrong damage", "desc": "Build the opposite damage type: AP champions go AD, AD champions go AP.",
     "rule": None},
    {"id": "pen", "name": "Armor and MR are a myth", "desc": "Only items with armor or magic penetration or lethality.",
     "rule": lambda it: bool({"arpen", "mpen", "mpen_pct", "leth"} & set(it["stats"]))},
    {"id": "procs", "name": "Proc machine", "desc": "Only items with a damage passive: burn, spellblade or percent-health damage.",
     "rule": lambda it: bool({"burn", "spellblade", "maxhp", "curhp"} & set(it["feats"]))},
]


def week_key(d=None):
    d = d or date.today()
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def challenge_for(d=None):
    d = d or date.today()
    y, w, _ = d.isocalendar()
    return CHALLENGES[(y * 53 + w) % len(CHALLENGES)]


def _rule(ch, champ_data):
    if ch["id"] == "offtype":
        want = "ap" if champ_data.get("dmg") == "ad" else "ad"
        return lambda it: want in it["stats"]
    return ch["rule"]


def chaos_build(champion, data, mode="sr", ch=None):
    ch = ch or challenge_for()
    c = data["champions"].get(champion)
    if not c:
        return None
    rule = _rule(ch, c)
    b = eng.make_builds(champion, [], [], data, mode=mode, item_filter=rule, no_boots=ch.get("no_boots", False))
    return b[0] if b else None


def chaos_games(games, data):
    """Your games that followed this week's challenge (3+ finished items obey the rule), scored by damage/min."""
    ch = challenge_for()
    wk = week_key()
    out = []
    for g in games:
        d = datetime.fromtimestamp(g["when"] / 1000).date()
        if week_key(d) != wk:
            continue
        c = data["champions"].get(g["me"]["champ"], {})
        rule = _rule(ch, c)
        legend = [data["items"][str(i)] for i in g["me"].get("items", []) if str(i) in data["items"] and not data["items"][str(i)]["boots"]]
        boots = any(data["items"].get(str(i), {}).get("boots") for i in g["me"].get("items", []))
        if len(legend) >= 3 and sum(1 for it in legend if rule(it)) >= 3 and not (ch.get("no_boots") and boots):
            out.append({"id": g["id"], "champ": g["me"]["champ"], "win": g["me"]["win"], "dpm": g["me"]["dpm"],
                        "dmg": g["me"]["dmg"], "when": g["when"], "k": g["me"]["k"], "d": g["me"]["d"], "a": g["me"]["a"]})
    return sorted(out, key=lambda x: -x["dpm"])


# ------------------------------------------------------------------ missions
def _m(mid, text, goal, fn):
    return {"id": mid, "text": text, "goal": goal, "fn": fn}


DAILY_POOL = [
    _m("win1", "Win a game", 1, lambda gs, ctx: sum(g["me"]["win"] for g in gs)),
    _m("play3", "Play 3 games", 3, lambda gs, ctx: len(gs)),
    _m("dmg30", "Deal 30,000 damage in one game", 30000, lambda gs, ctx: max([g["me"]["dmg"] for g in gs] or [0])),
    _m("kills10", "Get 10 kills in one game", 10, lambda gs, ctx: max([g["me"]["k"] for g in gs] or [0])),
    _m("assist15", "Get 15 assists in one game", 15, lambda gs, ctx: max([g["me"]["a"] for g in gs] or [0])),
    _m("kda4", "Finish a game with a KDA of 4 or more", 1, lambda gs, ctx: sum(1 for g in gs if (g["me"]["k"] + g["me"]["a"]) / max(1, g["me"]["d"]) >= 4)),
    _m("mayhem", "Play an ARAM Mayhem game", 1, lambda gs, ctx: sum(1 for g in gs if g["queueId"] == 2400)),
    _m("multi", "Get a triple kill or better", 1, lambda gs, ctx: sum(1 for g in gs if g["me"].get("multi", 0) >= 3)),
    _m("safe", "Win a game dying 3 times or less", 1, lambda gs, ctx: sum(1 for g in gs if g["me"]["win"] and g["me"]["d"] <= 3)),
    _m("share", "Deal 30% of your team's damage", 1, lambda gs, ctx: sum(1 for g in gs if g["me"]["share"] >= 30)),
    _m("newchamp", "Play a champion you haven't played this week", 1, lambda gs, ctx: sum(1 for g in gs if g["me"]["champ"] not in ctx["week_champs_before"])),
    _m("sgrade", "Take an S-tier augment in ARAM Mayhem", 1, lambda gs, ctx: ctx["s_augments_today"]),
]
WEEKLY_POOL = [
    _m("w_win10", "Win 10 games", 10, lambda gs, ctx: sum(g["me"]["win"] for g in gs)),
    _m("w_champs5", "Play 5 different champions", 5, lambda gs, ctx: len({g["me"]["champ"] for g in gs})),
    _m("w_dmg300", "Deal 300,000 damage in total", 300000, lambda gs, ctx: sum(g["me"]["dmg"] for g in gs)),
    _m("w_triple3", "Get 3 triple kills or better", 3, lambda gs, ctx: sum(1 for g in gs if g["me"].get("multi", 0) >= 3)),
    _m("w_mayhem3", "Win 3 ARAM Mayhem games", 3, lambda gs, ctx: sum(1 for g in gs if g["queueId"] == 2400 and g["me"]["win"])),
    _m("w_chaos", "Finish a Chaos mode challenge game", 1, lambda gs, ctx: ctx["chaos_games"]),
    _m("w_kills50", "Get 50 kills", 50, lambda gs, ctx: sum(g["me"]["k"] for g in gs)),
    _m("w_streak3", "Win 3 games in a row", 3, lambda gs, ctx: ctx["week_best_streak"]),
]


def _pick(pool, seed, n=3):
    import random
    return random.Random(seed).sample(pool, min(n, len(pool)))


def _day_games(games, d):
    return [g for g in games if datetime.fromtimestamp(g["when"] / 1000).date() == d]


def missions(games, data, mayhem_history, grade_of):
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    week = [g for g in games if datetime.fromtimestamp(g["when"] / 1000).date() >= monday]
    todays = _day_games(games, today)

    def s_augs_on(d):
        n = 0
        for h in mayhem_history or []:
            try:
                hd = datetime.strptime(h.get("when", ""), "%b %d, %I:%M %p").replace(year=today.year).date()
            except Exception:
                continue
            if hd == d:
                n += sum(1 for a in h.get("augments", []) if grade_of(a) in ("S", "S+"))
        return n

    def ctx_for(d, day_games):
        week_before = [g for g in games if monday <= datetime.fromtimestamp(g["when"] / 1000).date() < d]
        return {"week_champs_before": {g["me"]["champ"] for g in week_before}, "s_augments_today": s_augs_on(d)}

    def run(defs, gs, ctx):
        out = []
        for m in defs:
            try:
                v = m["fn"](gs, ctx)
            except Exception:
                v = 0
            out.append({"id": m["id"], "text": m["text"], "goal": m["goal"], "now": min(v, m["goal"]), "done": v >= m["goal"]})
        return out
    daily = run(_pick(DAILY_POOL, today.toordinal()), todays, ctx_for(today, todays))
    from insights import streaks
    wk_chron = sorted(week, key=lambda g: -g["when"])
    wctx = {"chaos_games": len(chaos_games(week, data)), "week_best_streak": streaks(wk_chron)[1] if wk_chron else 0}
    weekly = run(_pick(WEEKLY_POOL, monday.toordinal() // 7, 3), week, wctx)
    # streak: consecutive past days (yesterday backwards, today included if done) with every daily mission done
    streak, d = 0, today
    for _ in range(60):
        dg = _day_games(games, d)
        done = all(x["done"] for x in run(_pick(DAILY_POOL, d.toordinal()), dg, ctx_for(d, dg)))
        if done:
            streak += 1
        elif d != today:
            break
        d -= timedelta(days=1)
    return {"daily": daily, "weekly": weekly, "streak": streak,
            "resets_in_h": round((datetime.combine(today + timedelta(days=1), datetime.min.time()) - datetime.now()).seconds / 3600, 1)}


# ------------------------------------------------------------------ augment collection
def collection(data, mayhem_history, grade_of):
    taken = {}
    for h in mayhem_history or []:
        for name in h.get("augments", []):
            r = taken.setdefault(name, {"games": 0, "wins": 0})
            r["games"] += 1
            r["wins"] += 1 if h.get("win") else 0
    rows = []
    for aid, a in data["augments"].items():
        t = taken.get(a["name"])
        rows.append({"id": aid, "name": a["name"], "tier": a["tier"], "icon": a.get("icon", ""), "grade": grade_of(aid),
                     "games": t["games"] if t else 0, "wr": round(t["wins"] / t["games"] * 100) if t else None})
    order = {"Prismatic": 0, "Gold": 1, "Silver": 2}
    rows.sort(key=lambda r: (r["games"] == 0, order.get(r["tier"], 3), -r["games"], r["name"]))
    return {"augments": rows, "tried": sum(1 for r in rows if r["games"]), "total": len(rows)}


# ------------------------------------------------------------------ build lab
PROFILES = {"Squishy": (40, 40, 2200), "Bruiser": (110, 80, 3600), "Tank": (220, 160, 5200)}


def build_lab(champion, item_ids, enemies, data, champ_items=None):
    ch = data["champions"].get(champion)
    if not ch:
        return {"error": "Pick a champion"}
    items = [data["items"][str(i)] for i in item_ids if str(i) in data["items"]]
    tot = {}
    for it in items:
        for k, v in it["stats"].items():
            tot[k] = tot.get(k, 0) + v
    feats = sorted({f for it in items for f in it["feats"]})
    gold = sum(it["gold"] for it in items)
    dmg = ch.get("dmg", "ad")
    # rough effective damage against three target types: physical and magic, after penetration
    out = {}
    for name, (armor, mr, hp) in PROFILES.items():
        eff_arm = max(0, armor * (1 - tot.get("arpen", 0) / 100) - tot.get("leth", 0))
        eff_mr = max(0, mr * (1 - tot.get("mpen_pct", 0) / 100) - tot.get("mpen", 0))
        phys = (60 + tot.get("ad", 0)) * (1 + tot.get("crit", 0) / 100 * (0.75 + tot.get("critdmg", 0) / 100)) * (1 + tot.get("as", 0) / 100 * 0.6)
        magic = (40 + tot.get("ap", 0)) * (1.3 if "ap_amp" in feats else 1) * (1 + tot.get("haste", 0) / 200)
        bonus = (0.05 * hp * ("maxhp" in feats) + 0.04 * hp * ("curhp" in feats) + 40 * ("burn" in feats) + 60 * ("spellblade" in feats))
        w_ad = 1.0 if dmg == "ad" else 0.35 if dmg == "ap" else 0.65
        w_ap = 1.0 if dmg == "ap" else 0.35 if dmg == "ad" else 0.65
        score = phys * w_ad * 100 / (100 + eff_arm) + magic * w_ap * 100 / (100 + eff_mr) + bonus
        out[name] = round(score)
    # LoLStat's own weighting for this champion against the chosen enemy team
    weights = eng.champion_weights(ch)
    if enemies:
        prof = eng.enemy_profile(enemies, data)
        for k, v in eng.enemy_weights(prof, dmg).items():
            weights[k] = weights.get(k, 0) + v
    core = [it for it in items if not it["boots"]]           # boots aren't part of the damage comparison
    value = sum(eng.item_score(it, weights, ch, set())[0] for it in core)
    best = eng.make_builds(champion, [], enemies, data, mode="sr", champ_items=champ_items)
    best_value = 0
    if best and core:
        bi = [data["items"][x["id"]] for x in best[0]["items"] if x["id"] in data["items"]]
        best_value = sum(eng.item_score(it, weights, ch, set())[0] for it in bi[:len(core)])
    return {"stats": {k: round(v, 1) for k, v in tot.items()}, "feats": feats, "gold": gold, "vs": out,
            "value": round(value), "best_value": round(best_value),
            "rating": round(value / best_value * 100) if best_value else None}


def compare_items(champion, a, b, enemies, data):
    ch = data["champions"].get(champion)
    ia, ib = data["items"].get(str(a)), data["items"].get(str(b))
    if not ch or not ia or not ib:
        return {"error": "Pick a champion and two items"}
    weights = eng.champion_weights(ch)
    prof = eng.enemy_profile(enemies or [], data)
    for k, v in eng.enemy_weights(prof, ch.get("dmg", "ad")).items():
        weights[k] = weights.get(k, 0) + v
    sa, pa = eng.item_score(ia, weights, ch, set())
    sb, pb = eng.item_score(ib, weights, ch, set())
    reason = lambda parts: [eng.REASON.get(k, k).format(tanks="tanky enemies", healers="healers", shielders="shields")
                            for k, _ in sorted(parts.items(), key=lambda kv: -kv[1])[:3]]
    win = ia["name"] if sa >= sb else ib["name"]
    return {"a": {"name": ia["name"], "score": round(sa), "why": reason(pa), "gold": ia["gold"]},
            "b": {"name": ib["name"], "score": round(sb), "why": reason(pb), "gold": ib["gold"]},
            "winner": win, "margin": round(abs(sa - sb) / max(1, min(sa, sb)) * 100) if min(sa, sb) > 0 else None}


# ------------------------------------------------------------------ tilt guard
def tilt_check(games, losses_needed=3, window_h=6):
    """Losses in a row in the last few hours (newest first). Returns the count, 0 if not on a losing run."""
    now = datetime.now().timestamp() * 1000
    run = 0
    for g in games:
        if now - g["when"] > window_h * 3600_000:
            break
        if g["me"]["win"]:
            break
        run += 1
    return run if run >= losses_needed else 0
