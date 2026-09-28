#!/usr/bin/env python3
"""ТАБЛИЦА ВСЕХ СДЕЛОК БЫСТРОГО БОТА (28.09, владелец: «снова сделай таблицу по всем сделкам нового бота с разбивкой по времени и медианой доски»).

Книги «пробуждение» (paper_wake) и «всплеск/вынос» (paper_fast3) с 27.09 07:15: вход (день, час, сессия UTC+3), монета, сторона
(лонг / перевёрнутый шорт / шорт), итог % и $ при 500 $, причина выхода, доска на входе (медиана монет за 6 ч и за 24 ч — поле fon записи входа).
Сводки: по сессиям, по дням, по знаку доски 6 ч и по её четвертям (границы — из самих данных). Монеты своего ММ (R43) помечены и в сводки не идут.

    .venv/bin/python claude/research/fast_trades_table.py        # → fast_trades.md
"""
from __future__ import annotations

import json
import statistics as st
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
L = timezone(timedelta(hours=3))
T0 = datetime(2026, 9, 27, 7, 15, tzinfo=L).timestamp()
OUT = Path(__file__).with_name("fast_trades.md")
DOW = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def ses(h: int) -> str:
    return "Сидней" if h < 3 else "Токио" if h < 10 else "Лондон" if h < 16 else "Нью-Йорк"


def main() -> int:
    own = {k for k, v in (json.load(open(ROOT / "output" / "own_mm.json")).get("coins") or {}).items() if v.get("block")}
    T = []
    for book, f in (("пробуждение", "paper_wake.jsonl"), ("всплеск/вынос", "paper_fast3.jsonl")):
        R = [json.loads(x) for x in open(ROOT / "output" / f) if x.strip()]
        ent = {(r["sym"], round(float(r["at"]), 1)): r for r in R if r.get("kind") == "entry"}
        for r in R:
            if not str(r.get("kind", "")).startswith("exit") or float(r.get("opened_at") or 0) < T0:
                continue
            e = ent.get((r["sym"], round(float(r["opened_at"]), 1))) or {}
            fon = e.get("fon") or {}
            ti = datetime.fromtimestamp(float(r["opened_at"]), L)
            side = int(r.get("side") or 1)
            kind = "лонг" if side == 1 else ("перев. шорт" if "перев" in (r.get("rule") or "") else "шорт")
            T.append(dict(t=ti, book=book, sym=r["sym"][:-4], kind=kind, res=float(r["result_pct"]), usd=float(r.get("usd") or r["result_pct"] * 5),
                          why=r.get("why_exit") or "", b6=fon.get("board6"), b24=fon.get("board24"), own=r["sym"] in own))
    T.sort(key=lambda x: x["t"])
    f = lambda x: "—" if x is None else f"{x:+.1f}%"  # noqa: E731
    md = [f"# Все сделки быстрого бота ({datetime.now(L):%d.%m %H:%M})", "",
          f"Книги «пробуждение» и «всплеск/вынос» с 27.09 07:15, закрытые: {len(T)}. 500 $ на сделку, цель +5% / стоп −5% / выход по сроку (сессия R41). "
          "Доска — медиана доходности монет за 6 ч и 24 ч в момент входа (поле fon). ⓜ — монета своего ММ (R43), в сводки не идёт.", "",
          "| вход | день | сессия | книга | монета | сторона | итог | $ | выход | доска 6ч | доска 24ч |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in T:
        md.append(f"| {x['t']:%d.%m %H:%M} | {DOW[x['t'].weekday()]} | {ses(x['t'].hour)} | {x['book']} | {x['sym']}{' ⓜ' if x['own'] else ''} | {x['kind']} | "
                  f"{x['res']:+.1f}% | {x['usd']:+.0f} | {x['why']} | {f(x['b6'])} | {f(x['b24'])} |")
    G = [x for x in T if not x["own"]]

    def line(lab, g):
        if g:
            md.append(f"| {lab} | {len(g)} | {sum(1 for x in g if x['res'] > 0)} ({sum(1 for x in g if x['res'] > 0) / len(g) * 100:.0f}%) | "
                      f"{sum(x['usd'] for x in g):+.0f} $ | {st.median(x['res'] for x in g):+.1f}% |")
    hdr = ["| группа | сделок | в плюс | итог | медиана |", "|---|---|---|---|---|"]
    md += ["", f"## Сводка без монет своего ММ ({len(G)} сделок)", ""] + hdr
    line("все", G)
    for k in ("лонг", "перев. шорт", "шорт"):
        line(k, [x for x in G if x["kind"] == k])
    md += ["", "### По сессиям входа", ""] + hdr
    for s in ("Сидней", "Токио", "Лондон", "Нью-Йорк"):
        line(s, [x for x in G if ses(x["t"].hour) == s])
        for k in ("лонг", "перев. шорт"):
            line(f"  {s} · {k}", [x for x in G if ses(x["t"].hour) == s and x["kind"] == k])
    md += ["", "### По дням", ""] + hdr
    for d in sorted({x["t"].date() for x in G}):
        line(f"{d:%d.%m} {DOW[d.weekday()]}", [x for x in G if x["t"].date() == d])
    b6 = sorted(x["b6"] for x in G if x["b6"] is not None)
    md += ["", "### По доске 6 ч на входе", ""] + hdr
    line("доска 6ч < 0", [x for x in G if x["b6"] is not None and x["b6"] < 0])
    line("доска 6ч ≥ 0", [x for x in G if x["b6"] is not None and x["b6"] >= 0])
    if len(b6) >= 8:
        qs = [b6[len(b6) * i // 4] for i in (1, 2, 3)]
        edges = [(-1e9, qs[0]), (qs[0], qs[1]), (qs[1], qs[2]), (qs[2], 1e9)]
        for i, (lo, hi) in enumerate(edges):
            g = [x for x in G if x["b6"] is not None and lo <= x["b6"] < hi]
            line(f"четверть {i + 1}: доска 6ч {'' if lo < -1e8 else f'от {lo:+.1f}% '}{'' if hi > 1e8 else f'до {hi:+.1f}%'}", g)
            for k in ("лонг", "перев. шорт"):
                line(f"  · {k}", [x for x in g if x["kind"] == k])
    md += ["", "### По доске 24 ч на входе", ""] + hdr
    line("доска 24ч < 0", [x for x in G if x["b24"] is not None and x["b24"] < 0])
    line("доска 24ч ≥ 0", [x for x in G if x["b24"] is not None and x["b24"] >= 0])
    for k in ("лонг", "перев. шорт"):
        line(f"  доска 24ч < 0 · {k}", [x for x in G if x["b24"] is not None and x["b24"] < 0 and x["kind"] == k])
        line(f"  доска 24ч ≥ 0 · {k}", [x for x in G if x["b24"] is not None and x["b24"] >= 0 and x["kind"] == k])
    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    i = md.index(f"## Сводка без монет своего ММ ({len(G)} сделок)")
    print("\n".join(md[i:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
