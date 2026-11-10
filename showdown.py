"""Party Showdown: a best-of-3 (or best-of-5) damage contest between you and your party.

After every game, whoever in the series did the most damage to champions wins the round.
The first player to win a majority of the series (2 in a best of 3, 3 in a best of 5) wins.
Everything is saved on this PC in showdown.json.
"""
import json
import os
import threading
import time
import uuid

REMAKE_SECONDS = 300          # games shorter than this are remakes and never count
HISTORY_KEEP = 1000     # a few years of showdowns: the yearly Hall of Fame needs them


def wins_needed(best_of):
    return int(best_of) // 2 + 1


class Showdown:
    def __init__(self, data_dir, notify=None, log=None):
        self.path = os.path.join(data_dir, "showdown.json")
        self.notify = notify or (lambda text: None)
        self.log = log or (lambda text: None)
        self.lock = threading.RLock()
        self.party = []              # [{puuid, name}] from your current lobby, you included
        self.party_for_game = []     # the party as it was when the last game started
        self.me = None
        self.data = {"series": None, "history": [], "party_for_game": []}
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                self.data.update(d)
        except Exception:
            pass
        self.party_for_game = list(self.data.get("party_for_game") or [])   # your party survives a restart

    # ------------------------------------------------------------------ storage
    def _save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f)
            os.replace(tmp, self.path)
        except Exception as e:
            self.log(f"Couldn't save the showdown: {e}")

    # ------------------------------------------------------------------ party
    def set_party(self, members, me=None):
        """members: [{puuid, name}] read from the League lobby (you included)."""
        with self.lock:
            if me:
                self.me = me
            clean, seen = [], set()
            for m in members or []:
                p = m.get("puuid")
                if p and p not in seen:
                    seen.add(p)
                    clean.append({"puuid": p, "name": m.get("name") or "Player"})
            self.party = clean
            if len(clean) >= 2 and clean != self.party_for_game:
                self.party_for_game = list(clean)
                self.data["party_for_game"] = list(clean)
                self._save()

    # ------------------------------------------------------------------ series control
    def start(self, players, best_of=3):
        with self.lock:
            s = self.data.get("series")
            if s and not s.get("winner") and s.get("rounds"):
                self._archive(s, ended_early=True)
            players = [{"puuid": p["puuid"], "name": p.get("name") or "Player"} for p in players if p.get("puuid")]
            if len(players) < 2:
                raise ValueError("A showdown needs at least 2 players")
            self.data["series"] = {"id": uuid.uuid4().hex[:10], "best_of": int(best_of), "players": players,
                                   "rounds": [], "winner": None, "started": time.time(), "finished": None}
            self._save()
            return self.data["series"]

    def set_best_of(self, n):
        """Change the format of the series in progress. Switching down can end it on the spot."""
        n = 5 if int(n) >= 5 else 3
        with self.lock:
            s = self.data.get("series")
            if not s or s.get("winner"):
                return
            if sum(1 for v in self._score(s).values() if v >= wins_needed(n)) > 1:
                return "It's tied too far to shorten it. Play the deciding game first."
            s["best_of"] = n
            self._check_winner(s, announce=True)
            self._save()

    def extend(self):
        """Turn a finished best of 3 into a best of 5 and keep playing."""
        with self.lock:
            s = self.data.get("series")
            if not s or s.get("best_of", 3) >= 5:
                return
            if s.get("winner"):
                self.data["history"] = [h for h in self.data["history"] if h.get("id") != s["id"]]
            s.update(best_of=5, winner=None, finished=None)
            self._check_winner(s, announce=True)
            self._save()

    def rematch(self):
        with self.lock:
            s = self.data.get("series")
            if s:
                return self.start(s["players"], s.get("best_of", 3))

    def end(self):
        with self.lock:
            s = self.data.get("series")
            if s and not s.get("winner") and s.get("rounds"):
                self._archive(s, ended_early=True)
            self.data["series"] = None
            self._save()

    def remove_player(self, puuid):
        with self.lock:
            s = self.data.get("series")
            if not s or len(s["players"]) <= 2:
                return
            s["players"] = [p for p in s["players"] if p["puuid"] != puuid]
            for r in s["rounds"]:
                self._score_round(s, r)
            self._check_winner(s, announce=True)
            self._save()

    def undo(self):
        with self.lock:
            s = self.data.get("series")
            if not s or not s["rounds"]:
                return
            if s.get("winner"):
                self.data["history"] = [h for h in self.data["history"] if h.get("id") != s["id"]]
                s.update(winner=None, finished=None)
            s["rounds"].pop()
            self._save()

    def give_round(self, idx, puuid):
        """Hand a round to someone by hand (or pass puuid=None to make it not count)."""
        with self.lock:
            s = self.data.get("series")
            if not s or not (0 <= idx < len(s["rounds"])):
                return
            r = s["rounds"][idx]
            r["winner"] = puuid if puuid in [p["puuid"] for p in s["players"]] else None
            r["counted"] = r["winner"] is not None
            r["manual"] = True
            r["note"] = "" if r["counted"] else "Not counted"
            self._recheck(s)
            self._save()

    def count_anyway(self, idx):
        """Count a round even though someone in the series wasn't in that game."""
        with self.lock:
            s = self.data.get("series")
            if not s or not (0 <= idx < len(s["rounds"])):
                return
            r = s["rounds"][idx]
            r["force"] = True
            self._score_round(s, r)
            self._recheck(s)
            self._save()

    def _recheck(self, s):
        if s.get("winner"):
            self.data["history"] = [h for h in self.data["history"] if h.get("id") != s["id"]]
            s.update(winner=None, finished=None)
        self._check_winner(s, announce=False)

    # ------------------------------------------------------------------ game results
    def on_game(self, game, auto_start=True, best_of=3):
        """game: {game_id, length, mode, players:[{puuid, name, champion, damage, k, d, a}]} (all 10 players is fine).

        Returns the round that was added, or None."""
        with self.lock:
            gid = str(game.get("game_id") or "")
            by_puuid = {p["puuid"]: p for p in game.get("players") or [] if p.get("puuid")}
            s = self.data.get("series")
            if s and s.get("winner"):
                s = None                                    # finished: a new game can start the next one
            if s and any(str(r.get("game_id")) == gid for r in s["rounds"]):
                return None
            if not s:
                party = [p for p in self.party_for_game if p["puuid"] in by_puuid]
                if not auto_start or len(party) < 2:
                    return None
                if self.data.get("series") and self.data["series"].get("winner"):
                    last = self.data["series"]
                    if {p["puuid"] for p in last["players"]} == {p["puuid"] for p in party} and \
                            any(str(r.get("game_id")) == gid for r in last["rounds"]):
                        return None
                s = self.start(party, best_of)
                self.notify(f"New showdown: {', '.join(p['name'] for p in party)}, best of {best_of}. Most damage wins each game.")
            for p in s["players"]:                          # keep names fresh (Riot ID changes, lookups that failed)
                g = by_puuid.get(p["puuid"])
                if g and g.get("name") and p.get("name") in ("", "Player"):
                    p["name"] = g["name"]
            r = {"game_id": gid, "when": time.time(), "mode": game.get("mode") or "",
                 "minutes": round((game.get("length") or 0) / 60, 1),
                 "stats": {p["puuid"]: {k: by_puuid[p["puuid"]].get(k) for k in ("champion", "damage", "k", "d", "a")}
                           for p in s["players"] if p["puuid"] in by_puuid}}
            self._score_round(s, r)
            if not r["stats"]:
                return None                                 # none of you were in this game
            s["rounds"].append(r)
            self._announce_round(s, r)
            self._check_winner(s, announce=True)
            self._save()
            return r

    def _score_round(self, s, r):
        if r.get("manual"):
            return
        names = {p["puuid"]: p["name"] for p in s["players"]}
        present = {pu: st for pu, st in r["stats"].items() if pu in names}
        missing = [names[pu] for pu in names if pu not in present]
        r["winner"], r["counted"], r["note"] = None, False, ""
        if r.get("minutes", 99) * 60 < REMAKE_SECONDS:
            r["note"] = "Remake, doesn't count"
            return
        if missing and not r.get("force"):
            r["note"] = f"Not counted: {', '.join(missing)} wasn't in this game"
            return
        if len(present) < 2:
            r["note"] = "Not counted: only one of you played"
            return
        best = max(int(st.get("damage") or 0) for st in present.values())
        top = [pu for pu, st in present.items() if int(st.get("damage") or 0) == best]
        if len(top) > 1:
            r["note"] = "Tie on damage, nobody gets the point"
            return
        r["winner"], r["counted"] = top[0], True

    def _score(self, s):
        sc = {p["puuid"]: 0 for p in s["players"]}
        for r in s["rounds"]:
            if r.get("counted") and r.get("winner") in sc:
                sc[r["winner"]] += 1
        return sc

    @staticmethod
    def margin(s, r):
        """How much more damage the game's winner did than the next best player: (amount, runner-up puuid)."""
        names = {p["puuid"] for p in s["players"]}
        dmg = sorted(((int(st.get("damage") or 0), pu) for pu, st in r["stats"].items() if pu in names), reverse=True)
        if len(dmg) < 2:
            return 0, None
        top = r.get("winner") if r.get("counted") and r.get("winner") else dmg[0][1]
        mine = int(r["stats"][top].get("damage") or 0)
        rest = [d for d in dmg if d[1] != top]
        return mine - rest[0][0], rest[0][1]

    def totals_lead(self, s):
        """Series damage leader and how far ahead of the next player: (puuid, amount)."""
        tot = sorted(((sum(int((r["stats"].get(p["puuid"]) or {}).get("damage") or 0) for r in s["rounds"]), p["puuid"])
                      for p in s["players"]), reverse=True)
        if len(tot) < 2 or not tot[0][0]:
            return None, 0
        return tot[0][1], tot[0][0] - tot[1][0]

    def _announce_round(self, s, r):
        names = {p["puuid"]: p["name"] for p in s["players"]}
        n = len(s["rounds"])
        if not r.get("counted"):
            self.notify(f"Game {n}: {r.get('note')}")
            return
        sc = self._score(s)
        lead = sorted(sc.items(), key=lambda x: -x[1])
        dmg = int(r["stats"][r["winner"]].get("damage") or 0)
        board = " to ".join(str(v) for _, v in lead) if len(lead) == 2 else ", ".join(f"{names[p]} {v}" for p, v in lead)
        if lead[0][1] >= wins_needed(s["best_of"]):
            return                                          # the series-winner message covers it
        state = f"{names[lead[0][0]]} leads {board}" if lead[0][1] > lead[1][1] else f"It's tied {board}"
        by, who = self.margin(s, r)
        beat = f", {by:,} more than {names[who]}" if who else ""
        self.notify(f"Game {n}: {names[r['winner']]} wins with {dmg:,} damage{beat}. {state}.")

    def _check_winner(self, s, announce=True):
        need = wins_needed(s["best_of"])
        sc = self._score(s)
        champ = next((p for p, v in sc.items() if v >= need), None)
        if champ and not s.get("winner"):
            s["winner"], s["finished"] = champ, time.time()
            self._archive(s)
            if announce:
                name = next(p["name"] for p in s["players"] if p["puuid"] == champ)
                lp, amt = self.totals_lead(s)
                extra = ""
                if lp and amt:
                    who = next(p["name"] for p in s["players"] if p["puuid"] == lp)
                    extra = f" {who} did {amt:,} more damage in total."
                self.notify(f"{name} wins it all, {self.score_text(s)} (best of {s['best_of']})!{extra}")

    def _archive(self, s, ended_early=False):
        sc = self._score(s)
        rec = {"id": s["id"], "best_of": s["best_of"], "winner": s.get("winner"), "ended_early": ended_early,
               "finished": s.get("finished") or time.time(), "games": len(s["rounds"]),
               "players": [self._player_record(s, p, sc) for p in s["players"]]}
        self.data["history"] = ([rec] + [h for h in self.data["history"] if h.get("id") != s["id"]])[:HISTORY_KEEP]

    def _player_record(self, s, p, sc):
        pid = p["puuid"]
        dmg = [int((r["stats"].get(pid) or {}).get("damage") or 0) for r in s["rounds"] if pid in r["stats"]]
        margins = [self.margin(s, r)[0] for r in s["rounds"] if r.get("counted") and r.get("winner") == pid]
        return {"puuid": pid, "name": p["name"], "wins": sc.get(pid, 0), "damage": sum(dmg),
                "played": len(dmg), "best": max(dmg or [0]), "margin_best": max([m for m in margins if m] or [0]),
                "margin_total": sum(m for m in margins if m)}

    def score_text(self, s):
        return "-".join(str(v) for v in sorted(self._score(s).values(), reverse=True))

    # ------------------------------------------------------------------ for the app
    def view(self, best_of_setting=3):
        with self.lock:
            s = self.data.get("series")
            out = {"party": self.party, "me": self.me, "series": None, "history": self.data["history"][:20],
                   "leaderboard": self.leaderboard(), "hall": self.hall_of_fame(), "best_of_setting": best_of_setting}
            if s:
                sc = self._score(s)
                need = wins_needed(s["best_of"])
                players = []
                for p in s["players"]:
                    dmg = [int((r["stats"].get(p["puuid"]) or {}).get("damage") or 0) for r in s["rounds"] if p["puuid"] in r["stats"]]
                    players.append(dict(p, wins=sc[p["puuid"]], total=sum(dmg), best=max(dmg or [0]),
                                        avg=round(sum(dmg) / len(dmg)) if dmg else 0, me=p["puuid"] == self.me,
                                        last_champ=next(((r["stats"][p["puuid"]].get("champion")) for r in reversed(s["rounds"]) if p["puuid"] in r["stats"]), None),
                                        match_point=not s.get("winner") and sc[p["puuid"]] == need - 1))
                totals = {p["puuid"]: p["total"] for p in players}
                for p in players:                       # + ahead / - behind the next best total
                    others = [v for k, v in totals.items() if k != p["puuid"]]
                    p["diff"] = p["total"] - max(others) if others else 0
                rounds = []
                for r in s["rounds"]:
                    by, who = self.margin(s, r)
                    rounds.append(dict(r, margin=by, runner_up=who))
                tl, tamt = self.totals_lead(s)
                top = max(sc.values()) if sc else 0
                leaders = [p for p, v in sc.items() if v == top and top > 0]
                out["series"] = dict(s, rounds=rounds, players=players, need=need, score=self.score_text(s),
                                     damage_leader=tl, damage_lead=tamt,
                                     leader=leaders[0] if len(leaders) == 1 else None,
                                     counted=sum(1 for r in s["rounds"] if r.get("counted")))
            return out

    @staticmethod
    def period_start(period, now=None):
        """Start of this week (Monday), month or year, in your local time. None = all time."""
        import datetime as _dt
        d = _dt.datetime.fromtimestamp(now or time.time())
        d = d.replace(hour=0, minute=0, second=0, microsecond=0)
        if period == "week":
            d -= _dt.timedelta(days=d.weekday())
        elif period == "month":
            d = d.replace(day=1)
        elif period == "year":
            d = d.replace(month=1, day=1)
        else:
            return None
        return d.timestamp()

    def hall_of_fame(self):
        """The Hall of Fame for this week, this month, this year and all time: titles, games won and every
        damage stat."""
        out = {}
        for period in ("week", "month", "year", "all"):
            since = self.period_start(period)
            board = {}
            for h in self.data["history"]:
                if since and float(h.get("finished") or 0) < since:
                    continue
                for p in h["players"]:
                    b = board.setdefault(p["puuid"], {"puuid": p["puuid"], "name": p["name"], "series": 0, "titles": 0,
                                                      "rounds": 0, "played": 0, "damage": 0, "best": 0,
                                                      "margin_best": 0, "margin_total": 0})
                    b["name"] = p["name"]
                    b["series"] += 1
                    b["rounds"] += p.get("wins", 0)
                    b["damage"] += p.get("damage", 0)
                    b["played"] += p.get("played") or h.get("games") or 0
                    b["best"] = max(b["best"], p.get("best") or 0)
                    b["margin_best"] = max(b["margin_best"], p.get("margin_best") or 0)
                    b["margin_total"] += p.get("margin_total") or 0
                    if h.get("winner") == p["puuid"]:
                        b["titles"] += 1
            for b in board.values():
                b["avg"] = round(b["damage"] / b["played"]) if b["played"] else 0
                b["win_rate"] = round(b["rounds"] / b["played"] * 100) if b["played"] else 0
            out[period] = {"since": since, "showdowns": sum(1 for h in self.data["history"] if not since or float(h.get("finished") or 0) >= since),
                           "board": sorted(board.values(), key=lambda b: (-b["titles"], -b["rounds"], -b["damage"]))}
        return out

    def leaderboard(self):
        board = {}
        for h in self.data["history"]:
            for p in h["players"]:
                b = board.setdefault(p["puuid"], {"puuid": p["puuid"], "name": p["name"], "series": 0, "titles": 0, "rounds": 0, "damage": 0})
                b["name"] = p["name"]
                b["series"] += 1
                b["rounds"] += p.get("wins", 0)
                b["damage"] += p.get("damage", 0)
                if h.get("winner") == p["puuid"]:
                    b["titles"] += 1
        return sorted(board.values(), key=lambda b: (-b["titles"], -b["rounds"], -b["damage"]))

    def summary(self):
        """Small version for the Home page."""
        with self.lock:
            s = self.data.get("series")
            if not s:
                return None
            sc = self._score(s)
            return {"best_of": s["best_of"], "need": wins_needed(s["best_of"]), "games": len(s["rounds"]),
                    "winner": next((p["name"] for p in s["players"] if p["puuid"] == s.get("winner")), None),
                    "players": [{"name": p["name"], "wins": sc[p["puuid"]]} for p in s["players"]]}
