#!/usr/bin/env python3
"""СДЕЛКИ БЫСТРОГО БОТА ПО СТРАТЕГИЯМ (28.09, владелец: «сделай выборку по всем сделкам обновлённого бота и выведи, какие монеты и по каким
стратегиям выходили в плюс, а какие в минус»).

Книги «пробуждение» и «всплеск/вынос» с 27.09 07:15 (запуск обновлённого бота), закрытые. Стратегия — по правилу входа:
  лонг-всплеск (R39: бар в плюс на объёме ×N); перевёрнутый шорт по интересу за час (≥ +3%); перевёрнутый шорт по 5-мин бару интереса (≤ 0);
  вынос (шорт после бара-вертикали с падающим интересом). Монеты своего ММ (R43) — ⓜ.

    .venv/bin/python claude/research/fast_by_strategy.py        # → fast_by_strategy.md
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
L = timezone(timedelta(hours=3))
T0 = datetime(2026, 9, 27, 7, 15, tzinfo=L).timestamp()
OUT = Path(__file__).with_name("fast_by_strategy.md")


def strat(rule: str, side: int) -> str:
    head = rule.split(" · ")[0]
    if head.startswith("перевёрнутый всплеск: интерес за 5 мин"):
        return "перевёрнутый шорт · 5-мин бар интереса ≤ 0"
    if head.startswith("перевёрнутый всплеск"):
        return "перевёрнутый шорт · интерес за час ≥ +3%"
    if head.startswith("вынос"):
        return "вынос · шорт"
    return "лонг-всплеск (R39)" if side == 1 else "шорт · прочее"


def main() -> int:
    own = {k for k, v in (json.load(open(ROOT / "output" / "own_mm.json")).get("coins") or {}).items() if v.get("block")}
    G = defaultdict(list)
    for book, f in (("пробуждение", "paper_wake.jsonl"), ("всплеск/вынос", "paper_fast3.jsonl")):
        for ln in open(ROOT / "output" / f):
            r = json.loads(ln)
            if not str(r.get("kind", "")).startswith("exit") or float(r.get("opened_at") or 0) < T0:
                continue
            s = strat(r.get("rule") or "", int(r.get("side") or 1))
            t = datetime.fromtimestamp(float(r["opened_at"]), L)
            G[s].append(dict(book=book, sym=r["sym"][:-4], res=float(r["result_pct"]), usd=float(r.get("usd") or r["result_pct"] * 5),
                             why=r.get("why_exit") or "", t=t, own=r["sym"] in own))
    md = [f"# Быстрый бот: монеты по стратегиям — плюс и минус ({datetime.now(L):%d.%m %H:%M})", "",
          "Закрытые сделки «пробуждения» и «всплеска/выноса» с 27.09 07:15, 500 $ на сделку, выход +5% / −5% / по сроку. "
          "Формат монеты: имя итог% (вход дд.мм чч:мм, выход). ⓜ — свой ММ.", "",
          "| стратегия | сделок | в плюс | в минус | итог | без своего ММ |", "|---|---|---|---|---|---|"]
    order = sorted(G, key=lambda k: -len(G[k]))
    for k in order:
        g = G[k]; g2 = [x for x in g if not x["own"]]
        md.append(f"| {k} | {len(g)} | {sum(1 for x in g if x['res'] > 0)} | {sum(1 for x in g if x['res'] <= 0)} | {sum(x['usd'] for x in g):+.0f} $ | "
                  f"{len(g2)} сделок · {sum(x['usd'] for x in g2):+.0f} $ |")
    fmt = lambda x: f"{x['sym']}{' ⓜ' if x['own'] else ''} {x['res']:+.1f}% ({x['t']:%d.%m %H:%M}, {x['why']})"  # noqa: E731
    for k in order:
        g = sorted(G[k], key=lambda x: -x["res"])
        md += ["", f"## {k}", "", f"**В плюс ({sum(1 for x in g if x['res'] > 0)}):** " + ", ".join(fmt(x) for x in g if x["res"] > 0), "",
               f"**В минус ({sum(1 for x in g if x['res'] <= 0)}):** " + ", ".join(fmt(x) for x in g if x["res"] <= 0)]
    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
