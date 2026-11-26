# CLAUDE.md

Seed context for sessions in this repo. Read `docs/` before proposing design changes.

## Project

Batch pipeline: pro CS2 match demo → ranked plays → grounded script → 2D radar
breakdown + 3 s POV hook → vertical MP4 → operator review → post at T+24h to
YouTube Shorts and TikTok. Single operator/builder. Stage: planning, no code.

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
- Parser library: awpy vs demoparser2, chosen by matching kills per round to the scoreboard.
- Whether CS2 demo playback can be scripted for hands-free POV capture.
- LLM/TTS spend cap.

## Build order

Follow `docs/roadmap.md` section 3. Each step has a pass check; a step counts as
done only when its check passes. Intake automation (`poll.py`, `fetch.py`) is
last; until then, demos are downloaded by hand into an intake folder.

## Narration rule

Every script sentence must cite an event ID from the timeline; the verifier
rejects uncited sentences. Feed the model callout names and derived facts, not
raw coordinates. 80–100 words, two or three causal beats.
