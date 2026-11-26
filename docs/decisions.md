# Decisions, proposals and unknowns

As of 2026-11-25.

## Decided by the operator

- Format: the first 3 seconds are the clip; the rest of the short is breakdown.
- Own observer footage with voice-over; no broadcast video.
- Grey-zone rights exposure is acceptable for now.
- Post 24 hours after the game is complete, for now.
- CS2 first; other self-sustaining scenes later. Overwatch can run on a longer
  delay, using replay codes if they can be obtained.
- This is a seed-level plan, not a final design.

## Proposed, not yet confirmed

- The demo-based batch design and the component names.
- The build order, with intake automation last.
- Liquipedia as the results source.
- A human review gate before posting.
- Hand-set ranking weights, refit from metrics later.
- A verifier that requires an event citation for every sentence.
- Every numeric threshold in the roadmap (7/10 ranking check, 60 s limit, 30%
  verifier stop, 3-day no-demo stop, ~300-post refit).
- The operator as owner of every next step.

## Implementation choices in the first code (2026-11-26, proposed)

- demoparser2 as the parser, pending the scoreboard check.
- Hook = zoomed radar clip until CS2 POV capture is proven.
- TTS behind a provider switch (`silent` placeholder or any local CLI); no voice chosen.
- Review queue = local Flask page.
- Intake = sidecar JSON per match in a folder; Liquipedia poll not built.
- Stakes formula: base 1.0, +0.5 match point, +0.3 overtime, +0.2 pistol,
  +0.3 × closeness, +0.5 deciding round.

## Open unknowns

- Where pro demos can be fetched reliably, and how soon after a match.
- How scriptable CS2 demo playback is.
- Whether automated pro-play breakdown shorts already exist.
- Whether organizers treat demo-rendered clips differently from broadcast clips.
- Monthly LLM/TTS spend cap: not set.

## Rights position (not legal advice)

- Demo-rendered footage avoids the organizer's broadcast production: casters,
  camera work and overlays.
- The 24-hour delay matches the rule in
  [BLAST's content guidelines](https://blast.tv/blast-premier-content-guidelines).
- [ESL's community broadcast guidelines](https://esl.com/cs/community-broadcast-guidelines/)
  ban restreaming the official feed, which this design never uses.

## Scaling order (proposed)

1. Dota 2, to reuse Valve replay tooling.
2. One fighting game, to prove a broadcast-only adapter.
3. Overwatch, if replay codes are obtainable.

Each is a new adapter on the same timeline schema.

## Known inconsistency in the source artifacts

The Build Steps walkthrough has 8 steps and no "channel and platform API access"
step; it puts review/`post.py` at step 6 and starts platform applications there.
The roadmap has 10 steps with channel access at 8 and review/`post.py` at 9.
`docs/roadmap.md` follows the roadmap.
