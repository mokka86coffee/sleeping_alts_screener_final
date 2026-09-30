#!/usr/bin/env python3
"""ИНДИКАТОРЫ ТРЁХ АВТОРОВ TradingView (владелец 30.09: LeviathanCapital, BigBeluga, AlgoAlpha — «у них тоже все посмотри и попробуй что-то применить») на закрытых сделках бота.
Из списков авторов (по ~24 скрипта) реализованы те, что считаются по OHLCV + taker-buy + интерес Binance (30-мин бары до входа); реализация по названиям/описаниям, упрощённо:
  Leviathan: Volume and Price Z Score (z объёма и хода цены), Open Interest Delta / Suite (ΔOI 6 ч и 24 ч, расхождение цены и OI), Market Order Bubbles / Liquidation Bands CVD Bubbles (бары с дельтой дальше 2σ: белые/красные за 12 баров),
            Range Analysis (диапазон 24 ч к среднему), Gaps / Imbalances (нетронутый медвежий FVG выше цены: расстояние);
  BigBeluga: Liquidity Sweep Hunter (прокол свинг-хая/лоя и возврат за 6 баров), Reversal Trap Probability Bands / Z Score Range Boxes (z цены к 50 барам), Premium and Discount (положение в диапазоне 100 баров);
  AlgoAlpha: Volume Weighted Median Oscillator / Dynamic Median Momentum (цена к медиане 50 в MAD), Money Flow / Volume Divergence Zones (цена у максимума 24 бара при падающей дельте), High Volume Breakout (объём бара к медиане).
Не реализуемо с этих данных: Liquidation Levels / Heatmap (нужны карты ликвидаций), Net Positions, Open Interest Profile по бирже, закрытые премиум-версии.
Деление: верхняя/нижняя треть по значению; вердикт «есть сигнал» — только если ЭКСТРЕМАЛЬНЫЕ трети различаются ≥ 12 п. по доле в плюсе, обе половины по времени в ту же сторону и n ≥ 10 (середина не считается, чтобы не ловить немонотонный шум). Только запись.
    .venv/bin/python claude/research/authors_test.py → authors_test.md"""
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
def get(u):
    for _ in range(3):
        try: return json.load(urllib.request.urlopen(u, timeout=25))
        except Exception: pass
    return []
def load(t):
    e = int(t["t_in"] * 1000)
    k = [x for x in get(f"https://fapi.binance.com/fapi/v1/klines?symbol={t['sym']}&interval=30m&endTime={e}&limit=210") if int(x[0]) + 1_800_000 <= e]
    oi = [x for x in get(f"https://fapi.binance.com/futures/data/openInterestHist?symbol={t['sym']}&period=30m&endTime={e}&limit=60") if int(x["timestamp"]) <= e]
    return k, [float(x["sumOpenInterest"]) for x in oi]
with ThreadPoolExecutor(8) as ex: D = list(ex.map(load, T))
def feats(k, oi, px):
    if len(k) < 120: return None
    h = np.array([float(x[2]) for x in k]); l = np.array([float(x[3]) for x in k]); c = np.array([float(x[4]) for x in k]); v = np.array([float(x[5]) for x in k]); tb = np.array([float(x[9]) for x in k])
    d = 2 * tb - v; n = len(c); f = {}
    lv = np.log(np.maximum(v, 1e-9)); f["Leviathan · Volume Z Score (объём 30-мин бара, z за 100)"] = float((lv[-1] - lv[-100:].mean()) / (lv[-100:].std() or 1))
    r = np.diff(np.log(c)); f["Leviathan · Price Z Score (ход бара, z за 100)"] = float((r[-1] - r[-100:].mean()) / (r[-100:].std() or 1))
    if len(oi) >= 50:
        f["Leviathan · OI Delta 6 ч, %"] = float((oi[-1] / oi[-13] - 1) * 100); f["Leviathan · OI Delta 24 ч, %"] = float((oi[-1] / oi[-49] - 1) * 100)
        pc = (c[-1] / c[-49] - 1) * 100; oc = (oi[-1] / oi[-49] - 1) * 100
        f["Leviathan · цена 24 ч вверх при OI 24 ч вниз (1 = да)"] = 1 if (pc > 0 and oc < 0) else 0
    sd = np.std(d[-100:]); z = d / (sd or 1)
    f["Leviathan · Market Order Bubbles: белых(+2σ) минус красных(−2σ) за 12 баров"] = float((z[-12:] > 2).sum() - (z[-12:] < -2).sum())
    rg = (h[-48:].max() - l[-48:].min()) / c[-1]; avg = np.mean([(h[i - 48:i].max() - l[i - 48:i].min()) / c[i] for i in range(100, n, 24)]) if n > 150 else None
    if avg: f["Leviathan · Range Analysis: диапазон 24 ч / средний"] = float(rg / avg)
    fv = [(i, l[i - 2]) for i in range(2, n - 1) if l[i - 2] > h[i] and h[i + 1:].max() < l[i - 2]]
    up = [p for i, p in fv if p > px]; f["Leviathan · Gaps/Imbalances: до нетронутого медвежьего FVG выше, %"] = float((min(up) / px - 1) * 100) if up else 30.0
    sh = h[-26:-6].max(); sl = l[-26:-6].min(); w = slice(-6, None)
    sw_up = bool(((h[w] > sh) & (c[w] < sh)).any()); sw_dn = bool(((l[w] < sl) & (c[w] > sl)).any())
    f["BigBeluga · Liquidity Sweep: за 6 баров прокол хая с возвратом (1) / прокол лоя с возвратом (−1) / нет (0)"] = 1 if sw_up else (-1 if sw_dn else 0)
    f["BigBeluga · Reversal Trap Bands: z цены к 50 барам"] = float((px - c[-50:].mean()) / (c[-50:].std() or 1))
    f["BigBeluga · Premium/Discount: положение в диапазоне 100 баров (0 низ … 1 верх)"] = float((px - l[-100:].min()) / max(h[-100:].max() - l[-100:].min(), 1e-12))
    med = np.median(c[-50:]); mad = np.median(np.abs(c[-50:] - med)); f["AlgoAlpha · Volume Weighted Median Osc: (цена−медиана50)/MAD"] = float((px - med) / (mad or 1e-12))
    cvd = np.cumsum(d); f["AlgoAlpha · Money Flow Divergence: цена у макс. 24 баров при падающей CVD (1 = да)"] = 1 if (c[-1] >= h[-24:].max() * 0.995 and cvd[-1] < cvd[-24]) else 0
    f["AlgoAlpha · High Volume Breakout: объём бара / медиана 30"] = float(v[-1] / (np.median(v[-30:]) or 1))
    return f
X = []
for t, (k, oi) in zip(T, D):
    f = feats(k, oi, t["px_in"])
    if f: X.append(dict(f=f, side=t["side"], usd=t["res"] * 10, res=t["res"], tin=t["t_in"]))
print(len(T), "сделок,", len(X), "с индикаторами")
mid = sorted(x["tin"] for x in X)[len(X) // 2]
def stat(g):
    if len(g) < 10: return None
    a = [x for x in g if x["tin"] < mid]; b = [x for x in g if x["tin"] >= mid]
    w = lambda z: None if len(z) < 5 else sum(1 for x in z if x["usd"] > 0) / len(z)
    return dict(n=len(g), win=sum(1 for x in g if x["usd"] > 0) * 100 // len(g), tgt=sum(1 for x in g if x["res"] >= 4.5), usd=sum(x["usd"] for x in g), w1=w(a), w2=w(b))
md = [f"# Индикаторы Leviathan / BigBeluga / AlgoAlpha на сделках бота ({datetime.now(L):%d.%m %H:%M})", "",
      f"Сделок {len(X)} (27.09–30.09, обе книги, без двойников). Реализация по описаниям, упрощённо. Вердикт только по крайним третям (≥ 12 п. и обе половины по времени в ту же сторону, n ≥ 10). Не проверено вне выборки.", ""]
verd = []
for side, nm in ((1, "ЛОНГИ"), (-1, "ШОРТЫ")):
    S = [x for x in X if x["side"] == side]
    if len(S) < 30: continue
    md += [f"## {nm}: n={len(S)}, в плюсе {sum(1 for x in S if x['usd'] > 0) * 100 // len(S)}%, сумма {sum(x['usd'] for x in S):.0f} $", ""]
    for nme in S[0]["f"]:
        vals = [(x["f"].get(nme), x) for x in S if x["f"].get(nme) is not None]
        if len(vals) < 30: continue
        uniq = sorted({v for v, _ in vals})
        if len(uniq) <= 3: groups = [(str(u), [x for v, x in vals if v == u]) for u in uniq]; lo_, hi_ = groups[0], groups[-1]
        else:
            q = st.quantiles([v for v, _ in vals], n=3)
            groups = [(f"нижняя треть (<{q[0]:.3g})", [x for v, x in vals if v < q[0]]), ("средняя", [x for v, x in vals if q[0] <= v < q[1]]), (f"верхняя треть (≥{q[1]:.3g})", [x for v, x in vals if v >= q[1]])]
            lo_, hi_ = groups[0], groups[-1]
        md.append(f"**{nme}**"); md.append("")
        ss = [(lab, stat(g)) for lab, g in groups]
        for lab, c in ss: md.append(f"- {lab}: " + (f"n={c['n']} · плюс {c['win']}% · до цели {c['tgt']} · сумма {c['usd']:.0f} $ · половины {'—' if c['w1'] is None else f'{c[chr(119)+chr(49)]*100:.0f}%'}/{'—' if c['w2'] is None else f'{c[chr(119)+chr(50)]*100:.0f}%'}" if c else "мало"))
        a, b = stat(lo_[1]), stat(hi_[1])
        if a and b:
            same = None not in (a["w1"], a["w2"], b["w1"], b["w2"]) and ((a["w1"] > b["w1"] and a["w2"] > b["w2"]) or (a["w1"] < b["w1"] and a["w2"] < b["w2"]))
            sig = abs(a["win"] - b["win"]) >= 12 and same
            verd.append((nm, nme, sig, lo_[0], a["win"], hi_[0], b["win"]))
            md.append(f"→ {'ЕСТЬ СИГНАЛ' if sig else 'нет сигнала'}: «{lo_[0]}» {a['win']}% против «{hi_[0]}» {b['win']}%"); md.append("")
md += ["## Сводка", ""]
for nm, nme, sig, l1, w1, l2, w2 in verd: md.append(f"- {nm} · {nme}: {'**можно**' if sig else 'нет'} ({l1} {w1}% / {l2} {w2}%)")
(R / "authors_test.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print("\n".join(md[-(len(verd) + 2):]))
