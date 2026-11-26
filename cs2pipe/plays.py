"""plays.py: detect plays in a timeline and rank them day-wide.

score = rarity x stakes x player x match tier. Weights are hand-set in config until the
metrics refit (~300 posts). Every feature is kept on the play so it can be logged next to
post metrics later.
"""
from __future__ import annotations

from .schema import Event, Round, Timeline

FLAG_KEYS = ["noscope", "thrusmoke", "attackerblind", "penetrated", "attackerinair"]


def _win_target(total_before: int) -> tuple[int, bool]:
    """Rounds needed to win (MR12, MR3 overtime) and whether this round is overtime."""
    if total_before < 24:
        return 13, False
    segment = (total_before - 24) // 6
    return 16 + 3 * segment, True


def stakes(rnd: Round, tl: Timeline) -> tuple[float, dict]:
    a, b = rnd.score_before["A"], rnd.score_before["B"]
    target, overtime = _win_target(a + b)
    after = {"A": a, "B": b}
    after[rnd.winner_team] += 1
    f = {
        "match_point": max(a, b) == target - 1,
        "overtime": overtime,
        "pistol": rnd.number in (1, 13),
        "closeness": max(0.0, 1 - abs(a - b) / 13),
        "decider": rnd.number == len(tl.rounds) and after[rnd.winner_team] >= target,
    }
    value = (1.0 + 0.5 * f["match_point"] + 0.3 * f["overtime"] + 0.2 * f["pistol"]
             + 0.3 * f["closeness"] + 0.5 * f["decider"])
    return value, f


def _round_plays(tl: Timeline, rnd: Round, rarity_w: dict) -> dict[str, dict]:
    """Per actor: the play components found in this round."""
    sides = rnd.sides
    kills = [e for e in tl.events_in_round(rnd.number)
             if e.type == "kill" and e.actor and e.target and sides.get(e.actor) != sides.get(e.target)
             and e.actor in sides]
    found: dict[str, dict] = {}

    def comp(actor: str) -> dict:
        return found.setdefault(actor, {"components": {}, "events": set()})

    by_actor: dict[str, list[Event]] = {}
    for k in kills:
        by_actor.setdefault(k.actor, []).append(k)
    for actor, ks in by_actor.items():
        if len(ks) >= 3:
            c = comp(actor)
            c["components"][f"{min(len(ks), 5)}k"] = rarity_w.get(f"{min(len(ks), 5)}k", 0)
            c["events"].update(k.id for k in ks)
        for k in ks:
            hits = [f for f in k.flags if f in FLAG_KEYS]
            if hits:
                c = comp(actor)
                for f in hits:
                    c["components"][f] = c["components"].get(f, 0) + rarity_w.get(f, 0)
                c["events"].add(k.id)

    alive = {s: set(p for p, v in sides.items() if v == s) for s in ("CT", "T")}
    clutch = None
    for k in [e for e in tl.events_in_round(rnd.number) if e.type == "kill"]:
        for s in alive.values():
            s.discard(k.target)
        if clutch is None:
            for side, other in (("CT", "T"), ("T", "CT")):
                if len(alive[side]) == 1 and len(alive[other]) >= 2:
                    clutch = (next(iter(alive[side])), side, len(alive[other]), k.tick)
                    break
    if clutch and clutch[1] == rnd.winner_side:
        actor, _, n, from_tick = clutch
        c = comp(actor)
        c["components"][f"clutch_1v{n}"] = rarity_w.get(f"clutch_1v{n}", 0)
        c["events"].update(e.id for e in tl.events_in_round(rnd.number)
                           if e.tick >= from_tick and (e.actor == actor or e.type != "kill"))
    return found


def detect(tl: Timeline, cfg: dict) -> list[dict]:
    rank_cfg = cfg["rank"]
    rarity_w, tier_w, player_w = rank_cfg["rarity"], rank_cfg["tier"], rank_cfg.get("player", {})
    tier = tl.meta.get("tier")
    plays = []
    by_id = {e.id: e for e in tl.events}
    for rnd in tl.rounds:
        st, st_features = stakes(rnd, tl)
        for actor, c in _round_plays(tl, rnd, rarity_w).items():
            values = sorted(c["components"].values(), reverse=True)
            if not values or values[0] <= 0:
                continue
            rarity = values[0] + 0.5 * sum(values[1:])
            name = tl.player_name(actor)
            pw = float(player_w.get(name, 1.0))
            tw = float(tier_w.get(tier, 1.0)) if tier else 1.0
            ev = sorted(c["events"])
            ticks = [by_id[i].tick for i in ev if by_id[i].type != "round_end"]
            plays.append({
                "id": f"{tl.match_id}-r{rnd.number:02d}-{actor}",
                "match_id": tl.match_id,
                "round": rnd.number,
                "actor": actor,
                "actor_name": name,
                "types": sorted(c["components"], key=lambda k: -c["components"][k]),
                "event_ids": ev,
                "start_tick": max(rnd.freeze_end_tick, min(ticks) - 8 * tl.tickrate),
                "key_tick": max(by_id[i].tick for i in ev if by_id[i].type == "kill") if any(
                    by_id[i].type == "kill" for i in ev) else max(ticks),
                "end_tick": min(rnd.end_tick, max(ticks) + 2 * tl.tickrate),
                "rarity": rarity, "stakes": st, "player_w": pw, "tier_w": tw,
                "score": round(rarity * st * pw * tw, 4),
                "features": {"components": c["components"], **st_features, "tier": tier},
            })
    return plays


def rank_day(timelines: list[Timeline], cfg: dict) -> list[dict]:
    plays = [p for tl in timelines for p in detect(tl, cfg) if p["score"] >= cfg["rank"]["min_score"]]
    return sorted(plays, key=lambda p: (-p["score"], p["id"]))
