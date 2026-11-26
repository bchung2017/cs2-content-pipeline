"""Daily batch: intake -> parse -> rank -> narrate -> render. Each stage enforces its entry gate."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import assemble, narrate, parse, plays, poll
from .ledger import Ledger
from .schema import Timeline


class Paths:
    def __init__(self, cfg: dict):
        data = Path(cfg["paths"]["data_dir"])
        self.db = data / "ledger.sqlite"
        self.timelines = data / "timelines"
        self.drafts = data / "drafts"
        self.intake = Path(cfg["paths"]["intake_dir"])


def stage_intake(cfg: dict, lg: Ledger) -> list[str]:
    p = Paths(cfg)
    p.intake.mkdir(parents=True, exist_ok=True)
    added = poll.scan_intake(p.intake, lg)
    idle = poll.days_since_last_demo(lg)
    limit = cfg["intake"]["alert_after_days_without_demos"]
    if idle is None or idle >= limit:
        print(f"ALERT: no demos for {'ever' if idle is None else f'{idle:.1f} days'}; intake stopped", file=sys.stderr)
    return added


def rank_gate(tl: Timeline) -> str | None:
    """Rank entry gate: round count equals the final score total (and the published score, if given)."""
    score = tl.final_score()
    if not tl.rounds or sum(score.values()) != len(tl.rounds):
        return f"{len(tl.rounds)} rounds but score {score}"
    published = tl.meta.get("final_score")
    if published and sorted(published) != sorted(score.values()):
        return f"parsed score {score} does not match published {published}"
    return None


def stage_parse(cfg: dict, lg: Ledger) -> list[str]:
    p = Paths(cfg)
    done = []
    for m in lg.matches("queued"):
        demo = Path(m["demo_path"])
        meta = parse.load_sidecar(demo)
        try:
            tl = parse.parse_demo(demo, m["match_id"], meta, cfg["rank"]["position_stride_ticks"])
        except Exception as e:  # a bad demo must not stop the day's batch
            lg.x("UPDATE matches SET status = 'parse_failed', error = ? WHERE match_id = ?", repr(e), m["match_id"])
            continue
        problem = rank_gate(tl)
        out = p.timelines / f"{m['match_id']}.json"
        tl.save(out)
        lg.x("UPDATE matches SET status = ?, error = ?, timeline_path = ? WHERE match_id = ?",
             "parsed" if problem is None else "parse_failed", problem, str(out), m["match_id"])
        if problem is None:
            done.append(m["match_id"])
    return done


def stage_rank(cfg: dict, lg: Ledger, day: str) -> list[dict]:
    tls = [Timeline.load(Path(m["timeline_path"])) for m in lg.matches("parsed", day)]
    ranked = plays.rank_day(tls, cfg)
    lg.replace_day_plays(day, ranked, cfg["rank"]["posting_budget"])
    return lg.plays(day)


def _timeline(lg: Ledger, match_id: str) -> Timeline:
    return Timeline.load(Path(lg.q("SELECT timeline_path FROM matches WHERE match_id = ?", match_id)[0]["timeline_path"]))


def stage_narrate(cfg: dict, lg: Ledger, day: str, client) -> dict:
    todo = [pl for pl in lg.plays(day) if lg.draft(pl["id"]) is None]
    results = {"ok": 0, "rejected": 0, "stopped": False}
    for pl in todo:
        r = narrate.narrate(_timeline(lg, pl["match_id"]), pl, cfg, client)
        lg.upsert_draft(pl["id"], "scripted" if r["ok"] else "rejected",
                        script_json=json.dumps(r["script"]),
                        verifier_json=json.dumps({"problems": r["problems"], "verdict": r["verifier"]}))
        results["ok" if r["ok"] else "rejected"] += 1
        total = results["ok"] + results["rejected"]
        if total >= 3 and results["rejected"] / total > cfg["narrate"]["max_reject_ratio"]:
            print(f"STOP: {results['rejected']}/{total} scripts rejected today; narration halted", file=sys.stderr)
            results["stopped"] = True
            break
    return results


def stage_render(cfg: dict, lg: Ledger, day: str) -> list[str]:
    p = Paths(cfg)
    done = []
    for d in lg.drafts("scripted"):
        if d["day"] != day:
            continue
        pl = json.loads(d["play_json"])
        video, duration = assemble.assemble(_timeline(lg, pl["match_id"]), pl, json.loads(d["script_json"]),
                                            cfg, p.drafts / pl["id"])
        if duration > cfg["render"]["max_total_seconds"]:
            lg.upsert_draft(pl["id"], "rejected", video_path=str(video), duration=duration,
                            verifier_json=json.dumps({"problems": [f"video {duration:.1f}s over length limit"]}))
            continue
        lg.upsert_draft(pl["id"], "rendered", video_path=str(video), duration=duration)
        done.append(pl["id"])
    return done
