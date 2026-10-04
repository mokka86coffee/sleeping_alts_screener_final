#!/usr/bin/env python3
"""ВХОД ПОСЛЕ ВЫНОСА В СТОРОНУ, ОБРАТНУЮ СВЕЧЕ ВЫНОСА (03.10 18:50, владелец по LYN: «боту повезло, что свеча ушла ниже входа… дальше бот должен был взять лонг»; раньше: «вынос лонгов, 99 % будет рост»).
Сигнал: закрытый час с рекордным выносом стороны (≥ ×1.3 максимума суток и больше любого часа другой стороны). Вынос ЛОНГОВ на свече ВНИЗ → ЛОНГ по закрытию часа; вынос ШОРТОВ на свече ВВЕРХ → ШОРТ.
Разбивка по размаху свечи выноса и по ходу минимумов за 24 ч до неё. Выходы: 10/10 с безубытком после 5 % (как у сканера) и 5/5. Источники: А) поток бота OKX+Bybit после исправления сторон
(26.09–03.10), Б) ликвидации Binance с графика TradingView (часовые, 12.09–03.10). Цены — часовые бары TradingView. Только запись."""
import json, glob, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT)); D = Path(__file__).parent / "tvd"; L = timezone(timedelta(hours=3))
import fast_tier as ft
own = ft._own_mm()
def walk(side, e, bars, tp, sl, be_at):
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
def collect(liq_of):
    out = []
    for f in sorted(glob.glob(str(D / "*_60.json"))):
        d = json.load(open(f))
        if not isinstance(d, dict): continue
        sym = d["sym"].split(":")[1].replace(".P", ""); b = d["bars"]
        if sym in own or len(b) < 200: continue
        LLm, LSm = liq_of(sym, d)
        if not LLm and not LSm: continue
        lows = [x[3] for x in b]
        for i in range(25, len(b) - 2):
            hm = b[i][0] * 1000
            for side, A, O in (("long", LLm, LSm), ("short", LSm, LLm)):
                win = A.get(hm, 0.0)
                if win <= 0: continue
                prev = [v for h, v in A.items() if hm - 86_400_000 <= h < hm]
                if not prev or win < 1.3 * max(prev): continue
                if win <= max((v for h, v in O.items() if hm - 86_400_000 <= h <= hm), default=0.0): continue
                o_, h_, l_, c_ = b[i][1:5]; down = c_ < o_
                if (side == "long") != down: continue                      # лонги выносят на свече вниз, шорты — на свече вверх
                lw = lows[i - 24:i]; a1, a2 = sum(lw[:8]) / 8, sum(lw[-8:]) / 8
                mv = 1 if (min(lw[-8:]) > min(lw[:8]) and a2 > a1) else (-1 if (max(lw[-8:]) < max(lw[:8]) and a2 < a1) else 0)
                sd = 1 if side == "long" else -1; seg = b[i + 1:i + 169]
                r10 = walk(sd, c_, seg, .10, .10, .05); r5 = walk(sd, c_, seg[:24], .05, .05, 0)
                if r10 is None: continue
                out.append(dict(sym=sym, t=b[i][0], side=side, rng=(h_ / l_ - 1) * 100, body=abs(c_ / o_ - 1) * 100, mv=mv, r10=r10, r5=r5, win=win, x=win / max(prev),
                                back=(c_ - l_) / (h_ - l_) if side == "long" and h_ > l_ else ((h_ - c_) / (h_ - l_) if h_ > l_ else 0)))
    return out
HL = ft._liq_hourly()
def stream(sym, d): return HL.get((sym, "long"), {}), HL.get((sym, "short"), {})
def tv(sym, d):
    a, b_ = {}, {}
    for x in d.get("liq") or []:
        if x[1]: a[x[0] * 1000] = abs(x[1])
        if len(x) > 2 and x[2]: b_[x[0] * 1000] = abs(x[2])
    return a, b_
def rep(nm, g):
    if len(g) < 10: print(f"    {nm:44s} мало ({len(g)})"); return
    n = len(g); tm = sorted(s["t"] for s in g)[n // 2]; A = [s for s in g if s["t"] < tm]; B = [s for s in g if s["t"] >= tm]
    u = lambda q, k: (sum(s[k] for s in q) * 1000 - len(q)) / max(1, len(q))
    print(f"    {nm:44s} n={n:4d} · 10/10: {u(g, 'r10'):+6.1f}$ ({u(A, 'r10'):+6.1f} / {u(B, 'r10'):+6.1f}), целей {sum(1 for s in g if s['r10'] >= .0999) * 100 // n}%, стопов {sum(1 for s in g if s['r10'] <= -.0999) * 100 // n}%"
          f" · 5/5 за сутки: {u(g, 'r5'):+6.1f}$ ({u(A, 'r5'):+6.1f} / {u(B, 'r5'):+6.1f}), целей {sum(1 for s in g if s['r5'] >= .0499) * 100 // n}%")
for title, fn in (("А) ПОТОК БОТА (OKX+Bybit, стороны исправлены)", stream), ("Б) BINANCE (ликвидации с графика TradingView)", tv)):
    S = collect(fn); print(f"\n{title}: сигналов {len(S)} · {datetime.fromtimestamp(min(s['t'] for s in S), L):%d.%m}–{datetime.fromtimestamp(max(s['t'] for s in S), L):%d.%m}")
    for side, nm in (("long", "ВЫНОС ЛОНГОВ на свече вниз → ЛОНГ"), ("short", "ВЫНОС ШОРТОВ на свече вверх → ШОРТ")):
        G = [s for s in S if s["side"] == side]; print(f"  {nm}"); rep("все", G)
        for lo, hi in ((0, 4), (4, 8), (8, 15), (15, 999)): rep(f"свеча {lo}–{hi}%", [s for s in G if lo <= s["rng"] < hi])
        W = [s for s in G if s["rng"] >= 8]
        rep("свеча ≥ 8% · до выноса сутки роста", [s for s in W if s["mv"] == 1]); rep("свеча ≥ 8% · до выноса сутки падения", [s for s in W if s["mv"] == -1]); rep("свеча ≥ 8% · без хода", [s for s in W if s["mv"] == 0])
        rep("свеча ≥ 8% · рекорд ×5 и больше", [s for s in W if s["x"] >= 5]); rep("свеча ≥ 8% · цена уже отбила ≥ треть свечи", [s for s in W if s["back"] >= .33]); rep("свеча ≥ 8% · закрытие у края (отбито < трети)", [s for s in W if s["back"] < .33])
