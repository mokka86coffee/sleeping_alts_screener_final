#!/usr/bin/env python3
"""ИНДИКАТОРЫ ChartPrime (TradingView, владелец 30.09: «пройди по всем индикаторам этого автора, применить к сделкам, протестировать, что можно использовать, что нет») на закрытых сделках бота.
Берём те, у которых логика ясна из описания и хватает OHLCV + taker-buy Binance (30-мин бары до входа, 200 баров). Каждый индикатор → число на входе; сделки делятся на трети по этому числу
(или по состоянию); считаем долю в плюсе, число достижений цели +5%, сумму при 1000 $ и согласованность двух половин по времени. Только запись; правила бота не меняются. Не проверено вне выборки.
    Реализовано по описаниям (не по исходникам — часть скриптов закрытая): RSI Probability Matrix / BB Range RSI (RSI14), SuperTrend Oscillator, Session VWAP + StdDev Bands, DeltaPulse Wave (нормированная дельта),
    Trend-Reset Cumulative Delta (дельта с сбросом по ATR-коридору, упрощённо), Volume Whale Zones / Volume Profile PoC (25 корзин), Forward-Projecting Opportunity Cone (ожидаемое движение 2 ч против цели 5%),
    Specter Trend Cloud (EMA9/21 ± ATR), Pivot Support & Resistance / Breakout Boxes (расстояние до ближайшего нетронутого пивота), Market Break Analytics (пробой пивота + доля покупок), MA Oscillator (цена к EMA50 в ATR).
    .venv/bin/python claude/research/chartprime_test.py  → chartprime_test.md"""
import json, urllib.request, statistics as st, math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np

R = Path(__file__).parent; L = timezone(timedelta(hours=3))
tr = json.load(open(R / "cgr" / "trades.json"))
seen = set(); T = []
for t in sorted(tr, key=lambda t: t["t_in"]):
    k = (t["sym"], round(t["t_in"] / 300))
    if k in seen: continue
    seen.add(k); T.append(t)
def kl(t):
    e = int(t["t_in"] * 1000)
    for _ in range(3):
        try:
            k = json.load(urllib.request.urlopen(f"https://fapi.binance.com/fapi/v1/klines?symbol={t['sym']}&interval=30m&endTime={e}&limit=210", timeout=25))
            k = [x for x in k if int(x[0]) + 1_800_000 <= e]
            return k
        except Exception: pass
    return []
with ThreadPoolExecutor(8) as ex: K = list(ex.map(kl, T))
def ema(a, n):
    out = []; k = 2 / (n + 1)
    for v in a: out.append(v if not out else out[-1] + k * (v - out[-1]))
    return np.array(out)
def atr(h, l, c, n=14):
    tr_ = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]
    return ema(tr_, n)
def feats(k, px):
    if len(k) < 120: return None
    o = np.array([float(x[1]) for x in k]); h = np.array([float(x[2]) for x in k]); l = np.array([float(x[3]) for x in k]); c = np.array([float(x[4]) for x in k])
    v = np.array([float(x[5]) for x in k]); tb = np.array([float(x[9]) for x in k]); ts = np.array([int(x[0]) for x in k]) / 1000
    d = 2 * tb - v; A = atr(h, l, c); f = {}
    # RSI14
    ch = np.diff(c); up = ema(np.maximum(ch, 0), 14); dn = ema(np.maximum(-ch, 0), 14); f["RSI14 (RSI Probability Matrix / BB Range RSI)"] = float(100 - 100 / (1 + up[-1] / dn[-1])) if dn[-1] > 0 else 100.0
    # SuperTrend oscillator (10, 3)
    n = len(c); hl2 = (h + l) / 2; ub = hl2 + 3 * A; lb = hl2 - 3 * A; fu = ub.copy(); fl = lb.copy(); tr_ = 1; stl = np.zeros(n)
    for i in range(1, n):
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]; fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        if tr_ == 1 and c[i] < fl[i]: tr_ = -1
        elif tr_ == -1 and c[i] > fu[i]: tr_ = 1
        stl[i] = fl[i] if tr_ == 1 else fu[i]
    f["SuperTrend Oscillator: (цена−ST)/ATR"] = float((c[-1] - stl[-1]) / A[-1])
    # Session VWAP (сброс 00:00 UTC) ± σ
    day0 = int(ts[-1] // 86400) * 86400; m = ts >= day0
    if m.sum() >= 4:
        tp = (h + l + c) / 3; w = v[m]; vw = (tp[m] * w).sum() / w.sum(); sd = math.sqrt(((tp[m] - vw) ** 2 * w).sum() / w.sum())
        f["Session VWAP + StdDev: (цена−VWAP)/σ"] = float((px - vw) / sd) if sd > 0 else 0.0
    # DeltaPulse Wave: дельта последних 3 баров / σ дельты за 50
    sd_ = np.std(d[-50:]); f["DeltaPulse Wave: дельта 3 баров / σ"] = float(d[-3:].sum() / (sd_ * math.sqrt(3))) if sd_ > 0 else 0.0
    f["Доля покупок за 12 баров (Market Break Analytics: buy%)"] = float(tb[-12:].sum() / v[-12:].sum() * 100) if v[-12:].sum() > 0 else 50.0
    # Trend-Reset CVD: дельта с последнего касания ATR-коридора EMA20 (±1.5 ATR) — упрощённо
    e20 = ema(c, 20); idx = 0
    for i in range(n - 1, 0, -1):
        if abs(c[i] - e20[i]) > 1.5 * A[i]: idx = i; break
    f["Trend-Reset CVD: дельта с сброса / объём"] = float(d[idx:].sum() / max(v[idx:].sum(), 1e-9))
    # Volume Whale Zones / PoC: 25 корзин по 100 барам
    hh = h[-100:]; ll = l[-100:]; vv = v[-100:]; cc = c[-100:]; lo_, hi_ = ll.min(), hh.max()
    if hi_ > lo_:
        bins = np.linspace(lo_, hi_, 26); prof = np.zeros(25)
        for a, b, w, cl in zip(ll, hh, vv, cc):
            i0 = min(24, int((a - lo_) / (hi_ - lo_) * 25)); i1 = min(24, int((b - lo_) / (hi_ - lo_) * 25)); prof[i0:i1 + 1] += w / (i1 - i0 + 1)
        poc = (bins[prof.argmax()] + bins[prof.argmax() + 1]) / 2
        f["Volume Whale Zones: цена к PoC, % "] = float((px / poc - 1) * 100)
    # Opportunity Cone: σ 30-мин доходности × √4 (2 ч) против цели 5%
    r = np.diff(np.log(c[-100:])); s2h = r.std() * math.sqrt(4) * 100; f["Opportunity Cone: цель 5% / ожидаемое движение 2 ч (σ)"] = float(5 / s2h) if s2h > 0 else None
    # Specter Trend Cloud: EMA9 vs EMA21 ± ATR: +1 выше облака, 0 внутри, −1 ниже
    e9 = ema(c, 9)[-1]; e21 = ema(c, 21)[-1]; a = A[-1]; f["Specter Trend Cloud: +1 над облаком / 0 внутри / −1 под"] = 1 if px > max(e9, e21) + 0 * a and e9 > e21 else (-1 if px < min(e9, e21) and e9 < e21 else 0)
    # MA Oscillator: (цена − EMA50)/ATR
    f["MA Oscillator: (цена−EMA50)/ATR"] = float((px - ema(c, 50)[-1]) / A[-1])
    # Pivot S/R / Breakout Boxes: нетронутый пивот-хай выше цены (5/5 баров), расстояние %
    pv = [(i, h[i]) for i in range(5, n - 5) if h[i] == h[i - 5:i + 6].max()]
    above = [(i, p) for i, p in pv if p > px and h[i + 1:].max() <= p]
    f["Pivot S&R: до ближайшего нетронутого пивота выше, %"] = float((min(p for i, p in above) / px - 1) * 100) if above else 30.0
    # Market Break Analytics: пробой последнего пивот-хая на баре входа (да/нет)
    pv2 = [p for i, p in pv if i < n - 6]
    f["Market Break: цена выше последнего пивота (1/0)"] = 1 if pv2 and px > pv2[-1] else 0
    return f
X = []
for t, k in zip(T, K):
    f = feats(k, t["px_in"])
    if f: X.append(dict(f=f, side=t["side"], usd=t["res"] * 10, res=t["res"], tin=t["t_in"], sym=t["sym"]))
print(len(T), "сделок,", len(X), "с индикаторами")
mid = sorted(x["tin"] for x in X)[len(X) // 2]
def cell(g):
    if len(g) < 10: return None
    a = [x for x in g if x["tin"] < mid]; b = [x for x in g if x["tin"] >= mid]
    hf = lambda z: "—" if len(z) < 5 else f"{sum(1 for x in z if x['usd'] > 0) * 100 // len(z)}%"
    return dict(n=len(g), win=sum(1 for x in g if x["usd"] > 0) * 100 // len(g), tgt=sum(1 for x in g if x["res"] >= 4.5), usd=sum(x["usd"] for x in g), h1=hf(a), h2=hf(b),
                w1=(sum(1 for x in a if x["usd"] > 0) / len(a) if len(a) >= 5 else None), w2=(sum(1 for x in b if x["usd"] > 0) / len(b) if len(b) >= 5 else None))
md = [f"# Индикаторы ChartPrime на сделках бота ({datetime.now(L):%d.%m %H:%M})", "",
      f"Сделок {len(X)} (27.09–30.09, обе книги, без двойников); индикаторы считаны по 30-мин барам до входа (реализация по описаниям, упрощённо). Трети по значению индикатора внутри стороны. Вердикт: «есть сигнал» — разница долей трети ≥ 12 п. и обе половины по времени в ту же сторону при n ≥ 10; иначе «нет сигнала». Не проверено вне выборки.", ""]
verd = []
for side, nm in ((1, "ЛОНГИ"), (-1, "ШОРТЫ")):
    S = [x for x in X if x["side"] == side]
    if len(S) < 30: md += [f"## {nm}: n={len(S)} — мало", ""]; continue
    md += [f"## {nm}: n={len(S)}, в плюсе {sum(1 for x in S if x['usd'] > 0) * 100 // len(S)}%, сумма {sum(x['usd'] for x in S):.0f} $", ""]
    names = list(S[0]["f"].keys())
    for nme in names:
        vals = [(x["f"].get(nme), x) for x in S if x["f"].get(nme) is not None]
        if len(vals) < 30: continue
        uniq = sorted({v for v, _ in vals})
        if len(uniq) <= 3:
            groups = [(f"{u}", [x for v, x in vals if v == u]) for u in uniq]
        else:
            q = st.quantiles([v for v, _ in vals], n=3)
            groups = [(f"нижняя треть (<{q[0]:.3g})", [x for v, x in vals if v < q[0]]), ("средняя", [x for v, x in vals if q[0] <= v < q[1]]), (f"верхняя треть (≥{q[1]:.3g})", [x for v, x in vals if v >= q[1]])]
        cs = [(lab, cell(g)) for lab, g in groups]
        md.append(f"**{nme}**"); md.append("")
        for lab, c in cs: md.append(f"- {lab}: " + (f"n={c['n']} · плюс {c['win']}% · до цели {c['tgt']} · сумма {c['usd']:.0f} $ · половины {c['h1']}/{c['h2']}" if c else "мало"))
        ok = [(lab, c) for lab, c in cs if c]
        if len(ok) >= 2:
            best = max(ok, key=lambda z: z[1]["win"]); worst = min(ok, key=lambda z: z[1]["win"])
            same = all(c["w1"] is not None and c["w2"] is not None for c in (best[1], worst[1])) and best[1]["w1"] > worst[1]["w1"] and best[1]["w2"] > worst[1]["w2"]
            sig = best[1]["win"] - worst[1]["win"] >= 12 and same
            verd.append((nm, nme, sig, best[0], best[1]["win"], worst[0], worst[1]["win"]))
            md.append(f"→ {'ЕСТЬ СИГНАЛ' if sig else 'нет сигнала'}: лучшая «{best[0]}» {best[1]['win']}%, худшая «{worst[0]}» {worst[1]['win']}%"); md.append("")
md += ["## Сводка: что можно использовать, что нет", ""]
for nm, nme, sig, bl, bw, wl, ww in verd:
    md.append(f"- {nm} · {nme}: {'**можно**' if sig else 'нет'} ({bl} {bw}% / {wl} {ww}%)")
(R / "chartprime_test.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print("\n".join(md[-(len(verd) + 3):]))
