"""
LoLStat Mayhem service: everything the ARAM Mayhem screens and the overlay show,
kept up to date in the background (game data, live game, augment ranks, builds,
augments detected on screen).
"""

import copy
import json
import os
import ssl
import threading
import time
import urllib.request
from datetime import datetime

import mayhem_engine as eng

LIVE_URL = "https://127.0.0.1:2999/liveclientdata/allgamedata"
LIVE_POLL_SECONDS = 0.75  # live game stats (1.25 s in performance mode)
DATA_REFRESH_HOURS = 6
MAX_AUGMENTS = 5
DD_IMG = "https://ddragon.leagueoflegends.com/cdn/{v}/img/{kind}/{file}"

_SSL = ssl._create_unverified_context()  # the game's local data feed uses a self-signed cert


def _live_snapshot():
    try:
        with urllib.request.urlopen(LIVE_URL, context=_SSL, timeout=2) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _augment_ids(d):
    out = []

    def take(v):
        if isinstance(v, (int, str)) and str(v).isdigit() and int(v) > 0:
            out.append(str(int(v)))
        elif isinstance(v, dict):
            take(v.get("id") or v.get("augmentId") or v.get("ID"))
        elif isinstance(v, list):
            for x in v:
                take(x)
    for k, v in (d or {}).items():
        if "augment" in k.lower() and v:
            take(v)
    return out


class MayhemService:
    def __init__(self, data_dir, log, settings):
        self.data_dir, self.log, self.settings = data_dir, log, settings
        self.lock = threading.RLock()
        self.data = eng.load_data(data_dir, refresh=False, log=log)
        self.data_status = "saved copy"
        self.overall = (eng._cached(os.path.join(data_dir, "ranks", "overall_v2.json"), None)
                        or self.data.get("overall_ranks") or {})
        self.champ_ranks = {}
        self.rank_fetching = set()
        self.ranks_version = 1
        self.live = None
        self.game_key = None
        self.manual_champ = ""
        self.manual_enemies = [""] * 5
        self.chosen = []
        self.offer = None            # {"ids": [...], "since": t} cards on screen right now
        self.offer_ver = 0           # goes up whenever the cards on screen change (the overlay redraws at once)
        self.unconfirmed = None      # last offer whose pick wasn't seen: {"ids": [...]}
        self.scanner_status = "off"
        self.champ_tiers = (eng._cached(os.path.join(data_dir, "ranks", "champions_v1.json"), None)
                            or self.data.get("champion_tiers") or {})
        self.champ_select = None     # live champ select from the League client
        self.toast = None            # {"text", "t"} short notice for the app and overlay
        self.lcu_call = None         # set by the main app: (method, path, body) -> result
        self.screen_cards = None     # (names, time) champion cards read off the client screen
        self.mode = "mayhem"         # "sr" (Summoner's Rift), "aram" or "mayhem": picks the shop and build styles
        self.queue_id = 0
        self.cs_debug = {}
        self.overlay_status = "not started"
        self.hotkey_status = ""
        self.reader_info = {}
        self.test_until = 0          # "Test overlay" shows sample letters until this time
        self.preview = (b"", 0)      # live picture of what the card reader sees
        self.pairs = eng._cached(os.path.join(data_dir, "ranks", "pairs_v1.json"), None) or {}
        self.history = eng._cached(os.path.join(data_dir, "history.json"), None) or []
        self.locale = "en_US"        # the League client's language, for reading cards
        self.local_names = {}        # augment names in that language
        self._match_cache = None
        self._builds_cache = (None, None)
        self._index()

    # ------------------------------------------------------------ start
    def start(self):
        threading.Thread(target=self._data_loop, daemon=True).start()
        threading.Thread(target=self._live_loop, daemon=True).start()

    def match_names(self):
        """(id, name) pairs the screen reader looks for: English plus the client's language."""
        if self._match_cache is None:
            pairs = list(self.aug_names.items())
            pairs += [(k, v) for k, v in self.local_names.items() if k in self.aug_names]
            self._match_cache = pairs
        return self._match_cache

    def set_locale(self, loc):
        if not loc or loc == self.locale:
            return
        self.locale = loc
        self.log(f"League client language: {loc}")
        if loc.lower() == "en_us":
            self.local_names, self._match_cache = {}, None
            return

        def fetch():
            try:
                url = eng.CD_CHERRY.replace("/global/default/", f"/global/{loc.lower()}/")
                rows = eng._get_json(url)
                names = {str(r["id"]): r.get("nameTRA", "") for r in rows if r.get("nameTRA")}
                eng._save(os.path.join(self.data_dir, "ranks", f"names_{loc}.json"), names)
            except Exception:
                names = eng._cached(os.path.join(self.data_dir, "ranks", f"names_{loc}.json"), None) or {}
            with self.lock:
                self.local_names, self._match_cache = names, None
            if names:
                self.log(f"Loaded augment names in {loc} ({len(names)}).")
        threading.Thread(target=fetch, daemon=True).start()

    def _index(self):
        self.champ_lower = {n.lower(): n for n in self.data["champions"]}
        self.alias_to_name = {c["alias"].lower(): n for n, c in self.data["champions"].items()}
        self.aug_names = {aid: a["name"] for aid, a in self.data["augments"].items()}
        self._match_cache = None

    # ------------------------------------------------------------ data
    def refresh_data(self):
        try:
            data = eng.download_data()
            with open(os.path.join(self.data_dir, "mayhem_data.json"), "w", encoding="utf-8") as f:
                json.dump(data, f)
            with self.lock:
                self.data = data
                self._index()
                self.data_status = "updated " + datetime.now().strftime("%b %d, %I:%M %p")
            self.log(f"Game data updated (patch {data['patch']}).")
        except Exception as e:
            with self.lock:
                self.data_status = "offline, using saved copy"
            self.log(f"Couldn't update game data ({e.__class__.__name__}).")
        ov = eng.overall_ranks(self.data_dir)
        ct = eng.champion_tiers(self.data_dir)
        pairs = eng.augment_pairs(self.data_dir)
        if pairs:
            self.pairs = pairs
        with self.lock:
            if ct:
                self.champ_tiers = ct
            if ov:
                self.overall = ov
            self.champ_ranks = {}
            self.ranks_version += 1
            self._builds_cache = (None, None)

    def _data_loop(self):
        while True:
            self.refresh_data()
            time.sleep(DATA_REFRESH_HOURS * 3600)

    def _fetch_ranks(self, key):
        r = eng.champion_ranks(self.data_dir, key)
        with self.lock:
            if r:
                self.champ_ranks[key] = r
            self.rank_fetching.discard(key)
            self.ranks_version += 1

    # ------------------------------------------------------------ live game
    def _resolve(self, p):
        name = p.get("championName", "")
        if name in self.data["champions"]:
            return name
        raw = p.get("rawChampionName", "")
        alias = raw.split("displayname_")[-1].lower() if raw else ""
        return self.alias_to_name.get(alias) or self.champ_lower.get(name.lower()) or name

    def parse_live(self, j):
        try:
            ap = j.get("activePlayer", {}) or {}
            ids = {ap.get("riotId"), ap.get("summonerName"), ap.get("riotIdGameName")} - {None, ""}
            players = j.get("allPlayers", []) or []
            me = next((p for p in players if {p.get("riotId"), p.get("summonerName"),
                                               p.get("riotIdGameName")} & ids), None)
            if not me:
                return None
            team = me.get("team")
            enemies = [p for p in players if p.get("team") != team]
            return {
                "mode": (j.get("gameData", {}) or {}).get("gameMode", ""),
                "time": (j.get("gameData", {}) or {}).get("gameTime", 0),
                "level": ap.get("level") or me.get("level") or 0,
                "champion": self._resolve(me),
                "enemies": [self._resolve(p) for p in enemies],
                "enemy_items": {self._resolve(p): [i.get("itemID") for i in p.get("items", [])] for p in enemies},
                "owned": [i.get("itemID") for i in me.get("items", [])],
                "augments": _augment_ids(me) or _augment_ids(ap),
                "stats": self._live_stats(me, [p for p in players if p.get("team") == team], ap),
                "skin": int(me.get("skinID") or 0),
                "players": [{"riotId": p.get("riotId") or p.get("summonerName"), "champion": self._resolve(p),
                             "team": "ally" if p.get("team") == team else "enemy", "isBot": p.get("isBot", False),
                             "k": (p.get("scores") or {}).get("kills", 0), "d": (p.get("scores") or {}).get("deaths", 0),
                             "a": (p.get("scores") or {}).get("assists", 0), "level": p.get("level", 0),
                             "me": p is me} for p in players],
            }
        except Exception:
            return None

    @staticmethod
    def _live_stats(me, mates, ap):
        sc = me.get("scores") or {}
        team_k = sum((p.get("scores") or {}).get("kills", 0) for p in mates) or 0
        k, d, a = sc.get("kills", 0), sc.get("deaths", 0), sc.get("assists", 0)
        return {"k": k, "d": d, "a": a, "cs": sc.get("creepScore", 0),
                "dead": bool(me.get("isDead")), "respawn": round(float(me.get("respawnTimer") or 0)),
                "kp": round((k + a) / team_k * 100) if team_k else 0,
                "kda": round((k + a) / max(1, d), 2), "gold": int(ap.get("currentGold") or 0)}

    def live_build_view(self):
        """The Live build page: worked out at most every 1.5 s, and only when something changed."""
        if not self.live or not self.settings.get("live_build_on", True):
            return None
        lv = self.live
        sig = (tuple(sorted(map(str, lv.get("owned") or []))), repr(sorted((k, tuple(map(str, v))) for k, v in (lv.get("enemy_items") or {}).items())),
               tuple(self.chosen), int((lv.get("stats") or {}).get("gold") or 0) // 50, lv.get("champion"))
        c = getattr(self, "_lb", None)
        if c and (c[0] == sig or time.time() - c[2] < 1.5):
            return c[1]
        try:
            import live_build
            v = live_build.analyze(self)
        except Exception as e:
            self.log(f"Live build: {e}")
            v = c[1] if c else None
        self._lb = (sig, v, time.time())
        return v

    def manual_pick(self, aid):
        """Picked from the app's card pop-up."""
        with self.lock:
            ok = self._add(aid)
            self.offer = None
            self.unconfirmed = None
            if ok:
                self.log(f"Picked: {self.aug_names.get(str(aid), aid)} (from the app)")

    def record_game(self, eog):
        """Save the end-of-game damage report (League client stats) to history."""
        try:
            lp = eog.get("localPlayer") or {}
            st = lp.get("stats") or {}
            g = lambda key: int(st.get(key) or 0)
            team = next((t for t in eog.get("teams") or [] if t.get("isPlayerTeam")), None)
            team_dmg = sum(int((p.get("stats") or {}).get("TOTAL_DAMAGE_DEALT_TO_CHAMPIONS") or 0)
                           for p in (team or {}).get("players") or []) or g("TOTAL_DAMAGE_DEALT_TO_CHAMPIONS")
            mins = max(1, int(eog.get("gameLength") or 0) / 60)
            rec = {
                "id": eog.get("gameId"), "when": datetime.now().strftime("%b %d, %I:%M %p"),
                "mode": eog.get("gameMode", ""), "champion": self.champ_name(lp.get("championId")) or "",
                "win": bool((team or {}).get("isWinningTeam") or st.get("WIN")),
                "minutes": round(mins, 1),
                "damage": g("TOTAL_DAMAGE_DEALT_TO_CHAMPIONS"), "physical": g("PHYSICAL_DAMAGE_DEALT_TO_CHAMPIONS"),
                "magic": g("MAGIC_DAMAGE_DEALT_TO_CHAMPIONS"), "true": g("TRUE_DAMAGE_DEALT_TO_CHAMPIONS"),
                "taken": g("TOTAL_DAMAGE_TAKEN"), "healed": g("TOTAL_HEAL"), "gold": g("GOLD_EARNED"),
                "k": g("CHAMPIONS_KILLED"), "d": g("NUM_DEATHS"), "a": g("ASSISTS"),
                "augments": [self.aug_names.get(a, a) for a in self.chosen],
            }
            rec["dpm"] = round(rec["damage"] / mins)
            rec["share"] = round(rec["damage"] / team_dmg * 100) if team_dmg else 0
            path = os.path.join(self.data_dir, "history.json")
            hist = eng._cached(path, None) or []
            if not any(h.get("id") == rec["id"] for h in hist):
                hist = ([rec] + hist)[:60]
                eng._save(path, hist)
                self.notify(f"Game over: {rec['damage']:,} damage to champions ({rec['share']}% of your team)")
            self.history = hist
        except Exception as e:
            self.log(f"Couldn't read end-of-game stats: {e}")

    def set_live(self, live):
        with self.lock:
            self.live = live
            if not live:
                if self.game_key is not None:
                    self.game_key = None
                    self.offer = None
                return
            gm = str(live.get("mode", "")).upper()
            mode = "mayhem" if gm == "KIWI" or "MAYHEM" in gm else "aram" if gm == "ARAM" else "sr" if gm == "CLASSIC" else self.mode
            if mode != self.mode:
                self.mode, self._builds_cache = mode, (None, None)
            key = (live["champion"], tuple(sorted(live["enemies"])))
            if key != self.game_key:
                self.game_key = key
                self.chosen = []
                self.offer = None
                self.unconfirmed = None
                self.manual_champ = live["champion"]
                self.manual_enemies = (live["enemies"] + [""] * 5)[:5]
                self.champ_select = None
                resumed = self._resume(live)
                if not (resumed and getattr(self, "locked", None) and self.locked.get("key") == self.game_key):
                    self._lock_builds()
                self.notify(("Back in your game: " if resumed else "Connected to your game: ")
                            + f"{live['champion']} vs {', '.join(live['enemies'])}")
            for aid in live["augments"]:
                self._add(aid)
            self._ensure_ranks(live["champion"])

    def _live_loop(self):
        while True:
            snap = _live_snapshot()
            self.set_live(self.parse_live(snap) if snap else None)
            cb = getattr(self, "on_snapshot", None)
            if cb:
                try:
                    cb(snap)                     # clips: the live game data says what just happened
                except Exception as e:
                    self.log(f"Clips: {e}")
            self._save_session()
            time.sleep(LIVE_POLL_SECONDS * (1.67 if self.settings.get("perf_mode") and self.live else 1))

    # ---- pick up where you left off: the game in progress survives closing LoLStat or a crash
    def _session_path(self):
        return os.path.join(self.data_dir, "session.json")

    def _save_session(self):
        live = self.live
        if not live:
            return
        lk = getattr(self, "locked", None)
        sig = (self.game_key, tuple(self.chosen), id(lk))
        if sig == getattr(self, "_session_sig", None):
            return
        self._session_sig = sig
        eng._save(self._session_path(), {"champion": live["champion"], "enemies": sorted(live["enemies"]),
                                         "start": time.time() - float(live.get("time") or 0), "chosen": list(self.chosen),
                                         "builds": (lk or {}).get("builds") if lk and lk.get("key") == self.game_key else None})

    def _resume(self, live):
        """Same game as before LoLStat closed? Bring back the augments you'd already picked."""
        try:
            s = eng._cached(self._session_path(), None) or {}
            start = time.time() - float(live.get("time") or 0)
            if s.get("champion") == live["champion"] and s.get("enemies") == sorted(live["enemies"]) \
                    and abs(float(s.get("start") or 0) - start) < 180:
                for a in s.get("chosen") or []:
                    self._add(a)
                if s.get("builds"):
                    self.locked = {"key": self.game_key, "builds": s["builds"]}   # same builds as before the restart
                if self.chosen:
                    self.log(f"Picked up your game where LoLStat left off ({len(self.chosen)} augments)")
                return True
        except Exception:
            pass
        return False

    def in_game(self):
        return self.live is not None

    # ------------------------------------------------------------ augments
    def _add(self, aid):
        aid = str(aid)
        if aid in self.data["augments"] and aid not in self.chosen and len(self.chosen) < MAX_AUGMENTS:
            self.chosen.append(aid)
            return True
        return False

    def add_augment(self, aid):
        with self.lock:
            ok = self._add(aid)
            if ok and self.unconfirmed and str(aid) in self.unconfirmed["ids"]:
                self.unconfirmed = None
            return ok

    def remove_augment(self, aid):
        with self.lock:
            if str(aid) in self.chosen:
                self.chosen.remove(str(aid))

    def clear_augments(self):
        with self.lock:
            self.chosen = []

    def notify(self, text):
        self.toast = {"text": text, "t": time.time()}
        self.log(text)

    # called by the screen reader
    def on_offer(self, ids, pos=None, game_rect=None):
        with self.lock:
            if ids:
                if not self.offer or self.offer["ids"] != ids:
                    self.log("Augment cards on screen: " + ", ".join(self.aug_names.get(i, i) for i in ids))
                self.offer = {"ids": ids, "since": time.time(), "pos": pos or [], "rect": game_rect}
                self.unconfirmed = None
            else:
                self.offer = None
            self.offer_ver += 1

    def on_pick(self, aid, offer_ids):
        with self.lock:
            if aid and self._add(aid):
                self.log(f"Picked: {self.aug_names.get(aid, aid)} (detected)")
                self.unconfirmed = None
            elif not aid and offer_ids and not (set(offer_ids) & set(self.chosen)):
                self.unconfirmed = {"ids": offer_ids}
            self.offer = None
            self.offer_ver += 1

    def dismiss_unconfirmed(self):
        with self.lock:
            self.unconfirmed = None

    # ------------------------------------------------------------ champ select (League client)
    def champ_name(self, cid):
        for n, c in self.data["champions"].items():
            if c["key"] == cid:
                return n
        return ""

    def on_champ_select(self, sess, pickable=None):
        """Called by the main app with /lol-champ-select/v1/session (None when not in champ select)."""
        with self.lock:
            if not sess:
                self.champ_select = None
                return
            me = sess.get("localPlayerCellId")
            team = sess.get("myTeam") or []
            mine = next((p for p in team if p.get("cellId") == me), {})
            cid = mine.get("championId") or mine.get("championPickIntent") or 0
            name = self.champ_name(cid)
            pick_action = None
            for group in sess.get("actions") or []:
                for a in group:
                    if a.get("actorCellId") == me and a.get("type") == "pick" and a.get("isInProgress"):
                        pick_action = a.get("id")
            my_action, ban_action = None, None
            for group in sess.get("actions") or []:
                for a in group:
                    if a.get("actorCellId") == me and a.get("type") == "pick":
                        my_action = a
                    if a.get("actorCellId") == me and a.get("type") == "ban" and a.get("isInProgress"):
                        ban_action = a.get("id")
            locked = bool(cid and (mine.get("championId") or (my_action or {}).get("completed")))
            cards = []
            if isinstance(pickable, list) and 2 <= len(pickable) <= 4 and not locked:
                cards = [self.champ_name(c) for c in pickable if self.champ_name(c)]
            if not cards and self.screen_cards and time.time() - self.screen_cards[1] < 6 and not locked:
                cards = list(self.screen_cards[0])            # read off the client screen instead
            self.cs_debug = {"pickable": len(pickable) if isinstance(pickable, list) else None,
                             "timer": (sess.get("timer") or {}).get("phase"), "locked": locked,
                             "pick_action": bool(pick_action), "cards": cards}
            first = self.champ_select is None
            prev = (self.champ_select or {}).get("champion")
            self.champ_select = {
                "champion": name,
                "champion_id": cid,
                "bench": [self.champ_name(b.get("championId")) for b in sess.get("benchChampions") or []
                          if self.champ_name(b.get("championId"))],
                "bench_enabled": bool(sess.get("benchEnabled")),
                "rerolls": sess.get("rerollsRemaining", 0) or 0,
                "team": [self.champ_name(p.get("championId")) for p in team if p.get("cellId") != me],
                "pick_action": pick_action,
                "cards": cards,
                "locked": locked,
                "skin_id": int(mine.get("selectedSkinId") or 0),
                "queue": sess.get("queueId") or (self.champ_select or {}).get("queue") or self.queue_id,
                "role": (mine.get("assignedPosition") or "").lower(),
                "enemies": [self.champ_name(p.get("championId")) for p in sess.get("theirTeam") or []
                            if self.champ_name(p.get("championId"))],
                "ban_action": ban_action,
            }
            mode = self.mode_for(self.champ_select["queue"], bool(sess.get("benchEnabled")))
            if mode != self.mode:
                self.mode, self._builds_cache = mode, (None, None)
            if self.champ_select["enemies"]:              # draft: enemy picks are visible as they lock in
                self.manual_enemies = (self.champ_select["enemies"] + [""] * 5)[:5]
            if first:
                self.chosen, self.offer, self.unconfirmed = [], None, None
                self.manual_enemies = [""] * 5
                self.notify("Champ select started" + (f": you have {name}" if name else ""))
            if name and name != prev:
                self.manual_champ = name
                self._ensure_ranks(name)
                if not first:
                    self.notify(f"Switched to {name}")

    @staticmethod
    def mode_for(queue, bench=False):
        q = int(queue or 0)
        if q == 2400:
            return "mayhem"
        if q in (450, 100, 720, 900) or bench:
            return "aram"
        return "sr" if q else "mayhem"

    def ban(self, name):
        c = self.data["champions"].get(name)
        cs = self.champ_select or {}
        if not c:
            raise RuntimeError("pick a champion to ban")
        if not cs.get("ban_action"):
            raise RuntimeError("it isn't your turn to ban right now")
        aid = cs["ban_action"]
        self.lcu_call("PATCH", f"/lol-champ-select/v1/session/actions/{aid}", {"championId": c["key"]})
        return self.lcu_call("POST", f"/lol-champ-select/v1/session/actions/{aid}/complete", None)

    def swap_bench(self, name):
        c = self.data["champions"].get(name)
        if c and self.lcu_call:
            return self.lcu_call("POST", f"/lol-champ-select/v1/session/bench/swap/{c['key']}", None)

    def reroll(self):
        if self.lcu_call:
            return self.lcu_call("POST", "/lol-champ-select/v1/session/my-selection/reroll", None)

    def pick(self, name):
        """Draft/blind modes: lock in a champion for my current pick turn."""
        c = self.data["champions"].get(name)
        cs = self.champ_select or {}
        if c and not cs.get("pick_action"):
            raise RuntimeError("it isn't your turn to pick right now")
        if c and cs.get("pick_action") and self.lcu_call:
            aid = cs["pick_action"]
            self.lcu_call("PATCH", f"/lol-champ-select/v1/session/actions/{aid}", {"championId": c["key"]})
            return self.lcu_call("POST", f"/lol-champ-select/v1/session/actions/{aid}/complete", None)

    def rune_page(self, champ):
        """Damage rune page for this champion (not used in Mayhem, which has no runes)."""
        import runes
        ch = self.data["champions"].get(champ or "")
        if not ch or self.mode == "mayhem":
            return None
        pg = runes.build_page(ch, self.data.get("runes"))
        if pg:
            trees = {t["id"]: t for t in self.data.get("runes", [])}
            icon = {r["id"]: r["icon"] for t in self.data.get("runes", []) for sl in t["slots"] for r in sl}
            base = "https://ddragon.leagueoflegends.com/cdn/img/"
            pg = dict(pg, icons=[base + icon[i] for i in pg["selectedPerkIds"][:6] if i in icon],
                      tree_icons=[base + trees[pg["primaryStyleId"]]["icon"], base + trees[pg["subStyleId"]]["icon"]])
        return pg

    def champion_page(self, name, mode="sr"):
        """Everything for one champion in one mode (Champions tab): builds, runes, tier, best augments."""
        import runes
        ch = self.data["champions"].get(name)
        if not ch:
            return {"error": "Unknown champion"}
        prof = self.champ_ranks.get(ch["key"])
        if not prof:
            prof = eng.champion_ranks(self.data_dir, ch["key"])
            if prof:
                with self.lock:
                    self.champ_ranks[ch["key"]] = prof
        builds = []
        for b in eng.make_builds(name, [], [], self.data, champ_items=(prof or {}).get("items"), mode=mode):
            builds.append({"style": b["style"], "blurb": b["blurb"].replace(" against this team", "").replace("this enemy team", "the enemy team"),
                           "boots": self.item_view(b["boots"]) if b["boots"] else None,
                           "items": [self.item_view(i) for i in b["items"]],
                           "guide": self.guide_view(b, name, mode)})
        page = None
        if mode != "mayhem":
            saved, self.mode = self.mode, mode
            page = self.rune_page(name)
            self.mode = saved
        augs = []
        if prof:
            ranked = sorted(prof.get("ranks", {}).items(), key=lambda kv: (eng.GRADE_ORDER.get(kv[1], 9), prof.get("order", {}).get(kv[0], 999)))
            augs = [dict(self.aug_view(a), grade=g, cpick=prof.get("pick", {}).get(a)) for a, g in ranked[:10] if a in self.data["augments"]]
        tier, pick = self.champ_tier(name)
        return {"champion": self.champ_view(name), "mode": mode, "builds": builds, "runes": page,
                "augments": augs, "tier": tier, "pick": pick, "classes": ch.get("classes", []),
                "damage": ch.get("dmg")}

    def combos(self, limit=5):
        """Augments that pair well with the ones you have, for your champion (best first)."""
        ch = self.data["champions"].get(self.current_champion())
        rows = self.pairs.get(str(ch["key"])) if ch else None
        if not rows or not self.chosen:
            return []
        have, out, seen = set(self.chosen), [], set()
        for a, b, pr in rows:
            if (a in have) == (b in have):
                continue
            partner, mate = (b, a) if a in have else (a, b)
            if partner in seen or partner not in self.data["augments"]:
                continue
            seen.add(partner)
            out.append(dict(self.aug_view(partner), with_=self.aug_names.get(mate, ""), pair_pick=pr))
            if len(out) >= limit:
                break
        return out

    def combo_partners(self):
        """{augment id: name of the augment you have that it pairs with} for tagging offered cards."""
        ch = self.data["champions"].get(self.current_champion())
        rows = self.pairs.get(str(ch["key"])) if ch else None
        out = {}
        for a, b, pr in (rows or [])[:40]:
            if a in self.chosen and b not in self.chosen:
                out.setdefault(b, self.aug_names.get(a, ""))
            elif b in self.chosen and a not in self.chosen:
                out.setdefault(a, self.aug_names.get(b, ""))
        return out

    def champ_tier(self, name):
        c = self.data["champions"].get(name)
        if not c:
            return "", None
        k = str(c["key"])
        return (self.champ_tiers.get("tiers") or {}).get(k, ""), (self.champ_tiers.get("pick") or {}).get(k)

    # ------------------------------------------------------------ champion / ranks
    def set_champion(self, name):
        with self.lock:
            self.manual_champ = self.champ_lower.get((name or "").strip().lower(), "")
            self._ensure_ranks(self.manual_champ)

    def set_enemy(self, i, name):
        with self.lock:
            if 0 <= i < 5:
                self.manual_enemies[i] = self.champ_lower.get((name or "").strip().lower(), "")

    def current_champion(self):
        return self.manual_champ if self.manual_champ in self.data["champions"] else ""

    def _ensure_ranks(self, champ):
        ch = self.data["champions"].get(champ or "")
        if ch and ch["key"] not in self.champ_ranks and ch["key"] not in self.rank_fetching:
            self.rank_fetching.add(ch["key"])
            threading.Thread(target=self._fetch_ranks, args=(ch["key"],), daemon=True).start()

    def grade(self, aid):
        """(grade, source, global pick rate, champion pick rate)"""
        aid = str(aid)
        gp = (self.overall.get("pick") or {}).get(aid)
        ch = self.data["champions"].get(self.current_champion())
        cr = self.champ_ranks.get(ch["key"]) if ch else None
        cp = (cr or {}).get("pick", {}).get(aid)
        if cr and aid in cr.get("ranks", {}):
            return cr["ranks"][aid], "champ", gp, cp
        g = (self.overall.get("ranks") or {}).get(aid)
        return (g or "", "overall" if g else "", gp, cp)

    @staticmethod
    def _fmt_date(d):
        d = str(d or "")
        return f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 and d.isdigit() else d

    # ------------------------------------------------------------ JSON views
    def _ver(self):
        return self.data.get("patch", "")

    def champ_view(self, name):
        c = self.data["champions"].get(name)
        if not c:
            return {"name": name, "alias": "", "icon": ""}
        tier, pick = self.champ_tier(name)
        return {"name": name, "alias": c["alias"],
                "icon": DD_IMG.format(v=self._ver(), kind="champion", file=c["alias"] + ".png"),
                "art": f"https://ddragon.leagueoflegends.com/cdn/img/champion/loading/{c['alias']}_0.jpg",
                "classes": c["classes"], "tier": tier, "pick": pick}

    def aug_view(self, aid):
        a = self.data["augments"].get(str(aid), {"name": f"Augment {aid}", "tier": "", "text": "", "icon": ""})
        g, src, gp, cp = self.grade(aid)
        return {"id": str(aid), "name": a["name"], "tier": a["tier"], "text": a.get("text", ""),
                "icon": a.get("icon", ""), "grade": g, "source": src, "gpick": gp, "cpick": cp}

    def guide_view(self, build, champ, mode, role="", enemies=()):
        """What to buy first, core, boots, end game and situational swaps for one build."""
        import build_guide
        try:
            g = build_guide.guide(build, champ, self.data, mode, role, enemies)
        except Exception as e:
            self.log(f"Build guide: {e}")
            return None
        if not g:
            return None
        iv = self.item_view
        g["start"]["items"] = [iv(i) for i in g["start"]["items"]]
        g["first_back"]["items"] = [iv(i) for i in g["first_back"]["items"]]
        g["core"] = [iv(i) for i in g["core"]]
        g["late"] = [iv(i) for i in g["late"]]
        g["situational"] = [iv(i) for i in g["situational"]]
        if g["boots"] and g["boots"]["item"]:
            g["boots"]["item"] = iv(g["boots"]["item"])
        return g

    def item_view(self, it):
        return dict(it, icon=DD_IMG.format(v=self._ver(), kind="item", file=f"{it['id']}.png"))

    def augments_list(self):
        with self.lock:
            rows = [self.aug_view(aid) for aid in self.data["augments"]]
            order = {}
            ch = self.data["champions"].get(self.current_champion())
            if ch and ch["key"] in self.champ_ranks:
                order = self.champ_ranks[ch["key"]].get("order", {})
        tier_order = {"Prismatic": 0, "Gold": 1, "Silver": 2}
        rows.sort(key=lambda r: (eng.GRADE_ORDER.get(r["grade"], 9),
                                 order.get(r["id"], 999) if r["source"] == "champ" else -(r["gpick"] or 0),
                                 tier_order.get(r["tier"], 3), r["name"].lower()))
        return rows

    def champions_list(self):
        return [self.champ_view(n) for n in sorted(self.data["champions"])]

    def remember_set_builds(self, champ, builds):
        """The builds just written as item sets in champ select: the game uses exactly these."""
        self._set_builds = (champ, copy.deepcopy(builds))

    def _lock_builds(self):
        """Freeze the builds for this game (the in-game panel never changes mid-game)."""
        live = self.live or {}
        champ = live.get("champion")
        sb = getattr(self, "_set_builds", None)
        builds = copy.deepcopy(sb[1]) if sb and sb[0] == champ and sb[1] else copy.deepcopy(self._make_builds())
        self.locked = {"key": self.game_key, "builds": builds}

    def builds(self):
        lk = getattr(self, "locked", None)
        if self.live and lk and lk.get("key") == self.game_key and lk.get("builds"):
            owned = {str(i) for i in (self.live.get("owned") or [])}       # only the Owned marks update
            out = copy.deepcopy(lk["builds"])
            for b in out:
                for it in (b.get("items") or []) + ([b["boots"]] if b.get("boots") else []):
                    it["owned"] = str(it.get("id")) in owned
                g = b.get("guide") or {}
                for it in (g.get("core") or []) + (g.get("late") or []) + ([g["boots"]["item"]] if g.get("boots") and g["boots"].get("item") else []):
                    it["owned"] = str(it.get("id")) in owned
            return out
        return self._make_builds()

    def _make_builds(self):
        champ = self.current_champion()
        enemies = [e for e in self.manual_enemies if e in self.data["champions"]]
        live = self.live
        enemy_items = live.get("enemy_items") if live else None
        owned = live.get("owned") if live else None
        sig = (champ, self.mode, tuple(enemies), tuple(self.chosen), self.ranks_version,
               tuple(owned or []), json.dumps(enemy_items, sort_keys=True) if enemy_items else "")
        if self._builds_cache[0] == sig:
            return self._builds_cache[1]
        out = []
        ch = self.data["champions"].get(champ)
        prof = self.champ_ranks.get(ch["key"]) if ch else None
        if champ:
            role = (self.champ_select or {}).get("role", "")
            for b in eng.make_builds(champ, self.chosen if self.mode == "mayhem" else [], enemies, self.data,
                                     enemy_items, owned, (prof or {}).get("items"), mode=self.mode):
                out.append({"style": b["style"], "blurb": b["blurb"],
                            "boots": self.item_view(b["boots"]) if b["boots"] else None,
                            "items": [self.item_view(i) for i in b["items"]],
                            "guide": self.guide_view(b, champ, self.mode, role, enemies)})
        self._builds_cache = (sig, out)
        return out

    def state(self):
        with self.lock:
            champ = self.current_champion()
            enemies = [e for e in self.manual_enemies if e in self.data["champions"]]
            ch = self.data["champions"].get(champ)
            cr = self.champ_ranks.get(ch["key"]) if ch else None
            live = self.live
            offer = None
            if self.offer:
                partners = self.combo_partners()
                cards = [dict(self.aug_view(i), combo=partners.get(i, "")) for i in self.offer["ids"]]
                best = min(range(len(cards)), key=lambda k: eng.GRADE_ORDER.get(cards[k]["grade"], 9)) if cards else None
                offer = {"cards": cards, "best": best, "pos": self.offer.get("pos") or [],
                         "rect": self.offer.get("rect")}
            return {
                "live": bool(live),
                "mode": (live or {}).get("mode", ""),
                "is_mayhem": (live or {}).get("mode") == "KIWI",
                "level": (live or {}).get("level", 0),
                "champion": self.champ_view(champ) if champ else None,
                "enemies": [self.champ_view(e) for e in enemies],
                "enemy_slots": list(self.manual_enemies),
                "notes": eng.summarize_enemies(enemies, self.data),
                "chosen": [self.aug_view(a) for a in self.chosen],
                "offer": offer,
                "unconfirmed": {"cards": [self.aug_view(i) for i in self.unconfirmed["ids"]]} if self.unconfirmed else None,
                "builds": self.builds(),
                "builds_locked": bool(live and getattr(self, "locked", None) and self.locked.get("key") == self.game_key),
                "live_build": self.live_build_view(),
                "rank_source": "champ" if cr else "overall",
                "mode": self.mode,
                "runes": self.rune_page(champ),
                "skills": (cr or {}).get("skills") or [],
                "rank_date": self._fmt_date((cr or self.overall or {}).get("date", "")),
                "ranks_version": self.ranks_version,
                "patch": self.data.get("patch", ""),
                "data_status": self.data_status,
                "scanner": self.scanner_status,
                "champ_select": dict(self.champ_select, champion=self.champ_view(self.champ_select["champion"]) if self.champ_select["champion"] else None,
                                     bench=[self.champ_view(n) for n in self.champ_select["bench"]],
                                     team=[self.champ_view(n) for n in self.champ_select["team"]],
                                     cards=[self.champ_view(n) for n in self.champ_select.get("cards") or []],
                                     enemies=[self.champ_view(n) for n in self.champ_select.get("enemies") or []]) if self.champ_select else None,
                "toast": self.toast if self.toast and time.time() - self.toast["t"] < 8 else None,
                "champ_date": self._fmt_date(self.champ_tiers.get("date", "")),
                "stats": (live or {}).get("stats"),
                "game_time": (live or {}).get("time", 0),
                "hotkeys": getattr(self, "hotkey_status", ""),
                "combos": self.combos(),
                "history": self.history[:20],
                "preview_t": self.preview[1],
            }
