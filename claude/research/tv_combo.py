#!/usr/bin/env python3
"""СОЧЕТАНИЯ: «горячая» монета против «спящей», место на доске + режим (03.10, владелец: «думай, как точнее определять, что пойдёт»).
К каждой монете на каждый день добавлено место на доске (0–1) по признакам: atr (размах дня), f7 (фандинг 7 дн), mom90, pos90 (цена к максимуму 90 дн), sq (ширина Боллинджера к своему минимуму 90 дн),
oi30 (интерес за 30 дн), lq (вынесено за 7 дн к интересу), up90 (цена к минимуму 90 дн). Плюс режим доски из tv_regime.py и «был ли у монеты ход ×2 по закрытиям за прошлые 120 дн» (ran120).
Сделка как в tv_rules.py. Печатает одну строку на отпечаток: число, $/сделку всего, первая и вторая половина (доля целей и $/сделку), месяцев в плюсе. Только запись."""
import sys, math
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from tv_rules import load, roll, ch, sim
from tv_regime import board
def prep():
    C = load(); board(C)
    for F in C.values():
        c = F["c"]; n = F["n"]
        with np.errstate(all="ignore"):
            F["x_atr"] = F["atr"]; F["x_f7"] = F["f7"]; F["x_pos90"] = c / F["hi90"]; F["x_up90"] = c / F["lo90"]; F["x_sq"] = F["bbw"] / F["bbmin"]
            F["x_mom90"] = np.array([ch(c, i, 90) for i in range(n)]); F["x_mom30"] = np.array([ch(c, i, 30) for i in range(n)]); F["x_oi30"] = np.array([ch(F["oi"], i, 30) for i in range(n)])
            F["x_lq"] = (F["ls7"] + F["ll7"]) / F["oi"]; F["x_flat30"] = F["hi30"] / F["lo30"]
        hi120 = roll(c, 120, np.max); lo_run = np.zeros(n)
        # ran120: за прошлые 120 дн был рост закрытия ×2 от минимума закрытия к более позднему максимуму в пределах 30 дн
        ran = np.zeros(n)
        mn30 = roll(c, 30, np.min)
        hit = np.array([1.0 if (i >= 30 and c[i] >= 2 * mn30[i]) else 0.0 for i in range(n)])
        ran = roll(hit, 120, np.max); F["ran120"] = np.nan_to_num(ran); F["hot_now"] = hit
        F["ath"] = np.maximum.accumulate(F["h"]); F["dead"] = c / F["ath"]
    keys = [k for k in next(iter(C.values())) if k.startswith("x_")]
    byd = defaultdict(list)
    for sym, F in C.items():
        for k in keys: F["r" + k[1:]] = np.full(F["n"], np.nan)
        for i in range(180, F["n"]): byd[int(F["t"][i])].append((sym, i))
    for t, lst in byd.items():
        if len(lst) < 50: continue
        for k in keys:
            vals = np.array([C[s][k][i] for s, i in lst], float); ok = ~np.isnan(vals)
            if ok.sum() < 50: continue
            order = np.argsort(np.argsort(vals[ok])) / max(1, ok.sum() - 1); j = 0
            for (s, i), o in zip(lst, ok):
                if o: C[s]["r" + k[1:]][i] = order[j]; j += 1
    return C
def line(name, tr, tmid):
    if len(tr) < 30: print(f"  {name[:86]:86s} мало сделок ({len(tr)})"); return
    a = [x for x in tr if x[0] < tmid]; b = [x for x in tr if x[0] >= tmid]; bym = defaultdict(float)
    for x in tr: bym[datetime.fromtimestamp(x[0], timezone.utc).strftime("%y-%m")] += x[2]
    f = lambda g: f"{sum(1 for x in g if x[3]) / max(1, len(g)) * 100:3.0f}% {sum(x[2] for x in g) / max(1, len(g)):+6.1f}$ n={len(g)}"
    print(f"  {name[:86]:86s} n={len(tr):5d} {sum(x[2] for x in tr) / len(tr):+6.1f}$ | 1: {f(a)} | 2: {f(b)} | мес+ {sum(1 for v in bym.values() if v > 0)}/{len(bym)}")
SIG = {
 "база: любой день": lambda F, i: True,
 "горячая: размах в верхней пятой доски": lambda F, i: F["r_atr"][i] >= .8,
 "горячая + фандинг в верхней пятой (лонги платят)": lambda F, i: F["r_atr"][i] >= .8 and F["r_f7"][i] >= .8,
 "горячая + фандинг в нижней пятой (шорты платят)": lambda F, i: F["r_atr"][i] >= .8 and F["r_f7"][i] <= .2,
 "горячая + цена в верхней пятой к максимуму 90 дн": lambda F, i: F["r_atr"][i] >= .8 and F["r_pos90"][i] >= .8,
 "горячая + был ход ×2 за 120 дн + сейчас откат ≥ 30% от максимума 30 дн": lambda F, i: F["r_atr"][i] >= .8 and F["ran120"][i] > 0 and F["c"][i] <= .7 * F["hi30"][i],
 "был ход ×2 за 120 дн (любой день)": lambda F, i: F["ran120"][i] > 0,
 "не было хода ×2 за 120 дн": lambda F, i: F["ran120"][i] == 0,
 "цена у максимума 90 дн (верхняя десятая доски)": lambda F, i: F["r_pos90"][i] >= .9,
 "цена у максимума 90 дн + тихая (размах в нижней половине)": lambda F, i: F["r_pos90"][i] >= .9 and F["r_atr"][i] <= .5,
 "вынесено много к интересу (верхняя десятая)": lambda F, i: F["r_lq"][i] >= .9,
 "спящая: размах 30 дн ≤ 30% и цена ≤ 25% от исторического максимума": lambda F, i: F["x_flat30"][i] <= 1.30 and F["dead"][i] <= .25,
 "спящая + сжатие у минимума 90 дн": lambda F, i: F["x_flat30"][i] <= 1.30 and F["dead"][i] <= .25 and F["bbw"][i] <= 1.1 * F["bbmin"][i],
 "сжатие у минимума 90 дн": lambda F, i: F["bbw"][i] <= 1.1 * F["bbmin"][i],
 "сжатие + фандинг 7 дн ≥ 0": lambda F, i: F["bbw"][i] <= 1.1 * F["bbmin"][i] and F["f7"][i] >= 0,
 "сжатие + фандинг 7 дн < 0": lambda F, i: F["bbw"][i] <= 1.1 * F["bbmin"][i] and F["f7"][i] < 0,
 "сжатие + доска 7 дн > 0": lambda F, i: F["bbw"][i] <= 1.1 * F["bbmin"][i] and F["b7"][i] > 0,
 "сжатие + доска 7 дн ≤ 0": lambda F, i: F["bbw"][i] <= 1.1 * F["bbmin"][i] and F["b7"][i] <= 0,
 "сжатие + интерес 30 дн в верхней пятой": lambda F, i: F["bbw"][i] <= 1.1 * F["bbmin"][i] and F["r_oi30"][i] >= .8,
 "сжатие + закрытие выше максимума 14 дн (выход из сжатия вверх)": lambda F, i: F["bbw"][i - 1] <= 1.2 * F["bbmin"][i - 1] and F["c"][i] > F["hi14"][i - 1],
 "доска 7 дн > +5%": lambda F, i: F["b7"][i] > .05,
 "доска 7 дн > +5% + горячая": lambda F, i: F["b7"][i] > .05 and F["r_atr"][i] >= .8,
 "доска 7 дн > +5% + тихая (размах в нижней пятой)": lambda F, i: F["b7"][i] > .05 and F["r_atr"][i] <= .2,
 "доска 7 дн > +5% + монета сильнее доски за 30 дн (верхняя пятая)": lambda F, i: F["b7"][i] > .05 and F["r_mom30"][i] >= .8,
 "доска 7 дн > +5% + монета слабее доски за 30 дн (нижняя пятая)": lambda F, i: F["b7"][i] > .05 and F["r_mom30"][i] <= .2,
}
if __name__ == "__main__":
    C = prep(); ts = sorted(int(t) for F in C.values() for t in F["t"][180:]); tmid = ts[len(ts) // 2]
    print(f"монет {len(C)} · середина {datetime.fromtimestamp(tmid, timezone.utc):%d.%m.%Y}")
    for tp, sl, hold in ((.20, .10, 14), (.50, .15, 21), (.10, .10, 7)):
        for side, nm in ((1, "ЛОНГ"), (-1, "ШОРТ")):
            if side == -1 and tp == .50: continue
            print(f"\n=== {nm} цель {tp:.0%} стоп {sl:.0%} срок {hold} дн ===")
            for k, fn in SIG.items(): line(k, sim(C, fn, tp, sl, hold, side), tmid)
