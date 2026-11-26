"""SQLite job ledger: one row per match, play, draft and post. Single source of pipeline state."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    event TEXT, tier TEXT, ended_at TEXT NOT NULL,
    demo_path TEXT, timeline_path TEXT,
    status TEXT NOT NULL DEFAULT 'queued',   -- queued | parsed | parse_failed
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plays (
    play_id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL REFERENCES matches(match_id),
    day TEXT NOT NULL,
    score REAL NOT NULL,
    day_rank INTEGER,
    selected INTEGER NOT NULL DEFAULT 0,
    play_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drafts (
    play_id TEXT PRIMARY KEY REFERENCES plays(play_id),
    status TEXT NOT NULL,                    -- scripted | rejected | rendered | approved | killed | posted
    script_json TEXT, verifier_json TEXT,
    video_path TEXT, duration REAL,
    kill_reason TEXT,
    reviewed_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
    play_id TEXT NOT NULL REFERENCES drafts(play_id),
    platform TEXT NOT NULL,
    remote_id TEXT,
    posted_at TEXT NOT NULL,
    views INTEGER, retention REAL,
    PRIMARY KEY (play_id, platform)
);
CREATE TABLE IF NOT EXISTS channel_pause (
    platform TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    paused_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Ledger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def q(self, sql: str, *args) -> list[sqlite3.Row]:
        return self.db.execute(sql, args).fetchall()

    def x(self, sql: str, *args) -> None:
        self.db.execute(sql, args)
        self.db.commit()

    # matches
    def add_match(self, match_id: str, ended_at: str, demo_path: str, event=None, tier=None) -> bool:
        cur = self.db.execute(
            "INSERT OR IGNORE INTO matches (match_id, event, tier, ended_at, demo_path, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)", (match_id, event, tier, ended_at, demo_path, now()))
        self.db.commit()
        return cur.rowcount == 1

    def matches(self, status: str | None = None, day: str | None = None) -> list[sqlite3.Row]:
        sql, args = "SELECT * FROM matches WHERE 1=1", []
        if status:
            sql, args = sql + " AND status = ?", args + [status]
        if day:
            sql, args = sql + " AND substr(ended_at, 1, 10) = ?", args + [day]
        return self.q(sql + " ORDER BY ended_at", *args)

    # plays
    def replace_day_plays(self, day: str, plays: list[dict], selected_n: int) -> None:
        self.x("DELETE FROM plays WHERE day = ? AND play_id NOT IN (SELECT play_id FROM drafts)", day)
        for rank, p in enumerate(plays, 1):
            self.db.execute(
                "INSERT OR REPLACE INTO plays (play_id, match_id, day, score, day_rank, selected, play_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (p["id"], p["match_id"], day, p["score"], rank, int(rank <= selected_n), json.dumps(p)))
        self.db.commit()

    def plays(self, day: str, selected_only=True) -> list[dict]:
        rows = self.q("SELECT play_json FROM plays WHERE day = ?" + (" AND selected = 1" if selected_only else "")
                      + " ORDER BY day_rank", day)
        return [json.loads(r["play_json"]) for r in rows]

    # drafts
    def upsert_draft(self, play_id: str, status: str, **fields) -> None:
        existing = self.q("SELECT 1 FROM drafts WHERE play_id = ?", play_id)
        if not existing:
            self.x("INSERT INTO drafts (play_id, status, created_at) VALUES (?, ?, ?)", play_id, status, now())
        cols = {"status": status, **fields}
        self.x(f"UPDATE drafts SET {', '.join(f'{k} = ?' for k in cols)} WHERE play_id = ?",
               *cols.values(), play_id)

    def drafts(self, status: str | None = None) -> list[sqlite3.Row]:
        sql = ("SELECT d.*, p.match_id, p.day, p.play_json, m.ended_at FROM drafts d"
               " JOIN plays p USING (play_id) JOIN matches m USING (match_id)")
        if status:
            return self.q(sql + " WHERE d.status = ? ORDER BY d.created_at", status)
        return self.q(sql + " ORDER BY d.created_at")

    def draft(self, play_id: str) -> sqlite3.Row | None:
        rows = self.q("SELECT d.*, p.match_id, p.play_json, m.ended_at FROM drafts d"
                      " JOIN plays p USING (play_id) JOIN matches m USING (match_id) WHERE play_id = ?", play_id)
        return rows[0] if rows else None

    # posts and stops
    def record_post(self, play_id: str, platform: str, remote_id: str | None) -> None:
        self.x("INSERT OR REPLACE INTO posts (play_id, platform, remote_id, posted_at) VALUES (?, ?, ?, ?)",
               play_id, platform, remote_id, now())

    def posted(self, play_id: str) -> set[str]:
        return {r["platform"] for r in self.q("SELECT platform FROM posts WHERE play_id = ?", play_id)}

    def pause(self, platform: str, reason: str) -> None:
        self.x("INSERT OR REPLACE INTO channel_pause VALUES (?, ?, ?)", platform, reason, now())

    def resume(self, platform: str) -> None:
        self.x("DELETE FROM channel_pause WHERE platform = ?", platform)

    def paused(self) -> dict[str, str]:
        return {r["platform"]: r["reason"] for r in self.q("SELECT * FROM channel_pause")}
