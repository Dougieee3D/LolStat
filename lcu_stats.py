"""
LoLStat player stats from the League client itself (no Riot API key needed):
your profile (ranks, match history, champion stats, mastery, today's session) and
live game scouting (every player's rank, recent form and champion experience, once
the game has started and names are visible to you).
"""

import json
import os
import time
import urllib.parse
from datetime import datetime

QUEUES = {
    420: "Ranked Solo/Duo", 440: "Ranked Flex", 400: "Normal Draft", 430: "Normal Blind", 490: "Quickplay",
    450: "ARAM", 2400: "ARAM Mayhem", 1700: "Arena", 1710: "Arena", 1900: "URF", 900: "ARURF", 1020: "One for All",
    700: "Clash", 720: "ARAM Clash", 830: "Co-op vs AI", 840: "Co-op vs AI", 850: "Co-op vs AI", 870: "Co-op vs AI",
    880: "Co-op vs AI", 890: "Co-op vs AI", 0: "Custom", 3100: "Custom", 2300: "Brawl",
}
RANK_QUEUES = {"RANKED_SOLO_5x5": "Solo/Duo", "RANKED_FLEX_SR": "Flex", "RANKED_TFT": "TFT",
               "RANKED_TFT_DOUBLE_UP": "TFT Double Up", "RANKED_TFT_TURBO": "TFT Hyper Roll", "CHERRY": "Arena"}
TIER_ORDER = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER"]


def _queue(qid):
    return QUEUES.get(int(qid or 0), f"Queue {qid}")


def _ranks(ranked):
    out = []
    for q in (ranked or {}).get("queues", []):
        qt = q.get("queueType")
        if qt not in RANK_QUEUES:
            continue
        tier = (q.get("tier") or "").upper()
        if tier in ("", "NONE"):
            label = "Unranked"
        else:
            div = q.get("division") or ""
            label = f"{tier.title()} {'' if tier in ('MASTER', 'GRANDMASTER', 'CHALLENGER') else div}".strip()
        w, l = int(q.get("wins") or 0), int(q.get("losses") or 0)
        out.append({"queue": RANK_QUEUES[qt], "type": qt, "tier": tier, "label": label,
                    "lp": int(q.get("leaguePoints") or 0), "wins": w, "losses": l,
                    "wr": round(w / (w + l) * 100) if w + l else None,
                    "provisional": bool(q.get("isProvisional"))})
    order = list(RANK_QUEUES)
    out.sort(key=lambda r: order.index(r["type"]))
    return out


def _lp_score(r):
    """One number for tier + division + LP, so today's LP change survives promotions."""
    div = r["label"].split()[-1]
    tier = TIER_ORDER.index(r["tier"]) if r["tier"] in TIER_ORDER else 0
    return tier * 400 + (["IV", "III", "II", "I"].index(div) * 100 if div in ("IV", "III", "II", "I") else 0) + r["lp"]


def _game(g, puuid, champ_name):
    """One match from the client's match history, from this player's side."""
    pid = None
    for ident in g.get("participantIdentities") or []:
        pl = ident.get("player") or {}
        if pl.get("puuid") == puuid:
            pid = ident.get("participantId")
    parts = g.get("participants") or []
    me = next((p for p in parts if p.get("participantId") == pid), parts[0] if parts else {})
    st = me.get("stats") or {}
    mins = max(1, (g.get("gameDuration") or 0) / 60)
    cs = int(st.get("totalMinionsKilled") or 0) + int(st.get("neutralMinionsKilled") or 0)
    dmg = int(st.get("totalDamageDealtToChampions") or 0)
    return {
        "id": g.get("gameId"), "when": int(g.get("gameCreation") or 0), "minutes": round(mins, 1),
        "queue": _queue(g.get("queueId")), "queueId": g.get("queueId"), "mode": g.get("gameMode", ""),
        "champion": champ_name(me.get("championId")), "win": bool(st.get("win")),
        "k": int(st.get("kills") or 0), "d": int(st.get("deaths") or 0), "a": int(st.get("assists") or 0),
        "cs": cs, "csm": round(cs / mins, 1), "gold": int(st.get("goldEarned") or 0),
        "damage": dmg, "dpm": round(dmg / mins), "level": int(st.get("champLevel") or 0),
        "items": [int(st.get(f"item{i}") or 0) for i in range(7)],
        "role": ((me.get("timeline") or {}).get("lane") or "").lower(),
        "remake": (g.get("gameDuration") or 0) < 300,
    }


def _champ_table(games):
    by = {}
    for g in games:
        if g["remake"] or not g["champion"]:
            continue
        c = by.setdefault(g["champion"], {"champion": g["champion"], "games": 0, "wins": 0, "k": 0, "d": 0, "a": 0, "dmg": 0})
        c["games"] += 1; c["wins"] += g["win"]; c["k"] += g["k"]; c["d"] += g["d"]; c["a"] += g["a"]; c["dmg"] += g["dpm"]
    rows = []
    for c in by.values():
        n = c["games"]
        rows.append({"champion": c["champion"], "games": n, "wr": round(c["wins"] / n * 100),
                     "kda": round((c["k"] + c["a"]) / max(1, c["d"]), 2), "dpm": round(c["dmg"] / n)})
    rows.sort(key=lambda r: (-r["games"], -r["wr"]))
    return rows


def _streak(games):
    real = [g for g in games if not g["remake"]]
    if not real:
        return 0
    first, n = real[0]["win"], 0
    for g in real:
        if g["win"] != first:
            break
        n += 1
    return n if first else -n


def _matches(lcu_call, path_puuid, count):
    res = lcu_call("GET", f"/lol-match-history/v1/products/lol/{path_puuid}/matches?begIndex=0&endIndex={count - 1}") or {}
    return ((res.get("games") or {}).get("games")) or []


def profile(lcu_call, champ_name, data_dir):
    me = lcu_call("GET", "/lol-summoner/v1/current-summoner") or {}
    puuid = me.get("puuid")
    ranks = _ranks(lcu_call("GET", "/lol-ranked/v1/current-ranked-stats"))
    games = [_game(g, puuid, champ_name) for g in _matches(lcu_call, "current-summoner", 40)]
    games.sort(key=lambda g: -g["when"])
    try:
        mastery = lcu_call("GET", "/lol-champion-mastery/v1/local-player/champion-mastery") or []
    except Exception:
        mastery = []
    mastery = sorted(mastery, key=lambda m: -(m.get("championPoints") or 0))[:10]
    mastery = [{"champion": champ_name(m.get("championId")), "level": m.get("championLevel"),
                "points": m.get("championPoints")} for m in mastery if champ_name(m.get("championId"))]

    # today's session: games since midnight, and LP change since the first look today
    today = datetime.now().strftime("%Y-%m-%d")
    midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000
    todays = [g for g in games if g["when"] >= midnight and not g["remake"]]
    lp_path = os.path.join(data_dir, "lp_log.json")
    try:
        lp_log = json.load(open(lp_path))
    except Exception:
        lp_log = {}
    day = lp_log.setdefault(today, {})
    lp_change = {}
    for r in ranks:
        if r["tier"] in ("", "NONE"):
            continue
        score = _lp_score(r)
        day.setdefault(r["type"], score)
        lp_change[r["queue"]] = score - day[r["type"]]
    try:
        json.dump({k: v for k, v in lp_log.items() if k >= today[:8]}, open(lp_path, "w"))
    except Exception:
        pass
    return {
        "summary": summary(games), "puuid": puuid,
        "name": f"{me.get('gameName', '')}#{me.get('tagLine', '')}".strip("#"),
        "level": me.get("summonerLevel"), "icon": me.get("profileIconId"),
        "ranks": ranks, "games": games, "champions": _champ_table(games), "mastery": mastery,
        "streak": _streak(games),
        "session": {"games": len(todays), "wins": sum(g["win"] for g in todays),
                    "losses": sum(not g["win"] for g in todays), "lp": lp_change},
        "updated": datetime.now().strftime("%I:%M %p"),
    }


def _puuid_for(lcu_call, riot_id):
    name, _, tag = (riot_id or "").partition("#")
    if not name or not tag:
        return None
    for path in (f"/lol-summoner/v1/alias/lookup?gameName={urllib.parse.quote(name)}&tagLine={urllib.parse.quote(tag)}",
                 f"/lol-summoner/v1/summoners?name={urllib.parse.quote(riot_id)}"):
        try:
            r = lcu_call("GET", path)
            if isinstance(r, dict) and r.get("puuid"):
                return r["puuid"]
        except Exception:
            continue
    return None


def scout_player(lcu_call, p, champ_name):
    """One player's rank, recent form and experience on the champion they're playing."""
    out = {"name": p.get("riotId") or p.get("summonerName") or "Player", "champion": p.get("champion"),
           "team": p.get("team"), "bot": bool(p.get("isBot")), "rank": None, "tags": []}
    if out["bot"]:
        out["tags"] = ["Bot"]
        return out
    puuid = _puuid_for(lcu_call, out["name"])
    if not puuid:
        out["tags"] = ["Profile hidden"]
        return out
    try:
        ranks = _ranks(lcu_call("GET", f"/lol-ranked/v1/ranked-stats/{puuid}"))
        solo = next((r for r in ranks if r["type"] == "RANKED_SOLO_5x5"), None) or (ranks[0] if ranks else None)
        out["rank"] = solo
    except Exception:
        pass
    try:
        games = [_game(g, puuid, champ_name) for g in _matches(lcu_call, puuid, 20)]
    except Exception:
        games = []
    real = [g for g in games if not g["remake"]]
    if real:
        on = [g for g in real if g["champion"] == out["champion"]]
        out["recent_wr"] = round(sum(g["win"] for g in real) / len(real) * 100)
        out["recent_games"] = len(real)
        out["champ_games"] = len(on)
        out["champ_wr"] = round(sum(g["win"] for g in on) / len(on) * 100) if on else None
        out["kda"] = round(sum(g["k"] + g["a"] for g in real) / max(1, sum(g["d"] for g in real)), 2)
        st = _streak(games)
        tags = []
        if st >= 3:
            tags.append(f"{st}-win streak")
        if st <= -3:
            tags.append(f"{-st}-loss streak")
        if len(on) >= max(8, int(0.6 * len(real))):
            tags.append("One-trick")
        elif not on:
            tags.append("New to this champ")
        if out["recent_wr"] >= 65 and len(real) >= 10 and st >= 0:
            tags.append("On fire")
        if out["kda"] >= 4:
            tags.append("High KDA")
        out["tags"] = tags
    return out


# ---------------------------------------------------------------- other players and friends
def summary(games):
    real = [g for g in games if not g["remake"]]
    if not real:
        return {"games": 0}
    n = len(real)
    return {"games": n, "wr": round(sum(g["win"] for g in real) / n * 100),
            "kda": round(sum(g["k"] + g["a"] for g in real) / max(1, sum(g["d"] for g in real)), 2),
            "dpm": round(sum(g["dpm"] for g in real) / n), "csm": round(sum(g["csm"] for g in real) / n, 1),
            "k": round(sum(g["k"] for g in real) / n, 1), "d": round(sum(g["d"] for g in real) / n, 1),
            "a": round(sum(g["a"] for g in real) / n, 1)}


def player_profile(lcu_call, champ_name, riot_id=None, puuid=None):
    """Any player's profile through the League client: ranks, recent matches, champion stats."""
    puuid = puuid or _puuid_for(lcu_call, riot_id)
    if not puuid:
        raise RuntimeError(f"couldn't find {riot_id}. Check the name and tag (Name#TAG).")
    try:
        sm = lcu_call("GET", f"/lol-summoner/v2/summoners/puuid/{puuid}") or {}
    except Exception:
        sm = {}
    ranks = _ranks(lcu_call("GET", f"/lol-ranked/v1/ranked-stats/{puuid}"))
    games = [_game(g, puuid, champ_name) for g in _matches(lcu_call, puuid, 30)]
    games.sort(key=lambda g: -g["when"])
    mastery = []
    for path in (f"/lol-champion-mastery/v1/{puuid}/champion-mastery", f"/lol-collections/v1/inventories/{puuid}/champion-mastery"):
        try:
            mastery = lcu_call("GET", path) or []
            if isinstance(mastery, list):
                break
        except Exception:
            continue
    mastery = sorted(mastery if isinstance(mastery, list) else [], key=lambda m: -(m.get("championPoints") or 0))[:10]
    name = f"{sm.get('gameName', '')}#{sm.get('tagLine', '')}".strip("#") or riot_id or "Player"
    return {"name": name, "puuid": puuid, "level": sm.get("summonerLevel"), "icon": sm.get("profileIconId"),
            "ranks": ranks, "games": games, "champions": _champ_table(games), "streak": _streak(games),
            "summary": summary(games),
            "mastery": [{"champion": champ_name(m.get("championId")), "level": m.get("championLevel"),
                         "points": m.get("championPoints")} for m in mastery if champ_name(m.get("championId"))],
            "updated": datetime.now().strftime("%I:%M %p"), "other": True}


def friends(lcu_call):
    rows = lcu_call("GET", "/lol-chat/v1/friends") or []
    out = []
    for f in rows:
        name, tag = f.get("gameName") or f.get("name") or "", f.get("gameTag") or ""
        if not name:
            continue
        lol = f.get("lol") or {}
        out.append({"name": f"{name}#{tag}" if tag else name, "puuid": f.get("puuid"),
                    "status": f.get("availability", "offline"),
                    "playing": lol.get("gameStatus", ""), "champ_id": lol.get("championId") or "",
                    "queue": lol.get("gameQueueType", "")})
    order = {"chat": 0, "online": 0, "dnd": 1, "away": 2, "mobile": 3, "offline": 4}
    out.sort(key=lambda f: (order.get(f["status"], 3), f["name"].lower()))
    return out


def friend_card(lcu_call, champ_name, f):
    """A friend's leaderboard row: ranks, last 20 games, streak and favourite champion."""
    puuid = f.get("puuid") or _puuid_for(lcu_call, f.get("name"))
    if not puuid:
        return None
    ranks = _ranks(lcu_call("GET", f"/lol-ranked/v1/ranked-stats/{puuid}"))
    games = [_game(g, puuid, champ_name) for g in _matches(lcu_call, puuid, 20)]
    games.sort(key=lambda g: -g["when"])
    champs = _champ_table(games)
    solo = next((r for r in ranks if r["type"] == "RANKED_SOLO_5x5"), None)
    flex = next((r for r in ranks if r["type"] == "RANKED_FLEX_SR"), None)
    return {"name": f.get("name"), "puuid": puuid, "solo": solo, "flex": flex,
            "rank_score": _lp_score(solo) if solo and solo["tier"] not in ("", "NONE") else -1,
            "summary": summary(games), "streak": _streak(games),
            "top": champs[0]["champion"] if champs else None,
            "last_played": games[0]["when"] if games else 0, "updated": int(datetime.now().timestamp())}
