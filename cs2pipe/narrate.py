"""narrate.py: grounded script per play, then a verifier pass.

The model sees callout names and derived facts (alive counts, score, time into round), never
raw coordinates. A script passes only if every sentence cites at least one event id from the
fact sheet, the word count is in budget, and a second model pass finds every sentence
supported by the events it cites.
"""
from __future__ import annotations

import json
import re

from .schema import Timeline

FALLBACK_BETA = "server-side-fallback-2026-07-01"

SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "cites": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text", "cites"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "sentences"],
    "additionalProperties": False,
}

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "supported": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["index", "supported", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["results"],
    "additionalProperties": False,
}

WRITER_SYSTEM = """You write narration for a vertical short that breaks down one professional Counter-Strike 2 play.
The viewer has just watched the 3-second clip. Your job is to explain how it happened: two or three causal beats
(positioning, timing, numbers advantage, utility, economy or score pressure) that led to the outcome.

Rules:
- Use only facts in the fact sheet. Never invent positions, utility, intent or player history.
- Every sentence must cite one or more event ids from the fact sheet in its "cites" list.
- Use callout names and player names as written. No raw coordinates or tick numbers.
- {min_words} to {max_words} words in total across all sentences. Plain spoken English, no hype words.
- "title" is a short on-screen title (under 60 characters) naming the player and the play."""

VERIFIER_SYSTEM = """You check narration against a fact sheet from a Counter-Strike 2 demo.
For each numbered sentence, decide whether every factual claim in it is supported by the events it cites
(plus the round header). A claim not stated in or directly implied by those events is unsupported.
Return one result per sentence."""


def fact_sheet(tl: Timeline, play: dict) -> dict:
    rnd = tl.rounds[play["round"] - 1]
    side_of = rnd.sides
    alive = {s: sum(1 for v in side_of.values() if v == s) for s in ("CT", "T")}
    t0 = rnd.freeze_end_tick
    rows = []
    for e in tl.events_in_round(rnd.number):
        row = {"id": e.id, "t": round((e.tick - t0) / tl.tickrate, 1), "type": e.type}
        if e.type == "kill":
            victim_side = side_of.get(e.target)
            if victim_side:
                alive[victim_side] -= 1
            row.update({
                "killer": tl.player_name(e.actor), "killer_side": side_of.get(e.actor),
                "victim": tl.player_name(e.target), "victim_side": victim_side,
                "weapon": e.weapon, "flags": e.flags,
                "killer_place": e.place, "victim_place": e.data.get("victim_place"),
                "alive_after": dict(alive),
            })
        elif e.type in ("bomb_planted", "bomb_defused"):
            row.update({"player": tl.player_name(e.actor), "place": e.place})
        else:
            row.update({"winner_side": e.data.get("winner_side"), "reason": e.data.get("reason")})
        rows.append(row)
    team_side = {rnd.sides[p.steamid]: tl.teams[p.team] for p in tl.players if p.steamid in rnd.sides}
    return {
        "match": {"event": tl.meta.get("event"), "map": tl.map, "teams": tl.teams},
        "round": {
            "number": rnd.number,
            "score_before": {tl.teams["A"]: rnd.score_before["A"], tl.teams["B"]: rnd.score_before["B"]},
            "sides": team_side,
            "winner": tl.teams[rnd.winner_team],
            "stakes": {k: v for k, v in play["features"].items() if k in ("match_point", "overtime", "pistol", "decider")},
        },
        "play": {"player": play["actor_name"], "types": play["types"], "key_events": play["event_ids"]},
        "events": rows,
    }


def _call(client, cfg: dict, system: str, user: str, schema: dict) -> dict | None:
    n = cfg["narrate"]
    response = client.beta.messages.create(
        model=n["model"],
        max_tokens=16000,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        system=system,
        output_config={"effort": n["effort"], "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": user}],
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        return None
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def check_script(script: dict, facts: dict, cfg: dict) -> list[str]:
    """Deterministic checks. Returns a list of problems; empty means pass."""
    n = cfg["narrate"]
    ids = {e["id"] for e in facts["events"]}
    problems = []
    for i, s in enumerate(script["sentences"]):
        if not s["cites"]:
            problems.append(f"sentence {i}: no citation")
        bad = [c for c in s["cites"] if c not in ids]
        if bad:
            problems.append(f"sentence {i}: unknown event ids {bad}")
        if re.search(r"\bE\d{4}\b", s["text"]):
            problems.append(f"sentence {i}: event id in spoken text")
    words = sum(len(s["text"].split()) for s in script["sentences"])
    if not n["min_words"] <= words <= n["max_words"]:
        problems.append(f"word count {words} outside {n['min_words']}-{n['max_words']}")
    return problems


def narrate(tl: Timeline, play: dict, cfg: dict, client) -> dict:
    """Returns {"ok": bool, "script": ..., "problems": [...], "verifier": ...}."""
    facts = fact_sheet(tl, play)
    n = cfg["narrate"]
    system = WRITER_SYSTEM.format(min_words=n["min_words"], max_words=n["max_words"])
    script = _call(client, cfg, system, "Fact sheet:\n" + json.dumps(facts, indent=1), SCRIPT_SCHEMA)
    if script is None:
        return {"ok": False, "script": None, "problems": ["writer returned no script"], "verifier": None}
    problems = check_script(script, facts, cfg)
    if problems:
        return {"ok": False, "script": script, "problems": problems, "verifier": None}

    numbered = [{"index": i, "text": s["text"], "cites": s["cites"]} for i, s in enumerate(script["sentences"])]
    verdict = _call(client, cfg, VERIFIER_SYSTEM,
                    "Fact sheet:\n" + json.dumps(facts, indent=1) + "\n\nSentences:\n" + json.dumps(numbered, indent=1),
                    VERIFY_SCHEMA)
    if verdict is None:
        return {"ok": False, "script": script, "problems": ["verifier returned no verdict"], "verifier": None}
    unsupported = [r for r in verdict["results"] if not r["supported"]]
    if len(verdict["results"]) != len(numbered):
        unsupported.append({"index": -1, "reason": "verifier skipped sentences"})
    return {
        "ok": not unsupported,
        "script": script,
        "problems": [f"sentence {r['index']}: {r['reason']}" for r in unsupported],
        "verifier": verdict,
    }


def spoken_text(script: dict) -> str:
    return " ".join(s["text"] for s in script["sentences"])
