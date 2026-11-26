from cs2pipe import narrate, plays
from tests.conftest import FakeClient


def _play(timeline, cfg):
    return next(p for p in plays.detect(timeline, cfg) if p["id"] == "m1-r03-7")


def _script(ids):
    return {"title": "p7 1v2 to steal round 3", "sentences": [
        {"text": "Bravo were down two men early after trades at Long and Pit on the CT side.", "cites": ids[:2]},
        {"text": "p7 was left alone against two and picked p4 with a noscope before finishing p5.", "cites": ids[2:]},
    ]}


def test_fact_sheet_has_alive_counts_not_coordinates(timeline, cfg):
    facts = narrate.fact_sheet(timeline, _play(timeline, cfg))
    kills = [e for e in facts["events"] if e["type"] == "kill"]
    assert kills[-1]["alive_after"] == {"CT": 0, "T": 1}
    assert "X" not in str(facts) and "victim_xy" not in str(facts)


def test_passes_when_cited_and_verified(timeline, cfg):
    play = _play(timeline, cfg)
    ids = play["event_ids"]
    client = FakeClient([_script(ids), {"results": [{"index": 0, "supported": True, "reason": ""},
                                                    {"index": 1, "supported": True, "reason": ""}]}])
    r = narrate.narrate(timeline, play, cfg, client)
    assert r["ok"], r["problems"]
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["fallbacks"] == "default"
    assert call["output_config"]["format"]["type"] == "json_schema"


def test_rejects_uncited_and_unknown_ids(timeline, cfg):
    play = _play(timeline, cfg)
    bad = _script(play["event_ids"])
    bad["sentences"][0]["cites"] = []
    bad["sentences"][1]["cites"] = ["E9999"]
    r = narrate.narrate(timeline, play, cfg, FakeClient([bad]))
    assert not r["ok"]
    assert any("no citation" in p for p in r["problems"])
    assert any("E9999" in p for p in r["problems"])


def test_rejects_when_verifier_finds_unsupported_claim(timeline, cfg):
    play = _play(timeline, cfg)
    client = FakeClient([_script(play["event_ids"]), {"results": [
        {"index": 0, "supported": True, "reason": ""},
        {"index": 1, "supported": False, "reason": "noscope not on cited kill"}]}])
    r = narrate.narrate(timeline, play, cfg, client)
    assert not r["ok"] and "noscope not on cited kill" in r["problems"][0]


def test_refusal_is_a_rejection(timeline, cfg):
    r = narrate.narrate(timeline, _play(timeline, cfg), cfg, FakeClient(["refusal"]))
    assert not r["ok"] and r["script"] is None
