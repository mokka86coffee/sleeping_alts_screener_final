#!/usr/bin/env python3
"""ЛОНГИ БОТА: СКОЛЬКО МОЖНО БЫЛО ДЕРЖАТЬ ДО ВЫНОСА ШОРТОВ (28.09, владелец: «посмотри по коингласс, сколько можно было на растущей монете
досидеть с твх до выноса в лонге — все лонги, которые открывались в боте»).

Ликвидации — Coinglass (все биржи, 15m, выгрузка cg_review.py → cgx/<монета>_15.json). По каждому лонгу за 24 ч после входа:
  вынос — 15-мин бар с самым крупным выносом шортов за эти 24 ч (задним числом: бот в моменте не знает, что он самый крупный);
  % на закрытии бара выноса, часов от входа; просадка до выноса и задел ли её стоп −5% раньше; лучшая цена до выноса;
  против фактического выхода. Сделки, у которых после входа ещё нет 24 ч, — с пометкой «окно N ч».

    .venv/bin/python claude/research/long_hold.py            # → long_hold.md
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
L = timezone(timedelta(hours=3))
OUT = HERE / "long_hold.md"
STOP = 5.0          # стоп бота −5% (как в книгах)


def main() -> int:
    T = [x for x in json.load(open(HERE / "cgr" / "trades.json")) if x["side"] == 1]
    rows, miss = [], []
    for x in T:
        f = HERE / "cgx" / f"{x['sym']}_15.json"
        if not f.exists():
            miss.append(x["sym"][:-4]); continue
        R = [r for r in json.load(open(f))["rows"] if r.get("c")]
        t0, t1 = x["t_in"], x["t_in"] + 86400
        W = [r for r in R if t0 - 900 < r["t"] <= t1]                 # бар, в котором вход, и сутки после
        if not W or x["px_in"] <= 0:
            miss.append(x["sym"][:-4]); continue
        pk = max(W, key=lambda r: r.get("liq_short") or 0)
        before = [r for r in W if r["t"] <= pk["t"]]
        low = min(r["l"] for r in before); high = max(r["h"] for r in before)
        stop_hit = next((r for r in before if r["l"] <= x["px_in"] * (1 - STOP / 100)), None)
        rows.append(dict(x=x, pk=pk, flush=pk.get("liq_short") or 0, at=(pk["c"] / x["px_in"] - 1) * 100,
                         hrs=(pk["t"] + 900 - t0) / 3600, dd=(low / x["px_in"] - 1) * 100, best=(high / x["px_in"] - 1) * 100,
                         stop=stop_hit, win=(min(time.time(), t1) - t0) / 3600))
    fmt_t = lambda t: datetime.fromtimestamp(t, L).strftime("%d.%m %H:%M")  # noqa: E731
    reach = [r for r in rows if not r["stop"]]
    md = [f"# Лонги бота: держать до выноса шортов ({datetime.now(L):%d.%m %H:%M})", "",
          "Ликвидации — Coinglass, все биржи, 15m. Вынос — самый крупный 15-мин бар выноса шортов за 24 ч после входа (задним числом). "
          f"Стоп −{STOP:g}% как в боте. Расчёт по одной группе (все лонги бота с 27.09 07:15), не анализ; правило из него — не проверено.", "",
          f"Лонгов {len(rows)} (без данных Coinglass: {', '.join(miss) or 'нет'}).",
          f"- стоп −5% задел раньше выноса: **{len(rows) - len(reach)}**;",
          f"- дожили до выноса: **{len(reach)}**, из них на выносе в плюсе {sum(1 for r in reach if r['at'] > 0)}; "
          f"сумма % на выносе {sum(r['at'] for r in reach):+.1f}% (500 $ на сделку: {sum(r['at'] for r in reach) * 5:+.0f} $);",
          f"- с учётом стопов (−5% у выбитых): {sum(r['at'] for r in reach) - STOP * (len(rows) - len(reach)):+.1f}% "
          f"({(sum(r['at'] for r in reach) - STOP * (len(rows) - len(reach))) * 5:+.0f} $);",
          f"- факт бота по тем же лонгам: {sum(r['x']['res'] for r in rows):+.1f}% ({sum(r['x']['res'] for r in rows) * 5:+.0f} $).", "",
          "| монета | вход | факт | вынос шортов | через | % на выносе | просадка до | лучшее до | стоп раньше |", "|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: r["x"]["t_in"]):
        x = r["x"]; s = x["sym"][:-4]
        md.append(f"| [{s}](https://www.coinglass.com/tv/Binance_{x['sym']}) · [TV](https://www.tradingview.com/chart/?symbol=BINANCE:{x['sym']}.P) | "
                  f"{fmt_t(x['t_in'])} | {x['res']:+.1f}% ({x['why']}) | {r['flush'] / 1e3:.0f}K$ в {fmt_t(r['pk']['t'])} | {r['hrs']:.1f} ч | "
                  f"{r['at']:+.1f}% | {r['dd']:+.1f}% | {r['best']:+.1f}% | {('да, ' + fmt_t(r['stop']['t'])) if r['stop'] else 'нет'}"
                  f"{'' if r['win'] >= 24 else f' · окно {r[chr(119)+chr(105)+chr(110)]:.0f} ч'} |")
    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:12]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
