# CLAUDE.md

Seed context for sessions in this repo. Read `docs/` before proposing design changes.

## Project

Batch pipeline: pro CS2 match demo → ranked plays → grounded script → 2D radar
breakdown + 3 s POV hook → vertical MP4 → operator review → post at T+24h to
YouTube Shorts and TikTok. Single operator/builder. Stage: code end to end in
`cs2pipe/`, tested on synthetic timelines (`tests/conftest.py`) and parsed/rendered on one
real demo (branch `demo-fixture`, LFS: Imperial vs Liquid, Cache, 13-16). README "Not done"
lists the gaps.

## Code conventions

- Python 3.11+, package `cs2pipe`, one module per pipeline stage, SQLite ledger as the only state.
- Run tests with `.venv/bin/python -m pytest -q`; CI runs the same on push.
- Each stage enforces its own entry gate (README layout table). Keep gates at the point of
  action, e.g. `post.py` re-checks approval and the 24 h delay itself.
- demoparser2 column names live only in `parse.py`. They matched the first real demo
  (patch 14200). Admin round restarts log a self-kill per player at the restart tick;
  `parse.py` drops kills before freeze end for that reason.
- Demo fixtures live only on the `demo-fixture` branch (Git LFS, ~0.5 GB each). Never merge
  it into main; GitHub Free has 10 GiB LFS storage and 10 GiB/month bandwidth.
- Narration uses the Anthropic SDK (`claude-opus-5-5`, structured JSON output, server-side
  refusal fallback). Tests use `tests.conftest.FakeClient`; never call the API in tests.

## Hard constraints (decided by the operator)

- No broadcast video, no caster audio, no live capture. Footage comes from demos only.
- Format: first 3 s is the play, the rest is breakdown.
- Post no earlier than 24 h after the match ends.
- CS2 first; other games come later as adapters on the same timeline schema.

## Treat as proposals, not decisions

Component names, build order, Liquipedia as results source, the review gate,
hand-set ranking weights, the citation verifier, and every numeric threshold.
See `docs/decisions.md`. Flag when work depends on one of these.

## Unresolved — don't assume an answer

- Demo source and latency (HLTV / organizer / FACEIT unverified).
- Parser library: demoparser2 is used provisionally; the scoreboard check (kills per round
  match) on a real demo is still the deciding test.
- Whether CS2 demo playback can be scripted for hands-free POV capture.
- LLM/TTS spend cap.

## Build order

Follow `docs/roadmap.md` section 3. Each step has a pass check; a step counts as
done only when its check passes. Code existing for a step is not the same as its
check passing: as of the first code commit, no roadmap check has passed. Intake
automation (Liquipedia poll) is last; until then, demos and sidecars go into the
intake folder by hand.

## Narration rule

Every script sentence must cite an event ID from the timeline; the verifier
rejects uncited sentences. Feed the model callout names and derived facts, not
raw coordinates. 80–100 words, two or three causal beats.
