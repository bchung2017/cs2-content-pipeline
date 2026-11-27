from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from . import config, parse, pipeline, post
from .ledger import Ledger


def _client(cfg: dict):
    import anthropic

    return anthropic.Anthropic(api_key=os.environ["CS2PIPE_ANTHROPIC_KEY"], base_url=cfg["narrate"]["base_url"])


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="cs2pipe")
    ap.add_argument("--config", type=Path)
    sub = ap.add_subparsers(dest="cmd", required=True)
    today = datetime.now(timezone.utc).date().isoformat()
    for name in ("intake", "parse", "status"):
        sub.add_parser(name)
    for name in ("rank", "narrate", "render", "run"):
        sub.add_parser(name).add_argument("--day", default=today, help="UTC date of match end (default today)")
    rv = sub.add_parser("review")
    rv.add_argument("--port", type=int, default=5050)
    sub.add_parser("post")
    pa = sub.add_parser("pause")
    pa.add_argument("platform")
    pa.add_argument("reason")
    sub.add_parser("resume").add_argument("platform")
    sub.add_parser("inspect-demo").add_argument("demo", type=Path)
    args = ap.parse_args(argv)

    if args.cmd == "inspect-demo":
        print(json.dumps(parse.inspect(args.demo), indent=1, default=str))
        return
    cfg = config.load(args.config)
    paths = pipeline.Paths(cfg)
    lg = Ledger(paths.db)

    if args.cmd in ("intake", "run"):
        print("intake:", pipeline.stage_intake(cfg, lg))
    if args.cmd in ("parse", "run"):
        print("parsed:", pipeline.stage_parse(cfg, lg))
    if args.cmd in ("rank", "run"):
        print("selected:", [p["id"] for p in pipeline.stage_rank(cfg, lg, args.day)])
    if args.cmd in ("narrate", "run"):
        print("narrate:", pipeline.stage_narrate(cfg, lg, args.day, _client(cfg)))
    if args.cmd in ("render", "run"):
        print("rendered:", pipeline.stage_render(cfg, lg, args.day))
    if args.cmd == "review":
        from .review import create_app

        create_app(paths.db).run(host="127.0.0.1", port=args.port)
    if args.cmd == "post":
        print("posted:", post.post_due(lg, cfg))
    if args.cmd == "pause":
        lg.pause(args.platform, args.reason)
    if args.cmd == "resume":
        lg.resume(args.platform)
    if args.cmd == "status":
        for table, col in (("matches", "status"), ("drafts", "status")):
            print(table, {r[col]: r["n"] for r in lg.q(f"SELECT {col}, count(*) AS n FROM {table} GROUP BY {col}")})
        print("paused", lg.paused())


if __name__ == "__main__":
    main()
