"""
LoLStat insights: a local archive of your games (all 10 players) and everything computed from it:
post-game coach, records and badges, LP history, duo partners, rivals, habits, champion journey,
season wrap-up, highlights. Everything stays on this PC.
"""

import json
import os
import threading
import time
from datetime import datetime

import lcu_stats

KEEP_GAMES = 500


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def compact_game(g, my_puuid, champ_name):
    """Full LCU game -> compact record with me + all 10 players."""
    ids = {}
    for ident in g.get("participantIdentities") or []:
        pl = ident.get("player") or {}
        name = f"{pl.get('gameName') or pl.get('summonerName') or ''}#{pl.get('tagLine') or ''}".strip("#")
        ids[ident.get("participantId")] = (pl.get("puuid"), name)
    players, me = [], None
    dur = max(1, int(g.get("gameDuration") or 0))
    for p in g.get("participants") or []:
        st = p.get("stats") or {}
        puuid, name = ids.get(p.get("participantId"), (None, ""))
        row = {"pid": p.get("participantId"), "puuid": puuid, "name": name, "champ": champ_name(p.get("championId")),
               "team": p.get("teamId"), "win": bool(st.get("win")),
               "k": int(st.get("kills") or 0), "d": int(st.get("deaths") or 0), "a": int(st.get("assists") or 0),
               "dmg": int(st.get("totalDamageDealtToChampions") or 0)}
        players.append(row)
        if puuid and puuid == my_puuid:
            cs = int(st.get("totalMinionsKilled") or 0) + int(st.get("neutralMinionsKilled") or 0)
            me = dict(row, phys=int(st.get("physicalDamageDealtToChampions") or 0),
                      magic=int(st.get("magicDamageDealtToChampions") or 0),
                      true=int(st.get("trueDamageDealtToChampions") or 0),
                      taken=int(st.get("totalDamageTaken") or 0), heal=int(st.get("totalHeal") or 0),
                      gold=int(st.get("goldEarned") or 0), cs=cs, level=int(st.get("champLevel") or 0),
                      items=[int(st.get(f"item{i}") or 0) for i in range(7)],
                      multi=int(st.get("largestMultiKill") or 0), penta=int(st.get("pentaKills") or 0),
                      quadra=int(st.get("quadraKills") or 0), triple=int(st.get("tripleKills") or 0),
                      fb=bool(st.get("firstBloodKill")), vision=int(st.get("visionScore") or 0),
                      spree=int(st.get("largestKillingSpree") or 0))
    if not me:
        return None
    team_k = sum(p["k"] for p in players if p["team"] == me["team"]) or 1
    team_dmg = sum(p["dmg"] for p in players if p["team"] == me["team"]) or 1
    mins = dur / 60
    me.update(kp=round((me["k"] + me["a"]) / team_k * 100), share=round(me["dmg"] / team_dmg * 100),
              dpm=round(me["dmg"] / mins), csm=round(me["cs"] / mins, 1))
    return {"id": g.get("gameId"), "when": int(g.get("gameCreation") or 0), "minutes": round(mins, 1),
            "queueId": g.get("queueId"), "queue": lcu_stats._queue(g.get("queueId")), "mode": g.get("gameMode", ""),
            "remake": dur < 300, "me": me, "players": players}


class Archive:
    def __init__(self, data_dir, log=print):
        self.dir = data_dir
        self.log = log
        self.path = os.path.join(data_dir, "archive.json")
        self.lp_path = os.path.join(data_dir, "lp_history.json")
        self.notes_path = os.path.join(data_dir, "journal.json")
        self.lock = threading.Lock()
        a = _load(self.path, {})
        self.puuid = a.get("puuid")
        self.games = {str(k): v for k, v in (a.get("games") or {}).items()}
        self.lp = _load(self.lp_path, [])
        self.notes = _load(self.notes_path, {})
        self.version = 0
        self.coach = None

    # ---------------------------------------------------------- syncing
    def sync(self, lcu_call, champ_name, max_new=6):
        """Add your newest games (full detail) to the archive. Returns how many were added."""
        me = lcu_call("GET", "/lol-summoner/v1/current-summoner") or {}
        puuid = me.get("puuid")
        if not puuid:
            return 0
        if puuid != self.puuid:                       # another account logged in: separate archive
            self.puuid, self.games = puuid, {}
            other = _load(os.path.join(self.dir, f"archive_{puuid[:12]}.json"), {})
            self.games = {str(k): v for k, v in (other.get("games") or {}).items()}
        new_ids = []
        for beg in range(0, 200, 20):                # page back through the client's history
            res = lcu_call("GET", f"/lol-match-history/v1/products/lol/current-summoner/matches?begIndex={beg}&endIndex={beg + 19}") or {}
            page = ((res.get("games") or {}).get("games")) or []
            fresh = [str(g.get("gameId")) for g in page if str(g.get("gameId")) not in self.games]
            new_ids += fresh
            if len(page) < 20 or (not fresh and beg >= 40) or len(new_ids) >= max_new:
                break
        added = 0
        for gid in new_ids[:max_new]:
            try:
                full = lcu_call("GET", f"/lol-match-history/v1/games/{gid}")
                rec = compact_game(full or {}, puuid, champ_name)
                if rec:
                    with self.lock:
                        self.games[gid] = rec
                    added += 1
            except Exception:
                continue
            time.sleep(0.4)
        if added:
            self._persist()
        return added

    def _persist(self):
        with self.lock:
            keep = dict(sorted(self.games.items(), key=lambda kv: -kv[1]["when"])[:KEEP_GAMES])
            self.games = keep
            self.version += 1
            data = {"puuid": self.puuid, "games": keep}
        _save(self.path, data)
        if self.puuid:
            _save(os.path.join(self.dir, f"archive_{self.puuid[:12]}.json"), data)

    def list(self, include_remakes=False):
        with self.lock:
            gs = sorted(self.games.values(), key=lambda g: -g["when"])
        return gs if include_remakes else [g for g in gs if not g["remake"]]

    # ---------------------------------------------------------- LP history
    def record_lp(self, ranks):
        changed = False
        now = int(time.time() * 1000)
        for r in ranks or []:
            if r["type"] not in ("RANKED_SOLO_5x5", "RANKED_FLEX_SR") or r["tier"] in ("", "NONE"):
                continue
            score = lcu_stats._lp_score(r)
            last = next((x for x in reversed(self.lp) if x["q"] == r["type"]), None)
            if not last or last["score"] != score:
                self.lp.append({"t": now, "q": r["type"], "score": score, "label": r["label"], "lp": r["lp"]})
                changed = True
        if changed:
            self.lp = self.lp[-2000:]
            _save(self.lp_path, self.lp)

    # ---------------------------------------------------------- journal
    def set_note(self, game_id, mood=None, text=None):
        n = self.notes.get(str(game_id), {})
        if mood is not None:
            n["mood"] = mood
        if text is not None:
            n["text"] = text[:300]
        n["t"] = int(time.time())
        self.notes[str(game_id)] = n
        _save(self.notes_path, self.notes)


# -------------------------------------------------------------- calculations
def _avg(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0


def overview(games):
    if not games:
        return {"games": 0}
    n = len(games)
    me = [g["me"] for g in games]
    return {"games": n, "wins": sum(m["win"] for m in me), "wr": round(sum(m["win"] for m in me) / n * 100),
            "kda": round(sum(m["k"] + m["a"] for m in me) / max(1, sum(m["d"] for m in me)), 2),
            "dpm": round(_avg(m["dpm"] for m in me)), "csm": round(_avg(m["csm"] for m in me), 1),
            "kp": round(_avg(m["kp"] for m in me)), "hours": round(sum(g["minutes"] for g in games) / 60, 1)}


def streaks(games):
    """Current and longest win streak (games newest first)."""
    cur = 0
    for g in games:
        if g["me"]["win"] and cur >= 0:
            cur += 1
        elif not g["me"]["win"] and cur <= 0:
            cur -= 1
        else:
            break
    best = run = 0
    for g in reversed(games):
        run = run + 1 if g["me"]["win"] else 0
        best = max(best, run)
    return cur, best


RECORDS = [("dmg", "Most damage", "{:,} damage"), ("k", "Most kills", "{} kills"), ("a", "Most assists", "{} assists"),
           ("dpm", "Highest damage per minute", "{:,} per minute"), ("csm", "Best CS per minute", "{} CS/min"),
           ("gold", "Most gold", "{:,} gold"), ("heal", "Most healing", "{:,} healed"),
           ("taken", "Most damage taken", "{:,} taken"), ("spree", "Longest killing spree", "{} in a row"),
           ("vision", "Best vision score", "{} vision")]


def records(games):
    out = []
    for key, label, fmtv in RECORDS:
        best = max(games, key=lambda g: g["me"].get(key, 0), default=None)
        if best and best["me"].get(key, 0) > 0:
            out.append({"key": key, "label": label, "value": fmtv.format(best["me"][key]),
                        "champ": best["me"]["champ"], "when": best["when"], "id": best["id"], "queue": best["queue"]})
    kda = max(games, key=lambda g: (g["me"]["k"] + g["me"]["a"]) / max(1, g["me"]["d"]), default=None)
    if kda:
        m = kda["me"]
        out.insert(3, {"key": "kda", "label": "Best KDA", "value": f"{m['k']}/{m['d']}/{m['a']}", "champ": m["champ"],
                       "when": kda["when"], "id": kda["id"], "queue": kda["queue"]})
    return out


BADGES = [
    ("first_win", "First blood of the archive", "Win a game", lambda s: s["wins"] >= 1),
    ("ten_wins", "Double digits", "Win 10 games", lambda s: s["wins"] >= 10),
    ("fifty_wins", "Veteran", "Win 50 games", lambda s: s["wins"] >= 50),
    ("hundred_games", "Dedicated", "Play 100 games", lambda s: s["games"] >= 100),
    ("penta", "PENTAKILL", "Get a pentakill", lambda s: s["penta"] >= 1),
    ("quadra", "Quadra", "Get a quadra kill", lambda s: s["quadra"] >= 1),
    ("triple", "Triple threat", "Get a triple kill", lambda s: s["triple"] >= 1),
    ("streak5", "On fire", "Win 5 games in a row", lambda s: s["best_streak"] >= 5),
    ("streak10", "Unstoppable", "Win 10 games in a row", lambda s: s["best_streak"] >= 10),
    ("dmg50k", "Glass cannon", "Deal 50,000 damage in one game", lambda s: s["max_dmg"] >= 50000),
    ("dmg100k", "Nuclear", "Deal 100,000 damage in one game", lambda s: s["max_dmg"] >= 100000),
    ("kills20", "Slaughter", "Get 20 kills in one game", lambda s: s["max_k"] >= 20),
    ("deathless", "Untouchable", "Win a game without dying", lambda s: s["deathless"] >= 1),
    ("perfect10", "Perfect game", "Win with 10+ kills and no deaths", lambda s: s["perfect"] >= 1),
    ("support", "Team player", "Get 30 assists in one game", lambda s: s["max_a"] >= 30),
    ("pool10", "Champion pool", "Win with 10 different champions", lambda s: s["champs_won"] >= 10),
    ("pool30", "Jack of all trades", "Win with 30 different champions", lambda s: s["champs_won"] >= 30),
    ("firstblood", "First blood", "Get first blood 5 times", lambda s: s["fb"] >= 5),
    ("marathon", "Marathon", "Win a game over 40 minutes", lambda s: s["long_win"] >= 1),
    ("stomp", "Stomp", "Win a game under 20 minutes", lambda s: s["short_win"] >= 1),
    ("nightowl", "Night owl", "Win 10 games after midnight", lambda s: s["night_wins"] >= 10),
    ("allmodes", "Explorer", "Play 4 different game modes", lambda s: s["modes"] >= 4),
    ("mayhem", "Agent of chaos", "Win 10 ARAM Mayhem games", lambda s: s["mayhem_wins"] >= 10),
    ("carry", "Carry", "Deal 40% of your team's damage in a win", lambda s: s["carry"] >= 1),
]


def badge_stats(games):
    me = [g["me"] for g in games]
    wins = [g for g in games if g["me"]["win"]]
    return {"games": len(games), "wins": len(wins), "penta": sum(m["penta"] for m in me),
            "quadra": sum(m["quadra"] for m in me), "triple": sum(m["triple"] for m in me),
            "best_streak": streaks(games)[1], "max_dmg": max((m["dmg"] for m in me), default=0),
            "max_k": max((m["k"] for m in me), default=0), "max_a": max((m["a"] for m in me), default=0),
            "deathless": sum(1 for g in wins if g["me"]["d"] == 0),
            "perfect": sum(1 for g in wins if g["me"]["d"] == 0 and g["me"]["k"] >= 10),
            "champs_won": len({g["me"]["champ"] for g in wins}), "fb": sum(1 for m in me if m["fb"]),
            "long_win": sum(1 for g in wins if g["minutes"] >= 40), "short_win": sum(1 for g in wins if g["minutes"] < 20),
            "night_wins": sum(1 for g in wins if 0 <= datetime.fromtimestamp(g["when"] / 1000).hour < 5),
            "modes": len({g["queue"] for g in games}), "mayhem_wins": sum(1 for g in wins if g["queueId"] == 2400),
            "carry": sum(1 for g in wins if g["me"]["share"] >= 40)}


def badges(games):
    s = badge_stats(games)
    return [{"id": b[0], "name": b[1], "how": b[2], "got": bool(b[3](s))} for b in BADGES]


def people(games, friend_puuids, my_puuid):
    """Duo partners (friends you've played with) and rivals (enemies you keep meeting)."""
    duo, rival, regular = {}, {}, {}
    for g in games:
        my_team = g["me"]["team"]
        for p in g["players"]:
            if not p.get("puuid") or p["puuid"] == my_puuid:
                continue
            same = p["team"] == my_team
            key = p["puuid"]
            book = duo if (same and key in friend_puuids) else regular if same else rival
            r = book.setdefault(key, {"puuid": key, "name": p["name"], "games": 0, "wins": 0, "champs": {}})
            r["games"] += 1
            r["wins"] += g["me"]["win"]
            r["champs"][p["champ"]] = r["champs"].get(p["champ"], 0) + 1
            r["name"] = p["name"] or r["name"]
            r["last"] = max(r.get("last", 0), g["when"])

    def finish(book, min_games):
        rows = []
        for r in book.values():
            if r["games"] < min_games:
                continue
            r["wr"] = round(r["wins"] / r["games"] * 100)
            r["main"] = max(r["champs"], key=r["champs"].get) if r["champs"] else ""
            del r["champs"]
            rows.append(r)
        return sorted(rows, key=lambda r: (-r["games"], -r["wr"]))
    duos = finish(duo, 1) + [dict(r, premade=True) for r in finish(regular, 3)]
    return {"duos": sorted(duos, key=lambda r: (-r["games"], -r["wr"]))[:20], "rivals": finish(rival, 2)[:20]}


def habits(games):
    def bucket(rows, keyf, order):
        out = {k: {"label": k, "games": 0, "wins": 0} for k in order}
        for g in rows:
            k = keyf(g)
            if k in out:
                out[k]["games"] += 1
                out[k]["wins"] += g["me"]["win"]
        return [dict(v, wr=round(v["wins"] / v["games"] * 100) if v["games"] else None) for v in out.values()]

    def tod(g):
        h = datetime.fromtimestamp(g["when"] / 1000).hour
        return "Morning" if 5 <= h < 12 else "Afternoon" if h < 17 else "Evening" if h < 22 else "Late night"

    def length(g):
        m = g["minutes"]
        return "Under 20 min" if m < 20 else "20-30 min" if m < 30 else "30-40 min" if m < 40 else "40+ min"
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    # games played in a row: how do you do on game 1, 2, 3, 4+ of a session (gap > 90 min starts a new session)
    chron = sorted(games, key=lambda g: g["when"])
    pos, last_end, n = {}, 0, 0
    for g in chron:
        n = n + 1 if g["when"] - last_end < 90 * 60_000 else 1
        last_end = g["when"] + g["minutes"] * 60_000
        pos[g["id"]] = n
    return {"time": bucket(games, tod, ["Morning", "Afternoon", "Evening", "Late night"]),
            "length": bucket(games, length, ["Under 20 min", "20-30 min", "30-40 min", "40+ min"]),
            "day": bucket(games, lambda g: days[datetime.fromtimestamp(g["when"] / 1000).weekday()], days),
            "session": bucket(games, lambda g: "Game 1" if pos[g["id"]] == 1 else "Game 2" if pos[g["id"]] == 2
                              else "Game 3" if pos[g["id"]] == 3 else "Game 4+", ["Game 1", "Game 2", "Game 3", "Game 4+"]),
            "queue": sorted(bucket(games, lambda g: g["queue"], sorted({g["queue"] for g in games})),
                            key=lambda b: -b["games"])}


def journey(games, champ):
    rows = sorted([g for g in games if g["me"]["champ"] == champ], key=lambda g: g["when"])
    if not rows:
        return None
    trend, w = [], 0
    for i, g in enumerate(rows, 1):
        w += g["me"]["win"]
        trend.append({"t": g["when"], "wr": round(w / i * 100), "win": g["me"]["win"], "dpm": g["me"]["dpm"]})
    best = max(rows, key=lambda g: (g["me"]["win"], (g["me"]["k"] + g["me"]["a"]) / max(1, g["me"]["d"]), g["me"]["dmg"]))
    return {"champion": champ, "games": len(rows), "summary": overview(rows), "trend": trend,
            "first": rows[0]["when"], "last": rows[-1]["when"],
            "best": {"id": best["id"], "when": best["when"], "k": best["me"]["k"], "d": best["me"]["d"],
                     "a": best["me"]["a"], "dmg": best["me"]["dmg"], "win": best["me"]["win"], "queue": best["queue"]}}


def champions_list(games):
    by = {}
    for g in games:
        c = g["me"]["champ"]
        r = by.setdefault(c, {"champion": c, "games": 0, "wins": 0})
        r["games"] += 1
        r["wins"] += g["me"]["win"]
    return sorted([dict(r, wr=round(r["wins"] / r["games"] * 100)) for r in by.values()], key=lambda r: -r["games"])


def highlights(games):
    out = []
    for g in games[:80]:
        m = g["me"]
        tags = []
        if m["penta"]:
            tags.append("Pentakill")
        elif m["quadra"]:
            tags.append("Quadra kill")
        elif m["triple"]:
            tags.append("Triple kill")
        if m["d"] == 0 and m["win"] and m["k"] + m["a"] >= 8:
            tags.append("Deathless")
        if m["share"] >= 38:
            tags.append(f"{m['share']}% of team damage")
        if (m["k"] + m["a"]) / max(1, m["d"]) >= 8:
            tags.append("Huge KDA")
        if m["spree"] >= 8:
            tags.append(f"{m['spree']}-kill spree")
        if tags:
            out.append({"id": g["id"], "when": g["when"], "champ": m["champ"], "win": m["win"], "queue": g["queue"],
                        "k": m["k"], "d": m["d"], "a": m["a"], "dmg": m["dmg"], "tags": tags})
    return out[:15]


def season(games, year=None):
    year = year or datetime.now().year
    rows = [g for g in games if datetime.fromtimestamp(g["when"] / 1000).year == year]
    if not rows:
        return {"year": year, "games": 0}
    ov = overview(rows)
    champs = champions_list(rows)
    me = [g["me"] for g in rows]
    months = {}
    for g in rows:
        mo = datetime.fromtimestamp(g["when"] / 1000).strftime("%b")
        months[mo] = months.get(mo, 0) + 1
    return {"year": year, **ov, "top": champs[:3], "champions": len(champs),
            "kills": sum(m["k"] for m in me), "damage": sum(m["dmg"] for m in me),
            "pentas": sum(m["penta"] for m in me), "best_month": max(months, key=months.get),
            "best_streak": streaks(sorted(rows, key=lambda g: -g["when"]))[1],
            "fav_mode": max({g["queue"] for g in rows}, key=lambda q: sum(1 for g in rows if g["queue"] == q))}


def coach(game, games, timeline=None):
    """Plain-English recap of one game against your own history."""
    m = game["me"]
    same = [g for g in games if g["me"]["champ"] == m["champ"] and g["id"] != game["id"]]
    pool = same if len(same) >= 3 else [g for g in games if g["id"] != game["id"]]
    base = f"your {m['champ']} average" if len(same) >= 3 else "your average"
    tips = []

    def compare(val, avg, label, unit="", good_up=True):
        if not avg:
            return
        diff = (val - avg) / avg * 100
        if abs(diff) < 10:
            return
        better = diff > 0 if good_up else diff < 0
        tips.append({"good": better, "text": f"{label}: {val:,}{unit}, {abs(round(diff))}% {'above' if diff > 0 else 'below'} {base}."})
    compare(m["dpm"], _avg(g["me"]["dpm"] for g in pool), "Damage per minute")
    if game["queueId"] not in (450, 2400):
        compare(m["csm"], _avg(g["me"]["csm"] for g in pool), "CS per minute", "", True)
    compare(m["d"], _avg(g["me"]["d"] for g in pool), "Deaths", "", False)
    if m["kp"] >= 70:
        tips.append({"good": True, "text": f"In {m['kp']}% of your team's kills. You were where the fights were."})
    elif m["kp"] < 35 and game["minutes"] > 15:
        tips.append({"good": False, "text": f"Only in {m['kp']}% of your team's kills. Try grouping with your team more."})
    if m["share"] >= 35:
        tips.append({"good": True, "text": f"You dealt {m['share']}% of your team's damage."})
    if timeline:
        pid = m["pid"]
        early, killers = 0, {}
        first_items = []
        champs = {p["pid"]: p["champ"] for p in game["players"]}
        for fr in timeline.get("frames") or []:
            for ev in fr.get("events") or []:
                t = (ev.get("timestamp") or 0) / 60000
                if ev.get("type") == "CHAMPION_KILL" and ev.get("victimId") == pid:
                    if t < 10:
                        early += 1
                    k = champs.get(ev.get("killerId"))
                    if k:
                        killers[k] = killers.get(k, 0) + 1
                if ev.get("type") == "ITEM_PURCHASED" and ev.get("participantId") == pid:
                    first_items.append((t, ev.get("itemId")))
        if early >= 3:
            tips.append({"good": False, "text": f"You died {early} times before 10 minutes. Playing safer early keeps your gold lead."})
        elif early == 0 and m["d"] <= 3:
            tips.append({"good": True, "text": "No deaths before 10 minutes. Clean early game."})
        if killers:
            top = max(killers, key=killers.get)
            if killers[top] >= 3:
                tips.append({"good": False, "text": f"{top} killed you {killers[top]} times. Watch their cooldowns and keep your distance."})
        game["_items_timeline"] = first_items
    verdict = "Victory" if m["win"] else "Defeat"
    good = sum(1 for t in tips if t["good"])
    head = (f"{verdict} as {m['champ']}: " + ("a strong game." if good >= len(tips) - good and m["win"]
            else "solid numbers despite the loss." if good > len(tips) - good else "some things to work on."))
    return {"id": game["id"], "champ": m["champ"], "win": m["win"], "queue": game["queue"], "minutes": game["minutes"],
            "k": m["k"], "d": m["d"], "a": m["a"], "dmg": m["dmg"], "dpm": m["dpm"], "headline": head, "tips": tips[:6]}
