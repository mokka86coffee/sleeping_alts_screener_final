#!/usr/bin/env python3
"""ПРОВЕРКА ОТПЕЧАТКОВ СДЕЛКОЙ (03.10, владелец: «думай, как точнее определять, что пойдёт»; «ты проверь сначала сам свой анализ»).
Данные TradingView (tvd/*_1D.json). Сделка: вход по закрытию дня сигнала, 1000 $, комиссия 1 $ на круг; цель/стоп в долях; если в один день задеты оба — считаем стоп;
срок hold дней, потом выход по закрытию. По монете одна сделка за раз. Монета ≥ 180 дней истории (R48). Вывод: число, доля целей, $ всего и на сделку, отдельно первая и вторая половина периода и по месяцам.
Отпечатки заданы из механизма (кто зажат), а не подобраны по сетке. Только запись."""
import json, glob, math, sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import numpy as np
D = Path(__file__).parent / "tvd"
def roll(a, n, fn):
    out = np.full(len(a), np.nan)
    for i in range(n - 1, len(a)):
        w = a[i - n + 1:i + 1]
        if not np.all(np.isnan(w)): out[i] = fn(w)
    return out
def load():
    C = {}
    for f in sorted(glob.glob(str(D / "*_1D.json"))):
        d = json.load(open(f)); b = d["bars"]
        if len(b) < 240: continue
        sym = d["sym"].split(":")[1].replace("USDT.P", ""); t = np.array([x[0] for x in b]); n = len(b)
        o, h, l, c, v = (np.array([x[j] for x in b], float) for j in (1, 2, 3, 4, 5))
        def ser(key, j):
            m = {x[0]: x[j] for x in d.get(key) or [] if len(x) > j and x[j] is not None}
            return np.array([m.get(x, np.nan) for x in t], float)
        oi = ser("oi", 1); fu = ser("fund", 1); lql = np.abs(ser("liq", 1)); lqs = np.abs(ser("liq", 2)); ko = ser("ko", 1); ks = ser("ko", 2)
        F = dict(t=t, o=o, h=h, l=l, c=c, v=v, oi=oi, fu=fu, lql=lql, lqs=lqs, ko=ko, ks=ks, n=n)
        for k in (5, 7, 14, 30, 90):
            F[f"hi{k}"] = roll(h, k, np.max); F[f"lo{k}"] = roll(l, k, np.min)
        tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1)))); tr[0] = h[0] - l[0]
        F["atr"] = roll(tr, 14, np.mean) / c
        F["v20"] = roll(v, 20, np.median); F["f7"] = roll(fu, 7, np.nanmean); F["fneg7"] = roll((fu < 0).astype(float), 7, np.mean); F["f3"] = roll(fu, 3, np.nanmean)
        F["ls7"] = roll(np.nan_to_num(lqs), 7, np.sum); F["ll7"] = roll(np.nan_to_num(lql), 7, np.sum)
        F["lqs30"] = roll(np.nan_to_num(lqs), 30, np.max); F["lql30"] = roll(np.nan_to_num(lql), 30, np.max)
        sma = roll(c, 20, np.mean); sd = roll(c, 20, np.std); F["bbw"] = sd / sma; F["bbmin"] = roll(F["bbw"], 90, np.nanmin)
        C[sym] = F
    return C
def ch(a, i, k):
    return a[i] / a[i - k] - 1 if i >= k and a[i - k] > 0 and not (math.isnan(a[i]) or math.isnan(a[i - k])) else float("nan")
def sim(C, sig, tp, sl, hold, side=1, tmid=None, show=0):
    tr = []
    for sym, F in C.items():
        i = 180; n = F["n"]
        while i < n - 1:
            try: ok = sig(F, i)
            except Exception: ok = False
            if not ok: i += 1; continue
            e = F["c"][i]; res = None; j = i
            for j in range(i + 1, min(n, i + 1 + hold)):
                up = F["h"][j] / e - 1; dn = F["l"][j] / e - 1
                if side == 1:
                    if dn <= -sl: res = -sl; break
                    if up >= tp: res = tp; break
                else:
                    if up >= sl: res = -sl; break
                    if dn <= -tp: res = tp; break
            if res is None:
                if j < i + hold and j == n - 1: i = n; continue   # ещё открыта — не считаем
                res = side * (F["c"][j] / e - 1)
            tr.append((int(F["t"][i]), sym, res * 1000 - 1, res >= tp - 1e-9)); i = j + 1
    return tr
def rep(name, tr, tmid):
    if not tr: print(f"{name}: нет сделок"); return
    s = sum(x[2] for x in tr); a = [x for x in tr if x[0] < tmid]; b = [x for x in tr if x[0] >= tmid]
    bym = defaultdict(float)
    for x in tr: bym[datetime.fromtimestamp(x[0], timezone.utc).strftime("%y-%m")] += x[2]
    pos = sum(1 for v in bym.values() if v > 0)
    f = lambda g: f"{len(g)} сд., цель {sum(1 for x in g if x[3]) / max(1, len(g)) * 100:.0f}%, {sum(x[2] for x in g):+.0f}$ ({sum(x[2] for x in g) / max(1, len(g)):+.1f}$/сд.)"
    print(f"{name}\n    всего {f(tr)} · 1-я половина {f(a)} · 2-я половина {f(b)} · месяцев в плюсе {pos} из {len(bym)} · монет {len({x[1] for x in tr})}")
    return s
SIG = {
 "0 база: любой день": lambda F, i: True,
 "A лестница (R47): рост ×1.25+ за 30 дн, цена ≥85% максимума, 5 дн размах ≤25%": lambda F, i: F["hi30"][i] / F["lo30"][i] >= 1.25 and F["c"][i] >= .85 * F["hi30"][i] and F["hi5"][i] / F["lo5"][i] - 1 <= .25 and np.argmax(F["h"][i - 29:i + 1]) > np.argmin(F["l"][i - 29:i + 1]),
 "A2 лестница крепкая: рост ×1.5+ за 30 дн, цена ≥85%, 5 дн ≤25%": lambda F, i: F["hi30"][i] / F["lo30"][i] >= 1.5 and F["c"][i] >= .85 * F["hi30"][i] and F["hi5"][i] / F["lo5"][i] - 1 <= .25 and np.argmax(F["h"][i - 29:i + 1]) > np.argmin(F["l"][i - 29:i + 1]),
 "B топливо шортов: фандинг 7 дн < 0, интерес 14 дн ≥ +15%, цена 14 дн не упала": lambda F, i: F["f7"][i] < 0 and ch(F["oi"], i, 14) >= .15 and ch(F["c"], i, 14) >= 0,
 "B2 топливо + полка: фандинг 7 дн < 0, интерес 14 дн ≥ +15%, размах 7 дн ≤ 20%": lambda F, i: F["f7"][i] < 0 and ch(F["oi"], i, 14) >= .15 and F["hi7"][i] / F["lo7"][i] - 1 <= .20,
 "B3 шорты платят все 7 дней": lambda F, i: F["fneg7"][i] >= .99,
 "C пробой 30 дн: закрытие выше максимума прошлых 30 дн, объём ≥ ×2": lambda F, i: F["c"][i] > F["hi30"][i - 1] and F["v"][i] >= 2 * F["v20"][i - 1],
 "C2 пробой 90 дн с объёмом ≥ ×2": lambda F, i: F["c"][i] > F["hi90"][i - 1] and F["v"][i] >= 2 * F["v20"][i - 1],
 "C3 пробой 30 дн из сжатия (размах 14 дн до ≤ 25%)": lambda F, i: F["c"][i] > F["hi30"][i - 1] and F["hi14"][i - 1] / F["lo14"][i - 1] - 1 <= .25,
 "D рекорд выноса шортов за 30 дн (день), цена день вверх": lambda F, i: F["lqs"][i] > 0 and F["lqs"][i] >= F["lqs30"][i] and F["c"][i] > F["o"][i],
 "E рекорд выноса лонгов за 30 дн (день)": lambda F, i: F["lql"][i] > 0 and F["lql"][i] >= F["lql30"][i],
 "F сжатие: ширина Боллинджера у минимума 90 дн (≤ ×1.1)": lambda F, i: F["bbw"][i] <= 1.1 * F["bbmin"][i],
 "G первый день объёма ×5 и свеча ≥ +15% (зажигание)": lambda F, i: F["v"][i] >= 5 * F["v20"][i - 1] and F["c"][i] / F["c"][i - 1] - 1 >= .15,
 "H интерес +30% за 7 дн при цене в полке ≤ 15%": lambda F, i: ch(F["oi"], i, 7) >= .30 and F["hi7"][i] / F["lo7"][i] - 1 <= .15,
 "I Klinger пересёк сигнал вверх, цена в нижней трети 90 дн": lambda F, i: F["ko"][i] > F["ks"][i] and F["ko"][i - 1] <= F["ks"][i - 1] and (F["c"][i] - F["lo90"][i]) / (F["hi90"][i] - F["lo90"][i]) <= .33,
}
if __name__ == "__main__":
    C = load(); ts = sorted(int(t) for F in C.values() for t in F["t"][180:]); tmid = ts[len(ts) // 2]
    print(f"монет {len(C)} · середина периода {datetime.fromtimestamp(tmid, timezone.utc):%d.%m.%Y}")
    for tp, sl, hold in ((.20, .10, 14), (.10, .10, 7)):
        print(f"\n=== ЛОНГ цель +{tp:.0%} стоп −{sl:.0%} срок {hold} дн ===")
        for k, fn in SIG.items(): rep(k, sim(C, fn, tp, sl, hold, 1), tmid)
        print(f"\n=== ШОРТ цель {tp:.0%} стоп {sl:.0%} срок {hold} дн ===")
        for k, fn in SIG.items(): rep(k, sim(C, fn, tp, sl, hold, -1), tmid)
