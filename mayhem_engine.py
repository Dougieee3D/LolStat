"""
ARAM Mayhem chaos build engine
------------------------------
Turns your champion + the augments you picked + the enemy team into a few
max-damage item builds. No win rates are used (Riot doesn't allow augment win
rates in apps); builds come from item stats, augment effects and what the
enemy team is made of.

Game data:
  - Items and champions: Riot's Data Dragon (ddragon.leagueoflegends.com)
  - Mayhem augments, augment build tags, champion classes, Mayhem shop list:
    DeepARAM (github.com/nicothomas02/DeepARAM, MIT License), which reads them
    from the game files.
The app ships with a snapshot and refreshes it from those sources when online.
"""

import base64
import json
import os
import re
import time
import urllib.request
import zlib

# ---------------------------------------------------------------- data sources
DD_VERSIONS = "https://ddragon.leagueoflegends.com/api/versions.json"
DD_DATA = "https://ddragon.leagueoflegends.com/cdn/{v}/data/en_US/{f}"
DEEPARAM_RAW = "https://raw.githubusercontent.com/nicothomas02/DeepARAM/main/"
CD_CHERRY = "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/cherry-augments.json"
CD_ASSETS = "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/"
DEEPARAM_FILES = {
    "augments": "guide/augment_details.json",
    "tags": "champions/tags.json",
    "groups": "web/src/data/item-groups.json",
}

# Gold value of one point of each stat (roughly what the shop charges for it).
STAT_GOLD = {
    "ad": 35, "ap": 20, "as": 25, "crit": 40, "critdmg": 30, "leth": 32,
    "arpen": 40, "mpen": 46, "mpen_pct": 40, "haste": 26.7, "hp": 2.67,
    "armor": 20, "mr": 20, "ls": 37, "omni": 40, "ms": 12, "ms_pct": 39,
    "mana": 1.4, "hsp": 45, "tenacity": 10,
}
# Gold-equivalent value of item passives.
FEATURE_GOLD = {
    "antiheal": 650, "maxhp": 750, "curhp": 550, "onhit": 350, "spellblade": 650,
    "burn": 550, "antishield": 550, "ap_amp": 1000, "execute": 350,
}

STAT_NAMES = [  # (text on the item, key, is it a percent stat)
    ("Attack Damage", "ad"), ("Ability Power", "ap"), ("Attack Speed", "as"),
    ("Critical Strike Chance", "crit"), ("Critical Strike Damage", "critdmg"),
    ("Lethality", "leth"), ("Armor Penetration", "arpen"), ("Magic Penetration", "mpen"),
    ("Ability Haste", "haste"), ("Health", "hp"), ("Armor", "armor"),
    ("Magic Resist", "mr"), ("Life Steal", "ls"), ("Omnivamp", "omni"),
    ("Move Speed", "ms"), ("Mana", "mana"), ("Heal and Shield Power", "hsp"),
    ("Tenacity", "tenacity"),
]

KNOWN_HEALERS = {
    "Soraka", "Aatrox", "Vladimir", "Sylas", "Warwick", "Dr. Mundo", "Swain",
    "Fiddlesticks", "Briar", "Yuumi", "Sona", "Nami", "Seraphine", "Illaoi",
    "Olaf", "Darius", "Gwen", "Kayn", "Nasus", "Trundle", "Volibear", "Zac",
    "Maokai", "Senna", "Taric", "Milio", "Renekton", "Samira", "Yone", "Irelia",
}
CLASS_TO_SHOP = {
    "Mage": "mage", "Marksman": "marksman", "Slayer": "assassin", "Fighter": "fighter",
    "Tank": "tank", "Controller": "support",
}


# ---------------------------------------------------------------- data building
def _strip(html):
    return re.sub(r"<[^>]+>", " ", html or "").replace("  ", " ")


def _parse_item(item_id, d, group):
    desc = d.get("description", "")
    stats = {}
    block = re.search(r"<stats>(.*?)</stats>", desc, re.S)
    if block:
        for num, pct, name in re.findall(
                r"<attention>\s*([\d.]+)(%?)\s*</attention>\s*([A-Za-z][A-Za-z' \-]*)", block.group(1)):
            name = name.strip()
            for label, key in STAT_NAMES:
                if name.startswith(label):
                    if key == "mpen" and pct:
                        key = "mpen_pct"
                    if key == "ms" and pct:
                        key = "ms_pct"
                    stats[key] = stats.get(key, 0) + float(num)
                    break
    passive = _strip(re.sub(r"<stats>.*?</stats>", "", desc, flags=re.S)).lower()
    tags = d.get("tags", [])
    feats = []
    if "grievous wounds" in passive:
        feats.append("antiheal")
    if re.search(r"max(imum)? health[^.]{0,50}damage|damage[^.]{0,70}max(imum)? health", passive):
        feats.append("maxhp")
    if re.search(r"current health[^.]{0,50}damage|damage[^.]{0,70}current health|percentage of enemy", passive):
        feats.append("curhp")
    if "OnHit" in tags or "on-hit" in passive:
        feats.append("onhit")
    if "spellblade" in passive:
        feats.append("spellblade")
    if "burn" in passive or "ImmolateItems" in group.get("g", []):
        feats.append("burn")
    if re.search(r"reduc\w* (any |all )?shields|shields? (on them|they gain)[^.]{0,20}reduc", passive):
        feats.append("antishield")
    if re.search(r"increase[^.]{0,30}ability power by", passive):
        feats.append("ap_amp")
    if "execute" in passive:
        feats.append("execute")
    return {
        "name": d["name"],
        "gold": d["gold"]["total"],
        "stats": stats,
        "feats": feats,
        "classes": group.get("c", []),
        "groups": [g for g in group.get("g", []) if g not in ("BootsWithoutActives", "BootsOfSpeed")],
        "boots": "Boots" in tags,
        "tear": "TearItems" in group.get("g", []),
    }


def basic_items(item_json, finished):
    """Starter items and components (what you buy on the way to a finished item)."""
    out = {}
    for iid, d in item_json["data"].items():
        g = d.get("gold", {})
        maps = d.get("maps", {})
        if iid in finished or not g.get("purchasable") or not (maps.get("11") or maps.get("12")):
            continue
        if int(iid) >= 200000 or d.get("requiredChampion") or d.get("requiredAlly"):
            continue                       # Arena copies and champion-only items
        out[iid] = {"name": d["name"], "gold": g.get("total", 0), "from": list(d.get("from") or []),
                    "tags": d.get("tags", []), "sr": bool(maps.get("11")), "aram": bool(maps.get("12"))}
    return out


def build_data(champion_json, item_json, groups, tags_json, augment_json, patch="", cherry=None, runes_json=None):
    tag_champs = {c["id"]: c for c in tags_json.get("champions", {}).values()}
    champions = {}
    for c in champion_json["data"].values():
        key = int(c["key"])
        t = tag_champs.get(key, {})
        att, mag = c["info"]["attack"], c["info"]["magic"]
        if att >= mag + 2:
            dmg = "ad"
        elif mag >= att + 2:
            dmg = "ap"
        else:
            dmg = "ap" if "Mage" in c["tags"] else "ad" if "Marksman" in c["tags"] else "hybrid"
        champions[c["name"]] = {
            "key": key, "alias": c["id"], "name": c["name"], "dmg": dmg,
            "partype": c.get("partype", ""), "range": c["stats"]["attackrange"],
            "classes": t.get("classes", c["tags"]), "subclasses": t.get("subclasses", []),
            "playstyles": t.get("playstyles", []),
            "ratings": t.get("ratings", {"damage": 2, "toughness": 2}),
        }

    items = {}
    for iid, d in item_json["data"].items():
        g = groups.get(iid)
        if not g or g.get("m") != 1 or not d.get("gold", {}).get("purchasable"):
            continue
        is_boots = "Boots" in d.get("tags", [])
        if g.get("e") == 5 or (is_boots and g.get("e") == 4):
            items[iid] = _parse_item(iid, d, g)
            items[iid]["sr"] = bool(d.get("maps", {}).get("11"))       # sold on Summoner's Rift
            items[iid]["aram"] = bool(d.get("maps", {}).get("12"))
            items[iid]["from"] = list(d.get("from") or [])
    basics = basic_items(item_json, items)

    aug_tags = tags_json.get("augments", {})
    icons = {}
    for x in cherry or []:
        p = (x.get("augmentSmallIconPath") or "").replace("/lol-game-data/assets/", "").lower()
        if p:
            icons[str(x.get("id"))] = CD_ASSETS + p
    augments = {}
    for aid, a in augment_json.get("augments", {}).items():
        augments[aid] = {
            "name": a["name"], "tier": a.get("tier", ""),
            "text": a.get("text") or a.get("tooltip") or "",
            "tooltip": a.get("tooltip", ""),
            "tags": aug_tags.get(aid, []),
            "icon": icons.get(aid, ""),
        }
    runes = [{"id": st["id"], "name": st["name"], "icon": st.get("icon", ""),
              "slots": [[{"id": r["id"], "name": r["name"], "icon": r.get("icon", "")} for r in sl["runes"]]
                        for sl in st["slots"]]} for st in (runes_json or [])]
    return {"patch": patch or tags_json.get("patch", ""), "champions": champions, "basics": basics,
            "items": items, "augments": augments, "runes": runes}


def _get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "LoL-AutoAccept"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def download_data():
    """Fetch the latest game data and build it. Raises on any failure."""
    version = _get_json(DD_VERSIONS)[0]
    champ = _get_json(DD_DATA.format(v=version, f="champion.json"))
    item = _get_json(DD_DATA.format(v=version, f="item.json"))
    try:
        runes = _get_json(DD_DATA.format(v=version, f="runesReforged.json"))
    except Exception:
        runes = None
    raw = {k: _get_json(DEEPARAM_RAW + p) for k, p in DEEPARAM_FILES.items()}
    try:
        cherry = _get_json(CD_CHERRY)
    except Exception:
        cherry = None   # icons are optional
    data = build_data(champ, item, raw["groups"], raw["tags"], raw["augments"], version, cherry, runes)
    if len(data["items"]) < 50 or len(data["augments"]) < 50 or len(data["champions"]) < 100:
        raise ValueError("downloaded data looks incomplete")
    return data


def load_data(cache_dir, refresh=True, log=print):
    """Cached/fresh data if possible, otherwise the snapshot bundled with the app."""
    cache = os.path.join(cache_dir, "mayhem_data.json")
    if refresh:
        try:
            data = download_data()
            with open(cache, "w", encoding="utf-8") as f:
                json.dump(data, f)
            log(f"Mayhem data updated (patch {data['patch']}).")
            return data
        except Exception as e:
            log(f"Couldn't update Mayhem data ({e.__class__.__name__}); using saved copy.")
    try:
        with open(cache, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        pass
    from mayhem_snapshot import SNAPSHOT
    return json.loads(zlib.decompress(base64.b64decode(SNAPSHOT)).decode("utf-8"))


# ---------------------------------------------------------------- augment rankings
# Letter grades only (S best). Per-champion grades come from DeepARAM's daily
# per-champion files; the overall grade ranks each augment against the others
# of its rarity. No win-rate numbers are kept or shown.
GRADE_ORDER = {"S+": 0, "S": 1, "A": 2, "B": 3, "C": 4, "D": 5}


def overall_ranks_from(augments_json):
    by_rarity = {}
    for a in augments_json.get("augments", []):
        if a.get("win_rate") is None or not a.get("tier"):
            continue
        by_rarity.setdefault(a["tier"], []).append(a)
    ranks, pick = {}, {}
    for rows in by_rarity.values():
        rows.sort(key=lambda a: -a["win_rate"])
        n = len(rows)
        for i, a in enumerate(rows):
            q = i / max(1, n)
            ranks[str(a["augment_id"])] = ("S+" if q < 0.05 else "S" if q < 0.15 else "A" if q < 0.40 else
                                           "B" if q < 0.70 else "C" if q < 0.90 else "D")
            if a.get("pick_rate") is not None:
                pick[str(a["augment_id"])] = round(a["pick_rate"], 4)
    date = (augments_json.get("meta") or {}).get("augment_stat_date", "")
    return {"date": date, "ranks": ranks, "pick": pick}


def _cached(path, max_age_h):
    try:
        if max_age_h is None or time.time() - os.path.getmtime(path) < max_age_h * 3600:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _save(path, obj):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"                  # write then swap: a crash never leaves a half-written file
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f)
        os.replace(tmp, path)
    except Exception:
        pass


def overall_ranks(cache_dir, max_age_h=6):
    path = os.path.join(cache_dir, "ranks", "overall_v2.json")
    fresh = _cached(path, max_age_h)
    if fresh:
        return fresh
    try:
        out = overall_ranks_from(_get_json(DEEPARAM_RAW + "data/cn/augments.json"))
        if len(out["ranks"]) > 50:
            _save(path, out)
            return out
    except Exception:
        pass
    return _cached(path, None)


def champion_tiers_from(champs_json):
    rows = sorted((c for c in champs_json.get("champions", []) if c.get("rank")), key=lambda c: c["rank"])
    n = len(rows)
    tiers, pick = {}, {}
    for i, c in enumerate(rows):
        q = i / max(1, n)
        tiers[str(c["champion_id"])] = ("S+" if q < 0.05 else "S" if q < 0.15 else "A" if q < 0.40 else
                                        "B" if q < 0.70 else "C" if q < 0.90 else "D")
        if c.get("pick_rate") is not None:
            pick[str(c["champion_id"])] = round(c["pick_rate"], 4)
    date = (champs_json.get("meta") or {}).get("champion_stat_date", "")
    return {"date": date, "tiers": tiers, "pick": pick}


def champion_tiers(cache_dir, max_age_h=6):
    path = os.path.join(cache_dir, "ranks", "champions_v1.json")
    fresh = _cached(path, max_age_h)
    if fresh:
        return fresh
    try:
        out = champion_tiers_from(_get_json(DEEPARAM_RAW + "data/cn/champions.json"))
        if len(out["tiers"]) > 100:
            _save(path, out)
            return out
    except Exception:
        pass
    return _cached(path, None)


def augment_pairs(cache_dir, max_age_h=12):
    """{champion key: [[augment id, augment id, pick rate], ...]} best pairs first (no win rates kept)."""
    path = os.path.join(cache_dir, "ranks", "pairs_v1.json")
    fresh = _cached(path, max_age_h)
    if fresh:
        return fresh
    try:
        est = _get_json(DEEPARAM_RAW + "data/estimates/estimates.json", timeout=40)
        out = {str(k): [[str(r["ids"][0]), str(r["ids"][1]), round(r.get("pick_rate") or 0, 4)] for r in rows[:60] if len(r.get("ids") or []) == 2]
               for k, rows in (est.get("augment_pairs") or {}).items()}
        if out:
            _save(path, out)
            return out
    except Exception:
        pass
    return _cached(path, None) or {}


def champion_ranks(cache_dir, champ_key, max_age_h=6):
    path = os.path.join(cache_dir, "ranks", f"v3_{champ_key}.json")
    fresh = _cached(path, max_age_h)
    if fresh:
        return fresh
    try:
        b = _get_json(DEEPARAM_RAW + f"data/cn/builds/{champ_key}.json")
        ranks, order, pick = {}, {}, {}
        groups = b.get("augments") or {}
        lists = [groups[k] for k in ("prismatic", "gold", "silver") if k in groups] or list(groups.values())
        for rows in lists:
            top_s = 0
            for i, x in enumerate(sorted(rows, key=lambda r: -(r.get("pick_rate") or 0))):
                g = x.get("grade")
                if g not in GRADE_ORDER:
                    continue
                if g == "S" and top_s < 3:      # the 3 most-picked S cards of each rarity are S+
                    g, top_s = "S+", top_s + 1
                aid = str(x["id"])
                ranks.setdefault(aid, g)
                order.setdefault(aid, i)
                if x.get("pick_rate") is not None:
                    pick.setdefault(aid, round(x["pick_rate"], 4))
        # what this champion actually builds in Mayhem (item pick rates) and its skill order
        items = {}
        its = b.get("items") or {}
        for grp in ("other", "boots"):
            for row in its.get(grp) or []:
                for iid in row.get("items") or []:
                    items[str(3095 if iid == 3097 else iid)] = max(items.get(str(iid), 0), row.get("pick_rate") or 0)
        skills = (b.get("skills") or [{}])[0].get("max_order") or []
        out = {"date": b.get("date", ""), "ranks": ranks, "order": order, "pick": pick,
               "items": items, "skills": skills}
        if ranks:
            _save(path, out)
            return out
    except Exception:
        pass
    return _cached(path, None)


# ---------------------------------------------------------------- the engine
def _add(w, key, amount):
    w[key] = w.get(key, 0) + amount


def champion_weights(ch):
    w = {}
    ps = set(ch["playstyles"])
    classes = set(ch["classes"])
    auto = "Auto-attack" in ps or "Marksman" in classes or "Hypercarry" in ps
    ad = 1.0 if ch["dmg"] == "ad" else 0.7 if ch["dmg"] == "hybrid" else 0.0
    ap = 1.0 if ch["dmg"] == "ap" else 0.7 if ch["dmg"] == "hybrid" else 0.0
    _add(w, "ad", ad)
    _add(w, "ap", ap)
    _add(w, "ap_amp", ap)
    if auto:
        _add(w, "as", 0.7)
        _add(w, "crit", 0.6 if ad else 0.1)
        _add(w, "critdmg", 0.5 if ad else 0.0)
        _add(w, "onhit", 0.6)
    else:
        _add(w, "haste", 0.6)
        _add(w, "as", 0.1)
    _add(w, "spellblade", 0.55 + (0.35 if ps & {"Battlecaster", "Duelist", "Auto-attack"} else 0))
    if "Damage-over-Time" in ps or "Battlemage" in ch["subclasses"]:
        _add(w, "burn", 0.6)
        _add(w, "hp", 0.2)
    if classes & {"Fighter", "Tank"} or "Durable" in ps:
        _add(w, "hp", 0.3)
        _add(w, "haste", 0.2)
        _add(w, "omni", 0.2)
    if "Tank" in classes and ch["ratings"].get("damage", 2) <= 2:
        # tanks hit hardest by stacking health and %-health damage
        _add(w, "hp", 0.5)
        _add(w, "maxhp", 0.5)
        _add(w, "burn", 0.4)
    _add(w, "ls", 0.1 * ad)
    _add(w, "omni", 0.1)
    _add(w, "ms", 0.15)
    _add(w, "mana", 0.25 if ch["partype"] == "Mana" and ap else 0.0)
    return w


AUG_TAG_WEIGHTS = {
    "onhit": {"as": 0.6, "onhit": 1.0, "ad": 0.1},
    "crit": {"crit": 0.8, "critdmg": 0.6, "as": 0.3},
    "ap": {"ap": 0.8, "ap_amp": 0.6, "mpen": 0.2},
    "lethality": {"leth": 0.9, "ad": 0.3, "haste": 0.2},
    "tank": {"hp": 0.6, "armor": 0.2, "mr": 0.2, "maxhp": 0.4},
    "fighter": {"ad": 0.3, "hp": 0.3, "haste": 0.2, "omni": 0.2},
    "enchanter": {"hsp": 0.3, "haste": 0.3},
}
AUG_KEYWORDS = [
    (r"attack speed", {"as": 0.4}), (r"ability haste", {"haste": 0.4}),
    (r"critical|crit chance", {"crit": 0.4, "critdmg": 0.2}),
    (r"ability power", {"ap": 0.35}), (r"attack damage", {"ad": 0.35}),
    (r"on-hit", {"onhit": 0.5, "as": 0.2}), (r"lethality", {"leth": 0.5}),
    (r"magic penetration", {"mpen": 0.4, "mpen_pct": 0.3}),
    (r"armor penetration", {"arpen": 0.4}),
    (r"(max(imum)?|bonus) health", {"hp": 0.35}),
    (r"\bmana\b", {"mana": 0.3}), (r"move(ment)? speed", {"ms": 0.25}),
    (r"omnivamp|life steal", {"omni": 0.2, "ls": 0.2}),
    (r"spellblade|sheen", {"spellblade": 0.6}), (r"\bburn", {"burn": 0.4}),
    (r"(heal|shield)\w* (your )?all", {"hsp": 0.3}),
]


def augment_weights(aug):
    w = {}
    for t in aug.get("tags", []):
        for k, v in AUG_TAG_WEIGHTS.get(t, {}).items():
            _add(w, k, v)
    text = (aug.get("text", "") + " " + aug.get("tooltip", "")).lower()
    for pattern, add in AUG_KEYWORDS:
        if re.search(pattern, text):
            for k, v in add.items():
                _add(w, k, v)
    flags = set()
    if re.search(r"convert bonus attack damage to ability power", text):
        flags.add("ad_to_ap")
    if re.search(r"convert ability power to bonus attack damage", text):
        flags.add("ap_to_ad")
    if re.search(r"convert all of your attack speed into ability haste", text):
        flags.add("as_to_haste")
    return w, flags


def enemy_profile(enemy_names, data, enemy_items=None):
    champs = data["champions"]
    p = {"armor": 0.0, "mr": 0.0, "heal": 0.0, "shield": 0.0, "squishy": 0, "tanky": 0,
         "healers": [], "shielders": [], "tanks": [], "squishies": []}
    for n in enemy_names:
        c = champs.get(n)
        if not c:
            continue
        cls, ps, sub = set(c["classes"]), set(c["playstyles"]), set(c["subclasses"])
        tough = c["ratings"].get("toughness", 2)
        if "Tank" in cls:
            p["armor"] += 1.0; p["mr"] += 1.0; p["tanky"] += 1; p["tanks"].append(n)
        elif "Fighter" in cls or "Durable" in ps or tough >= 3:
            p["armor"] += 0.6; p["mr"] += 0.4; p["tanky"] += 0.6
            if tough >= 3:
                p["tanks"].append(n)
        if "Self Healing" in ps or n in KNOWN_HEALERS:
            p["heal"] += 1.0; p["healers"].append(n)
        if "Ally Protection" in ps or "Enchanter" in sub:
            p["shield"] += 1.0; p["shielders"].append(n)
            if n not in p["healers"]:
                p["heal"] += 0.5
        if cls & {"Mage", "Marksman", "Slayer"} and tough <= 1:
            p["squishy"] += 1; p["squishies"].append(n)
    for its in (enemy_items or {}).values():
        for iid in its:
            it = data["items"].get(str(iid))
            if it:
                p["armor"] += it["stats"].get("armor", 0) / 120
                p["mr"] += it["stats"].get("mr", 0) / 120
    return p


def enemy_weights(prof, dmg):
    w = {}
    if dmg in ("ad", "hybrid"):
        _add(w, "arpen", 0.35 + 0.25 * prof["armor"])
        _add(w, "leth", 0.15 + 0.2 * prof["squishy"])
    if dmg in ("ap", "hybrid"):
        _add(w, "mpen_pct", 0.35 + 0.25 * prof["mr"])
        _add(w, "mpen", 0.2 + 0.2 * prof["squishy"])
    _add(w, "maxhp", 0.25 * prof["tanky"])
    _add(w, "curhp", 0.2 * prof["tanky"])
    _add(w, "antiheal", 0.35 * prof["heal"])
    _add(w, "antishield", 0.3 * prof["shield"])
    _add(w, "execute", 0.1 * prof["tanky"])
    return w


AD_PRIMARY = {"ad", "crit", "leth", "arpen"}
AP_PRIMARY = {"ap", "mpen", "mpen_pct"}


def primary_stats(ch, dmg, flags, w):
    """Stats that actually turn into damage for this champion."""
    p = set()
    if dmg in ("ad", "hybrid") or "ad_to_ap" in flags:
        p |= AD_PRIMARY | {"as"}
    if dmg in ("ap", "hybrid") or "ap_to_ad" in flags:
        p |= AP_PRIMARY
    if w.get("onhit", 0) >= 0.9 or "as_to_haste" in flags:
        p.add("as")
    if "Tank" in ch["classes"] and ch["ratings"].get("damage", 2) <= 2:
        p.add("hp")
    return p


def item_score(item, w, ch, flags, primary=None):
    s = 0.0
    parts = {}
    for k, v in item["stats"].items():
        weight = w.get(k, 0)
        if k == "ad" and "ad_to_ap" in flags:
            weight = max(weight, w.get("ap", 0) * 0.9)
        if k == "ap" and "ap_to_ad" in flags:
            weight = max(weight, w.get("ad", 0) * 0.9)
        if k == "as" and "as_to_haste" in flags:
            weight = max(weight, w.get("haste", 0) * 0.8)
        val = v * STAT_GOLD.get(k, 0) * weight
        if val:
            parts[k] = parts.get(k, 0) + val
            s += val
    for f in item["feats"]:
        val = FEATURE_GOLD.get(f, 0) * w.get(f, 0)
        if f == "onhit" and item["stats"].get("ap") and not item["stats"].get("ad"):
            val *= 0.8
        if val:
            parts[f] = parts.get(f, 0) + val
            s += val
    if item.get("tear") and ch["partype"] != "Mana":
        s *= 0.4
    if primary is not None and not item["boots"] and not (primary & set(item["stats"])):
        s *= 0.1  # no stat this champ can turn into damage
    return s, parts


REASON = {
    "ad": "big Attack Damage", "ap": "huge Ability Power", "as": "attack speed",
    "crit": "crit chance", "critdmg": "crit damage", "leth": "lethality to shred squishies",
    "arpen": "armor pen vs {tanks}", "mpen": "magic pen", "mpen_pct": "magic pen vs {tanks}",
    "haste": "ability haste to spam spells", "hp": "health that feeds your damage",
    "onhit": "on-hit damage every attack", "maxhp": "%-health damage vs {tanks}",
    "curhp": "%-health damage vs {tanks}", "antiheal": "anti-heal vs {healers}",
    "antishield": "breaks shields from {shielders}", "spellblade": "Spellblade burst",
    "burn": "burn damage over time", "ap_amp": "multiplies all your AP",
    "execute": "executes low targets", "omni": "sustain", "ls": "life steal",
    "ms": "speed", "mana": "mana for spamming", "hsp": "stronger shields/heals",
    "armor": "armor", "mr": "magic resist",
}


def _reason(parts, prof, aug_boost, aug_names):
    top = sorted(parts.items(), key=lambda kv: -kv[1])[:2]
    fill = {
        "tanks": ", ".join(prof["tanks"][:2]) or "tanky enemies",
        "healers": ", ".join(prof["healers"][:2]) or "healers",
        "shielders": ", ".join(prof["shielders"][:2]) or "shielders",
    }
    bits = [REASON.get(k, k).format(**fill) for k, _ in top]
    text = " + ".join(bits)
    if "ad" in dict(top) and aug_boost.get("ad") == "ADAPt":
        text += " (turns into AP)"
    if "ap" in dict(top) and aug_boost.get("ap") == "escAPADe":
        text += " (turns into AD)"
    for k, _ in top:
        if k in aug_boost:
            text += f"  (combos with {aug_boost[k]})"
            break
    return text[0].upper() + text[1:] if text else ""


BUILD_STYLES = [
    ("MAX DAMAGE", "The hardest-hitting build for your champ, augments and this enemy team."),
    ("AUGMENT OVERDRIVE", "Goes all-in on your augments, even if it's not what your champ usually builds."),
    ("NEVER BEEN DONE", "Off-meta: skips the items your champ type normally buys and finds damage elsewhere."),
]


BUILD_STYLES_CLASSIC = [
    ("MAX DAMAGE", "The hardest-hitting build for your champion against this team."),
    ("COUNTER-DAMAGE", "Built to punch through this enemy team: armor and magic pen, anti-heal, shield breaking."),
    ("NEVER BEEN DONE", "Off-meta: skips the items your champion normally buys and finds damage elsewhere."),
]


def needs_mana(ch):
    """Champions that run out of mana without it: mages, controllers, spell-spamming fighters."""
    if ch.get("partype") != "Mana":
        return False
    cls, ps = set(ch["classes"]), set(ch.get("playstyles") or [])
    return bool(cls & {"Mage", "Controller"} or ps & {"Poke", "Spell-spam"} or "Battlemage" in (ch.get("subclasses") or []))


def damage_model(stats, feats, ch, dmg, prof):
    """Damage output from a set of items against this enemy team (a relative number, used to compare
    builds and orders). Covers AD/AP, attack speed, crit, % multipliers, penetration vs their resists,
    ability haste, on-hit and burn."""
    auto = "Marksman" in ch["classes"] or "Auto-attack" in (ch.get("playstyles") or [])
    tanks = len(prof.get("tanks") or [])
    g = lambda k: float(stats.get(k, 0))
    n = lambda f: sum(1 for x in feats if x == f)
    out = 0.0
    if dmg in ("ad", "hybrid"):
        ad = 95 + g("ad")
        armor = 55 + 30 * tanks + 8 * prof.get("armor", 0)
        eff = max(0.0, armor * (1 - min(g("arpen"), 60) / 100) - g("leth"))
        mit = 100 / (100 + eff)
        if auto:
            crit = min(1.0, g("crit") / 100)
            hit = ad * (1 + crit * (0.75 + g("critdmg") / 100)) + 20 * n("onhit")
            v = hit * (0.7 + 0.7 * min(g("as"), 200) / 100)
        else:
            v = ad * (1 + min(g("haste"), 150) / 160) * (1 + 0.15 * n("spellblade"))
        out += v * mit * (1 + 0.08 * n("maxhp") + 0.06 * n("curhp"))
    if dmg in ("ap", "hybrid"):
        ap = 30 + g("ap")
        if n("ap_amp"):
            ap *= 1.3
        mr = 45 + 20 * tanks + 8 * prof.get("mr", 0)
        eff = max(0.0, mr * (1 - min(g("mpen_pct"), 60) / 100) - g("mpen"))
        mit = 100 / (100 + eff)
        v = (120 + 0.9 * ap) * (1 + min(g("haste"), 150) / 140)
        if auto:
            v *= 0.75 + 0.35 * min(g("as"), 200) / 100
        v *= 1 + 0.10 * n("burn") + 0.08 * n("maxhp") + 0.12 * n("spellblade") + 0.06 * n("onhit")
        out += v * mit * (0.6 if dmg == "hybrid" else 1.0)
    return out


def order_for_damage(picks, legend, ch, dmg, prof, healers=False):
    """Buy order: at every step, the item that adds the most damage per gold on top of what you
    already have. Items that multiply other stats (bonus % AP, crit damage, % penetration) land where
    they're worth the most. Mana users get a mana item in their first two."""
    rest = list(picks)
    have_st, have_f, order = {}, [], []
    while rest:
        base = damage_model(have_st, have_f, ch, dmg, prof)

        def gain(p):
            it = legend[p[0]]
            st = dict(have_st)
            for k, v in it["stats"].items():
                st[k] = st.get(k, 0) + v
            return (damage_model(st, have_f + list(it["feats"]), ch, dmg, prof) - base) / max(1, it.get("gold") or 3000)
        nxt = max(rest, key=gain)
        rest.remove(nxt)
        order.append(nxt)
        for k, v in legend[nxt[0]]["stats"].items():
            have_st[k] = have_st.get(k, 0) + v
        have_f += list(legend[nxt[0]]["feats"])
    if needs_mana(ch) and not any(legend[p[0]]["stats"].get("mana") for p in order[:2]):
        m = next((p for p in order[2:] if legend[p[0]]["stats"].get("mana")), None)
        if m:
            order.remove(m)
            order.insert(1, m)
    if healers:                                  # anti-heal by your third item against heavy healing
        h = next((p for p in order[3:] if "antiheal" in legend[p[0]]["feats"]), None)
        if h:
            order.remove(h)
            order.insert(2, h)
    return order


def make_builds(champion, augment_ids, enemies, data, enemy_items=None, owned=None, champ_items=None, mode="mayhem",
                item_filter=None, no_boots=False):
    ch = data["champions"].get(champion)
    if not ch:
        return []
    if champ_items:   # AD or AP from what this champion actually builds (e.g. Ezreal goes AD, not AP)
        adp = sum(p for i, p in champ_items.items() if data["items"].get(i, {}).get("stats", {}).get("ad"))
        app = sum(p for i, p in champ_items.items() if data["items"].get(i, {}).get("stats", {}).get("ap"))
        if adp + app > 0.3:
            ch = dict(ch, dmg="ad" if adp > 1.6 * app else "ap" if app > 1.6 * adp else "hybrid")
    owned = set(str(i) for i in (owned or []))
    base = champion_weights(ch)
    aug_w, flags, aug_boost = {}, set(), {}
    aug_names = []
    for aid in augment_ids:
        a = data["augments"].get(str(aid))
        if not a:
            continue
        aug_names.append(a["name"])
        w, f = augment_weights(a)
        flags |= f
        for k, v in w.items():
            _add(aug_w, k, v)
            if v >= 0.3 and k not in aug_boost:
                aug_boost[k] = a["name"]
    if "ad_to_ap" in flags:
        aug_boost.setdefault("ad", "ADAPt")
    if "ap_to_ad" in flags:
        aug_boost.setdefault("ap", "escAPADe")
    dmg = ch["dmg"]
    if "ad_to_ap" in flags and dmg == "ad":
        dmg = "hybrid"
    if "ap_to_ad" in flags and dmg == "ap":
        dmg = "hybrid"
    prof = enemy_profile(enemies, data, enemy_items)
    en_w = enemy_weights(prof, dmg)
    main_shop = CLASS_TO_SHOP.get(ch["classes"][0] if ch["classes"] else "", "")

    styles = [
        (1.0, 1.5, 1.0, False, 2.4),   # champ, augments, enemies, avoid usual items, lean on what this champ builds
        (0.45, 3.2, 0.8, False, 0.6),
        (1.0, 1.4, 1.0, True, 0.0),
    ]
    style_names = BUILD_STYLES
    if mode != "mayhem":                # no augments outside Mayhem: the middle build counters the enemy team
        styles[1] = (0.8, 0.0, 2.2, False, 0.8)
        style_names = BUILD_STYLES_CLASSIC
    pop = champ_items or {}
    builds, used = [], {}
    shop = {iid: it for iid, it in data["items"].items()
            if (mode == "sr" and it.get("sr", True)) or (mode != "sr" and it.get("aram", True))}
    if item_filter:                      # challenge rules (Chaos mode)
        legal_boots = {iid: it for iid, it in shop.items() if it["boots"] and item_filter(it)}
        shop = {iid: it for iid, it in shop.items() if (not it["boots"] and item_filter(it))}
        shop.update(legal_boots or {i: it for i, it in data["items"].items() if it["boots"] and it.get("sr", True)})
    if no_boots:
        shop = {iid: it for iid, it in shop.items() if not it["boots"]}
    for (name, blurb), (cm, am, em, offmeta, lean) in zip(style_names, styles):
        w = {}
        for src, m in ((base, cm), (aug_w, am), (en_w, em)):
            for k, v in src.items():
                _add(w, k, v * m)
        if prof["heal"] >= 1.5:
            w["antiheal"] = max(w.get("antiheal", 0), 0.9)
        if needs_mana(ch):
            w["mana"] = max(w.get("mana", 0), 0.6)    # mana users: a mana item keeps the damage coming

        def score(iid, it):
            s, parts = item_score(it, w, ch, flags, primary_stats(ch, dmg, flags, w))
            pr = pop.get(iid, 0.0)
            if pop and not offmeta:
                s *= 1 + lean * min(1.0, pr * 2.5)        # favour items this champion really builds
            if offmeta:
                if pop:
                    s *= max(0.12, 1 - 2.2 * pr)          # skip what this champion usually buys
                    s *= 1.08 if pr < 0.02 else 1.0       # almost nobody builds it on this champ: never been done
                elif main_shop and main_shop in it["classes"]:
                    s *= 0.45
            s *= 0.8 ** used.get(iid, 0)
            return s, parts

        legend = {i: it for i, it in shop.items() if not it["boots"]}
        boots = {i: it for i, it in shop.items() if it["boots"]}
        picks, taken_groups = [], set()
        for _ in range(5):
            best = None
            for iid, it in legend.items():
                if iid in [p[0] for p in picks] or taken_groups & set(it["groups"]):
                    continue
                s, parts = score(iid, it)
                if best is None or s > best[1]:
                    best = (iid, s, parts)
            if not best:
                break
            iid, s, parts = best
            picks.append(best)
            taken_groups |= set(legend[iid]["groups"])
            for f in legend[iid]["feats"]:
                if f in ("antiheal", "antishield", "ap_amp", "spellblade"):
                    w[f] = 0
                elif f in ("maxhp", "curhp", "burn", "onhit"):
                    w[f] = w.get(f, 0) * 0.6
        # make sure there's anti-heal against heavy healing
        if prof["heal"] >= 1.5 and picks and not any("antiheal" in legend[p[0]]["feats"] for p in picks):
            w["antiheal"] = 1.0
            prim = primary_stats(ch, dmg, flags, w)
            best_swap = None
            for i, it in legend.items():
                if "antiheal" not in it["feats"] or not (prim & set(it["stats"])):
                    continue
                # drop the item it clashes with, or else the weakest pick
                clash = [p for p in picks if set(legend[p[0]]["groups"]) & set(it["groups"])]
                drop = clash[0] if clash else min(picks, key=lambda p: p[1])
                s, parts = score(i, it)
                if best_swap is None or s - drop[1] > best_swap[0]:
                    best_swap = (s - drop[1], drop, (i, s, parts))
            if best_swap:
                picks = [p for p in picks if p is not best_swap[1]] + [best_swap[2]]
        bpick = max(((i, *score(i, it)) for i, it in boots.items()), key=lambda c: c[1], default=None)

        # order: the most damage per gold at every step
        picks = order_for_damage(picks, legend, ch, dmg, prof, healers=prof["heal"] >= 1.5)

        out = []
        for iid, s, parts in picks:
            why = _reason(parts, prof, aug_boost, aug_names)
            feats = legend[iid]["feats"]
            if "antiheal" in feats and prof["healers"] and "anti-heal" not in why:
                why += "  · anti-heal vs " + ", ".join(prof["healers"][:2])
            if "antishield" in feats and prof["shielders"] and "shields" not in why:
                why += "  · breaks shields from " + ", ".join(prof["shielders"][:2])
            out.append({"id": iid, "name": legend[iid]["name"], "owned": iid in owned, "why": why})
            used[iid] = used.get(iid, 0) + 1
        bout = None
        if bpick:
            bout = {"id": bpick[0], "name": boots[bpick[0]]["name"], "owned": bpick[0] in owned,
                    "why": _reason(bpick[2], prof, aug_boost, aug_names)}
        builds.append({"style": name, "blurb": blurb, "boots": bout, "items": out})
    return builds


def summarize_enemies(enemies, data):
    p = enemy_profile(enemies, data)
    notes = []
    if p["tanks"]:
        notes.append("Tanky: " + ", ".join(p["tanks"]))
    if p["healers"]:
        notes.append("Healing: " + ", ".join(p["healers"]))
    if p["shielders"]:
        notes.append("Shields: " + ", ".join(p["shielders"]))
    if p["squishies"]:
        notes.append("Squishy: " + ", ".join(p["squishies"]))
    return notes
