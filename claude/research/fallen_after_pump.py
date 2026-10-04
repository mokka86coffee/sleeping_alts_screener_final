#!/usr/bin/env python3
"""ЗАПРЕТ ЛОНГОВ В ПАДАЮЩЕЙ ПОСЛЕ БОЛЬШОГО РОСТА МОНЕТЕ (03.10 22:25, владелец по BR: «если от самой высокой точки цена ушла более чем на 30 % — лонги не берём, это по сути просто
отскоки для того, чтобы выбивать заходящие лонги»). Дневные данные TradingView, 497 монет, 15 месяцев. Состояние на день: за 90 дней был рост от минимума до более поздней вершины
в RISE раз и цена закрытия ниже вершины на DROP и больше. Лонг и шорт по закрытию такого дня (сделка как в tv_rules.py), по половинам периода, и то же для остальных дней."""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from tv_rules import sim
from tv_combo import prep, line
C = prep(); ts = sorted(int(t) for F in C.values() for t in F["t"][180:]); tmid = ts[len(ts) // 2]
for F in C.values():
    n = F["n"]; h, l = F["h"], F["l"]; rise = np.full(n, np.nan); drop = np.full(n, np.nan)
    for i in range(89, n):
        w0 = i - 89; im = w0 + int(np.argmax(h[w0:i + 1])); top = h[im]; lo = l[w0:im + 1].min()
        rise[i] = top / lo if lo > 0 else np.nan; drop[i] = 1 - F["c"][i] / top
    F["p_rise"], F["p_drop"] = rise, drop
def st(rise, dlo, dhi): return lambda F, i: F["p_rise"][i] >= rise and dlo <= F["p_drop"][i] < dhi
for tp, sl, h in ((.10, .10, 7), (.05, .10, 3)):
    print(f"\n=== цель {tp:.0%} стоп {sl:.0%} срок {h} дн ===")
    for side, nm in ((1, "ЛОНГ"), (-1, "ШОРТ")):
        print(nm)
        line("  любой день (база)", sim(C, lambda F, i: True, tp, sl, h, side), tmid)
        for rise in (1.6, 2.0, 3.0):
            line(f"  рост ×{rise:g}+ за 90 дн, цена ниже вершины на 30 %+", sim(C, st(rise, .30, 9), tp, sl, h, side), tmid)
        line("  рост ×2+, ниже вершины на 0–15 %", sim(C, st(2.0, 0, .15), tp, sl, h, side), tmid)
        line("  рост ×2+, ниже вершины на 15–30 %", sim(C, st(2.0, .15, .30), tp, sl, h, side), tmid)
        line("  рост ×2+, ниже вершины на 30–50 %", sim(C, st(2.0, .30, .50), tp, sl, h, side), tmid)
        line("  рост ×2+, ниже вершины на 50 %+", sim(C, st(2.0, .50, 9), tp, sl, h, side), tmid)
        line("  роста ×2 не было, ниже вершины на 30 %+", sim(C, lambda F, i: F["p_rise"][i] < 2.0 and F["p_drop"][i] >= .30, tp, sl, h, side), tmid)
now = [(s, float(F["p_rise"][-2]), float(F["p_drop"][-2])) for s, F in C.items() if F["p_rise"][-2] >= 2.0 and F["p_drop"][-2] >= .30]
print(f"\nсейчас под запретом (рост ×2+ за 90 дн и ниже вершины на 30 %+): {len(now)} монет из {len(C)}: " + ", ".join(f"{s} −{d * 100:.0f}%" for s, r, d in sorted(now, key=lambda x: -x[2])[:60]))
