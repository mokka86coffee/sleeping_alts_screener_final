#!/usr/bin/env python3
"""РАЗВОРОТ ДОСКИ (03.10 17:40, владелец: «главное разберём: мы открываем лонги на растущей доске, и доска начинает падать, или открываем шорты, и доска начинает расти»).
Доска = медиана хода закрытия всех перпов Binance (данные TradingView tvd/*_240.json — 107 дней, или *_60.json — 27 дней).
На каждый бар: ход доски за прошлые 24 ч / 6 ч / 7 дн, доля монет в плюсе, сумма ликвидаций лонгов и шортов по всей доске, медианный фандинг, медианный ход интереса.
Вопросы: 1) что делает доска в следующие 6/24 ч в зависимости от того, что она сделала за прошлые 24 ч (продолжение или откат); 2) сколько длится режим; 3) что заранее отличает разворот.
Только запись.   .venv/bin/python claude/research/tv_board_turn.py [240|60]"""
import json, glob, sys, math
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import numpy as np
D = Path(__file__).parent / "tvd"; TF = sys.argv[1] if len(sys.argv) > 1 else "240"; H = 6 if TF == "240" else 24; L = timezone(timedelta(hours=3))
acc = defaultdict(lambda: defaultdict(list)); liqL = defaultdict(float); liqS = defaultdict(float)
for f in glob.glob(str(D / f"*_{TF}.json")):
    d = json.load(open(f)); b = d["bars"]
    if len(b) < 9 * H: continue
    c = [x[4] for x in b]; t = [x[0] for x in b]; n = len(b)
    fu = {x[0]: x[1] for x in d.get("fund") or [] if x[1] is not None}; oi = {x[0]: x[1] for x in d.get("oi") or [] if x[1] is not None}
    for x in d.get("liq") or []:
        if x[1]: liqL[x[0]] += abs(x[1])
        if len(x) > 2 and x[2]: liqS[x[0]] += abs(x[2])
    for i in range(7 * H, n):
        a = acc[t[i]]
        for nm, k in (("b24", H), ("b6", max(1, H // 4)), ("b7d", 7 * H), ("b72", 3 * H)):
            if c[i - k] > 0: a[nm].append(c[i] / c[i - k] - 1)
        for nm, k in (("f6", max(1, H // 4)), ("f24", H), ("f72", 3 * H)):
            if i + k < n and c[i] > 0: a[nm].append(c[i + k] / c[i] - 1)
        if t[i] in fu: a["fund"].append(fu[t[i]])
        if t[i] in oi and t[i - H] in oi and oi[t[i - H]] > 0: a["oi24"].append(oi[t[i]] / oi[t[i - H]] - 1)
ts = sorted(t for t, a in acc.items() if len(a["b24"]) >= 200); R = []
for t in ts:
    a = acc[t]; r = dict(t=t, up=sum(1 for x in a["b24"] if x > 0) / len(a["b24"]) * 100, lL=liqL.get(t, 0.0), lS=liqS.get(t, 0.0))
    for k in ("b24", "b6", "b7d", "b72", "f6", "f24", "f72", "fund", "oi24"): r[k] = float(np.median(a[k])) * (100 if k != "fund" else 1) if len(a[k]) >= 100 else float("nan")
    R.append(r)
n = len(R); print(f"таймфрейм {TF} · баров {n} · {datetime.fromtimestamp(ts[0], L):%d.%m}–{datetime.fromtimestamp(ts[-1], L):%d.%m}")
# рекорд ликвидаций по доске: к максимуму прошлых 7 дней
for i, r in enumerate(R):
    w = R[max(0, i - 7 * H):i]
    r["lLx"] = r["lL"] / max(1e-9, max((x["lL"] for x in w), default=0)) if w else float("nan"); r["lSx"] = r["lS"] / max(1e-9, max((x["lS"] for x in w), default=0)) if w else float("nan")
    w24 = R[max(0, i - H + 1):i + 1]; r["lL24"] = sum(x["lL"] for x in w24); r["lS24"] = sum(x["lS"] for x in w24); r["lshare"] = r["lS24"] / (r["lS24"] + r["lL24"]) if r["lS24"] + r["lL24"] > 0 else float("nan")
ok = lambda r, k: not math.isnan(r[k])
def rep(nm, g, show=("f6", "f24", "f72")):
    g = [r for r in g if ok(r, "f24")]
    if len(g) < 8: print(f"  {nm:56s} мало ({len(g)})"); return
    s = f"  {nm:56s} n={len(g):4d}"
    for k in show:
        v = [r[k] for r in g if ok(r, k)]
        if v: s += f" · {k[1:]} ч: {np.mean(v):+.2f}% (вверх {sum(1 for x in v if x > 0) * 100 // len(v)}%)"
    print(s)
print("\n1. ЧТО ДОСКА ДЕЛАЕТ ДАЛЬШЕ в зависимости от хода за прошлые 24 ч (средний ход доски за следующие 6 / 24 / 72 ч, доля случаев вверх):")
rep("все бары", R)
for lo, hi in ((-99, -5), (-5, -3), (-3, -1), (-1, 1), (1, 3), (3, 5), (5, 99)): rep(f"доска 24 ч {lo:+d}…{hi:+d}%", [r for r in R if lo <= r["b24"] < hi])
print("\n2. СКОЛЬКО ДЛИТСЯ РЕЖИМ (подряд баров, где доска 24 ч выше +1 % / ниже −1 %), в часах:")
for nm, fn in (("растёт (> +1%)", lambda r: r["b24"] > 1), ("падает (< −1%)", lambda r: r["b24"] < -1)):
    runs = []; cur = 0
    for r in R:
        if fn(r): cur += 1
        elif cur: runs.append(cur); cur = 0
    hrs = [x * (24 / H) for x in runs]
    if hrs: print(f"  {nm}: эпизодов {len(hrs)} · медиана {np.median(hrs):.0f} ч · четверть короче {np.percentile(hrs, 25):.0f} ч · четверть длиннее {np.percentile(hrs, 75):.0f} ч · самый длинный {max(hrs):.0f} ч")
print("\n3. ВОЗРАСТ РЕЖИМА: сколько уже длится рост/падение на момент входа → что дальше")
age = 0; sgn = 0
for r in R:
    s = 1 if r["b24"] > 1 else (-1 if r["b24"] < -1 else 0)
    age = age + 1 if s == sgn and s != 0 else (1 if s != 0 else 0); sgn = s; r["age"] = age * (24 / H); r["sg"] = s
for s, nm in ((1, "доска растёт"), (-1, "доска падает")):
    for lo, hi in ((0, 12), (12, 24), (24, 48), (48, 96), (96, 9999)): rep(f"{nm}, режим длится {lo}–{hi} ч", [r for r in R if r["sg"] == s and lo < r["age"] <= hi])
print("\n4. КОГДА ДОСКА ЗА 24 Ч ВЫРОСЛА (> +1%) — что отличает продолжение от разворота:")
G = [r for r in R if r["b24"] > 1]
rep("все", G)
rep("последние 6 ч тоже вверх", [r for r in G if r["b6"] > 0]); rep("последние 6 ч уже вниз", [r for r in G if r["b6"] <= 0])
rep("в плюсе > 80% монет", [r for r in G if r["up"] > 80]); rep("в плюсе 60–80%", [r for r in G if 60 < r["up"] <= 80]); rep("в плюсе ≤ 60%", [r for r in G if r["up"] <= 60])
rep("доска 7 дн > +5%", [r for r in G if r["b7d"] > 5]); rep("доска 7 дн 0…+5%", [r for r in G if 0 < r["b7d"] <= 5]); rep("доска 7 дн < 0 (отскок в падении)", [r for r in G if r["b7d"] <= 0])
fm = np.nanmedian([r["fund"] for r in R]); rep(f"фандинг доски выше обычного (> {fm:.4f})", [r for r in G if r["fund"] > fm]); rep("фандинг доски ниже обычного", [r for r in G if r["fund"] <= fm])
rep("за 24 ч выносили в основном шорты (доля > 60%)", [r for r in G if ok(r, "lshare") and r["lshare"] > .6]); rep("выносили в основном лонги (доля шортов < 40%)", [r for r in G if ok(r, "lshare") and r["lshare"] < .4])
rep("рекордный вынос шортов по доске (≥ макс. 7 дн)", [r for r in G if r["lSx"] >= 1]); rep("интерес доски за 24 ч вырос > +3%", [r for r in G if ok(r, "oi24") and r["oi24"] > 3]); rep("интерес доски за 24 ч упал", [r for r in G if ok(r, "oi24") and r["oi24"] < 0])
print("\n5. КОГДА ДОСКА ЗА 24 Ч УПАЛА (< −1%):")
G = [r for r in R if r["b24"] < -1]
rep("все", G)
rep("последние 6 ч тоже вниз", [r for r in G if r["b6"] < 0]); rep("последние 6 ч уже вверх", [r for r in G if r["b6"] >= 0])
rep("в плюсе < 20% монет", [r for r in G if r["up"] < 20]); rep("в плюсе 20–40%", [r for r in G if 20 <= r["up"] < 40]); rep("в плюсе ≥ 40%", [r for r in G if r["up"] >= 40])
rep("доска 7 дн < −5%", [r for r in G if r["b7d"] < -5]); rep("доска 7 дн −5…0%", [r for r in G if -5 <= r["b7d"] < 0]); rep("доска 7 дн > 0 (откат в росте)", [r for r in G if r["b7d"] >= 0])
rep("фандинг доски выше обычного", [r for r in G if r["fund"] > fm]); rep("фандинг доски ниже обычного", [r for r in G if r["fund"] <= fm])
rep("за 24 ч выносили в основном лонги (доля шортов < 40%)", [r for r in G if ok(r, "lshare") and r["lshare"] < .4]); rep("рекордный вынос лонгов по доске (≥ макс. 7 дн)", [r for r in G if r["lLx"] >= 1])
rep("интерес доски за 24 ч упал > 3%", [r for r in G if ok(r, "oi24") and r["oi24"] < -3]); rep("интерес доски за 24 ч вырос", [r for r in G if ok(r, "oi24") and r["oi24"] > 0])
print("\n6. РЕКОРДНЫЙ ВЫНОС ПО ВСЕЙ ДОСКЕ (сумма ликвидаций всех монет за бар ≥ максимума прошлых 7 дней), в любом режиме:")
rep("рекорд выноса ЛОНГОВ", [r for r in R if r["lLx"] >= 1]); rep("рекорд выноса ЛОНГОВ ×2 и больше", [r for r in R if r["lLx"] >= 2]); rep("рекорд выноса ШОРТОВ", [r for r in R if r["lSx"] >= 1]); rep("рекорд выноса ШОРТОВ ×2 и больше", [r for r in R if r["lSx"] >= 2])
x = np.array([r["b24"] for r in R if ok(r, "f24")]); y = np.array([r["f24"] for r in R if ok(r, "f24")]); print(f"\nсвязь «прошлые 24 ч → следующие 24 ч»: корреляция {np.corrcoef(x, y)[0, 1]:+.2f}")
json.dump(R, open(D / f"_bt{TF}.json", "w"))
