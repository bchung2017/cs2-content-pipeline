# CS2 Breakdown Shorts — Roadmap

Tentative, 2026-11-25. Seed-level plan, not a final design. Mirrors the
[roadmap doc](https://claude.ai/artifact/JtwRfYCwovj1DPJ79mgjYX), which stays the
editable source until this file supersedes it.

## 1. Quick intro

An automated pipeline that turns finished pro Counter-Strike 2 matches into
vertical short videos: 3 seconds of the play, then about 40 seconds explaining
how it happened, posted 24 hours after the match. One person builds and operates
it. It exists because raw clips are saturated and automated breakdowns are not.

It does not capture live matches, use broadcast video or caster audio, or cover
other games yet. In the proposed design it posts nothing the operator has not
approved.

## 2. How to interact with it

One role for now: the operator.

1. A match ends. Its demo file lands in the intake folder, by hand at first and
   through `poll.py` and `fetch.py` later.
2. The pipeline parses the demo, ranks the day's plays, writes a script for the
   top few, and renders a draft video for each.
3. Drafts appear in the review queue with their scripts. Approve or kill each one.
4. `post.py` publishes approved drafts once 24 hours have passed since the match
   ended.

| Can | Cannot |
| --- | --- |
| Change ranking weights in config | Post before the 24-hour mark |
| Kill or re-render a draft | Post an unreviewed draft |
| Add demos by hand | Cover a match that has no demo |

## 3. First-time setup

Setup is done when every check passes. Steps 1–7 need no accounts and run on one
machine.

1. **Demo source.** A note on where target-event demos can be fetched and how
   long after a match. Check: 5 pro demos from 2 recent events downloaded by hand.
2. **Timeline schema v0.** One-page schema for rounds, events and positions.
   Check: committed to the repo.
3. **`parse.py`.** Timeline files from demos. Check: kills per round match the
   published scoreboard for one full match.
4. **`plays.py`.** Ranked play list per day. Check (proposed): at least 7 of its
   top 10 across 5 demos are plays the operator would have picked by hand.
5. **`narrate.py` with verifier.** A script per play. Check: 10 scripts with no
   uncited sentence and no factual error on the operator's read.
6. **`render.py`.** 2D breakdown clip and 3-second POV hook. Check: both render
   for 5 plays with no manual input.
7. **`assemble.py`.** One vertical video with voice. Check: plays correctly on a
   phone and runs under 60 seconds (proposed limit).
8. **Channel and platform API access.** A channel per platform and upload
   credentials. Check: a private test upload succeeds through the API.
   **One-way door:** the channel name, its identity and any strikes it collects
   stay with the account.
9. **Review queue and `post.py`.** Approval step and timed posting. Check: an
   approved draft posts at its scheduled time and a killed one never posts.
10. **`poll.py` and `fetch.py`.** Automatic intake. Check: 3 consecutive days of
    completed matches become jobs with demos, with no manual step.

## 4. Intended steady-state loop

A daily batch, triggered by match completion, with the operator at the review
gate. Each video passes six gates.

| To enter | This must be true |
| --- | --- |
| Parse | A demo file for the match exists |
| Rank | The timeline's round count equals the final score total |
| Narrate | The play is in the day's top N, where N is the posting budget |
| Render | Every sentence of the script cites an event and the verifier passes |
| Review | An assembled video exists within the length limit |
| Post | The operator approved it and 24 hours have passed since the match ended |

**Stops.**
- A takedown or strike pauses posting on that channel until the source and rights
  position are re-checked.
- Verifier rejections above 30% of a day's scripts stop narration until fixed
  (proposed threshold).
- No demos for 3 days stops intake and raises an alert (proposed).
- A monthly spend cap for LLM and TTS is not set yet.

**Feedback.** Every killed draft is logged with a reason; those reasons become
rules in `plays.py` or `narrate.py`. Every post is logged with its ranking
features, views and retention; weights are refit after about 300 posts.

## 5. Immediate next steps

Items 1–4 are in dependency order. Items 5–7 are independent and can run in
parallel.

| # | Action | Done when |
| --- | --- | --- |
| 1 | Download 5 pro demos from 2 recent events by hand; note the source and the hours after match end | 5 files on disk and the note written |
| 2 | Run awpy and demoparser2 on one demo and pick one | One chosen; its kills per round match the scoreboard |
| 3 | Write timeline schema v0 | One page committed |
| 4 | Write `parse.py` against the 5 demos | 5 timeline files produced |
| 5 | Test whether CS2 demo playback can capture a 3-second POV clip at a given tick with no manual input | A yes or no, with the method |
| 6 | Search for existing automated pro-play breakdown channels | A list, or "none found" |
| 7 | Decide the channel name, then submit the YouTube and TikTok API applications | Both applications submitted |

All owned by the operator.
