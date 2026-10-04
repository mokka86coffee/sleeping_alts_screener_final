#!/usr/bin/env python3
"""R49/R52 НА ЧАСОВЫХ ДАННЫХ TRADINGVIEW (03.10; правило владельца: «рекордный за 24 часа вынос на часовой свече… вход против хода за 24 часа»; статус правила — не проверено).
Повтор правила сканера выносов бота (fast_tier.flush_entries) на всех перпах: Liquidations с графика владельца (Binance), часовые бары, ~27 дней.
Сигнал: закрытый час, вынос стороны ≥ ×1.3 максимума часа этой стороны за прошлые 24 ч и больше любого часа другой стороны за 24 ч.
Ход: минимумы 24 часовых свечей до выноса, первая треть против последней (как _move_10h). Вход по закрытию часа выноса, сторона ПРОТИВ хода; нет хода — пропуск.
Выход как у бота: цель 10 %, стоп 10 %, после +5 % стоп в точку входа, срок 7 дней; новый рекордный вынос при открытой позиции — закрыть и войти заново.
Печатает четыре клетки (чей вынос × какой ход) и для сравнения вход ПО ходу. Монеты своего ММ и моложе 180 дней исключены. Только запись.
    .venv/bin/python claude/research/tv_flush.py [60|240]"""
import json, glob, sys, math
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import numpy as np
D = Path(__file__).parent / "tvd"; ROOT = Path(__file__).resolve().parents[2]; TF = sys.argv[1] if len(sys.argv) > 1 else "60"
H = 24 if TF == "60" else 6; X = 1.3; L = timezone(timedelta(hours=3))
try: OWN = {s for s in json.load(open(ROOT / "output" / "own_mm.json"))["coins"]}
except Exception: OWN = set()
def walk(side, e, bars, tp=.10, sl=.10, be_at=.05):
    be = False
    for j, (t, o, h, l, c, v) in enumerate(bars):
        up = h / e - 1; dn = l / e - 1
        if side == 1:
            if l <= (e if be else e * (1 - sl)): return (0.0 if be else -sl), j, "безубыток" if be else "стоп"
            if up >= tp: return tp, j, "цель"
            if be_at and not be and up >= be_at: be = True
        else:
            if h >= (e if be else e * (1 + sl)): return (0.0 if be else -sl), j, "безубыток" if be else "стоп"
            if dn <= -tp: return tp, j, "цель"
            if be_at and not be and dn <= -be_at: be = True
    return None, len(bars), None
sig = []
for f in sorted(glob.glob(str(D / f"*_{TF}.json"))):
    d = json.load(open(f)); sym = d["sym"].split(":")[1].replace(".P", ""); b = d["bars"]
    if sym in OWN or len(b) < 3 * H: continue
    f1 = D / (Path(f).name.replace(f"_{TF}.json", "_1D.json"))
    try:
        if len(json.load(open(f1))["bars"]) < 180: continue
    except Exception: continue
    lq = {x[0]: (abs(x[1] or 0.0), abs(x[2] or 0.0) if len(x) > 2 else 0.0) for x in d.get("liq") or []}
    n = len(b); LL = np.array([lq.get(x[0], (0, 0))[0] for x in b]); LS = np.array([lq.get(x[0], (0, 0))[1] for x in b]); lows = np.array([x[3] for x in b])
    for i in range(H, n - 1):
        for side, A, O in (("short", LS, LL), ("long", LL, LS)):
            win = A[i]; prev = A[i - H:i]; pm = prev.max()
            if not (win > 0 and pm > 0 and win >= X * pm and win > O[i - H:i + 1].max()): continue
            lw = lows[i - H:i]; k = len(lw) // 3; first, last = lw[:k], lw[-k:]; a1, a2 = first.mean(), last.mean()
            mv = 1 if (last.min() > first.min() and a2 > a1) else (-1 if (last.max() < first.max() and a2 < a1) else 0)
            sig.append(dict(sym=sym, i=i, t=b[i][0], side=side, mv=mv, mvp=(a2 / a1 - 1) * 100, x=win / pm, e=b[i][4], rng=(b[i][2] / b[i][3] - 1) * 100, f=f))
print(f"таймфрейм {TF} · монет {len({s['sym'] for s in sig})} · рекордных выносов {len(sig)}; период {datetime.fromtimestamp(min(s['t'] for s in sig), L):%d.%m}–{datetime.fromtimestamp(max(s['t'] for s in sig), L):%d.%m}")
cache = {}
def bars_of(f):
    if f not in cache: cache[f] = json.load(open(f))["bars"]
    return cache[f]
def run(pick, against=True, tp=.10, sl=.10, be=.05):
    """одна позиция на монету; новый сигнал при открытой — закрыть по цене сигнала и войти заново"""
    out = []; bym = defaultdict(list)
    for s in sig:
        if s["mv"] != 0 and pick(s): bym[s["sym"]].append(s)
    for sym, ss in bym.items():
        ss.sort(key=lambda s: s["i"]); b = bars_of(ss[0]["f"])
        for n_, s in enumerate(ss):
            side = -s["mv"] if against else s["mv"]; nxt = ss[n_ + 1]["i"] if n_ + 1 < len(ss) else None
            end = min(len(b), s["i"] + 1 + 7 * 24 * (1 if TF == "60" else 0) + (42 if TF != "60" else 0)); seg = b[s["i"] + 1:(nxt + 1 if nxt is not None and nxt + 1 < end else end)]
            res, j, how = walk(side, s["e"], seg, tp, sl, be)
            if res is None:
                if not seg: continue
                if nxt is None and s["i"] + 1 + len(seg) >= len(b): res, how = side * (seg[-1][4] / s["e"] - 1), "открыта"
                else: res, how = side * (seg[-1][4] / s["e"] - 1), "перезаход" if nxt is not None else "срок"
            out.append(dict(s, res=res, how=how, sd=side))
    return out
def rep(nm, tr):
    if not tr: print(f"  {nm}: нет"); return
    n = len(tr); usd = sum(t["res"] for t in tr) * 1000 - n; tmid = sorted(t["t"] for t in tr)[n // 2]; a = [t for t in tr if t["t"] < tmid]; b = [t for t in tr if t["t"] >= tmid]
    hw = defaultdict(int)
    for t in tr: hw[t["how"]] += 1
    g = lambda q: f"{sum(t['res'] for t in q) * 1000 - len(q):+.0f}$ ({(sum(t['res'] for t in q) * 1000 - len(q)) / max(1, len(q)):+.1f}$/сд.)"
    print(f"  {nm:62s} n={n:4d} {g(tr)} · 1-я половина {g(a)} · 2-я {g(b)} · " + ", ".join(f"{k} {v}" for k, v in sorted(hw.items(), key=lambda kv: -kv[1])))
print("\nВХОД ПРОТИВ ХОДА (правило бота), цель 10 / стоп 10 / безубыток после 5:")
rep("все рекордные выносы", run(lambda s: True))
rep("вынос шортов после роста → шорт (R49)", run(lambda s: s["side"] == "short" and s["mv"] == 1))
rep("вынос лонгов после падения → лонг (R49-б)", run(lambda s: s["side"] == "long" and s["mv"] == -1))
rep("вынос лонгов после роста → шорт (R52)", run(lambda s: s["side"] == "long" and s["mv"] == 1))
rep("вынос шортов после падения → лонг (R52)", run(lambda s: s["side"] == "short" and s["mv"] == -1))
print("\nДЛЯ СРАВНЕНИЯ — ВХОД ПО ХОДУ:")
rep("все рекордные выносы", run(lambda s: True, against=False))
rep("вынос шортов после роста → лонг", run(lambda s: s["side"] == "short" and s["mv"] == 1, against=False))
rep("вынос лонгов после падения → шорт", run(lambda s: s["side"] == "long" and s["mv"] == -1, against=False))
rep("вынос лонгов после роста → лонг", run(lambda s: s["side"] == "long" and s["mv"] == 1, against=False))
rep("вынос шортов после падения → шорт", run(lambda s: s["side"] == "short" and s["mv"] == -1, against=False))
print("\nПРОТИВ ХОДА по силе рекорда (во сколько раз больше прежнего максимума за сутки):")
for lo, hi in ((1.3, 2), (2, 4), (4, 10), (10, 1e9)): rep(f"×{lo:g}–{hi:g}", run(lambda s, lo=lo, hi=hi: lo <= s["x"] < hi))
print("\nПРОТИВ ХОДА по размаху свечи выноса:")
for lo, hi in ((0, 3), (3, 6), (6, 12), (12, 1e9)): rep(f"{lo:g}–{hi:g}%", run(lambda s, lo=lo, hi=hi: lo <= s["rng"] < hi))
print("\nПРОТИВ ХОДА, другие выходы:")
for tp, sl, be in ((.05, .05, 0), (.05, .05, .03), (.10, .05, .05), (.10, .10, 0), (.03, .03, 0)): rep(f"цель {tp:.0%} стоп {sl:.0%} безубыток {'нет' if not be else f'после {be:.0%}'}", run(lambda s: True, tp=tp, sl=sl, be=be))
tr = run(lambda s: True); byd = defaultdict(list)
for t in tr: byd[datetime.fromtimestamp(t["t"], L).strftime("%d.%m")].append(t["res"])
print("\nпо дням (против хода): " + " · ".join(f"{d} {len(v)} сд {sum(v) * 1000 - len(v):+.0f}$" for d, v in sorted(byd.items(), key=lambda kv: (kv[0][3:], kv[0][:2]))))
print(f"без хода (пропуск): {sum(1 for s in sig if s['mv'] == 0)} из {len(sig)}")
