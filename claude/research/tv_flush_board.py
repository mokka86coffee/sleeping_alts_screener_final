#!/usr/bin/env python3
"""ВЫНОСЫ × ДОСКА (03.10; владелец: «при росте доски заменяй шорт на лонг»; «вынос шортов это конец в любом случае лонга» — проверка).
Тот же сигнал, что в tv_flush.py (рекордный за 24 ч вынос стороны, ход по минимумам за 24 ч), но каждая клетка разбита по состоянию доски на момент сигнала:
доска = медиана хода закрытия всех перпов за 24 ч и за 7 дней (по тем же барам TradingView). Для каждой клетки считаются ОБЕ стороны входа (шорт и лонг), цель 10 / стоп 10 / безубыток после 5,
и простой ход цены через 24 ч. Монеты своего ММ и моложе 180 дней исключены. Только запись.
    .venv/bin/python claude/research/tv_flush_board.py [60|240]"""
import json, glob, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import numpy as np
D = Path(__file__).parent / "tvd"; ROOT = Path(__file__).resolve().parents[2]; TF = sys.argv[1] if len(sys.argv) > 1 else "240"
H = 24 if TF == "60" else 6; X = 1.3; L = timezone(timedelta(hours=3)); HOLD = 7 * H
try: OWN = {s for s in json.load(open(ROOT / "output" / "own_mm.json"))["coins"]}
except Exception: OWN = set()
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
coins = {}; acc24 = defaultdict(list); acc7 = defaultdict(list)
for f in sorted(glob.glob(str(D / f"*_{TF}.json"))):
    d = json.load(open(f)); sym = d["sym"].split(":")[1].replace(".P", ""); b = d["bars"]
    if len(b) < 8 * H: continue
    for i in range(7 * H, len(b)):
        if b[i - H][4] > 0: acc24[b[i][0]].append(b[i][4] / b[i - H][4] - 1)
        if b[i - 7 * H][4] > 0: acc7[b[i][0]].append(b[i][4] / b[i - 7 * H][4] - 1)
    if sym in OWN: continue
    try:
        if len(json.load(open(D / Path(f).name.replace(f"_{TF}.json", "_1D.json")))["bars"]) < 180: continue
    except Exception: continue
    coins[sym] = d
B24 = {t: float(np.median(a)) for t, a in acc24.items() if len(a) >= 100}; B7 = {t: float(np.median(a)) for t, a in acc7.items() if len(a) >= 100}
sig = []
for sym, d in coins.items():
    b = d["bars"]; lq = {x[0]: (abs(x[1] or 0.0), abs(x[2] or 0.0) if len(x) > 2 else 0.0) for x in d.get("liq") or []}; n = len(b)
    LL = np.array([lq.get(x[0], (0, 0))[0] for x in b]); LS = np.array([lq.get(x[0], (0, 0))[1] for x in b]); lows = np.array([x[3] for x in b]); last_i = -10 ** 9
    for i in range(7 * H, n - 1):
        if b[i][0] not in B7: continue
        for side, A, O in (("short", LS, LL), ("long", LL, LS)):
            win = A[i]; pm = A[i - H:i].max()
            if not (win > 0 and pm > 0 and win >= X * pm and win > O[i - H:i + 1].max()): continue
            lw = lows[i - H:i]; k = max(1, len(lw) // 3); first, last = lw[:k], lw[-k:]; a1, a2 = first.mean(), last.mean()
            mv = 1 if (last.min() > first.min() and a2 > a1) else (-1 if (last.max() < first.max() and a2 < a1) else 0)
            if mv == 0: continue
            seg = b[i + 1:i + 1 + HOLD]; e = b[i][4]
            sig.append(dict(sym=sym, t=b[i][0], side=side, mv=mv, x=win / pm, b24=B24[b[i][0]], b7=B7[b[i][0]], sh=walk(-1, e, seg), lo=walk(1, e, seg),
                            f24=(b[min(n - 1, i + H)][4] / e - 1) if i + H < n else None, day=(b[i][4] / b[i][1] - 1)))
print(f"таймфрейм {TF} · монет {len(coins)} · сигналов с ходом {len(sig)} · {datetime.fromtimestamp(min(s['t'] for s in sig), L):%d.%m}–{datetime.fromtimestamp(max(s['t'] for s in sig), L):%d.%m}")
def rep(nm, g):
    g = [s for s in g if s["sh"] is not None]
    if len(g) < 20: print(f"    {nm:28s} мало ({len(g)})"); return
    n = len(g); f = [s["f24"] for s in g if s["f24"] is not None]
    print(f"    {nm:28s} n={n:5d} · шорт {(sum(s['sh'] for s in g) * 1000 - n) / n:+6.1f}$/сд. · лонг {(sum(s['lo'] for s in g) * 1000 - n) / n:+6.1f}$/сд. · через 24 ч цена: медиана {np.median(f) * 100:+.1f}%, выше входа в {sum(1 for x in f if x > 0) * 100 // max(1, len(f))}% случаев")
CELLS = (("вынос ШОРТОВ после РОСТА", "short", 1), ("вынос ШОРТОВ после ПАДЕНИЯ", "short", -1), ("вынос ЛОНГОВ после РОСТА", "long", 1), ("вынос ЛОНГОВ после ПАДЕНИЯ", "long", -1))
for nm, side, mv in CELLS:
    g = [s for s in sig if s["side"] == side and s["mv"] == mv]; print(f"\n{nm} (бот сейчас: {'шорт' if mv == 1 else 'лонг'})"); rep("все", g)
    rep("доска 24 ч > +1%", [s for s in g if s["b24"] > .01]); rep("доска 24 ч −1…+1%", [s for s in g if -.01 <= s["b24"] <= .01]); rep("доска 24 ч < −1%", [s for s in g if s["b24"] < -.01])
    rep("  доска 24 ч +1…+3%", [s for s in g if .01 < s["b24"] <= .03]); rep("  доска 24 ч > +3%", [s for s in g if s["b24"] > .03]); rep("  доска 24 ч −3…−1%", [s for s in g if -.03 <= s["b24"] < -.01]); rep("  доска 24 ч < −3%", [s for s in g if s["b24"] < -.03])
    rep("доска 7 дн > +5%", [s for s in g if s["b7"] > .05]); rep("доска 7 дн 0…+5%", [s for s in g if 0 < s["b7"] <= .05]); rep("доска 7 дн −5…0%", [s for s in g if -.05 < s["b7"] <= 0]); rep("доска 7 дн < −5%", [s for s in g if s["b7"] <= -.05])
    rep("рекорд ×10+", [s for s in g if s["x"] >= 10])
print("\nПО МЕСЯЦАМ (все сигналы): шорт / лонг $ на сделку")
bym = defaultdict(list)
for s in sig:
    if s["sh"] is not None: bym[datetime.fromtimestamp(s["t"], L).strftime("%y-%m")].append(s)
for m in sorted(bym):
    g = bym[m]; n = len(g); print(f"  {m}: n={n:5d} · шорт {(sum(s['sh'] for s in g) * 1000 - n) / n:+6.1f} · лонг {(sum(s['lo'] for s in g) * 1000 - n) / n:+6.1f} · доска 7 дн в среднем {np.mean([s['b7'] for s in g]) * 100:+.1f}%")
