---
name: working-style
description: "How the owner of sleeping_alts_screener wants to work — plan in words first, one option, no invented thresholds, one restart"
metadata:
  node_type: memory
  type: feedback
  originSessionId: a5ef0660-961c-44f9-ae97-a14c306bbad6
  modified: 2026-09-25T23:47:42.122Z
---

The owner is the only developer of the screener and trades micro-cap perps on BingX. They are in UTC+3 and fly a lot; all times on screens are shown in local time. They speak Russian.

1. Describe the plan in words first (what changes on screen), wait for "да", then change one file. Don't make a series of edits.
2. Give one option, not ten.
3. Don't present my own thresholds as rules. Put them in core_config and explain where the number came from.
4. Test on the archive before installing, one coin at a time with `--only`.
5. `run.py --loop` loads modules only at start. Batch edits and restart once, with `pkill -f "run.py"; sleep 3; nohup python3 run.py --loop > output/run.log 2>&1 &`. Check that exactly one process is running.
6. Pass thresholds through core_config, network calls through core_binance/core_http, and writes through write_atomic. Don't touch coinglass_* files; replacements go in binance_* files.
7. Prose meant for voice-over: numbers as words, no arrows or math symbols.
8. For visuals, first build an HTML prototype in the screen's own style (nebula, light, stars with rays), not schematic circles.
11. **Terminal commands only after the owner's explicit consent, ALWAYS (26.09).** Say what I want to run and why, wait for "да", then run. Reading and editing files with Read/Edit/Write is fine without asking. The rule came after I launched TradingView and installed a package on my own.
    **Weekly allowances** — the owner can approve a class of commands for one week; when it expires, ask again. Granted 26.09, valid until **2026-10-03**:
    1. read-only checks inside the project: scripts with `--only` and without `--write`/`--replay`, `py_compile`, `lab_*.py`, one-off `.venv/bin/python` analysis over the archive;
    2. reading state: `ls`, `grep`, `git status/log/diff`, `pgrep`, `tail` of logs;
    3. read-only network: Binance, OKX, Bybit market data, and a 1–2 minute liquidation-stream check;
    4. copying memory files into `claude/memory/`;
    5. launching TradingView with the debug port when it is closed and I need it: `open -a TradingView --args --remote-debugging-port=9222` (never quit it if it is already running — ask the owner to Cmd+Q).
    **`pkill` (and `kill`) I never run myself — no exceptions, no weekly allowance.** The owner stops and restarts processes.
    Always ask, every time: restarting the loop, installing packages, manual `git push`, launching apps, deleting files, anything writing to `output/` or the archive.

    **Update 26.09 (night), owner: «к папке с проектом у тебя полный доступ к файлам, от меня разрешений для их запуска не требуется».**
    Running the project's own scripts (including ones that write into the project: archive refresh, research outputs, `output/`) needs no «да».
    Also: «дальше все сверки/проверки делай сам, пока лимит сессии не закончится, периодически присылай, что вывел и что поменялось».
    Still ask every time for: restarting `run.py --loop`, installing packages, manual `git push`, launching apps, deleting files.
    `pkill`/`kill` — still never.
9. They want patterns and variations that narrow down trades, not "it's 50/50". Always test against background: board median, BTC, sessions and junctions (21/0/7/13 UTC), weekday vs weekend. A bare "random entry does the same" is not an answer. Follow it with the next filter to try.
10. **Never pool all coins into one test (25.09, the core lesson of the month).** Each coin has its own market maker and its own scenario, and the crowd can take over a coin. Pooled averages over ~150 coins always come out 50/50 — "comparing watermelons grown in Africa, Argentina and Australia". Instead:
    - compare a coin to its OWN previous moves: how they started, what fuelled them, how they ended;
    - a rule that works on 10% of coins is a rule for that group, and groups become separate strategies;
    - the indicator set is incomplete, so a failed test doesn't kill a rule — it means an assumption is missing;
    - every conclusion is a probability with stated assumptions, not a formula to rebuild each time.

   When the owner gives specific coins or charts, reason about those, not a sweep. A month of pooled analysis made them late at every step, and they lost money.

**Why:** from their handoff notes (CONTEXT.md 20.09 and 24.09) and their reaction on 24.09; breaking these annoys them.
**How to apply:** every change to this project. See [[screener-project]].
