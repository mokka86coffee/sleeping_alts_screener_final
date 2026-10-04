#!/usr/bin/env python3
"""КАКОЙ МИНИМАЛЬНЫЙ РАЗМЕР ВЫНОСА (03.10 18:10, владелец: «подумай, какой порог поставить, у тебя же все расчёты»; до этого: «вынос рекордным должен быть за 24 часа, ×2 минимум
от любого другого выноса, при условии что выносы были практически одинаковыми за 24 часа; если выносы ×2+ к общему среднему выносу уже были, то +30 % от него»).
Сигналы — из потока ликвидаций бота (OKX+Bybit, cq_v2/liq, с 25.09), цены — часовые бары TradingView (Binance). Правило стороны как у бота: против хода минимумов за 24 ч.
Выход: цель 10 %, стоп 10 %, после +5 % стоп в точку входа, срок 7 дней. Результат — $ на сделку стороны бота, по размеру выноса: в долларах, к часовому обороту монеты, к прежнему максимуму.
Считает оба определения рекорда: текущее (≥ ×1.3 максимума суток) и новое владельца (×2, если выносы ровные; +30 % к максимуму, если уже был вынос ×2 к среднему). Только запись."""
import json, sys, math
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import numpy as np
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT)); D = Path(__file__).parent / "tvd"; L = timezone(timedelta(hours=3))
import fast_tier as ft
HL = ft._liq_hourly(); own = ft._own_mm()
def walk(side, e, bars, tp=.10, sl=.10, be_at=.05):
    be = False
    for (t, o, h, l, c, v) in bars:
        if side == 1:
            if l <= (e if be else e * (1 - sl)): return 0.0 if be else -sl
            if h >= e * (1 + tp): return tp
            if not be and h >= e * (1 + be_at): be = True
        else:
            if h >= (e if be else e * (1 + sl)): return 0.0 if be else -sl
            if l <= e * (1 - tp): return tp
            if not be and l <= e * (1 - be_at): be = True
    return side * (bars[-1][4] / e - 1) if bars else None
syms = sorted({s for (s, _) in HL}); sig = []
for sym in syms:
    f = D / f"{sym}.P_60.json"
    if not f.exists() or sym in own: continue
    b = json.load(open(f))["bars"]
    if len(b) < 200: continue
    idx = {x[0] * 1000: i for i, x in enumerate(b)}; lows = [x[3] for x in b]
    for side in ("short", "long"):
        hs = HL.get((sym, side)) or {}; ho = HL.get((sym, "long" if side == "short" else "short")) or {}
        for hm, win in hs.items():
            i = idx.get(hm)
            if i is None or i < 25 or i >= len(b) - 2 or win <= 0: continue
            prev = [v for h, v in hs.items() if hm - 86_400_000 <= h < hm]
            if not prev: continue
            other = max((v for h, v in ho.items() if hm - 86_400_000 <= h <= hm), default=0.0)
            if win <= other: continue
            mx = max(prev); mean = sum(prev) / len(prev); old = win >= 1.3 * mx
            new = win >= (1.3 * mx if mx >= 2 * mean and len(prev) > 1 else 2 * mx)
            if not (old or new): continue
            lw = lows[i - 24:i]; k = 8; first, last = lw[:k], lw[-k:]; a1, a2 = sum(first) / k, sum(last) / k
            mv = 1 if (min(last) > min(first) and a2 > a1) else (-1 if (max(last) < max(first) and a2 < a1) else 0)
            if mv == 0: continue
            e = b[i][4]; seg = b[i + 1:i + 1 + 168]; side_bot = -mv; r = walk(side_bot, e, seg); ro = walk(-side_bot, e, seg)
            if r is None: continue
            vol = np.mean([x[5] * x[4] for x in b[i - 24:i]])                   # средний часовой оборот за сутки, $
            sig.append(dict(sym=sym, t=hm // 1000, side=side, mv=mv, win=win, x=win / mx, old=old, new=new, res=r, opp=ro, vol=vol, ratio=win / vol if vol > 0 else float("nan"), n_prev=len(prev), rng=(b[i][2] / b[i][3] - 1) * 100))
print(f"поток: {datetime.fromtimestamp(min(s['t'] for s in sig), L):%d.%m}–{datetime.fromtimestamp(max(s['t'] for s in sig), L):%d.%m} · сигналов с ходом: текущее правило {sum(1 for s in sig if s['old'])}, новое правило {sum(1 for s in sig if s['new'])}")
def rep(nm, g):
    if len(g) < 12: print(f"    {nm:34s} мало ({len(g)})"); return
    n = len(g); u = (sum(s["res"] for s in g) * 1000 - n) / n; o = (sum(s["opp"] for s in g) * 1000 - n) / n; tm = sorted(s["t"] for s in g)[n // 2]
    a = [s for s in g if s["t"] < tm]; b_ = [s for s in g if s["t"] >= tm]; h = lambda q: (sum(s["res"] for s in q) * 1000 - len(q)) / max(1, len(q))
    print(f"    {nm:34s} n={n:4d} · сторона бота {u:+6.1f}$/сд. (1-я половина {h(a):+6.1f}, 2-я {h(b_):+6.1f}) · целей {sum(1 for s in g if s['res'] >= .0999) * 100 // n}% · стопов {sum(1 for s in g if s['res'] <= -.0999) * 100 // n}% · обратная сторона {o:+6.1f}$")
for key, title in (("old", "ТЕКУЩЕЕ ПРАВИЛО (≥ ×1.3 максимума суток)"), ("new", "НОВОЕ ПРАВИЛО ВЛАДЕЛЬЦА (×2 при ровных выносах; +30 % если уже был ×2 к среднему)")):
    G = [s for s in sig if s[key]]; print(f"\n{title}: всего {len(G)}"); rep("все", G)
    print("  по размеру выноса, $:")
    for lo, hi in ((0, 1e3), (1e3, 3e3), (3e3, 1e4), (1e4, 3e4), (3e4, 1e5), (1e5, 1e12)): rep(f"{lo / 1e3:g}–{hi / 1e3:g}K$" if hi < 1e11 else f"> {lo / 1e3:g}K$", [s for s in G if lo <= s["win"] < hi])
    print("  накопленно — «не меньше»:")
    for lo in (0, 1e3, 3e3, 5e3, 1e4, 2e4, 3e4, 5e4, 1e5): rep(f"вынос ≥ {lo / 1e3:g}K$", [s for s in G if s["win"] >= lo])
    print("  по доле от среднего часового оборота монеты:")
    for lo, hi in ((0, .001), (.001, .003), (.003, .01), (.01, .03), (.03, 9e9)): rep(f"{lo * 100:g}–{hi * 100:g}%" if hi < 1e9 else f"> {lo * 100:g}%", [s for s in G if lo <= s["ratio"] < hi])
    print("  по размаху часовой свечи выноса:")
    for lo, hi in ((0, 2), (2, 4), (4, 8), (8, 999)): rep(f"{lo}–{hi}%", [s for s in G if lo <= s["rng"] < hi])
    print("  по числу часов с выносами за прошлые сутки (насколько поток по монете «живой»):")
    for lo, hi in ((1, 2), (2, 4), (4, 8), (8, 25)): rep(f"{lo}–{hi - 1} ч", [s for s in G if lo <= s["n_prev"] < hi])
w = sorted(s["win"] for s in sig if s["old"]); print(f"\nразмер выноса у сигналов текущего правила: медиана {np.median(w) / 1e3:.1f}K$, четверть меньше {np.percentile(w, 25) / 1e3:.1f}K$, четверть больше {np.percentile(w, 75) / 1e3:.1f}K$, десятая часть больше {np.percentile(w, 90) / 1e3:.0f}K$")
json.dump(sig, open(Path(__file__).parent / "flush_size_sig.json", "w"))
