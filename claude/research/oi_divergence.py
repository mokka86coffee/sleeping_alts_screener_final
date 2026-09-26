"""НОВЫЙ МАКСИМУМ ЦЕНЫ ПРИ СЛИВАЮЩЕМСЯ ИНТЕРЕСЕ (26.09, по кадру BEAT из видео Щукина: на последней параболе интерес уже падал, вершина — на выкупе шортов).
Наши 100 лидеров (anatomy.csv, первый большой ход, вершина peak1). Данные: получасовки фьючерсов Binance (klines) и история интереса в $ (openInterestHist, 30m).
Сигнал = бар в окне [вершина − 72 ч, вершина + 24 ч], где закрытие — максимум за 48 ч и монета в ходу (≥ +40% за 48 ч). Разрез: интерес на баре
относительно своего максимума за 48 ч — «интерес на максимуме» (≥ 95%) / «интерес слился» (< 90%). Исход: сдвиг к вершине, закрытие через 6/12/24 ч,
сколько ещё дал ход до вершины. Мерки для разметки, не правила.
    .venv/bin/python claude/research/oi_divergence.py
"""
import csv, json, statistics as st, time, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
L = timezone(timedelta(hours=3)); H = 3600000; B = 1800000
def loc(s): return int(datetime.strptime(s + ".2026", "%d.%m %H:%M.%Y").replace(tzinfo=L).timestamp() * 1000)
def get(u): return json.loads(urllib.request.urlopen(u, timeout=20).read())
def kl(sym, t0, t1):
    d = get(f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}USDT&interval=30m&startTime={t0}&endTime={t1}&limit=500")
    return [(k[0], float(k[2]), float(k[4]), float(k[7])) for k in d]
def oi(sym, t0, t1):
    d = get(f"https://fapi.binance.com/futures/data/openInterestHist?symbol={sym}USDT&period=30m&startTime={t0}&endTime={t1}&limit=500")
    return {int(x["timestamp"]): float(x["sumOpenInterestValue"]) for x in d}
rows = list(csv.DictReader(open(Path(__file__).with_name("anatomy.csv"), encoding="utf-8")))
sig, nomove = [], 0
print(f"{'монета':<9}{'вершина':<12}| сигналов | у вершины (±2ч): интерес на макс / слился | первый «слился»: сдвиг ч · 6ч · 24ч · ещё до вершины")
for r in rows:
    try: tp = loc(r["peak1"])
    except Exception: continue
    t0, t1 = tp - 5 * 24 * H, tp + 30 * H
    try: k = kl(r["sym"], t0, t1); o = oi(r["sym"], t0, t1)
    except Exception as e: print(r["sym"], "нет данных:", type(e).__name__); continue
    by = {x[0]: i for i, x in enumerate(k)}
    s_here = []
    for i, x in enumerate(k):
        if not (tp - 72 * H <= x[0] <= tp + 24 * H): continue
        j = by.get(x[0] - 48 * H)
        if j is None or x[2] / k[j][2] - 1 < 0.40: continue
        if x[2] < max(p[2] for p in k[j:i]): continue          # закрытие — максимум за 48 ч
        ov = [o[p[0]] for p in k[j:i + 1] if p[0] in o]
        if x[0] not in o or len(ov) < 10: continue
        rel = o[x[0]] / max(ov)
        kind = "макс" if rel >= 0.95 else ("слился" if rel < 0.90 else "между")
        after = {dt: ((k[i + 2 * dt][2] / x[2] - 1) * 100 if i + 2 * dt < len(k) else None) for dt in (6, 12, 24)}
        fut = [p[2] for p in k[i + 1:] if p[0] <= tp + 24 * H]
        more = (max(fut) / x[2] - 1) * 100 if fut else 0.0
        s_here.append(dict(sym=r["sym"], t=x[0], shift=(x[0] - tp) / H, rel=rel, kind=kind, after=after, more=more))
    if not s_here: nomove += 1; continue
    near = [s for s in s_here if abs(s["shift"]) <= 2]
    f = lambda v: "  —  " if v is None else f"{v:+5.1f}"
    d = next((s for s in s_here if s["kind"] == "слился"), None)
    print(f"{r['sym']:<9}{r['peak1']:<12}| {len(s_here):3d}      | {sum(1 for s in near if s['kind']=='макс'):2d} / {sum(1 for s in near if s['kind']=='слился'):2d}"
          + (f" | {d['shift']:+6.1f} · {f(d['after'][6])} · {f(d['after'][24])} · {f(d['more'])}" if d else " | —"))
    sig += s_here; time.sleep(0.12)
def grp(name, g):
    if not g: return
    a6 = [x["after"][6] for x in g if x["after"][6] is not None]; a24 = [x["after"][24] for x in g if x["after"][24] is not None]
    near = sum(1 for x in g if abs(x["shift"]) <= 2)
    print(f"  {name:<48} n={len(g):3d} · это вершина (±2 ч) {near / len(g) * 100:3.0f}% · через 6 ч ниже {sum(1 for v in a6 if v < 0) / len(a6) * 100 if a6 else 0:3.0f}% (мед {st.median(a6) if a6 else 0:+.1f}%)"
          f" · через 24 ч ниже {sum(1 for v in a24 if v < 0) / len(a24) * 100 if a24 else 0:3.0f}% (мед {st.median(a24) if a24 else 0:+.1f}%) · ещё ≥+10% до вершины {sum(1 for x in g if x['more'] >= 10) / len(g) * 100:3.0f}% · мед ещё {st.median(x['more'] for x in g):+.1f}%")
print(f"\nСВОДКА: новых максимумов цены в ходу — {len(sig)}; ходов без сигнала {nomove}")
grp("интерес на максимуме (≥95% от макс. за 48 ч)", [x for x in sig if x["kind"] == "макс"])
grp("интерес между (90–95%)", [x for x in sig if x["kind"] == "между"])
grp("интерес СЛИЛСЯ (< 90% от макс. за 48 ч)", [x for x in sig if x["kind"] == "слился"])
grp("  слился сильно (< 80%)", [x for x in sig if x["rel"] < 0.80])
# первый «слился» на ход
first = {}
for x in sig:
    if x["kind"] == "слился" and x["sym"] not in first: first[x["sym"]] = x
grp("ПЕРВЫЙ «слился» на ход", list(first.values()))
