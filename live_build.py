"""Live build: what to buy next to stay ahead, worked out from everyone's items as the game goes.

Uses the live game data (every player's items, your items and gold, your augments) and the build engine
in its adaptive mode. Separate from the in-game Builds page, which stays locked for the whole game.
"""
import mayhem_engine as eng


def _gold(data, iid):
    it = data["items"].get(str(iid)) or (data.get("basics") or {}).get(str(iid)) or {}
    return int(it.get("gold") or 0)


def _info(data, iid):
    it = data["items"].get(str(iid)) or (data.get("basics") or {}).get(str(iid)) or {}
    return {"id": str(iid), "name": it.get("name", ""), "gold": int(it.get("gold") or 0)}


def _parts(data, iid):
    it = data["items"].get(str(iid)) or (data.get("basics") or {}).get(str(iid)) or {}
    return [str(x) for x in it.get("from") or []]


def _remaining(data, iid, owned):
    """Gold still needed for an item, counting parts already in your inventory."""
    have = list(owned)
    left = _gold(data, iid)

    def walk(i):
        nonlocal left
        for p in _parts(data, i):
            if p in have:
                have.remove(p)
                left -= _gold(data, p)
            else:
                walk(p)
    walk(iid)
    return max(0, left)


def _affordable_part(data, iid, owned, gold):
    """The most expensive part of an item you can buy right now (and don't already have)."""
    have = list(owned)
    best = None
    todo = _parts(data, iid)
    while todo:
        p = todo.pop(0)
        if p in have:
            have.remove(p)
            continue
        g = _gold(data, p)
        if g <= gold:
            if not best or g > best[1]:
                best = (p, g)
        else:
            todo += _parts(data, p)
    return best[0] if best else None


def _item_value(data, items):
    return sum(_gold(data, i) for i in items if i)


def _stat(data, items, key):
    return sum(float((data["items"].get(str(i)) or {}).get("stats", {}).get(key, 0)) for i in items)


def _counter(data, ch, dmg, mode, test, owned, exclude):
    """The best item for this champion that answers a threat (armor, magic resist, health, healing)."""
    w = eng.champion_weights(dict(ch, dmg=dmg))
    for f in ("antiheal", "maxhp", "curhp", "arpen", "mpen_pct", "leth", "mpen"):
        w[f] = max(w.get(f, 0), 0.8)
    prim = eng.primary_stats(ch, dmg, set(), w)
    best = None
    for iid, it in data["items"].items():
        if it.get("boots") or iid in owned or iid in exclude or not test(it):
            continue
        if (mode == "sr" and not it.get("sr", True)) or (mode != "sr" and not it.get("aram", True)):
            continue
        sc, _ = eng.item_score(it, w, dict(ch, dmg=dmg), set(), prim)
        if best is None or sc > best[1]:
            best = (iid, sc)
    return best[0] if best else None


def analyze(svc):
    live = svc.live
    data = svc.data
    if not live or not data:
        return None
    champ = live["champion"]
    ch = data["champions"].get(champ)
    if not ch:
        return None
    builds = svc._make_builds()                    # adaptive: enemies, their items, your items, your augments
    if not builds:
        return None
    best = builds[0]
    owned = [str(i) for i in live.get("owned") or []]
    order = best["items"][:1] + ([best["boots"]] if best.get("boots") else []) + best["items"][1:]
    todo = [i for i in order if str(i["id"]) not in owned]
    gold = int((live.get("stats") or {}).get("gold") or 0)
    out = {"champion": champ, "gold": gold, "style": best.get("style", ""), "done": not todo,
           "next": None, "then": [], "afford": None, "reasons": [], "ahead": None, "threat": None, "defenses": None}
    if todo:
        nxt = todo[0]
        left = _remaining(data, nxt["id"], owned)
        out["next"] = svc.item_view(dict(nxt))
        out["then"] = [svc.item_view(dict(i)) for i in todo[1:3]]
        if gold >= left:
            out["afford"] = {"now": True, "text": f"Buy it now: you have {gold:,} gold"}
        else:
            part = _affordable_part(data, nxt["id"], owned, gold)
            pi = _info(data, part) if part else None
            out["afford"] = {"now": False, "need": left - gold, "part": svc.item_view(pi) if pi else None,
                             "text": (f"{left - gold:,} gold to go. Buy {pi['name']} now" if pi else f"{left - gold:,} gold to go")}

    # what the enemy team is building
    enemy_items = {e: [str(i) for i in items or []] for e, items in (live.get("enemy_items") or {}).items()}
    dmg = ch.get("dmg", "ad")
    armor = {e: _stat(data, it, "armor") for e, it in enemy_items.items()}
    mr = {e: _stat(data, it, "mr") for e, it in enemy_items.items()}
    hp = {e: _stat(data, it, "hp") for e, it in enemy_items.items()}
    heal = {e: sum(1 for i in it for k in ("ls", "omni", "hsp") if (data["items"].get(i) or {}).get("stats", {}).get(k))
            for e, it in enemy_items.items()}
    n = max(1, len(enemy_items))
    out["defenses"] = {"armor": round(sum(armor.values()) / n), "mr": round(sum(mr.values()) / n), "hp": round(sum(hp.values()) / n)}
    names = lambda d, limit: [e for e, v in sorted(d.items(), key=lambda x: -x[1]) if v >= limit][:2]
    plan_its = [data["items"].get(str(i["id"])) or {} for i in todo[:3]]

    def answer(test):
        """The planned item (next few buys) that answers a threat, if any."""
        return next((it for it in plan_its if test(it.get("stats") or {}, set(it.get("feats") or []))), None)
    reasons = []
    if dmg != "ap" and names(armor, 50):
        r = f"{' and '.join(names(armor, 50))} {'are' if len(names(armor, 50)) > 1 else 'is'} stacking armor"
        it = answer(lambda st, f: st.get("arpen") or st.get("leth"))
        if it:
            r += f": {it['name']} cuts through it"
        reasons.append(r)
    if dmg == "ap" and names(mr, 45):
        r = f"{' and '.join(names(mr, 45))} {'are' if len(names(mr, 45)) > 1 else 'is'} stacking magic resist"
        it = answer(lambda st, f: st.get("mpen_pct") or st.get("mpen"))
        if it:
            r += f": {it['name']} cuts through it"
        reasons.append(r)
    if names(hp, 800):
        r = f"{' and '.join(names(hp, 800))} {'have' if len(names(hp, 800)) > 1 else 'has'} a lot of health"
        it = answer(lambda st, f: {"maxhp", "curhp"} & f)
        if it:
            r += f": {it['name']} deals % health damage"
        reasons.append(r)
    healers = [e for e, v in heal.items() if v]
    prof = eng.enemy_profile(list(enemy_items), data, live.get("enemy_items"))
    if healers or prof.get("heal", 0) >= 1.5:
        who = healers or prof.get("healers") or []
        r = f"{', '.join(who[:2])} heal{'s' if len(who[:2]) == 1 else ''} a lot"
        it = answer(lambda st, f: "antiheal" in f)
        r += f": {it['name']} cuts healing" if it else ": get anti-heal soon"
        reasons.append(r)
    # the plan should answer what they're building: if it doesn't, the best counter item goes next
    mode = svc.mode or "mayhem"
    threat = None
    if dmg != "ap" and names(armor, 50):
        threat = ("armor", lambda it: it["stats"].get("arpen") or it["stats"].get("leth"))
    elif dmg == "ap" and names(mr, 45):
        threat = ("mr", lambda it: it["stats"].get("mpen_pct") or it["stats"].get("mpen"))
    elif names(hp, 800):
        threat = ("hp", lambda it: {"maxhp", "curhp"} & set(it.get("feats") or []))
    elif healers or prof.get("heal", 0) >= 1.5:
        threat = ("heal", lambda it: "antiheal" in (it.get("feats") or []))
    if threat:
        plan = [str(i["id"]) for i in todo[:2]]
        covered = any(threat[1](data["items"].get(i) or {"stats": {}, "feats": []}) for i in owned + plan)
        if not covered:
            cid = _counter(data, ch, dmg, mode, threat[1], set(owned), set())
            if cid:
                c = svc.item_view(_info(data, cid))
                rest = [i for i in todo if str(i["id"]) != cid]
                boots_first = rest and (data["items"].get(str(rest[0]["id"])) or {}).get("boots")
                lineup = ([rest[0]] if boots_first else []) + [c] + rest[1 if boots_first else 0:]
                out["next"] = svc.item_view(dict(lineup[0]))
                out["then"] = [svc.item_view(dict(i)) for i in lineup[1:3]]
                out["counter"] = c["name"]
                reasons[0] = reasons[0].split(":")[0] + f": {c['name']} answers it" if reasons else f"{c['name']} answers what they're building"
                nxt = lineup[0]
                left = _remaining(data, nxt["id"], owned)
                if gold >= left:
                    out["afford"] = {"now": True, "text": f"Buy it now: you have {gold:,} gold"}
                else:
                    part = _affordable_part(data, nxt["id"], owned, gold)
                    pi = _info(data, part) if part else None
                    out["afford"] = {"now": False, "need": left - gold, "part": svc.item_view(pi) if pi else None,
                                     "text": (f"{left - gold:,} gold to go. Buy {pi['name']} now" if pi else f"{left - gold:,} gold to go")}
    if not reasons and out["next"]:
        reasons.append(f"{out['next']['name']} adds the most damage against what they have right now")
    out["reasons"] = reasons[:3]

    # are you ahead? item gold compared with the enemy team
    mine = _item_value(data, owned)
    vals = {e: _item_value(data, it) for e, it in enemy_items.items()}
    if vals:
        avg = sum(vals.values()) / len(vals)
        out["ahead"] = {"mine": mine, "their_avg": round(avg), "diff": round(mine - avg)}
        top = max(vals, key=vals.get)
        sc = next((p for p in live.get("players") or [] if p.get("champion") == top), {})
        out["threat"] = {"champion": top, "items_gold": vals[top],
                         "kda": f"{sc.get('k', 0)}/{sc.get('d', 0)}/{sc.get('a', 0)}" if sc else ""}
        pl = {p.get("champion"): p for p in live.get("players") or []}
        out["enemies"] = [{"champion": e, "gold": vals.get(e, 0), "armor": round(armor.get(e, 0)), "mr": round(mr.get(e, 0)),
                           "kda": (f"{pl[e].get('k', 0)}/{pl[e].get('d', 0)}/{pl[e].get('a', 0)}" if e in pl else ""),
                           "items": [svc.item_view(_info(data, i)) for i in it if _gold(data, i) >= 300][:6]}
                          for e, it in sorted(enemy_items.items(), key=lambda x: -vals.get(x[0], 0))]
    return out
