#!/usr/bin/env python3
"""ГДЕ ЭТО РАБОТАЛО (07.10, владелец: «посмотри лучше где это работало»). Все прошлые случаи той же картины, что на его разборе DEXE и в mm_absorb_alert.py,
по архиву cq_v2/intraday (Coinglass Binance, шаг 30 минут, ~месяц): интерес в монетах вырос от низа до пика на 10 % и больше, пока по рынку на фьючерсе били
в одну сторону; потом от пика интерес ушёл на 5 % и больше (пик не старше 6 часов) — бьющая сторона выходит. Дальше смотрится, что сделала цена за 8 и 24 часа
в ожидаемую сторону (вверх, если выходили шорты; вниз, если лонги). Выводятся сами случаи — где сработало сильнее всего и где нет — и чем они отличались.
    .venv/bin/python claude/research/mm_absorb_cases.py"""
import json, glob, os, statistics as st, datetime as dt
from pathlib import Path
B = Path(__file__).resolve().parents[2]
E = []
for p in glob.glob(str(B / "cq_v2" / "intraday" / "*.jsonl")):
    r = []
    for l in open(p):
        try: x = json.loads(l)
        except ValueError: continue
        if x.get("px") and x.get("oi"): r.append(x)
    if len(r) < 150: continue
    oc = [x["oi"] / x["px"] for x in r]; sym = os.path.basename(p)[:-6].upper(); last_k = -99; last_i = -99
    for i in range(48, len(r) - 48):
        w0 = i - 48
        k = max(range(w0, i), key=lambda j: oc[j])
        if i - k > 12 or k - last_k < 6 or i - last_i < 24: continue
        if oc[i] / oc[k] - 1 > -0.05: continue
        lo = min(range(w0, k + 1), key=lambda j: oc[j]); rise = oc[k] / oc[lo] - 1
        if rise < 0.10 or k - lo < 4: continue
        seg = r[lo:k + 1]
        fb = sum(((x.get("fut") or {}).get("b") or 0) for x in seg); fs = sum(((x.get("fut") or {}).get("s") or 0) for x in seg)
        sb = sum(((x.get("spot") or {}).get("b") or 0) for x in seg); ss = sum(((x.get("spot") or {}).get("s") or 0) for x in seg)
        if fb + fs <= 0 or fb == fs: continue
        side = 1 if fs > fb else -1; e = r[i]["px"]
        nx8 = [x["px"] for x in r[i + 1:i + 17]]; nx24 = [x["px"] for x in r[i + 1:i + 49]]
        spot = "нет спота" if sb + ss <= 0 else ("согласен" if ((sb - ss) > 0) == (side == 1) else "против")
        prc = (r[k]["px"] / r[lo]["px"] - 1) * 100                         # что делала цена, пока набирали
        E.append(dict(sym=sym, t=r[i]["candle"][:16].replace("T", " "), side=side, rise=rise * 100, drop=(oc[i] / oc[k] - 1) * 100, spot=spot, prc=prc * side * -1,
                      r8=(nx8[-1] / e - 1) * side * 100, r24=(nx24[-1] / e - 1) * side * 100, best=(max(nx24) / e - 1) * 100 if side == 1 else (1 - min(nx24) / e) * 100,
                      worst=(1 - min(nx24) / e) * 100 if side == 1 else (max(nx24) / e - 1) * 100, imb=(fb - fs) / (fb + fs) * 100, fund=r[i].get("funding")))
        last_k, last_i = k, i
g = lambda v, p=0: "—" if v is None else f"{v:+.{p}f}"
def line(x):
    return (f"  {x['t'][5:]} {x['sym']:9s} {'ПОКУПАТЬ (шорты выходят)' if x['side'] == 1 else 'ПРОДАВАТЬ (лонги выходят)':25s} · интерес +{x['rise']:.0f}% → {x['drop']:.0f}% · били на {abs(x['imb']):.1f}% · спот {x['spot']:9s} · "
            f"цена пока набирали {g(-x['prc'] * x['side'])}% · фандинг {g(x['fund'], 3)} → за 8 ч {g(x['r8'])}% · за 24 ч {g(x['r24'])}% · лучшее {g(x['best'])}% · против {x['worst']:.0f}%")
print(f"случаев в архиве: {len(E)} на {len({x['sym'] for x in E})} монетах · с {min(x['t'] for x in E)[:10]} по {max(x['t'] for x in E)[:10]}")
W = sorted(E, key=lambda x: -x["r24"])
print("\nГДЕ СРАБОТАЛО СИЛЬНЕЕ ВСЕГО (ход за 24 часа в ожидаемую сторону):")
for x in W[:14]: print(line(x))
print("\nГДЕ НЕ СРАБОТАЛО СИЛЬНЕЕ ВСЕГО:")
for x in W[-8:]: print(line(x))
def grp(name, key, vals):
    print(f"\n{name}: случаев · в ожидаемую сторону за 24 ч · средний ход за 24 ч · дали от +10 % по лучшей цене")
    for v, sel in vals:
        q = [x for x in E if sel(x)]
        if len(q) < 5: print(f"  {v}: мало ({len(q)})"); continue
        print(f"  {v:34s} {len(q):3d} · {sum(1 for x in q if x['r24'] > 0)} · {st.mean(x['r24'] for x in q):+.1f}% · {sum(1 for x in q if x['best'] >= 10)}")
grp("сторона", "side", [("покупать (шорты выходят)", lambda x: x["side"] == 1), ("продавать (лонги выходят)", lambda x: x["side"] == -1)])
grp("спот", "spot", [("согласен", lambda x: x["spot"] == "согласен"), ("против", lambda x: x["spot"] == "против"), ("спота нет", lambda x: x["spot"] == "нет спота")])
grp("сколько набрали", "rise", [("интерес +10…20 %", lambda x: x["rise"] < 20), ("+20…40 %", lambda x: 20 <= x["rise"] < 40), ("от +40 %", lambda x: x["rise"] >= 40)])
grp("цена, пока набирали", "prc", [("шла ПРОТИВ бьющих (их зажимали)", lambda x: x["prc"] < -3), ("стояла (±3 %)", lambda x: -3 <= x["prc"] <= 3), ("шла ЗА бьющими (они в плюсе)", lambda x: x["prc"] > 3)])
