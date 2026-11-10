"""Turns a build (6 finished items + boots) into a buying guide:
starting items -> first back -> core (rush the first) -> boots -> end game -> situational swaps.
"""
import mayhem_engine as eng

POTION, BOOTS1, TEAR = "2003", "1001", "3070"
DORAN_BLADE, DORAN_RING, DORAN_SHIELD = "1055", "1056", "1054"
WORLD_ATLAS = "3865"
PET_DAMAGE, PET_MOBILITY, PET_TANK = "1101", "1102", "1103"     # Scorchclaw, Gustwalker, Mosstomper
START_GOLD = {"sr": 500, "aram": 1400, "mayhem": 1400}
MODE_WORD = {"sr": "Summoner's Rift", "aram": "ARAM", "mayhem": "ARAM Mayhem"}

STEELCAPS, MERCS = "3047", "3111"

# situational swaps: (key, heading, test on an item, when to buy it)
SITUATIONS = [
    ("heal", "Anti-heal", lambda it: "antiheal" in it["feats"],
     "if they have a lot of healing"),
    ("tank", "Vs tanks", lambda it: bool(it["stats"].get("arpen") or it["stats"].get("mpen_pct")
                                         or {"maxhp", "curhp"} & set(it["feats"])),
     "if they have 2 or more tanks"),
    ("shield", "Vs shields", lambda it: "antishield" in it["feats"],
     "if their supports shield a lot"),
    ("ad", "Vs physical damage", lambda it: it["stats"].get("armor", 0) >= 20,
     "if their damage is mostly physical (AD)"),
    ("ap", "Vs magic damage", lambda it: it["stats"].get("mr", 0) >= 20,
     "if their damage is mostly magic (AP)"),
]


def _info(data, iid):
    it = data["items"].get(iid) or (data.get("basics") or {}).get(iid)
    if not it:
        return None
    return {"id": iid, "name": it["name"], "gold": it.get("gold", 0)}


def _parts(data, iid):
    it = data["items"].get(iid) or (data.get("basics") or {}).get(iid) or {}
    return list(it.get("from") or [])


def _gold(data, iid):
    it = data["items"].get(iid) or (data.get("basics") or {}).get(iid) or {}
    return it.get("gold", 0)


def _buyable_parts(data, iid, budget):
    """Components of an item, split further until each one fits the budget."""
    out, todo = [], _parts(data, iid)
    while todo:
        p = todo.pop(0)
        if _gold(data, p) > budget and _parts(data, p):
            todo = _parts(data, p) + todo
        else:
            out.append(p)
    return out


def guess_role(ch):
    cls, sub = set(ch["classes"]), set(ch.get("subclasses") or [])
    if "Marksman" in cls:
        return "bottom"
    if "Controller" in cls or "Enchanter" in sub or "Catcher" in sub:
        return "utility"
    return ""


def build_dmg(build, data, ch):
    ad = sum(1 for i in build["items"] if data["items"].get(i["id"], {}).get("stats", {}).get("ad"))
    ap = sum(1 for i in build["items"] if data["items"].get(i["id"], {}).get("stats", {}).get("ap"))
    if ad >= ap + 2:
        return "ad"
    if ap >= ad + 2:
        return "ap"
    return ch["dmg"]


def _start(ch, data, mode, role, first, dmg, has_boots, build_items=None):
    if mode == "sr":
        role = role or guess_role(ch)
        cls = set(ch["classes"])
        first_it = data["items"].get(first, {})
        if role == "jungle":
            pet = PET_TANK if "Tank" in cls else PET_MOBILITY if "Slayer" in cls or "Assassin" in (ch.get("subclasses") or []) else PET_DAMAGE
            return [pet, POTION], "Jungle start. Upgrade your pet as you clear."
        if role == "utility":
            return [WORLD_ATLAS, POTION, POTION], "Support start. Finish your quest, then upgrade the support item."
        if first_it.get("tear") and ch["partype"] == "Mana":
            return [TEAR, POTION, POTION], "Start Tear to begin stacking mana early."
        if dmg == "ap" or "Mage" in cls:
            return [DORAN_RING, POTION, POTION], "Lane start for mages."
        if "Tank" in cls or ("Fighter" in cls and ch["ratings"].get("toughness", 2) >= 3 and dmg != "ad"):
            return [DORAN_SHIELD, POTION], "Safe lane start for tanks and bruisers."
        return [DORAN_BLADE, POTION], "Damage lane start."
    return _best_start(ch, data, mode, build_items or [first], has_boots, dmg)


# stats of the item parts you can start with (finished items carry their own stats in the game data)
PART_STATS = {
    "1036": {"ad": 10}, "1037": {"ad": 25}, "1038": {"ad": 40}, "1042": {"as": 10}, "1043": {"as": 15},
    "1018": {"crit": 15}, "1052": {"ap": 20}, "1026": {"ap": 45}, "1058": {"ap": 65}, "1027": {"mana": 300},
    "1028": {"hp": 150}, "1029": {"armor": 15}, "1031": {"armor": 40}, "1033": {"mr": 25}, "1057": {"mr": 45},
    "1011": {"hp": 350}, "1053": {"ad": 15, "ls": 7}, "2022": {"haste": 5}, "1001": {"ms": 25},
    "3070": {"mana": 240, "haste": 2}, "3802": {"ap": 40, "mana": 300, "haste": 10}, "3133": {"ad": 20, "haste": 10},
    "3134": {"ad": 20, "leth": 10}, "3057": {"haste": 5, "spellblade": 1}, "3145": {"ap": 45}, "3108": {"ap": 35, "haste": 10},
    "3113": {"ap": 30, "ms_pct": 4}, "3916": {"ap": 25, "antiheal": 1}, "3123": {"ad": 20, "antiheal": 1},
    "1082": {"ap": 15, "hp": 50}, "3086": {"as": 15, "crit": 15, "ms_pct": 2}, "6670": {"ad": 15, "as": 15, "crit": 20},
    "3044": {"ad": 15, "hp": 200}, "3067": {"hp": 200, "haste": 10}, "3077": {"ad": 20}, "3051": {"ad": 15, "as": 20},
    "3803": {"hp": 300, "mana": 300}, "3155": {"ad": 25, "mr": 35}, "3147": {"ap": 30, "hp": 150},
    "4630": {"ap": 25, "mpen_pct": 13}, "6660": {"hp": 200, "burn": 1}, "3801": {"hp": 200}, "3076": {"armor": 30},
    "3082": {"armor": 40}, "3211": {"hp": 250, "mr": 25}, "3140": {"mr": 30}, "4642": {"ap": 20, "haste": 10},
    "3024": {"armor": 20, "mana": 250, "haste": 10}, "3035": {"ad": 20, "arpen": 18}, "1083": {"ad": 7},
    "3041": {"ap": 20, "hp": 100}, "2019": {"armor": 30, "hp": 200}, "3112": {"ap": 40, "hp": 150},
}


def _needs_mana(ch):
    return eng.needs_mana(ch)


def _part_value(data, iid, w):
    """Gold-equivalent value of a part for this champion: damage stats count fully, the rest less."""
    st = PART_STATS.get(iid)
    if st is None:
        it = data["items"].get(iid) or {}
        st = dict(it.get("stats") or {}, **{f: 1 for f in it.get("feats") or []})
    v = 0.0
    for k, amt in st.items():
        if k in eng.FEATURE_GOLD:
            v += eng.FEATURE_GOLD[k] * 0.5 * max(w.get(k, 0), 0.2)
        else:
            v += amt * eng.STAT_GOLD.get(k, 0) * (w.get(k, 0) if k in w else 0.15)
    return v


def _best_start(ch, data, mode, build_items, has_boots, dmg):
    """Every way to spend your starting gold on parts of your build, scored: damage for your champion,
    progress on the item you rush, and mana if your champion needs it. The highest score wins."""
    budget = START_GOLD.get(mode, 1400)
    w = eng.champion_weights(dict(ch, dmg=dmg))
    nodes = []                                   # (part id, gold, tree, ancestors)

    def walk(iid, tree, anc):
        for p in _parts(data, iid):
            g = _gold(data, p)
            if g and g <= budget:
                nodes.append((p, g, tree, anc))
            walk(p, tree, anc + (p,))
    for t, it in enumerate(build_items[:2]):
        walk(str(it), t, ())
    if has_boots:
        nodes.append((BOOTS1, _gold(data, BOOTS1), 2, ()))
    nodes = nodes[:40]
    tree_w = {0: 1.0, 1: 0.7, 2: 0.55}            # the rush item first, then the second item, then boots
    needs_mana = _needs_mana(ch) and any(PART_STATS.get(n[0], {}).get("mana") for n in nodes)
    best, best_sc = [], -1
    n = len(nodes)

    def rec(i, picks, gold):
        nonlocal best, best_sc
        if i == n or len(picks) == 4:
            if not picks:
                return
            sc = sum(_part_value(data, nodes[j][0], w) * tree_w[nodes[j][2]] + nodes[j][1] * 0.35 * tree_w[nodes[j][2]]
                     + (0.15 * nodes[j][1] if _parts(data, nodes[j][0]) else 0)      # already combined: its bonus comes now
                     for j in picks)
            sc -= 80 * max(0, len(picks) - 2)     # fewer, bigger parts: inventory slots matter
            if needs_mana and not any(PART_STATS.get(nodes[j][0], {}).get("mana") for j in picks):
                sc *= 0.7                         # you'd run dry: a start with mana scores higher
            sc += min(2, (budget - gold) // 50) * 25  # leftover gold buys potions
            if sc > best_sc:
                best, best_sc = [nodes[j][0] for j in picks], sc
            return
        p, g, tree, anc = nodes[i]
        clash = any(nodes[j][2] == tree and (nodes[j][0] in anc or p in nodes[j][3]) for j in picks)
        if gold + g <= budget and not clash:
            rec(i + 1, picks + [i], gold + g)
        rec(i + 1, picks, gold)
    rec(0, [], 0)
    left = budget - sum(_gold(data, p) for p in best)
    best = sorted(best, key=lambda p: -_gold(data, p))
    while left >= 50 and best.count(POTION) < 2:
        best.append(POTION)
        left -= 50
    has_mana = any(PART_STATS.get(p, {}).get("mana") for p in best)
    note = "The best start for your champion: the most damage from your starting gold, building into the item you rush"
    note += ", with mana so you can keep casting." if needs_mana and has_mana else "."
    return best, note


def _remaining_parts(data, iid, have, budget):
    """What's left to buy for an item, counting parts you already have (also inside bigger parts)."""
    def contains(node, part):
        return any(p == part or contains(p, part) for p in _parts(data, node))
    out = []
    for p in _parts(data, iid):
        if p in have:
            have.remove(p)
        elif any(contains(p, h) for h in have) or _gold(data, p) > budget and _parts(data, p):
            out += _remaining_parts(data, p, have, budget)
        else:
            out.append(p)
    return out


def _first_back(data, mode, start, first, has_boots):
    have = list(start)
    rest = _remaining_parts(data, first, have, 1300 if mode == "sr" else 1400)
    rest.sort(key=lambda p: -_gold(data, p))
    if has_boots and BOOTS1 not in start:
        rest.insert(1 if rest else 0, BOOTS1)
    note = ("Back with about 1,100-1,300 gold and buy from the left." if mode == "sr"
            else "Each time you die, keep buying from the left until your first item is done.")
    return rest[:4], note


def _enemy_notes(prof, enemies, data):
    """Which situations are already true for this enemy team."""
    now = {}
    if prof["heal"] >= 1.5 and prof["healers"]:
        now["heal"] = "they have healing: " + ", ".join(prof["healers"][:3])
    if len(prof["tanks"]) >= 2:
        now["tank"] = "they have tanks: " + ", ".join(prof["tanks"][:3])
    if prof["shield"] >= 1 and prof["shielders"]:
        now["shield"] = "they shield: " + ", ".join(prof["shielders"][:2])
    ad = [e for e in enemies if data["champions"].get(e, {}).get("dmg") == "ad"]
    ap = [e for e in enemies if data["champions"].get(e, {}).get("dmg") == "ap"]
    if len(ad) >= 3:
        now["ad"] = f"{len(ad)} of them deal physical damage"
    if len(ap) >= 3:
        now["ap"] = f"{len(ap)} of them deal magic damage"
    return now


def _situational(ch, data, mode, build, dmg, enemies):
    in_build = {i["id"] for i in build["items"]} | ({build["boots"]["id"]} if build.get("boots") else set())
    shop = {iid: it for iid, it in data["items"].items() if not it["boots"]
            and ((mode == "sr" and it.get("sr", True)) or (mode != "sr" and it.get("aram", True)))}
    w = eng.champion_weights(dict(ch, dmg=dmg))
    prof = eng.enemy_profile(enemies, data)
    now = _enemy_notes(prof, enemies, data)
    out, used = [], set(in_build)
    for key, head, test, when in SITUATIONS:
        if key == "shield" and dmg == "ap":
            continue                                  # no AP shield breaker worth the slot
        ww = dict(w)
        for f in ("antiheal", "antishield", "maxhp", "curhp", "arpen", "mpen_pct"):
            ww[f] = max(ww.get(f, 0), 0.8)
        if key in ("ad", "ap"):
            ww["armor" if key == "ad" else "mr"] = max(ww.get("armor" if key == "ad" else "mr", 0), 0.6)
        prim = eng.primary_stats(ch, dmg, set(), ww) | ({"armor"} if key == "ad" else {"mr"} if key == "ap" else set())
        best = None
        for iid, it in shop.items():
            if iid in used or not test(it):
                continue
            s, _ = eng.item_score(it, ww, dict(ch, dmg=dmg), set(), prim)
            if best is None or s > best[1]:
                best = (iid, s)
        if not best:
            continue
        # an item already in the build covers this situation: say so instead of adding a swap
        covered = next((i for i in build["items"] if test(data["items"].get(i["id"], {"stats": {}, "feats": []}))), None)
        if covered and key in ("heal", "tank", "shield"):
            continue
        used.add(best[0])
        out.append({"id": best[0], "name": data["items"][best[0]]["name"], "situation": head,
                    "when": ("Buy it now: " + now[key]) if key in now else "Buy " + when,
                    "urgent": key in now})
    # boots swaps
    boots = build.get("boots")
    if boots:
        for bid, key, text in ((STEELCAPS, "ad", "vs auto-attackers and physical damage"),
                               (MERCS, "ap", "vs magic damage and lots of crowd control")):
            if bid != boots["id"] and bid in data["items"] and (mode == "sr" or data["items"][bid].get("aram", True)):
                out.append({"id": bid, "name": data["items"][bid]["name"], "situation": "Boots swap",
                            "when": ("Buy it now: " + now[key]) if key in now else "Swap your boots " + text,
                            "urgent": key in now})
    out.sort(key=lambda x: not x["urgent"])
    return out


def guide(build, champion, data, mode="sr", role="", enemies=()):
    """build: {"boots": {...} or None, "items": [{id, name, why}, ...]} as made by make_builds."""
    ch = data["champions"].get(champion)
    items = build.get("items") or []
    if not ch or not items:
        return None
    enemies = [e for e in enemies or [] if e in data["champions"]]
    dmg = build_dmg(build, data, ch)
    first = items[0]["id"]
    has_boots = bool(build.get("boots"))
    start, start_note = _start(ch, data, mode, role, first, dmg, has_boots, [i["id"] for i in items])
    back, back_note = _first_back(data, mode, start, first, has_boots)
    info = lambda ids: [x for x in (_info(data, i) for i in ids) if x]
    core = [dict(i, rush=(n == 0)) for n, i in enumerate(items[:3])]
    boots_note = "Finish these after your first item." if mode == "sr" else "Finish these right after your first item."
    if has_boots and "Marksman" in ch["classes"]:
        boots_note = "Finish these after your first or second item."
    return {
        "start": {"items": info(start), "note": start_note, "gold": START_GOLD.get(mode, 500)},
        "first_back": {"items": info(back), "note": back_note},
        "core": core,
        "boots": {"item": build.get("boots"), "note": boots_note} if has_boots else None,
        "late": items[3:],
        "situational": _situational(ch, data, mode, build, dmg, enemies),
    }
