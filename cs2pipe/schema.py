"""Timeline schema v0: the game-agnostic contract every adapter writes and every later stage reads.

A timeline is one map of one match. Sides are "CT" / "T"; teams are "A" / "B", where A is
the team that started on CT. Event ids ("E0001"...) are what narration must cite.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

SCHEMA_VERSION = 0


@dataclass
class Player:
    steamid: str
    name: str
    team: str  # "A" | "B"


@dataclass
class Event:
    id: str
    type: str  # "kill" | "bomb_planted" | "bomb_defused" | "round_end"
    tick: int
    round: int
    actor: str | None = None   # steamid
    target: str | None = None  # steamid
    weapon: str | None = None
    place: str | None = None   # callout name at the actor (victim place for kills is in data)
    flags: list[str] = field(default_factory=list)  # headshot, noscope, thrusmoke, ...
    data: dict = field(default_factory=dict)


@dataclass
class Round:
    number: int  # 1-based
    start_tick: int
    freeze_end_tick: int
    end_tick: int
    winner_side: str  # "CT" | "T"
    winner_team: str  # "A" | "B"
    reason: str
    sides: dict[str, str]  # steamid -> "CT" | "T" for this round
    score_before: dict[str, int]  # {"A": n, "B": m}


@dataclass
class PositionSample:
    tick: int
    round: int
    players: dict[str, list[float]]  # steamid -> [x, y, alive(0/1)]


@dataclass
class Timeline:
    match_id: str
    map: str
    tickrate: int
    teams: dict[str, str]  # {"A": name, "B": name}
    players: list[Player]
    rounds: list[Round]
    events: list[Event]
    positions: list[PositionSample]
    meta: dict = field(default_factory=dict)  # event, tier, ended_at from the intake sidecar
    schema_version: int = SCHEMA_VERSION

    def final_score(self) -> dict[str, int]:
        score = {"A": 0, "B": 0}
        for r in self.rounds:
            score[r.winner_team] += 1
        return score

    def player_name(self, steamid: str | None) -> str:
        return next((p.name for p in self.players if p.steamid == steamid), steamid or "?")

    def events_in_round(self, number: int) -> list[Event]:
        return [e for e in self.events if e.round == number]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self)))

    @classmethod
    def load(cls, path: Path) -> Timeline:
        d = json.loads(Path(path).read_text())
        return cls(
            match_id=d["match_id"],
            map=d["map"],
            tickrate=d["tickrate"],
            teams=d["teams"],
            players=[Player(**p) for p in d["players"]],
            rounds=[Round(**r) for r in d["rounds"]],
            events=[Event(**e) for e in d["events"]],
            positions=[PositionSample(**s) for s in d["positions"]],
            meta=d.get("meta", {}),
            schema_version=d.get("schema_version", SCHEMA_VERSION),
        )
