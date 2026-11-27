"""build_timeline against frames shaped like demoparser2 output. Shapes are assumptions until
checked with `cs2pipe inspect-demo` on a real demo."""
import pandas as pd

from cs2pipe import parse
from cs2pipe.pipeline import rank_gate

CT = [76561190000000001 + i for i in range(5)]
T = [76561190000000101 + i for i in range(5)]


def frames():
    return {
        "header": pd.DataFrame([{"map_name": "de_mirage"}]),
        "round_announce_match_start": pd.DataFrame([{"tick": 500}]),
        "round_start": pd.DataFrame({"tick": [100, 600, 3000]}),
        "round_freeze_end": pd.DataFrame({"tick": [150, 1000, 3400]}),
        "round_end": pd.DataFrame({"tick": [400, 2800, 5000], "winner": [3, 3, "T"], "reason": [7, 8, 9]}),
        "player_death": pd.DataFrame([
            {"tick": 300, "attacker_steamid": T[0], "user_steamid": CT[0], "weapon": "ak47"},  # warmup
            {"tick": 1500, "attacker_steamid": CT[0], "attacker_name": "ct0", "user_steamid": T[0], "user_name": "t0",
             "weapon": "awp", "headshot": True, "noscope": True, "thrusmoke": False, "penetrated": 0,
             "attacker_last_place_name": "Connector", "user_last_place_name": "Mid", "user_X": 1.0, "user_Y": 2.0},
            {"tick": 600, "attacker_steamid": CT[2], "user_steamid": CT[2], "weapon": "world"},  # restart self-kill
            {"tick": 3600, "attacker_steamid": T[1], "attacker_name": "t1", "user_steamid": CT[1], "user_name": "ct1",
             "weapon": "m4a1", "headshot": False},
        ]),
        "bomb_planted": pd.DataFrame([{"tick": 4000, "user_steamid": T[2], "user_last_place_name": "BombsiteA"}]),
        "bomb_defused": pd.DataFrame(),
    }


def tick_reader(props, ticks):
    rows = []
    for t in ticks:
        swapped = t >= 3400
        for sid in CT + T:
            on_ct = (sid in CT) != swapped
            rows.append({"tick": t, "steamid": sid, "name": f"n{sid % 1000}", "team_num": 3 if on_ct else 2,
                         "team_clan_name": "Alpha" if sid in CT else "Bravo",
                         "X": float(sid % 100), "Y": float(t), "is_alive": True})
    return pd.DataFrame(rows)


def test_build_timeline_rounds_kills_and_teams():
    tl = parse.build_timeline(frames(), "m", {"final_score": [1, 1]}, stride=200, tick_reader=tick_reader)
    assert tl.map == "de_mirage"
    assert [r.number for r in tl.rounds] == [1, 2]          # warmup round dropped
    assert tl.teams == {"A": "Alpha", "B": "Bravo"}
    assert [r.winner_team for r in tl.rounds] == ["A", "A"]  # round 2: T side is Alpha after the swap
    kills = [e for e in tl.events if e.type == "kill"]
    assert len(kills) == 2 and kills[0].flags == ["headshot", "noscope"]
    assert kills[0].place == "Connector" and kills[0].data["victim_place"] == "Mid"
    assert any(e.type == "bomb_planted" and e.round == 2 for e in tl.events)
    assert tl.positions and all(s.round in (1, 2) for s in tl.positions)
    assert rank_gate(tl) == "parsed score {'A': 2, 'B': 0} does not match published [1, 1]"
