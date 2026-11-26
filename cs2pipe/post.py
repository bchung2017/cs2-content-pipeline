"""post.py: publish approved drafts once delay_hours have passed since the match ended.

Never posts an unreviewed draft and never posts early: both are checked here, at the point
of upload, not upstream.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .ledger import Ledger


class DryRun:
    def upload(self, video: Path, title: str, description: str) -> str:
        return f"dryrun:{video.name}"


class YouTube:
    """YouTube Data API v3 upload. Needs an OAuth token file with the youtube.upload scope."""

    def __init__(self, cfg: dict):
        self.cfg = cfg["post"]["youtube"]

    def upload(self, video: Path, title: str, description: str) -> str:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = Credentials.from_authorized_user_file(
            self.cfg["token_file"], ["https://www.googleapis.com/auth/youtube.upload"])
        yt = build("youtube", "v3", credentials=creds)
        body = {
            "snippet": {"title": title[:100], "description": description, "categoryId": "20"},
            "status": {"privacyStatus": self.cfg["privacy"], "selfDeclaredMadeForKids": False},
        }
        req = yt.videos().insert(part="snippet,status", body=body,
                                 media_body=MediaFileUpload(str(video), resumable=True))
        return req.execute()["id"]


def uploaders(cfg: dict) -> dict:
    out = {}
    for name in cfg["post"]["platforms"]:
        if name == "dryrun":
            out[name] = DryRun()
        elif name == "youtube":
            out[name] = YouTube(cfg)
        else:
            raise NotImplementedError(f"no uploader for {name!r} (TikTok needs its app audit first)")
    return out


def is_due(ended_at: str, delay_hours: float, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return now >= datetime.fromisoformat(ended_at) + timedelta(hours=delay_hours)


def post_due(ledger: Ledger, cfg: dict, now: datetime | None = None, ups: dict | None = None) -> list[tuple[str, str]]:
    ups = ups if ups is not None else uploaders(cfg)
    paused = ledger.paused()
    done = []
    for d in ledger.drafts("approved"):
        if not is_due(d["ended_at"], cfg["post"]["delay_hours"], now):
            continue
        script = json.loads(d["script_json"])
        play = json.loads(d["play_json"])
        description = " ".join(s["text"] for s in script["sentences"])
        already = ledger.posted(d["play_id"])
        for platform, up in ups.items():
            if platform in paused or platform in already:
                continue
            remote = up.upload(Path(d["video_path"]), script["title"], description)
            ledger.record_post(d["play_id"], platform, remote)
            done.append((play["id"], platform))
        if set(ups) <= ledger.posted(d["play_id"]):
            ledger.upsert_draft(d["play_id"], "posted")
    return done
