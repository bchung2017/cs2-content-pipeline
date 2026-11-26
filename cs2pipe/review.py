"""Review queue: a local page listing rendered drafts with their scripts. Approve or kill each."""
from __future__ import annotations

import json
from pathlib import Path

from flask import Flask, abort, redirect, render_template_string, request, send_file

from .ledger import Ledger, now

PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Review queue</title>
<style>
body{font:15px/1.45 system-ui,sans-serif;margin:0;padding:16px;background:#f3f4f6;color:#111}
.d{background:#fff;border:1px solid #ddd;border-radius:8px;padding:14px;margin:0 auto 16px;max-width:980px;display:flex;gap:16px;flex-wrap:wrap}
video{width:270px;height:480px;background:#000;border-radius:6px}
.s{flex:1;min-width:260px} .c{color:#777;font-size:12px} form{display:inline-block;margin:6px 6px 0 0}
input[type=text]{width:220px} button{padding:6px 12px}
</style>
<h1>Review queue ({{ drafts|length }})</h1>
{% for d in drafts %}
<div class="d"><video controls src="/video/{{ d.play_id }}"></video><div class="s">
<h2>{{ d.script.title }}</h2>
<p class="c">{{ d.play_id }} · score {{ '%.3f'|format(d.play.score) }} · {{ d.play.types|join(', ') }} · {{ '%.1f'|format(d.duration) }} s · match ended {{ d.ended_at }}</p>
<ol>{% for s in d.script.sentences %}<li>{{ s.text }} <span class="c">{{ s.cites|join(' ') }}</span></li>{% endfor %}</ol>
<form method="post" action="/approve/{{ d.play_id }}"><button>Approve</button></form>
<form method="post" action="/kill/{{ d.play_id }}"><input type="text" name="reason" placeholder="reason (required)" required><button>Kill</button></form>
</div></div>
{% else %}<p>Nothing to review.</p>{% endfor %}
"""


def create_app(db_path: Path) -> Flask:
    app = Flask(__name__)

    def ledger() -> Ledger:
        return Ledger(db_path)

    @app.get("/")
    def index():
        rows = ledger().drafts("rendered")
        drafts = [dict(r) | {"script": json.loads(r["script_json"]), "play": json.loads(r["play_json"])} for r in rows]
        return render_template_string(PAGE, drafts=drafts)

    @app.get("/video/<play_id>")
    def video(play_id):
        d = ledger().draft(play_id)
        if not d or not d["video_path"]:
            abort(404)
        return send_file(d["video_path"], mimetype="video/mp4")

    @app.post("/approve/<play_id>")
    def approve(play_id):
        lg = ledger()
        d = lg.draft(play_id)
        if not d or d["status"] != "rendered":
            abort(409)
        lg.upsert_draft(play_id, "approved", reviewed_at=now())
        return redirect("/")

    @app.post("/kill/<play_id>")
    def kill(play_id):
        reason = request.form.get("reason", "").strip()
        lg = ledger()
        d = lg.draft(play_id)
        if not reason or not d or d["status"] != "rendered":
            abort(409)
        lg.upsert_draft(play_id, "killed", kill_reason=reason, reviewed_at=now())
        return redirect("/")

    return app
