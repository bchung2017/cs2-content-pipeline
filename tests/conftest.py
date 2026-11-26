import copy
import json
from types import SimpleNamespace

import pytest

from cs2pipe import config
from cs2pipe.schema import Event, Player, PositionSample, Round, Timeline

TR = 64


def _round(n, winner_side, winner_team, score_before, start):
    sides = {str(i): ("CT" if i <= 5 else "T") for i in range(1, 11)}
    return Round(n, start, start + 15 * TR, start + 100 * TR, winner_side, winner_team, "test", sides, score_before)


def make_timeline(match_id="m1", tier="S") -> Timeline:
    """Three rounds. R1: trade-only. R2: player 1 (CT, team A) 4k. R3: player 7 (T, team B) wins a 1v3."""
    rounds = [
        _round(1, "CT", "A", {"A": 0, "B": 0}, 0),
        _round(2, "CT", "A", {"A": 1, "B": 0}, 200 * TR),
        _round(3, "T", "B", {"A": 2, "B": 0}, 400 * TR),
    ]
    ev = []

    def kill(rnd, t, a, v, flags=(), place="Long"):
        r = rounds[rnd - 1]
        ev.append(Event("", "kill", r.freeze_end_tick + t * TR, rnd, str(a), str(v), "ak47", place,
                        list(flags), {"victim_place": "Pit"}))

    kill(1, 10, 1, 6)
    kill(1, 12, 7, 1)
    for i, v in enumerate((6, 7, 8, 9)):
        kill(2, 10 + 3 * i, 1, v, ("headshot",) if i == 0 else ())
    kill(2, 30, 2, 10)
    kill(3, 5, 6, 1)
    kill(3, 6, 8, 2)
    kill(3, 8, 3, 6)
    kill(3, 9, 4, 8)
    kill(3, 10, 5, 9)
    kill(3, 11, 2 + 8, 3)  # player 10 kills 3; T alive 7, 10
    kill(3, 13, 4, 10)     # T: only 7 left vs CT 4, 5 -> 1v2
    kill(3, 20, 7, 4, ("noscope",))
    kill(3, 25, 7, 5)
    for r in rounds:
        ev.append(Event("", "round_end", r.end_tick, r.number, data={"winner_side": r.winner_side, "reason": "test"}))
    ev.sort(key=lambda e: e.tick)
    for i, e in enumerate(ev, 1):
        e.id = f"E{i:04d}"

    positions = []
    dead: set = set()
    by_tick = sorted((e.tick, e.target, e.round) for e in ev if e.type == "kill")
    for r in rounds:
        dead = set()
        for t in range(r.freeze_end_tick, r.end_tick + 1, 16):
            for tick, tgt, rn in by_tick:
                if rn == r.number and tick <= t:
                    dead.add(tgt)
            players = {str(i): [float(i * 100 + (t - r.freeze_end_tick) / 8), float(i * 50), 0.0 if str(i) in dead else 1.0]
                       for i in range(1, 11)}
            positions.append(PositionSample(t, r.number, players))
    return Timeline(
        match_id=match_id, map="de_test", tickrate=TR, teams={"A": "Alpha", "B": "Bravo"},
        players=[Player(str(i), f"p{i}", "A" if i <= 5 else "B") for i in range(1, 11)],
        rounds=rounds, events=ev, positions=positions,
        meta={"tier": tier, "event": "Test Cup", "ended_at": "2026-11-25T18:00:00+00:00"},
    )


@pytest.fixture
def timeline():
    return make_timeline()


@pytest.fixture
def cfg(tmp_path):
    c = copy.deepcopy(config.load(config.EXAMPLE_PATH))
    c["paths"] = {"data_dir": tmp_path / "data", "intake_dir": tmp_path / "intake", "maps_dir": tmp_path / "maps"}
    c["render"].update(width=108, height=192, fps=8)
    c["narrate"].update(min_words=10, max_words=60)
    return c


class FakeClient:
    """Stands in for anthropic.Anthropic(); returns queued JSON payloads in order."""

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        payload = self.payloads.pop(0)
        if payload == "refusal":
            return SimpleNamespace(stop_reason="refusal", content=[])
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(payload))])
