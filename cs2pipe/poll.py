"""poll.py: completed matches -> job ledger.

Intake today is a folder: each match is a sidecar `<match_id>.json` plus either
`<match_id>.dem` beside it or a `demo_url` for fetch.py. Sidecar fields:

    match_id     required (defaults to the file stem)
    ended_at     required, ISO 8601 with offset, when the match ended
    event, tier  optional; tier keys into [rank.tier]
    final_score  optional [a, b]; checked against the parsed timeline (Rank gate)
    demo_url     optional

The daily Liquipedia poll that writes these sidecars is the last roadmap step and is not
built: Liquipedia's API terms and rate limits need checking first.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import fetch
from .ledger import Ledger


def scan_intake(intake: Path, ledger: Ledger) -> list[str]:
    added = []
    for side in sorted(intake.glob("*.json")):
        meta = json.loads(side.read_text())
        match_id = meta.get("match_id", side.stem)
        dem = side.with_suffix(".dem")
        if not dem.exists():
            if not meta.get("demo_url"):
                continue
            fetch.download(meta["demo_url"], dem)
        ended = datetime.fromisoformat(meta["ended_at"]).astimezone(timezone.utc).isoformat(timespec="seconds")
        if ledger.add_match(match_id, ended, str(dem), meta.get("event"), meta.get("tier")):
            added.append(match_id)
    return added


def days_since_last_demo(ledger: Ledger) -> float | None:
    rows = ledger.q("SELECT max(ended_at) AS last FROM matches")
    if not rows or rows[0]["last"] is None:
        return None
    last = datetime.fromisoformat(rows[0]["last"])
    return (datetime.now(timezone.utc) - last) / timedelta(days=1)


def poll_liquipedia(*_args, **_kwargs):
    raise NotImplementedError("Liquipedia polling not built; write sidecars into the intake folder")
