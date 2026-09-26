"""ОБЪЁМ ВТОРОГО ИМПУЛЬСА ПРОТИВ ПЕРВОГО (26.09, по видео Щукина: «цена растёт, объём падает на каждом новом экстремуме — тренд выдыхается» и «в здоровом
бычьем тренде каждый импульс на большем объёме»). Наши лидеры из anatomy.csv, у кого есть второй ход (move2_start … peak2). Объём ноги — сумма долларового
объёма получасовок фьючерсов Binance от старта ноги до её вершины, делённая на число баров (объём в час), чтобы длина ноги не мешала.
Смотрим: объём/час ноги 2 к ноге 1 (×), вершина 2 выше вершины 1 (peak2_vs_peak1 > 0)?, и что после вершины 2 (откат 2). Мерки разметки, не правила.
    .venv/bin/python claude/research/impulse_volume.py
"""
import csv, json, statistics as st, time, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
L = timezone(timedelta(hours=3)); B = 1800000
def loc(s): return int(datetime.strptime(s + ".2026", "%d.%m %H:%M.%Y").replace(tzinfo=L).timestamp() * 1000)
def kl(sym, t0, t1):
    out, t = {}, t0
    while t <= t1:
        d = json.loads(urllib.request.urlopen(f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}USDT&interval=30m&startTime={t}&endTime={t1}&limit=1500", timeout=20).read())
        if not d: break
        out.update({k[0]: float(k[7]) for k in d}); t = d[-1][0] + B
        if len(d) < 1500: break
    return out
def leg(qv, a, b):
    v = [qv[t] for t in range(a, b + 1, B) if t in qv]
    return (sum(v) / len(v) * 2) if v else None   # $/час
rows = [r for r in csv.DictReader(open(Path(__file__).with_name("anatomy.csv"), encoding="utf-8")) if r.get("peak2") and r.get("move2_start_after_peak1_h")]
print(f"{'монета':<9}{'нога1':<12}{'×объём/ч':>9} {'нога2':<12}{'×объём/ч':>9} | объём2/объём1 | вершина2 к вершине1 | откат после 2 | ход1 % · ход2 %")
res = []
for r in rows:
    try:
        t_s, t_p1, t_p2 = loc(r["start"]), loc(r["peak1"]), loc(r["peak2"])
        t_s2 = t_p1 + int(float(r["move2_start_after_peak1_h"])) * 3600000 if r.get("move2_start_after_peak1_h") else None
        # старт ноги 2 = минимум между вершиной 1 и вершиной 2 — берём момент отката 1 (pullback1), если есть
        t_s2 = loc(r["pullback1"]) if r.get("pullback1") else t_s2
    except Exception:
        continue
    if not t_s2 or t_s2 >= t_p2: continue
    try:
        qv = kl(r["sym"], t_s - 48 * B, t_p2 + B)
    except Exception as e:
        print(r["sym"], "нет данных:", type(e).__name__); continue
    base = st.median([qv[t] for t in range(t_s - 48 * B, t_s, B) if t in qv] or [1]) * 2
    v1, v2 = leg(qv, t_s, t_p1), leg(qv, t_s2, t_p2)
    if not v1 or not v2: continue
    ratio = v2 / v1; up = float(r["peak2_vs_peak1"]) if r.get("peak2_vs_peak1") else None
    pb2 = float(r["pullback2_pct"]) if r.get("pullback2_pct") else None
    print(f"{r['sym']:<9}{r['start'][:11]:<12}{v1 / base:9.1f} {r['pullback1'][:11]:<12}{v2 / base:9.1f} | {ratio:13.2f} | {up:+18.0f}% | {('%+.0f%%' % pb2) if pb2 is not None else '—':>13} | {r['move1_pct']:>5} · {r['move2_pct']:>5}")
    res.append(dict(sym=r["sym"], ratio=ratio, up=up, pb2=pb2, m1=float(r["move1_pct"]), m2=float(r["move2_pct"])))
    time.sleep(0.1)
print(f"\nСВОДКА: ходов со второй ногой {len(res)}")
def grp(name, g):
    if not g: return
    ups = [x for x in g if x["up"] is not None]
    print(f"  {name:<44} n={len(g):2d} · вершина 2 выше вершины 1 — {sum(1 for x in ups if x['up'] > 0)}/{len(ups)} · медиана хода 2 {st.median(x['m2'] for x in g):+.0f}% · медиана отката после 2 {st.median([x['pb2'] for x in g if x['pb2'] is not None] or [0]):+.0f}%")
grp("объём ноги 2 ≥ объёма ноги 1 (×1 и больше)", [x for x in res if x["ratio"] >= 1])
grp("объём ноги 2 меньше (×0.5–1)", [x for x in res if 0.5 <= x["ratio"] < 1])
grp("объём ноги 2 сильно меньше (< ×0.5)", [x for x in res if x["ratio"] < 0.5])
