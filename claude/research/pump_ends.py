#!/usr/bin/env python3
"""ЧЕМ И ГДЕ КОНЧАЛИСЬ ПАМПЫ ЗА НЕДЕЛЮ — ПО КЛАСТЕРАМ (07.10, владелец: «прямо возьми все пампы за последние 7 дней и посмотри что и где закончилось и почему»).
Данные — кластеры с графика владельца (tv_footprint.py, 30 минут, ~6 суток): по каждой свече покупки и продажи по рынку на каждом уровне цены.
По каждой монете: вершина (максимум окна), низ перед ней (минимум за 48 ч до вершины), сколько чистых покупок ушло на подъём, что было в последние
два часа перед вершиной и в самой вершинной свече, сколько купили у самого верха и что стало после. Это разбор по одной, не правило.
    .venv/bin/python claude/research/pump_ends.py"""
import json, glob, datetime as dt
from pathlib import Path
D = Path(__file__).parent / "tvd"; U = dt.timezone.utc
f = lambda t: dt.datetime.fromtimestamp(t, U).strftime("%d.%m %H:%M")
for p in sorted(glob.glob(str(D / "*_fp30.json"))):
    d = json.load(open(p)); b = d["bars"]; fp = {x["i"]: x for x in d["fp"]}; n = len(b)
    sym = Path(p).name.replace("_fp30.json", "")
    dl = [(fp[i]["buy"] - fp[i]["sell"]) if i in fp else 0.0 for i in range(n)]; vol = [b[i][5] for i in range(n)]
    T = max(range(n), key=lambda i: b[i][2]); S = min(range(max(0, T - 96), T + 1), key=lambda i: b[i][3])
    if T - S < 2 or b[T][2] / b[S][3] < 1.3: print(f"{sym}: в окне нет хода от 30 % (вершина {f(b[T][0])}, от низа ×{b[T][2] / b[S][3]:.2f})"); continue
    hi, lo = b[T][2], b[S][3]
    rise_v, rise_d = sum(vol[S:T + 1]), sum(dl[S:T + 1])
    def leg(a, z):
        a = max(S, a); v = sum(vol[a:z + 1]) or 1
        return (b[z][4] / b[a][1] - 1) * 100, sum(dl[a:z + 1]) / v * 100, v
    l2 = leg(T - 3, T); l1 = leg(T - 7, T - 4)
    tb = b[T]; rng = (tb[2] - tb[3]) or 1e-12
    wick = (tb[2] - max(tb[1], tb[4])) / rng * 100; poc = (fp[T]["poc"] - tb[3]) / rng * 100 if T in fp else None
    vrank = sorted(vol[S:T + 1], reverse=True).index(vol[T]) + 1
    # покупки у самого верха: уровни не ниже 3 % от вершины, свечи T−2…T+2, доля от всех покупок подъёма
    top_buy = sum(x[1] for i in range(max(S, T - 2), min(n, T + 3)) if i in fp for x in fp[i]["levels"] if x[0] >= hi * 0.97)
    all_buy = sum(fp[i]["buy"] for i in range(S, T + 1) if i in fp) or 1
    after = lambda k: (b[min(n - 1, T + k)][4] / hi - 1) * 100
    nxt = dl[T + 1] / (vol[T + 1] or 1) * 100 if T + 1 < n else None
    ret = (hi - b[-1][4]) / (hi - lo) * 100
    print(f"\n{sym}: низ {f(b[S][0])} → вершина {f(b[T][0])} UTC, ×{hi / lo:.2f} за {(T - S) / 2:.0f} ч")
    print(f"  подъём: чистые покупки {rise_d / rise_v * 100:+.1f}% от объёма")
    print(f"  предпоследние 2 ч: цена {l1[0]:+.1f}%, чистые покупки {l1[1]:+.1f}% объёма | последние 2 ч: цена {l2[0]:+.1f}%, чистые покупки {l2[1]:+.1f}% объёма, объём ×{l2[2] / (l1[2] or 1):.1f} к предыдущим двум часам")
    print(f"  вершинная свеча: дельта {dl[T] / (vol[T] or 1) * 100:+.1f}% объёма, объём {vrank}-й по величине за подъём, хвост сверху {wick:.0f}% свечи" + (f", главный объём на {poc:.0f}% высоты свечи" if poc is not None else ""))
    print(f"  куплено у самого верха (не ниже 3 % от вершины, 2,5 ч вокруг неё): {top_buy / all_buy * 100:.0f}% всех покупок подъёма")
    print(f"  после: следующая свеча дельта {nxt:+.1f}% объёма · через 2 ч {after(4):+.0f}% · через 8 ч {after(16):+.0f}% · сейчас {(b[-1][4] / hi - 1) * 100:+.0f}% от вершины (отдано {ret:.0f}% подъёма)" if nxt is not None else "  после: вершина — последняя свеча окна, ход ещё идёт")
