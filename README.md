# cs2-content-pipeline

Automated pipeline that turns finished pro CS2 matches into vertical breakdown
shorts: 3 s of the play, ~40 s on how it happened, posted 24 h after the match.
Built from match demos, never broadcast footage. Human review gate before posting.

Status: pipeline code end to end. Parsed and rendered on one real pro demo; the
per-player scoreboard comparison for that demo is pending (see "Not done" below).

## Run

Requires Python 3.11+ and ffmpeg.

```
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
cp config.example.toml config.toml
export ANTHROPIC_API_KEY=...            # narration
.venv/bin/cs2pipe inspect-demo some.dem # check parser column names on a real demo first
```

Drop `<match_id>.dem` plus a `<match_id>.json` sidecar (`ended_at` required; `event`,
`tier`, `final_score` optional) into `data/intake/`, then:

```
cs2pipe run --day 2026-11-25   # intake -> parse -> rank -> narrate -> render
cs2pipe review                 # http://127.0.0.1:5050, approve or kill each draft
cs2pipe post                   # uploads approved drafts once 24 h have passed
cs2pipe pause youtube "strike" # stop posting to a channel; `resume` to undo
cs2pipe status
```

`pytest -q` runs the test suite.

## Layout

| Module | Stage | Gate it enforces |
| --- | --- | --- |
| `cs2pipe/poll.py`, `fetch.py` | intake from folder sidecars; URL download with retry | alert after 3 days without demos |
| `cs2pipe/parse.py` | demo → timeline schema v0 (`schema.py`) via demoparser2 | round count = final score (and published score) |
| `cs2pipe/plays.py` | detect multi-kills, clutches, special kills; rarity × stakes × player × tier; day-wide top N | top N = posting budget |
| `cs2pipe/narrate.py` | Claude writes a cited script, then a second pass verifies it | every sentence cites a real event, word budget, verifier pass; halts above 30% rejections |
| `cs2pipe/render.py`, `assemble.py` | 2D radar breakdown + 3 s hook, TTS, ffmpeg → 1080×1920 MP4 | under 60 s |
| `cs2pipe/review.py` | local Flask review queue | kill requires a reason |
| `cs2pipe/post.py` | upload approved drafts | approved only, ≥ 24 h after match end, channel not paused |
| `cs2pipe/ledger.py` | SQLite state for all of the above | |

## Not done

- **Parser checked on one demo only.** Column names matched; score gate passes (16-13 over
  29 rounds). Per-player K-D still to be compared against HLTV's scoreboard.
- **POV hook.** The hook is a zoomed radar clip. `render.CS2ClientHook` is the slot for
  CS2 demo-playback capture (roadmap next step 5).
- **TTS.** `silent` (placeholder track) or `command` (any local TTS CLI). No voice chosen.
- **Map radars.** Without `maps/<map>.png` + the game's `maps/<map>.txt` overview file the
  radar draws on a plain background.
- **Liquipedia poll, TikTok upload.** Stubs. YouTube upload is written against the Data API v3
  but untested (no credentials).
- **Metrics loop.** Not built; play features are stored on each play for the later refit.

## Docs

- [docs/roadmap.md](docs/roadmap.md) — setup steps with pass checks, daily loop, next steps
- [docs/architecture.md](docs/architecture.md) — components, data flow, build notes
- [docs/decisions.md](docs/decisions.md) — decided vs proposed, unknowns, rights, scaling

Planning artifacts (private):
[roadmap doc](https://claude.ai/artifact/JtwRfYCwovj1DPJ79mgjYX) ·
[setup diagram](https://claude.ai/artifact/1Him325BVvx2H7xG5jVWmZ) ·
[build steps](https://claude.ai/artifact/Lwf9JgcLjhWbysXidXHU6Y) ·
[picture roadmap](https://claude.ai/artifact/QjeMd3yQB9igQYe97bFbkB)
