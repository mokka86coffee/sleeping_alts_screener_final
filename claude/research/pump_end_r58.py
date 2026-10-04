#!/usr/bin/env python3
"""R58 ПО ДАННЫМ: шорт «конец роста» ровно как в коде (03.10 21:20, владелец: «почему R54 и R57 не применяются к шорту „конец роста“?»).
Binance, часовые бары и ликвидации с графика TradingView (06.09–03.10). Сигнал как в боте: рекордный за сутки час выноса шортов (R61: ×2 при ровных выносах, +30 % если уже был
крупный; больше любого часа лонгов), минимумы 48 часовых свечей растут (первая треть против последней), максимум свечи выноса выше минимума за 48 ч на 60 %+.
Шорт по закрытию часа, цели нет, стоп 10 % без переноса, выход через 4 часа (и для сравнения 6, 12, 24). Разбивка: доска за 24 ч (выше +3 % — там R54 дал бы лонг) и ширина свечи выноса
(от 8 % — там R57 дал бы пропуск). Только запись."""
import json, glob, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import numpy as np
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT)); D = Path(__file__).parent / "tvd"; L = timezone(timedelta(hours=3))
import fast_tier as ft
own = ft._own_mm(); acc = defaultdict(list); coins = {}
for f in sorted(glob.glob(str(D / "*_60.json"))):
    d = json.load(open(f))
    if not isinstance(d, dict): continue
    b = d["bars"]
    for i in range(24, len(b)):
        if b[i - 24][4] > 0: acc[b[i][0]].append(b[i][4] / b[i - 24][4] - 1)
    sym = d["sym"].split(":")[1].replace(".P", "")
    if sym in own or len(b) < 200: continue
    try:
        if len(json.load(open(D / Path(f).name.replace("_60.json", "_1D.json")))["bars"]) < 180: continue
    except Exception: continue
    coins[sym] = d
B24 = {t: float(np.median(a)) * 100 for t, a in acc.items() if len(a) >= 100}
def short_time(e, bars, hold, sl=.10):
    for (t, o, h, l, c, v) in bars[:hold]:
        if h >= e * (1 + sl): return -sl, "стоп"
    return (1 - bars[min(hold, len(bars)) - 1][4] / e, "срок") if len(bars) >= hold else (None, None)
ev = []
for sym, d in coins.items():
    b = d["bars"]; LS, LL = {}, {}
    for x in d.get("liq") or []:
        if x[1]: LL[x[0]] = abs(x[1])
        if len(x) > 2 and x[2]: LS[x[0]] = abs(x[2])
    for i in range(49, len(b) - 25):
        t = b[i][0]; win = LS.get(t, 0.0)
        if win <= 0: continue
        prev = [v for h, v in LS.items() if t - 86400 <= h < t]
        if not prev or win <= max((v for h, v in LL.items() if t - 86400 <= h <= t), default=0.0): continue
        mx = max(prev); mean = sum(prev) / len(prev)
        if win < (1.3 * mx if (len(prev) > 1 and mx >= 2 * mean) else 2 * mx): continue
        l48 = [x[3] for x in b[i - 48:i]]; f3, l3 = l48[:16], l48[-16:]
        if not (min(l3) > min(f3) and sum(l3) > sum(f3)): continue
        rise = (b[i][2] / min(l48) - 1) * 100
        if rise < 40: continue
        e = b[i][4]; r = {h: short_time(e, b[i + 1:], h) for h in (4, 6, 12, 24)}
        ev.append(dict(sym=sym, t=t, rise=rise, rng=(b[i][2] / b[i][3] - 1) * 100, b24=B24.get(t), r=r, lo4=min(x[3] for x in b[i + 1:i + 5]) / e - 1, hi4=max(x[2] for x in b[i + 1:i + 5]) / e - 1))
P = [x for x in ev if x["rise"] >= 60]; G = [x for x in ev if 40 <= x["rise"] < 60]
print(f"сигналов «рост и памп» (от 60 %): {len(P)} у {len({x['sym'] for x in P})} монет · «просто рост» (40–60 %): {len(G)} · {datetime.fromtimestamp(min(x['t'] for x in ev), L):%d.%m}–{datetime.fromtimestamp(max(x['t'] for x in ev), L):%d.%m}")
def rep(nm, g):
    if len(g) < 6: print(f"  {nm:46s} мало ({len(g)})"); return
    s = f"  {nm:46s} n={len(g):3d}"
    for h in (4, 6, 12, 24):
        v = [x["r"][h][0] for x in g if x["r"][h][0] is not None]
        if v: s += f" · {h} ч: {(sum(v) * 1000 - len(v)) / len(v):+6.1f}$ (в плюс {sum(1 for q in v if q > 0) * 100 // len(v)}%, стопов {sum(1 for x in g if x['r'][h][1] == 'стоп') * 100 // len(g)}%)"
    print(s)
print("\nШОРТ «КОНЕЦ РОСТА» (рост от 60 %), стоп 10 %, выход по времени — $ на сделку:")
rep("все", P)
rep("доска 24 ч выше +3 % (R54 дал бы лонг)", [x for x in P if x["b24"] is not None and x["b24"] > 3]); rep("доска 24 ч +1…+3 %", [x for x in P if x["b24"] is not None and 1 < x["b24"] <= 3]); rep("доска 24 ч ниже +1 %", [x for x in P if x["b24"] is not None and x["b24"] <= 1])
rep("свеча выноса ≥ 8 % (R57 дал бы пропуск)", [x for x in P if x["rng"] >= 8]); rep("свеча выноса < 8 %", [x for x in P if x["rng"] < 8])
rep("рост 60–100 %", [x for x in P if x["rise"] < 100]); rep("рост от 100 %", [x for x in P if x["rise"] >= 100])
print("\n«ПРОСТО РОСТ» 40–60 % (шорт не берём) — что дал бы тот же шорт:"); rep("все", G)
print(f"\nв первые 4 часа после сквиза (рост от 60 %): худший ход против шорта — медиана {np.median([x['hi4'] for x in P]) * 100:+.1f}%, лучший ход в пользу — медиана {np.median([x['lo4'] for x in P]) * 100:+.1f}%")
by = defaultdict(list)
for x in P: by[x["sym"]].append(x["r"][4][0] or 0)
print("по монетам (4 ч):", ", ".join(f"{s} {len(v)} сд. {sum(v) * 1000 - len(v):+.0f}$" for s, v in sorted(by.items(), key=lambda kv: -len(kv[1]))[:14]))
print("\nТОТ ЖЕ ШОРТ ПРИ ДРУГОМ СТОПЕ (рост от 60 %), $ на сделку · доля стопов:")
def st2(e, bars, hold, sl):
    for (t, o, h, l, c, v) in bars[:hold]:
        if h >= e * (1 + sl): return -sl
    return 1 - bars[hold - 1][4] / e if len(bars) >= hold else None
for sl in (.10, .15, .20, .30, 9.9):
    s = f"  стоп {'нет' if sl > 9 else f'{sl:.0%}'}:"
    for h in (4, 6, 12, 24):
        v = []
        for x in P:
            b = coins[x["sym"]]["bars"]; i = next(j for j, y in enumerate(b) if y[0] == x["t"]); r = st2(b[i][4], b[i + 1:], h, sl)
            if r is not None: v.append(r)
        s += f" · {h} ч: {(sum(v) * 1000 - len(v)) / len(v):+6.1f}$ (стопов {sum(1 for q in v if abs(q + sl) < 1e-9) * 100 // len(v)}%)"
    print(s)
print("\nСТОП 10 %, ДРУГОЙ МОМЕНТ ВХОДА (03.10 21:35, владелец: «стоп 30 % это пиздец») — рост от 60 %, $ на сделку:")
def idx(x):
    b = coins[x["sym"]]["bars"]; return b, next(j for j, y in enumerate(b) if y[0] == x["t"])
def run(entry_fn, hold, sl=.10):
    v = []; n_no = 0
    for x in P:
        b, i = idx(x); j = entry_fn(b, i)
        if j is None or j + hold >= len(b): n_no += 1; continue
        r = st2(b[j][4], b[j + 1:], hold, sl)
        if r is not None: v.append(r)
    return v, n_no
def show(nm, fn):
    s = f"  {nm:58s}"
    for h in (4, 12, 24):
        v, no = run(fn, h)
        s += f" · {h} ч: " + (f"{(sum(v) * 1000 - len(v)) / len(v):+6.1f}$ (n={len(v)}, в плюс {sum(1 for q in v if q > 0) * 100 // len(v)}%, стопов {sum(1 for q in v if abs(q + .10) < 1e-9) * 100 // len(v)}%)" if len(v) >= 6 else f"мало ({len(v)})")
    print(s)
show("вход сразу, по закрытию часа сквиза (как в коде)", lambda b, i: i)
for k in (2, 4, 6, 12): show(f"вход через {k} ч после сквиза", lambda b, i, k=k: i + k)
def below_low(b, i, win=24):
    for j in range(i + 1, min(len(b), i + 1 + win)):
        if b[j][4] < b[i][3]: return j
    return None
show("вход, когда час закрылся ниже минимума свечи сквиза (до 24 ч)", below_low)
def below_open(b, i, win=24):
    for j in range(i + 1, min(len(b), i + 1 + win)):
        if b[j][4] < b[i][1]: return j
    return None
show("вход, когда час закрылся ниже открытия свечи сквиза (до 24 ч)", below_open)
def red_after_high(b, i, win=24):
    hi = b[i][2]
    for j in range(i + 1, min(len(b), i + 1 + win)):
        hi = max(hi, b[j][2])
        if b[j][4] < b[j][1] and b[j][4] <= hi * .93: return j          # откат от вершины на 7 % и час закрылся вниз
    return None
show("вход после отката на 7 % от вершины (час закрылся вниз)", red_after_high)
# повторный вход владельца: стоп 10 %, после стопа — вход на следующем рекордном выносе шортов (до 48 ч), выход по времени
print("\nПОВТОРНЫЙ ВХОД ПОСЛЕ СТОПА (стоп 10 %, новый вход на следующем рекордном часе выноса шортов в пределах 48 ч), итог цепочки на один сигнал:")
def chain(x, hold):
    b, i = idx(x); d = coins[x["sym"]]; LS = {y[0]: abs(y[2]) for y in d.get("liq") or [] if len(y) > 2 and y[2]}
    tot = 0.0; n = 0; j = i; end = min(len(b) - hold - 1, i + 48)
    while j is not None and j <= end and n < 4:
        e = b[j][4]; n += 1; stopped = None
        for q in range(j + 1, j + 1 + hold):
            if b[q][2] >= e * 1.10: stopped = q; break
        if stopped is None: tot += 1 - b[j + hold][4] / e - .001; return tot, n
        tot += -.10 - .001; nxt = None
        for q in range(stopped, end + 1):
            t = b[q][0]; win = LS.get(t, 0.0); prev = [v for h, v in LS.items() if t - 86400 <= h < t]
            if win > 0 and prev:
                mx = max(prev); mean = sum(prev) / len(prev)
                if win >= (1.3 * mx if (len(prev) > 1 and mx >= 2 * mean) else 2 * mx): nxt = q; break
        j = nxt
    return tot, n
for h in (4, 6, 12, 24):
    R = [chain(x, h) for x in P]; print(f"  выход через {h:2d} ч: {sum(r[0] for r in R) * 1000 / len(R):+6.1f}$ на сигнал · входов на сигнал в среднем {np.mean([r[1] for r in R]):.2f} · сигналов в плюс {sum(1 for r in R if r[0] > 0) * 100 // len(R)}%")
print("\nВХОД ЛИМИТКОЙ У ВЕРХА СВЕЧИ СКВИЗА (03.10 21:45, владелец: «поставь брать цену практически на верхе свечи сквиза и всё»; «от чего зависит 4 часа… завтра будет 3, и бот будет всегда на низах шортить»)")
print("уровень = максимум свечи сквиза × (1 − d); вход по уровню, когда цена его коснулась в следующие 24 ч; стоп 10 % от входа; выход по времени:")
def lim(d, hold, sl=.10, wait=24):
    v = []; fill = 0; imm = 0
    for x in P:
        b, i = idx(x); lvl = b[i][2] * (1 - d); j = None
        if b[i][4] >= lvl: j = i; e = b[i][4]; imm += 1                     # час закрылся уже у верха — вход по закрытию
        else:
            for q in range(i + 1, min(len(b), i + 1 + wait)):
                if b[q][2] >= lvl: j = q; e = lvl; break
        if j is None or j + hold >= len(b): continue
        fill += 1; r = None
        # в баре касания после входа цена могла уйти выше — стоп проверяем с этого же бара
        seq = b[j:j + 1 + hold] if e == lvl and j != i else b[j + 1:j + 1 + hold]
        for (t, o, h, l, c, vv) in seq:
            if h >= e * (1 + sl): r = -sl; break
        if r is None: r = 1 - b[j + hold][4] / e
        v.append(r)
    return v, fill, imm
for d in (0.0, .01, .02, .03, .05):
    s = f"  на {d * 100:.0f}% ниже максимума:"
    for h in (4, 12, 24):
        v, fill, imm = lim(d, h)
        s += f" · {h} ч: {(sum(v) * 1000 - len(v)) / max(1, len(v)):+6.1f}$ (в плюс {sum(1 for q in v if q > 0) * 100 // max(1, len(v))}%, стопов {sum(1 for q in v if abs(q + .10) < 1e-9) * 100 // max(1, len(v))}%)"
    print(s + f" · вошли в {fill} из {len(P)} (сразу по закрытию {imm})")
print("\nВЫХОД ПО СЛОВАМ ВЛАДЕЛЬЦА 03.10 21:50: «выход не через 4 часа, а через 16; через 6 часов стоп в твх или закрытие, если цена выше твх» — стоп 10 % первые 6 ч:")
def own_exit(b, j, e, same_bar, be_h=6, hold=16, sl=.10):
    """j — бар входа; same_bar — вход внутри бара j по лимитке (стоп проверяем с этого же бара). → (результат, чем вышел)"""
    seq = b[j:j + hold + 1] if same_bar else b[j + 1:j + 1 + hold]
    if len(seq) < hold: return None, None
    be = False
    for n, (t, o, h, l, c, vv) in enumerate(seq, 1):
        if h >= (e if be else e * (1 + sl)): return (0.0 if be else -sl), ("безубыток" if be else "стоп")
        if n == be_h and not be:
            if c > e: return 1 - c / e, "6 ч: цена выше входа — закрытие"
            be = True
    return 1 - seq[hold - 1][4] / e, "срок 16 ч"
def run_own(d=None):
    R = []
    for x in P:
        b, i = idx(x)
        if d is None: j, e, same = i, b[i][4], False
        else:
            lvl = b[i][2] * (1 - d); j = None
            if b[i][4] >= lvl: j, e, same = i, b[i][4], False
            else:
                for q in range(i + 1, min(len(b), i + 25)):
                    if b[q][2] >= lvl: j, e, same = q, lvl, True; break
            if j is None: continue
        r, how = own_exit(b, j, e, same)
        if r is not None: R.append((r, how, x["sym"]))
    return R
for nm, d in (("вход сразу по закрытию часа сквиза", None), ("вход лимиткой на максимуме свечи сквиза", 0.0), ("вход лимиткой на 1 % ниже максимума", .01), ("вход лимиткой на 3 % ниже максимума", .03)):
    R = run_own(d); n = len(R); how = defaultdict(list)
    for r, h, _ in R: how[h].append(r)
    print(f"  {nm:42s} сделок {n} из {len(P)} · {(sum(r for r, _, _ in R) * 1000 - n) / n:+6.1f}$ на сделку · в плюс {sum(1 for r, _, _ in R if r > 0) * 100 // n}% · " + " · ".join(f"{k}: {len(v)} ({sum(v) * 1000 / len(v):+.0f}$)" for k, v in sorted(how.items(), key=lambda kv: -len(kv[1]))))
print("\nТО ЖЕ + «если цена уже сходила на 5 % и стоп уже в твх — ничего не делать» (перенос стопа в точку входа после 5 % действует с самого входа):")
def own_exit2(b, j, e, same_bar, be_h=6, hold=16, sl=.10, be_at=.05):
    seq = b[j:j + hold + 1] if same_bar else b[j + 1:j + 1 + hold]
    if len(seq) < hold: return None, None
    be = False
    for n, (t, o, h, l, c, vv) in enumerate(seq, 1):
        if h >= (e if be else e * (1 + sl)): return (0.0 if be else -sl), ("безубыток" if be else "стоп")
        if not be and l <= e * (1 - be_at): be = True
        if n == be_h and not be:
            if c > e: return 1 - c / e, "6 ч: цена выше входа — закрытие"
            be = True
    return 1 - seq[hold - 1][4] / e, "срок 16 ч"
def run_own2(d=None):
    R = []
    for x in P:
        b, i = idx(x)
        if d is None: j, e, same = i, b[i][4], False
        else:
            lvl = b[i][2] * (1 - d); j = None
            if b[i][4] >= lvl: j, e, same = i, b[i][4], False
            else:
                for q in range(i + 1, min(len(b), i + 25)):
                    if b[q][2] >= lvl: j, e, same = q, lvl, True; break
            if j is None: continue
        r, how = own_exit2(b, j, e, same)
        if r is not None: R.append((r, how, x["t"]))
    return R
for nm, d in (("вход сразу по закрытию часа сквиза", None), ("вход лимиткой на максимуме свечи сквиза", 0.0), ("вход лимиткой на 1 % ниже максимума", .01)):
    R = run_own2(d); n = len(R); how = defaultdict(list); tm = sorted(t for _, _, t in R)[n // 2]
    for r, h, _ in R: how[h].append(r)
    u = lambda q: (sum(r for r, _, _ in q) * 1000 - len(q)) / max(1, len(q))
    print(f"  {nm:42s} сделок {n} из {len(P)} · {u(R):+6.1f}$ на сделку (половины месяца {u([z for z in R if z[2] < tm]):+.1f} / {u([z for z in R if z[2] >= tm]):+.1f}) · в плюс {sum(1 for r, _, _ in R if r > 0) * 100 // n}% · " + " · ".join(f"{k}: {len(v)} ({sum(v) * 1000 / len(v):+.0f}$)" for k, v in sorted(how.items(), key=lambda kv: -len(kv[1]))))
