#!/usr/bin/env python3
"""Проба интрадей-слоя: разброс заметности и скорости по выборке.

Зачем отдельный скрипт. flow_probe выгружает КОНТЕКСТ СЕМЕЙСТВА, а
интрадей-блок живёт в метриках, в raw["intraday"], и в тот дамп не
попадает вовсе. Проверить П-1 и П-8 по флоу-пробе нельзя — это
выяснилось на прогоне 16 августа: в JSON приехали oi_hist,
funding_hist, peak_up_x, но intraday там нет и быть не может.

Скрипт ничего не меняет в проекте: берёт ту же выборку, тянет часовые
свечи (они и так канонические, кэш общий) и печатает разбросы, по
которым выбираются пороги.

Запуск из корня проекта:
    python3 intraday_probe.py               вся выборка
    python3 intraday_probe.py --limit 40    быстрее, для проверки
    python3 intraday_probe.py --json out.json   сырые числа в файл
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from analytics.intraday import scan
from core.binance import get_futures_tickers, get_oi_history, klines_1h


def _pick_symbols(limit: int | None) -> list[str]:
    """Символы выборки по обороту.

    Отбор нарочно грубее боевого: задача пробы — разброс величин, а
    не воспроизведение отбора. Если бы скрипт тянул run.py целиком,
    он бы ломался при каждой правке отбора и переставал работать
    ровно тогда, когда нужен.
    """
    out = []
    for t in get_futures_tickers():
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        try:
            vol = float(t.get("quoteVolume", 0))
        except (TypeError, ValueError):
            continue
        out.append((vol, sym))
    out.sort(reverse=True)
    syms = [s for _, s in out]
    return syms[:limit] if limit else syms


def _q(vals: list[float], p: float) -> float:
    return vals[min(len(vals) - 1, int(len(vals) * p))]


def _spread(name: str, vals: list, digits: int = 2) -> None:
    v = sorted(x for x in vals if x is not None)
    if not v:
        print(f"  {name:16s} нет замеров")
        return
    f = f"{{:.{digits}f}}"
    print(f"  {name:16s} n {len(v):3d}  мин " + f.format(v[0]) +
          "  q25 " + f.format(_q(v, .25)) +
          "  мед " + f.format(_q(v, .5)) +
          "  q75 " + f.format(_q(v, .75)) +
          "  макс " + f.format(v[-1]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--json", dest="dump", default=None)
    args = ap.parse_args()

    syms = _pick_symbols(args.limit)
    print(f"монет к прогону: {len(syms)}\n")

    t0 = time.time()
    rows: list[dict] = []
    for i, sym in enumerate(syms, 1):
        try:
            kl = klines_1h(sym)
        except Exception as exc:                      # noqa: BLE001
            print(f"  {sym}: {exc}")
            continue
        try:
            oi = [float(r.get("sumOpenInterest") or 0.0)
                  for r in (get_oi_history(sym, period="1h", limit=200) or [])
                  if isinstance(r, dict)]
        except Exception:                             # noqa: BLE001
            oi = []
        s = scan(kl, "1h", oi)
        if not s:
            continue
        s["symbol"] = sym
        rows.append(s)
        if i % 25 == 0:
            print(f"  {i}/{len(syms)}  {time.time() - t0:.0f}с")

    print(f"\nзамеров: {len(rows)}, {time.time() - t0:.0f}с\n")
    if not rows:
        return 1

    g = lambda blk, key: [                              # noqa: E731
        (r.get(blk) or {}).get(key) for r in rows
    ]

    print("ЗАМЕТНОСТЬ (П-8):")
    _spread("q", g("prom", "q"))
    _spread("max_x", g("prom", "max_x"))
    _spread("p90_x", g("prom", "p90_x"))
    _spread("сделок в баре", g("prom", "trades_med"), 0)

    print("\nКРУПНЫЕ ЗАЯВКИ (П-1), порог ×3.0:")
    _spread("меток за 48ч", g("big", "count"), 0)
    _spread("из них покупок", g("big", "buys"), 0)
    _spread("максимум ×", g("big", "max_x"))
    zero = sum(1 for c in g("big", "count") if not c)
    print(f"  без единой метки: {zero} из {len(rows)}")
    много = sum(1 for c in g("big", "count") if (c or 0) >= 10)
    print(f"  десять и больше:  {много} из {len(rows)}")
    neutral = sum(
        1 for r in rows
        for m in ((r.get("big") or {}).get("marks") or [])
        if m.get("side") == "none"
    )
    total = sum(len((r.get("big") or {}).get("marks") or []) for r in rows)
    if total:
        print(f"  нейтральных сторон: {neutral} из {total} "
              f"({neutral / total * 100:.0f}%) — П-2")

    print("\nСКОРОСТЬ ХОДА (П-9):")
    _spread("v, ATR/бар", g("speed", "v"), 3)
    _spread("ход в ATR", g("speed", "atr_move"), 1)
    _spread("баров хода", g("speed", "bars"), 0)

    print("\nИМПАКТ (П-10), цена за миллион чистых продаж:")
    legs_n = [len((r.get("impact") or {}).get("legs") or []) for r in rows]
    _spread("ног за 48ч", legs_n, 0)
    _spread("impact", [(r.get("impact") or {}).get("last") for r in rows], 4)
    _spread("отношение к пред.", [(r.get("impact") or {}).get("ratio")
                                  for r in rows])
    rates = [l.get("rate_m") for r in rows
             for l in ((r.get("impact") or {}).get("legs") or [])
             if l.get("rate_m")]
    _spread("подача, М/бар", rates)
    # Направление важнее самой величины: импакт имеет смысл только в
    # сравнении ног одной монеты между собой.
    ratios = [x for x in ((r.get("impact") or {}).get("ratio") for r in rows)
              if x]
    if ratios:
        down = sum(1 for x in ratios if x < 1)
        print(f"  импакт падает от ноги к ноге: {down} из {len(ratios)}")
    none_legs = sum(1 for n in legs_n if not n)
    print(f"  без единой ноги: {none_legs} из {len(rows)}")

    print("\nКТО КОГО ПРИНЯЛ (П-11):")
    win = [(r.get("balance") or {}).get("window") for r in rows]
    for name in ("раздача", "поглощение", "согласие"):
        n = sum(1 for w in win if w == name)
        print(f"  {name:12s} {n:3d} из {len(rows)}")
    print(f"  {'без вердикта':12s} {sum(1 for w in win if not w):3d} из {len(rows)}")
    _spread("перевес, доля", [(r.get("balance") or {}).get("share") for r in rows], 3)
    _spread("раздача, М", [(r.get("balance") or {}).get("distrib_m") for r in rows], 1)
    _spread("поглощение, М", [(r.get("balance") or {}).get("absorb_m") for r in rows], 1)

    print("\nЛЕСТНИЦА ШКАЛ (П-8):")
    best = [(r.get("ladder") or {}).get("best", {}).get("scale") for r in rows]
    for sc in ("1h", "2h", "3h", "6h", "12h"):
        n = sum(1 for b in best if b == sc)
        print(f"  лучшая {sc:4s} {n:3d} из {len(rows)}")
    print(f"  без лестницы  {sum(1 for b in best if not b):3d} из {len(rows)}")

    print("\nЧТО ПРОИСХОДИТ (связка с OI):")
    verds = [(r.get("stance") or {}).get("verdict") for r in rows]
    for name in ("накопление", "выход толпы", "набор шорта", "делеверидж"):
        print(f"  {name:14s} {sum(1 for v in verds if v == name):3d} из {len(rows)}")
    print(f"  {'без вердикта':14s} {sum(1 for v in verds if not v):3d} из {len(rows)}")
    _spread("изм. OI, %", [(r.get("stance") or {}).get("oi_pct") for r in rows], 1)

    print("\nУРОВНИ КРУПНЫХ ПОКУПОК:")
    kinds = [(r.get("big_levels") or {}).get("kind") for r in rows]
    print(f"  поддержка {sum(1 for k in kinds if k == 'поддержка'):3d}  "
          f"навес {sum(1 for k in kinds if k == 'навес'):3d}  "
          f"нет меток {sum(1 for k in kinds if not k):3d}")
    _spread("до средней, %", [(r.get("big_levels") or {}).get("vs_price_pct")
                              for r in rows], 1)

    print("\nОСТАЛЬНОЕ:")
    _spread("перевес, п.п.", g("pressure", "delta"), 1)
    _spread("фон суток", [r.get("bg") for r in rows])
    _spread("в диапазоне %", [r.get("range_pos") for r in rows], 0)
    ago = [(r.get("vortex") or {}).get("bars_ago") for r in rows]
    up = sum(1 for r in rows if (r.get("vortex") or {}).get("dir") == "up")
    print(f"  вортекс вверх: {up} из {len(rows)}")
    _spread("перекрест, бар", [a for a in ago if a is not None and a >= 0], 0)

    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=1)
        print(f"\nсырые числа: {args.dump}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
