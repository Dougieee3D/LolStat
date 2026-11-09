"""LoLStat rune pages: damage-focused pages by champion type, built from Riot's current rune trees."""

# (primary tree, [keystone, row1, row2, row3], secondary tree, [two runes], first stat shard)
PRESETS = {
    "marksman":   ("Precision", ["Lethal Tempo", "Presence of Mind", "Legend: Alacrity", "Cut Down"],
                   "Domination", ["Taste of Blood", "Treasure Hunter"], 5005),
    "assassin":   ("Domination", ["Electrocute", "Sudden Impact", "Grisly Mementos", "Treasure Hunter"],
                   "Precision", ["Presence of Mind", "Coup de Grace"], 5008),
    "fighter":    ("Precision", ["Conqueror", "Triumph", "Legend: Alacrity", "Last Stand"],
                   "Resolve", ["Second Wind", "Unflinching"], 5008),
    "burst_mage": ("Domination", ["Electrocute", "Taste of Blood", "Grisly Mementos", "Ultimate Hunter"],
                   "Sorcery", ["Manaflow Band", "Gathering Storm"], 5008),
    "battlemage": ("Sorcery", ["Deathfire Touch", "Manaflow Band", "Transcendence", "Gathering Storm"],
                   "Domination", ["Taste of Blood", "Ultimate Hunter"], 5008),
    "artillery":  ("Sorcery", ["Arcane Comet", "Manaflow Band", "Transcendence", "Scorch"],
                   "Inspiration", ["Magical Footwear", "Biscuit Delivery"], 5008),
    "tank":       ("Resolve", ["Grasp of the Undying", "Demolish", "Second Wind", "Overgrowth"],
                   "Precision", ["Triumph", "Legend: Haste"], 5008),
    "enchanter":  ("Sorcery", ["Summon Aery", "Manaflow Band", "Transcendence", "Scorch"],
                   "Resolve", ["Font of Life", "Revitalize"], 5008),
    "onhit":      ("Precision", ["Lethal Tempo", "Presence of Mind", "Legend: Alacrity", "Last Stand"],
                   "Domination", ["Sudden Impact", "Treasure Hunter"], 5005),
}
LABEL = {"marksman": "Marksman", "assassin": "Assassin", "fighter": "Bruiser", "burst_mage": "Burst mage",
         "battlemage": "Battle mage", "artillery": "Poke mage", "tank": "Tank damage", "enchanter": "Enchanter",
         "onhit": "On-hit"}
SHARDS_FLEX, SHARDS_DEF = 5008, 5011     # adaptive force, base health


def archetype(ch, dmg=None):
    classes, subs, ps = set(ch.get("classes", [])), set(ch.get("subclasses", [])), set(ch.get("playstyles", []))
    dmg = dmg or ch.get("dmg", "ad")
    if "Tank" in classes and ch.get("ratings", {}).get("damage", 2) <= 2:
        return "tank"
    if "Enchanter" in subs or ("Controller" in classes and dmg != "ad"):
        return "enchanter"
    if "Marksman" in classes:
        return "onhit" if dmg != "ad" else "marksman"
    if "Assassin" in subs or "Slayer" in classes:
        return "burst_mage" if dmg == "ap" else "assassin"
    if "Mage" in classes or dmg == "ap":
        if "Burst" in subs:
            return "burst_mage"
        if "Artillery" in subs or "Long Range" in ps:
            return "artillery"
        return "battlemage"
    return "fighter"


def build_page(ch, runes_data, dmg=None):
    """A complete rune page for the client, or None if the rune trees aren't available."""
    if not runes_data:
        return None
    kind = archetype(ch, dmg)
    p_name, p_runes, s_name, s_runes, shard1 = PRESETS[kind]
    trees = {t["name"]: t for t in runes_data}
    prim, sec = trees.get(p_name), trees.get(s_name)
    if not prim or not sec:
        return None

    def pick(tree, name, rows):
        for i in rows:
            for r in tree["slots"][i]:
                if r["name"].lower() == name.lower():
                    return r, i
        return None, None

    ids, names = [], []
    for row, name in enumerate(p_runes):          # one rune per row; fall back to the row's first rune
        r, _ = pick(prim, name, [row])
        r = r or prim["slots"][row][0]
        ids.append(r["id"]); names.append(r["name"])
    used_rows = []
    for name in s_runes:                          # two runes from different non-keystone rows
        r, i = pick(sec, name, [1, 2, 3])
        if not r or i in used_rows:
            i = next(x for x in (1, 2, 3) if x not in used_rows)
            r = sec["slots"][i][0]
        used_rows.append(i)
        ids.append(r["id"]); names.append(r["name"])
    ids += [shard1, SHARDS_FLEX, SHARDS_DEF]
    return {"name": f"LoLStat {ch['name']}"[:25], "primaryStyleId": prim["id"], "subStyleId": sec["id"],
            "selectedPerkIds": ids, "current": True,
            "label": LABEL[kind], "keystone": names[0], "primary": p_name, "secondary": s_name, "runes": names}


def apply_page(lcu_call, page):
    """Put the page in the client: reuse LoLStat's page, else use a free slot. Never overwrites yours."""
    body = {k: page[k] for k in ("name", "primaryStyleId", "subStyleId", "selectedPerkIds", "current")}
    pages = lcu_call("GET", "/lol-perks/v1/pages") or []
    ours = [p for p in pages if str(p.get("name", "")).startswith("LoLStat") and p.get("isEditable", True)]
    if ours:
        lcu_call("DELETE", f"/lol-perks/v1/pages/{ours[0]['id']}")
    else:
        inv = lcu_call("GET", "/lol-perks/v1/inventory") or {}
        editable = [p for p in pages if p.get("isEditable")]
        owned = inv.get("ownedPageCount", 0)
        if owned and len(editable) >= owned:
            raise RuntimeError("all your rune pages are in use; free one up and LoLStat will keep it updated")
    lcu_call("POST", "/lol-perks/v1/pages", body)
    return True
