#!/usr/bin/env python3
"""РЕЖИМ ДОСКИ И ОТПЕЧАТКИ ВНУТРИ РЕЖИМА (03.10; владелец: «при росте доски заменяй шорт на лонг», «думай, как точнее определять, что пойдёт»).
Доска на день = все перпы Binance с данными TradingView: b7/b3/b1 — медиана хода закрытия за 7/3/1 дн; br — доля монет выше своей средней за 20 дн; br5 — изменение этой доли за 5 дн.
Сделка как в tv_rules.py (вход по закрытию дня, 1000 $, 1 $ комиссия, оба задеты в один день = стоп, одна сделка на монету за раз).
Вопрос 1: даёт ли режим доски знак сделки (лонг/шорт любой монеты) в обеих половинах периода.
Вопрос 2: какие отпечатки монеты добавляют к режиму. Только запись."""
import sys, math
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from tv_rules import load, roll, ch, sim, rep
def board(C):
    acc = {k: defaultdict(list) for k in ("b1", "b3", "b7", "b30", "br")}
    for F in C.values():
        c = F["c"]; sma = roll(c, 20, np.mean)
        for i in range(30, F["n"]):
            t = int(F["t"][i])
            for k, d in (("b1", 1), ("b3", 3), ("b7", 7), ("b30", 30)):
                if c[i - d] > 0: acc[k][t].append(c[i] / c[i - d] - 1)
            acc["br"][t].append(1.0 if c[i] > sma[i] else 0.0)
    Bd = {k: {t: float(np.median(a) if k != "br" else np.mean(a)) for t, a in d.items() if len(a) >= 50} for k, d in acc.items()}
    ts = sorted(Bd["br"]); Bd["br5"] = {t: Bd["br"][t] - Bd["br"][ts[j - 5]] for j, t in enumerate(ts) if j >= 5}
    for F in C.values():
        for k in Bd: F[k] = np.array([Bd[k].get(int(t), np.nan) for t in F["t"]])
    return Bd
if __name__ == "__main__":
    C = load(); Bd = board(C); ts = sorted(int(t) for F in C.values() for t in F["t"][180:]); tmid = ts[len(ts) // 2]
    print(f"монет {len(C)} · середина {datetime.fromtimestamp(tmid, timezone.utc):%d.%m.%Y}")
    R = {
     "любой день": lambda F, i: True,
     "доска 7 дн > 0": lambda F, i: F["b7"][i] > 0,
     "доска 7 дн ≤ 0": lambda F, i: F["b7"][i] <= 0,
     "доска 7 дн > +5%": lambda F, i: F["b7"][i] > .05,
     "доска 7 дн < −5%": lambda F, i: F["b7"][i] < -.05,
     "доска 30 дн > 0": lambda F, i: F["b30"][i] > 0,
     "доска 30 дн ≤ 0": lambda F, i: F["b30"][i] <= 0,
     "ширина > 50% (больше половины монет выше своей средней 20 дн)": lambda F, i: F["br"][i] > .5,
     "ширина ≤ 50%": lambda F, i: F["br"][i] <= .5,
     "ширина < 20% (почти все под средней)": lambda F, i: F["br"][i] < .2,
     "ширина > 80%": lambda F, i: F["br"][i] > .8,
     "ширина выросла за 5 дн на 20+ п.п.": lambda F, i: F["br5"][i] >= .2,
     "ширина упала за 5 дн на 20+ п.п.": lambda F, i: F["br5"][i] <= -.2,
     "ширина пересекла 50% снизу (вчера ≤50, сегодня >50)": lambda F, i: F["br"][i] > .5 and F["br"][i - 1] <= .5,
    }
    for tp, sl, hold in ((.10, .10, 7), (.20, .10, 14)):
        for side, nm in ((1, "ЛОНГ"), (-1, "ШОРТ")):
            print(f"\n=== {nm} цель {tp:.0%} стоп {sl:.0%} срок {hold} дн — режим доски ===")
            for k, fn in R.items(): rep(k, sim(C, fn, tp, sl, hold, side), tmid)
