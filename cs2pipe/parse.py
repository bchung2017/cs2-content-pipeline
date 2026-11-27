"""parse.py: .dem -> Timeline (schema v0) via demoparser2.

Column names follow demoparser2's conventions (event fields plus `attacker_`/`user_`
prefixed player props, `parse_ticks` rows keyed by tick + steamid). They have not been
checked against a real pro demo yet: run `cs2pipe inspect-demo <file>` on the first
downloaded demo and fix `_side`/column names here if anything differs. Roadmap check for
this stage: kills per round match the published scoreboard for one full match.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .schema import Event, Player, PositionSample, Round, Timeline

TICKRATE = 64
KILL_FLAGS = ["headshot", "noscope", "thrusmoke", "attackerblind", "attackerinair", "penetrated"]


def _side(value) -> str | None:
    """Team number (2 = T, 3 = CT) or a side string -> "CT" / "T"."""
    if value in (3, "3", "CT", "ct"):
        return "CT"
    if value in (2, "2", "T", "t", "TERRORIST"):
        return "T"
    return None


def _sid(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return str(int(value)) if not isinstance(value, str) else value


def _clan(steamids: list[str], clans: dict[str, str]) -> str | None:
    found = [clans[s] for s in steamids if s in clans]
    return max(set(found), key=found.count) if found else None


def inspect(demo_path: Path) -> dict:
    from demoparser2 import DemoParser

    p = DemoParser(str(demo_path))
    out = {"header": p.parse_header(), "game_events": sorted(p.list_game_events())}
    for name in ("round_end", "player_death"):
        df = p.parse_event(name, player=["last_place_name", "team_num"])
        out[name] = {"columns": list(df.columns), "head": df.head(3).to_dict("records")}
    return out


def read_demo(demo_path: Path) -> dict[str, pd.DataFrame]:
    from demoparser2 import DemoParser

    p = DemoParser(str(demo_path))
    events = set(p.list_game_events())
    frames = {
        "header": pd.DataFrame([p.parse_header()]),
        "round_start": p.parse_event("round_start"),
        "round_freeze_end": p.parse_event("round_freeze_end"),
        "round_end": p.parse_event("round_end"),
        "player_death": p.parse_event("player_death", player=["last_place_name", "team_num", "X", "Y"]),
    }
    for name in ("bomb_planted", "bomb_defused", "round_announce_match_start"):
        frames[name] = p.parse_event(name, player=["last_place_name"]) if name in events else pd.DataFrame()
    return frames | {"_parser": p}


def build_timeline(frames: dict, match_id: str, meta: dict, stride: int,
                   tick_reader=None) -> Timeline:
    """Normalize demoparser2 frames into a Timeline.

    `tick_reader(props, ticks) -> DataFrame` defaults to the parser's parse_ticks; tests
    pass a stub.
    """
    if tick_reader is None:
        parser = frames["_parser"]

        def tick_reader(props, ticks):
            return parser.parse_ticks(props, ticks=ticks)

    map_name = str(frames["header"].iloc[0].get("map_name", "unknown"))
    match_start = 0
    ms = frames.get("round_announce_match_start")
    if ms is not None and len(ms):
        match_start = int(ms["tick"].max())

    ends = frames["round_end"]
    ends = ends[ends["tick"] > match_start].sort_values("tick")
    ends = ends[ends["winner"].map(_side).notna()]
    starts = sorted(int(t) for t in frames["round_start"]["tick"] if t >= match_start)
    freezes = sorted(int(t) for t in frames["round_freeze_end"]["tick"] if t >= match_start)

    round_windows = []
    prev_end = match_start
    for _, row in ends.iterrows():
        end = int(row["tick"])
        start = max([t for t in starts if prev_end <= t < end], default=prev_end)
        freeze = max([t for t in freezes if start <= t < end], default=start)
        round_windows.append((start, freeze, end, _side(row["winner"]), str(row.get("reason", ""))))
        prev_end = end

    freeze_rows = tick_reader(["team_num", "team_clan_name"], [w[1] for w in round_windows])
    sides_by_tick: dict[int, dict[str, str]] = {}
    names: dict[str, str] = {}
    clans: dict[str, str] = {}
    for _, r in freeze_rows.iterrows():
        side = _side(r["team_num"])
        if side:
            sid = _sid(r["steamid"])
            sides_by_tick.setdefault(int(r["tick"]), {})[sid] = side
            names[sid] = str(r.get("name", sid))
            if r.get("team_clan_name"):
                clans.setdefault(sid, str(r["team_clan_name"]))

    team_a = {s for s, side in sides_by_tick.get(round_windows[0][1], {}).items() if side == "CT"} if round_windows else set()

    def team_of_side(sides: dict[str, str], side: str) -> str:
        members = {s for s, v in sides.items() if v == side}
        return "A" if len(members & team_a) >= len(members - team_a) else "B"

    rounds: list[Round] = []
    score = {"A": 0, "B": 0}
    for i, (start, freeze, end, winner_side, reason) in enumerate(round_windows, 1):
        sides = sides_by_tick.get(freeze, {})
        winner_team = team_of_side(sides, winner_side)
        rounds.append(Round(i, start, freeze, end, winner_side, winner_team, reason, sides, dict(score)))
        score[winner_team] += 1

    def round_at(tick: int) -> int | None:
        return next((r.number for r in rounds if r.start_tick <= tick <= r.end_tick), None)

    raw: list[tuple[int, Event]] = []
    for _, k in frames["player_death"].iterrows():
        tick = int(k["tick"])
        rn = round_at(tick)
        # Kills before freeze end are not play: admin round restarts (backup restores) log a
        # self-kill for every player at the restart tick.
        if rn is None or tick < rounds[rn - 1].freeze_end_tick:
            continue
        flags = [f for f in KILL_FLAGS if f in k and bool(k[f]) and not pd.isna(k[f])]
        raw.append((tick, Event(
            id="", type="kill", tick=tick, round=rn,
            actor=_sid(k.get("attacker_steamid")), target=_sid(k.get("user_steamid")),
            weapon=str(k.get("weapon", "")), place=k.get("attacker_last_place_name") or None,
            flags=flags,
            data={
                "victim_place": k.get("user_last_place_name") or None,
                "assister": _sid(k.get("assister_steamid")),
                "victim_xy": [float(k.get("user_X", 0) or 0), float(k.get("user_Y", 0) or 0)],
            },
        )))
        for prefix in ("attacker", "user"):
            sid = _sid(k.get(f"{prefix}_steamid"))
            if sid and f"{prefix}_name" in k:
                names.setdefault(sid, str(k[f"{prefix}_name"]))
    for name in ("bomb_planted", "bomb_defused"):
        df = frames.get(name)
        if df is None or not len(df):
            continue
        for _, b in df.iterrows():
            tick = int(b["tick"])
            rn = round_at(tick)
            if rn is not None:
                raw.append((tick, Event(id="", type=name, tick=tick, round=rn,
                                        actor=_sid(b.get("user_steamid")),
                                        place=b.get("user_last_place_name") or None)))
    for r in rounds:
        raw.append((r.end_tick, Event(id="", type="round_end", tick=r.end_tick, round=r.number,
                                      data={"winner_side": r.winner_side, "reason": r.reason})))
    raw.sort(key=lambda x: (x[0], x[1].type == "round_end"))
    events = []
    for i, (_, e) in enumerate(raw, 1):
        e.id = f"E{i:04d}"
        events.append(e)

    sample_ticks = [t for r in rounds for t in range(r.freeze_end_tick, r.end_tick + 1, stride)]
    positions: list[PositionSample] = []
    if sample_ticks:
        pos = tick_reader(["X", "Y", "is_alive"], sample_ticks)
        for tick, group in pos.groupby("tick"):
            players = {_sid(r["steamid"]): [float(r["X"]), float(r["Y"]), 1.0 if r["is_alive"] else 0.0]
                       for _, r in group.iterrows()}
            positions.append(PositionSample(int(tick), round_at(int(tick)), players))

    all_sides = rounds[0].sides if rounds else {}
    players = [Player(s, names.get(s, s), "A" if s in team_a else "B") for s in sorted(names)
               if s in all_sides or any(s in r.sides for r in rounds)]
    return Timeline(
        match_id=match_id, map=map_name, tickrate=TICKRATE,
        teams={t: _clan([s for s in names if (s in team_a) == (t == "A")], clans)
               or meta.get(f"team_{t.lower()}", f"Team {t}") for t in ("A", "B")},
        players=players, rounds=rounds, events=events, positions=positions, meta=meta,
    )


def parse_demo(demo_path: Path, match_id: str, meta: dict, stride: int) -> Timeline:
    return build_timeline(read_demo(demo_path), match_id, meta, stride)


def load_sidecar(demo_path: Path) -> dict:
    side = demo_path.with_suffix(".json")
    return json.loads(side.read_text()) if side.exists() else {}
