"""Ledger, render, review and post gates end to end with the fake client and silent TTS."""
import json
from datetime import datetime, timedelta

from cs2pipe import assemble, pipeline, post
from cs2pipe.ledger import Ledger
from cs2pipe.review import create_app
from tests.conftest import FakeClient, make_timeline

ENDED = "2026-11-25T18:00:00+00:00"


def _seed(cfg, timeline):
    paths = pipeline.Paths(cfg)
    lg = Ledger(paths.db)
    tl_path = paths.timelines / "m1.json"
    timeline.save(tl_path)
    lg.add_match("m1", ENDED, "m1.dem", "Test Cup", "S")
    lg.x("UPDATE matches SET status = 'parsed', timeline_path = ? WHERE match_id = 'm1'", str(tl_path))
    return lg


def _script_for(play):
    return {"title": "test", "sentences": [{"text": "p7 won the round alone against two defenders at Long.",
                                            "cites": play["event_ids"][:1]}]}


def test_daily_flow_to_post(cfg, timeline):
    lg = _seed(cfg, timeline)
    selected = pipeline.stage_rank(cfg, lg, "2026-11-25")
    assert 0 < len(selected) <= cfg["rank"]["posting_budget"]

    payloads = []
    for p in selected:
        payloads += [_script_for(p), {"results": [{"index": 0, "supported": True, "reason": ""}]}]
    assert pipeline.stage_narrate(cfg, lg, "2026-11-25", FakeClient(payloads))["ok"] == len(selected)

    rendered = pipeline.stage_render(cfg, lg, "2026-11-25")
    assert rendered
    d = lg.draft(rendered[0])
    assert d["duration"] > cfg["render"]["hook_seconds"]
    assert assemble.probe_duration(d["video_path"]) <= cfg["render"]["max_total_seconds"]

    app = create_app(pipeline.Paths(cfg).db).test_client()
    assert b"Review queue" in app.get("/").data
    assert app.post(f"/approve/{rendered[0]}").status_code == 302
    if len(rendered) > 1:
        assert app.post(f"/kill/{rendered[1]}", data={"reason": ""}).status_code == 409
        assert app.post(f"/kill/{rendered[1]}", data={"reason": "boring"}).status_code == 302

    early = datetime.fromisoformat(ENDED) + timedelta(hours=23)
    assert post.post_due(lg, cfg, now=early) == []
    late = datetime.fromisoformat(ENDED) + timedelta(hours=24, minutes=1)
    assert post.post_due(lg, cfg, now=late) == [(rendered[0], "dryrun")]
    assert lg.draft(rendered[0])["status"] == "posted"
    if len(rendered) > 1:
        assert lg.draft(rendered[1])["status"] == "killed"


def test_unreviewed_and_paused_never_post(cfg, timeline):
    lg = _seed(cfg, timeline)
    pl = pipeline.stage_rank(cfg, lg, "2026-11-25")[0]
    lg.upsert_draft(pl["id"], "rendered", script_json=json.dumps(_script_for(pl)), video_path="x.mp4")
    late = datetime.fromisoformat(ENDED) + timedelta(hours=25)
    assert post.post_due(lg, cfg, now=late) == []
    lg.upsert_draft(pl["id"], "approved")
    lg.pause("dryrun", "strike")
    assert post.post_due(lg, cfg, now=late) == []
    lg.resume("dryrun")
    assert post.post_due(lg, cfg, now=late) == [(pl["id"], "dryrun")]


def test_narration_stops_above_reject_ratio(cfg, timeline):
    lg = _seed(cfg, timeline)
    second = make_timeline("m2")
    second.save(pipeline.Paths(cfg).timelines / "m2.json")
    lg.add_match("m2", ENDED, "m2.dem")
    lg.x("UPDATE matches SET status = 'parsed', timeline_path = ? WHERE match_id = 'm2'",
         str(pipeline.Paths(cfg).timelines / "m2.json"))
    cfg["rank"]["posting_budget"] = 10
    pipeline.stage_rank(cfg, lg, "2026-11-25")
    r = pipeline.stage_narrate(cfg, lg, "2026-11-25", FakeClient(["refusal"] * 10))
    assert r["stopped"] and r["rejected"] == 3


def test_intake_sidecar(cfg, tmp_path):
    lg = Ledger(pipeline.Paths(cfg).db)
    intake = pipeline.Paths(cfg).intake
    intake.mkdir(parents=True)
    (intake / "x.dem").write_bytes(b"")
    (intake / "x.json").write_text(json.dumps({"ended_at": "2026-11-25T20:00:00+01:00", "tier": "A"}))
    (intake / "nodemo.json").write_text(json.dumps({"ended_at": ENDED}))
    assert pipeline.stage_intake(cfg, lg) == ["x"]
    assert lg.matches()[0]["ended_at"] == "2026-11-25T19:00:00+00:00"
