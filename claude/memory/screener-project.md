---
name: screener-project
description: "sleeping_alts_screener state — the owner edits in parallel chats, handoff files live in ~/Downloads, no Coinglass since 24.09"
metadata:
  node_type: memory
  type: project
  originSessionId: a5ef0660-961c-44f9-ae97-a14c306bbad6
  modified: 2026-09-25T12:48:14.832Z
---

- The owner also changes the repo from other chats (claude.ai, other Code branches). Before editing, check file mtimes and `git log` so parallel edits don't get overwritten. The handoff is `~/Downloads/CONTEXT.md` plus `FILES.md`; the fresh FILES.md they send replaces the repo copy.
- On 24.09 the Coinglass subscription ended. `binance_fetch.py` and `binance_crowd.py` write the same `coinglass_fetch.json` and `coinglass_crowd.json`. The switch is `COINGLASS_ENABLED` in core_config. Liquidations by side are gone.
- A 23.09 Code branch (transcript 9166a1c6) did the following (documented in FILES.md section «23–24.09» since 24.09 evening, together with the new book «3 в первых подряд» paper_first3.py):
  - fixed the `tick_fetch.py` cache bug (no 3m candles were written 17–23.09) and backfilled 3m candles from 15.09;
  - added `lab_replay.py`;
  - «картина» moved to live-price entry, a 5% target checked on 3m candles, and repeat entry (SIGHT_TICK_TARGET, SIGHT_REPEAT).
- 24.09 analysis of «картина» longs with honest entry: they perform the same as random longs. The background gate that held in both halves of the week was longs only 0–13 UTC, with BTC up over the last hour, on weekdays: +3.30% and +1.43% per trade against +2.03% and +0.46% for all longs. Shorts lose in every book.
- On 23.09 the owner lost half their deposit on ONE. On 25.09 they lost almost all of the rest on a PLAY long; they had read "spot buys it back, we're near the bottom" as a pump coming. They also lost on ARK 14.09. Money results are what matter to them. Never phrase a descriptive read so it sounds like a forecast, and say plainly what our numbers cannot predict.

Related: [[working-style]]
