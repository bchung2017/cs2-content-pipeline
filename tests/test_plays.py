from cs2pipe import plays
from tests.conftest import make_timeline


def test_detects_multikill_and_clutch(timeline, cfg):
    found = {p["id"]: p for p in plays.detect(timeline, cfg)}
    four_k = found["m1-r02-1"]
    assert four_k["types"][0] == "4k"
    assert len([e for e in four_k["event_ids"] if e.startswith("E")]) == 4

    clutch = found["m1-r03-7"]
    assert "clutch_1v2" in clutch["types"]
    assert "noscope" in clutch["types"]
    last_kill = max(e.tick for e in timeline.events if e.id in clutch["event_ids"] and e.type == "kill")
    assert clutch["end_tick"] == last_kill + 2 * timeline.tickrate


def test_no_play_for_single_trade_round(timeline, cfg):
    assert not [p for p in plays.detect(timeline, cfg) if p["round"] == 1]


def test_rank_day_orders_by_score_and_tier(cfg):
    s_tier = make_timeline("s", tier="S")
    c_tier = make_timeline("c", tier="C")
    ranked = plays.rank_day([c_tier, s_tier], cfg)
    assert [p["score"] for p in ranked] == sorted((p["score"] for p in ranked), reverse=True)
    assert ranked[0]["match_id"] == "s"


def test_stakes_match_point_and_overtime(timeline):
    r = timeline.rounds[0]
    r.score_before = {"A": 12, "B": 10}
    value, f = plays.stakes(r, timeline)
    assert f["match_point"] and not f["overtime"]
    r.score_before = {"A": 15, "B": 14}
    _, f = plays.stakes(r, timeline)
    assert f["overtime"] and f["match_point"]


def test_lone_flagged_kill_is_not_a_play(timeline, cfg):
    first_kill = next(e for e in timeline.events if e.type == "kill" and e.round == 1)
    first_kill.flags = ["noscope", "thrusmoke", "attackerblind"]
    assert not [p for p in plays.detect(timeline, cfg) if p["round"] == 1]
