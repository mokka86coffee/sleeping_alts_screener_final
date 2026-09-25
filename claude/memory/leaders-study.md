---
name: leaders-study
description: "Ongoing TradingView review of 100 leaders (1h), grouping by movement and indicator scenario — state lives in claude/research/ (в проекте)"
metadata:
  node_type: memory
  type: project
  originSessionId: fa91e09e-9d7a-4051-9dae-3dae50c899e1
  modified: 2026-09-25T18:56:22.752Z
---

Started 25.09: the owner asked to go through the 100 leaders from output/leaders.json on the 1h TradingView chart and group them by similar movement and indicators, noting exceptions and background.

All progress is on disk in `claude/research/ (в проекте)`:
- README.md: progress, the next coin, and how to take the screenshots;
- notes.md: one note per coin;
- table.csv: the numbers;
- groups.md: the groups found so far;
- queue_31_100.json: the remaining coins with their chart windows.

Read README.md first and continue from the listed next coin. After each coin, append to notes.md and update the progress line.

**Why:** the owner pointed out that my context runs out partway through 100 charts.
**How to apply:** never keep study results only in conversation context.

Related: [[working-style]], [[screener-project]]

26.09: everything moved into the project, in `claude/`:
- `claude/CONTEXT.md` holds the full context;
- `claude/research/` holds the research;
- `claude/memory/` holds a copy of these memory files.

Keep all three updated after every important step, and re-copy the memory files into `claude/memory/` whenever they change. The owner wants to be able to hand me that folder after any interruption.
