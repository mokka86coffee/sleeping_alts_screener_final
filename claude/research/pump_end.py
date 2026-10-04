#!/usr/bin/env python3
"""ПОСЛЕ СКВИЗА В КОНЦЕ РОСТА (03.10 19:10, владелец по ARK 30.09: «сквиз после окончания роста всегда большой и длительный и означает окончание движения, поэтому лонги тут после
выноса брать нельзя — именно их и будут выносить, причём достаточно долго»; «бот не должен выходить из шорта раньше чем через 2 часа»).
Binance, часовые бары и ликвидации с графика TradingView (06.09–03.10), свой ММ и монеты моложе 180 дней исключены.
Конец роста = рекордный за сутки час выноса ШОРТОВ на свече вверх после суток роста (минимумы росли); сила роста — ход закрытия за 24 ч до часа сквиза.
1) Что цена делает после такого сквиза через 2/6/12/24/48/72 ч и шорт от закрытия часа сквиза (10/10, безубыток после 5).
2) Лонг на рекордном выносе ЛОНГОВ (свеча вниз) в зависимости от того, сколько часов прошло после сквиза в конце роста. Только запись."""
import json, glob, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import numpy as np
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT)); D = Path(__file__).parent / "tvd"; L = timezone(timedelta(hours=3))
import fast_tier as ft
own = ft._own_mm()
def walk(side, e, bars, tp=.10, sl=.10, be_at=.05):
    be = False
    for (t, o, h, l, c, v) in bars:
        if side == 1:
            if l <= (e if be else e * (1 - sl)): return 0.0 if be else -sl
            if h >= e * (1 + tp): return tp
            if be_at and not be and h >= e * (1 + be_at): be = True
        else:
            if h >= (e if be else e * (1 + sl)): return 0.0 if be else -sl
            if l <= e * (1 - tp): return tp
            if be_at and not be and l <= e * (1 - be_at): be = True
    return side * (bars[-1][4] / e - 1) if bars else None
PE = []; LF = []
for f in sorted(glob.glob(str(D / "*_60.json"))):
    d = json.load(open(f))
    if not isinstance(d, dict): continue
    sym = d["sym"].split(":")[1].replace(".P", ""); b = d["bars"]
    if sym in own or len(b) < 200: continue
    try:
        if len(json.load(open(D / Path(f).name.replace("_60.json", "_1D.json")))["bars"]) < 180: continue
    except Exception: continue
    LLm, LSm = {}, {}
    for x in d.get("liq") or []:
        if x[1]: LLm[x[0]] = abs(x[1])
        if len(x) > 2 and x[2]: LSm[x[0]] = abs(x[2])
    idx = {x[0]: i for i, x in enumerate(b)}; lows = [x[3] for x in b]; ends = []
    def rec(A, O, t):
        win = A.get(t, 0.0)
        if win <= 0: return None
        prev = [v for h, v in A.items() if t - 86400 <= h < t]
        if not prev or win < 1.3 * max(prev) or win <= max((v for h, v in O.items() if t - 86400 <= h <= t), default=0.0): return None
        return win / max(prev)
    for i in range(25, len(b) - 2):
        t = b[i][0]; o_, h_, l_, c_ = b[i][1:5]
        lw = lows[i - 24:i]; a1, a2 = sum(lw[:8]) / 8, sum(lw[-8:]) / 8
        mv = 1 if (min(lw[-8:]) > min(lw[:8]) and a2 > a1) else (-1 if (max(lw[-8:]) < max(lw[:8]) and a2 < a1) else 0)
        xs = rec(LSm, LLm, t)
        if xs and c_ > o_ and mv == 1:
            run = c_ / b[i - 24][4] - 1; fw = {k: (b[i + k][4] / c_ - 1) if i + k < len(b) else None for k in (2, 6, 12, 24, 48, 72)}
            mn = {k: (min(x[3] for x in b[i + 1:i + 1 + k]) / c_ - 1) if i + k < len(b) else None for k in (24, 72)}
            PE.append(dict(sym=sym, t=t, run=run, x=xs, fw=fw, mn=mn, sh=walk(-1, c_, b[i + 1:i + 169]), rng=(h_ / l_ - 1) * 100)); ends.append((i, run))
        xl = rec(LLm, LSm, t)
        if xl and c_ < o_:
            last = [(i - j, r) for j, r in ends if 0 < i - j <= 72]
            hrs, run = (min(last, key=lambda z: z[0]) if last else (None, None))
            r = walk(1, c_, b[i + 1:i + 169])
            if r is not None: LF.append(dict(sym=sym, t=t, hrs=hrs, run=run, res=r, rs=walk(-1, c_, b[i + 1:i + 169]), mv=mv, rng=(h_ / l_ - 1) * 100))
print(f"сквизов в конце роста: {len(PE)} · выносов лонгов на свече вниз: {len(LF)} · {datetime.fromtimestamp(min(p['t'] for p in PE), L):%d.%m}–{datetime.fromtimestamp(max(p['t'] for p in PE), L):%d.%m}")
print("\n1. ПОСЛЕ СКВИЗА В КОНЦЕ РОСТА (рекордный вынос шортов на свече вверх после суток роста): ход цены от закрытия часа сквиза")
def rp(nm, g):
    if len(g) < 15: print(f"  {nm:38s} мало ({len(g)})"); return
    s = f"  {nm:38s} n={len(g):4d}"
    for k in (2, 6, 24, 72):
        v = [p["fw"][k] for p in g if p["fw"][k] is not None]
        if v: s += f" · {k} ч: {np.median(v) * 100:+.1f}% (ниже в {sum(1 for x in v if x < 0) * 100 // len(v)}%)"
    v = [p["mn"][72] for p in g if p["mn"][72] is not None]; sh = [p["sh"] for p in g if p["sh"] is not None]
    s += f" · худшее падение за 72 ч: медиана {np.median(v) * 100:+.0f}%" if v else ""; s += f" · шорт 10/10: {(sum(sh) * 1000 - len(sh)) / len(sh):+.1f}$, целей {sum(1 for x in sh if x >= .0999) * 100 // len(sh)}%, стопов {sum(1 for x in sh if x <= -.0999) * 100 // len(sh)}%" if sh else ""
    print(s)
rp("все", PE)
for lo, hi in ((0, .10), (.10, .20), (.20, .40), (.40, 99)): rp(f"рост за сутки до сквиза {lo * 100:.0f}–{hi * 100:.0f}%" if hi < 9 else f"рост за сутки > {lo * 100:.0f}%", [p for p in PE if lo <= p["run"] < hi])
for lo, hi in ((0, 5), (5, 10), (10, 999)): rp(f"свеча сквиза {lo}–{hi}%", [p for p in PE if lo <= p["rng"] < hi])
rp("рост > 20% и свеча ≥ 8%", [p for p in PE if p["run"] >= .2 and p["rng"] >= 8])
print("\n2. ЛОНГ НА РЕКОРДНОМ ВЫНОСЕ ЛОНГОВ (свеча вниз), цель 10 / стоп 10 / безубыток после 5 — по времени после сквиза в конце роста:")
def rl(nm, g):
    if len(g) < 15: print(f"  {nm:52s} мало ({len(g)})"); return
    n = len(g); tm = sorted(x["t"] for x in g)[n // 2]; u = lambda q, k="res": (sum(x[k] for x in q) * 1000 - len(q)) / max(1, len(q))
    print(f"  {nm:52s} n={n:5d} · лонг {u(g):+6.1f}$ ({u([x for x in g if x['t'] < tm]):+6.1f} / {u([x for x in g if x['t'] >= tm]):+6.1f}), целей {sum(1 for x in g if x['res'] >= .0999) * 100 // n}%, стопов {sum(1 for x in g if x['res'] <= -.0999) * 100 // n}% · шорт там же {u(g, 'rs'):+6.1f}$")
rl("сквиза в конце роста за 72 ч не было", [x for x in LF if x["hrs"] is None])
for lo, hi in ((0, 2), (2, 6), (6, 12), (12, 24), (24, 48), (48, 72)): rl(f"после сквиза прошло {lo}–{hi} ч", [x for x in LF if x["hrs"] is not None and lo < x["hrs"] <= hi])
print("  — то же, только после сильного роста (рост за сутки до сквиза ≥ 20%):")
for lo, hi in ((0, 6), (6, 24), (24, 72)): rl(f"  после сквиза прошло {lo}–{hi} ч", [x for x in LF if x["hrs"] is not None and lo < x["hrs"] <= hi and x["run"] >= .2])
print("  — после слабого роста (< 10%):")
for lo, hi in ((0, 6), (6, 24), (24, 72)): rl(f"  после сквиза прошло {lo}–{hi} ч", [x for x in LF if x["hrs"] is not None and lo < x["hrs"] <= hi and x["run"] < .1])
