# Architecture (tentative)

Batch, demo-based, posts at T+24h, no broadcast footage. Text form of the
[Tentative Setup](https://claude.ai/artifact/1Him325BVvx2H7xG5jVWmZ) diagram and the
[Build Steps](https://claude.ai/artifact/Lwf9JgcLjhWbysXidXHU6Y) walkthrough.

## Components and data flow

```
SOURCES (public, read-only)     PIPELINE (ours, batch)                          PUBLISH
Liquipedia API ──results──▶ poll.py   daily: completed matches → job ledger (SQLite)
                                │ job
Demo host (unverified) ─.dem─▶ fetch.py  download demo, retry until published
  HLTV / organizer / FACEIT     │ demo file
                              parse.py  [awpy | demoparser2 — pick one]
                                │ event timeline
                              plays.py  detect + rank, day-wide top N
                                │ ranked plays
                              narrate.py [LLM: script writer + verifier pass]
                                │ script + cited events
                              render.py  2D radar breakdown (ours)
                                │        [CS2 client demo playback → 3 s POV hook]
                                │ hook + breakdown clips
                              assemble.py  TTS + ffmpeg → vertical MP4
                                │ draft MP4
                                └──────────────────────────────────▶ Review queue (operator)
                                                                       │ approved
                                                                     post.py  holds until T+24h,
                                                                       │      one channel per game
                                                                 YouTube Shorts · TikTok
                                                                       │ views · retention
                                                                     Metrics → rank weights (later)
```

| Component | Role | Dependency / note |
| --- | --- | --- |
| `poll.py` | Daily poll of completed matches into a SQLite job ledger | Liquipedia API (results, tiers, brackets) |
| `fetch.py` | Download demo, retry until published | Demo host unverified: HLTV, organizer or FACEIT |
| `parse.py` | Demo → event timeline (positions, kills, utility, economy) | awpy or demoparser2, not yet chosen |
| `plays.py` | Detect and rank plays across the whole day, keep top N | Score = rarity × stakes × player × match tier |
| `narrate.py` | Grounded script per play | LLM writer + verifier; every sentence cites an event ID |
| `render.py` | 2D radar breakdown (own asset) + 3 s POV hook | Hook via CS2 client demo playback; POV chosen after the fact; game audio only |
| `assemble.py` | Hook + breakdown + voice → vertical MP4 | TTS + ffmpeg |
| Review queue | Operator approves or kills, checks narration | Plain web page or Slack message |
| `post.py` | Holds approved drafts until T+24h, one channel per game | YouTube Shorts (upload quota), TikTok (app audit first) |
| Metrics loop | Fit `plays.py` weights from views and retention | Not built now; after ~300 posts |

## Per-component build notes

From the Build Steps walkthrough.

- **parse.py** — start against a folder of manually downloaded demos; no
  scheduler yet. Normalize the parser library's output into our own timeline
  schema; that schema is what every later game adapter reuses.
- **plays.py** — rules for multi-kills, clutches and unusual kill types. Stakes
  first: how much the round moved the match. Hand-set weights for now. Rank the
  whole day together and keep the top N.
- **narrate.py** — feed the model callout names and derived facts, not raw
  coordinates. Verifier rejects any sentence without an event ID citation.
  Budget: 80–100 words, two or three causal beats.
- **render.py** — the 2D radar replay is the main visual and our own asset. The
  POV hook comes from CS2 client demo playback. Unknown: how scriptable that
  playback is; test early.
- **assemble.py** — TTS the script, lay it over the breakdown, cut to vertical.
  First end-to-end video exists here.
- **Review queue + post.py** — human approve/kill while learning where narration
  fails. Start platform API approvals early; they take longer than the code.
- **poll.py + fetch.py** — built last on purpose; manual download is fine until
  then. Unknown: where demos can be fetched reliably, and how soon.
- **Metrics** — log every ranking feature next to each post's views and
  retention; fit weights with a plain regression after a few hundred posts.
