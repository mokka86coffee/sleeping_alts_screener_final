"""Владелец 10.10: «объемы подходящие к капитализации и есть пик». Счёт по тем же ходам ×2 с 19.09: получасовой оборот фьючерсов Binance
к капитализации той же получасовки (монеты в обороте × цена закрытия). Где в ходе это отношение было наибольшим и где оно впервые дошло до порога."""
import json, glob, statistics as s_
from pathlib import Path
tab = json.load(open("output/circ_supply.json"))
res = []
for p in sorted(glob.glob("cq_v2/intraday/*.jsonl")):
    base = Path(p).stem.upper(); t = tab.get(base + "USDT")
    if not t or base in ("BTC", "ETH"): continue
    circ = t["circ"] / (1000 if base.startswith("1000") else 1)
    rows = []
    for line in open(p):
        try: r = json.loads(line)
        except Exception: continue
        if r.get("px") and r.get("h") and r.get("l"): rows.append((r["candle"], r["px"], r["h"], r["l"], ((r.get("kv") or {}).get("qv")) or 0))
    if len(rows) < 100: continue
    lo, lo_i, hi, hi_i = rows[0][3], 0, None, None
    def rec(end_i):
        if hi / lo >= 2 and rows[hi_i][0] >= "2026-09-19":
            seg = range(lo_i, min(len(rows), hi_i + 5))
            ratio = {i: rows[i][4] / (circ * rows[i][1]) for i in seg}
            imax = max(ratio, key=ratio.get)
            d = dict(sym=base, t1=rows[hi_i][0], c1=circ * hi, x=hi / lo, rmax=ratio[imax], off=imax - hi_i,
                     got_max=(rows[imax][1] - lo) / (hi - lo) * 100, rpeak=max(ratio[i] for i in seg if abs(i - hi_i) <= 1))
            for thr in (0.25, 0.5, 1.0):
                f = next((i for i in seg if ratio[i] >= thr), None)
                d[f"f{thr}"] = None if f is None else dict(off=f - hi_i, got=(rows[f][1] - lo) / (hi - lo) * 100,
                                                           up=(hi / rows[f][1] - 1) * 100)
            res.append(d)
    for i, r in enumerate(rows):
        if hi is None:
            if r[3] < lo: lo, lo_i = r[3], i
            if r[2] >= lo * 1.5: hi, hi_i = r[2], i
        else:
            if r[2] > hi: hi, hi_i = r[2], i
            if r[3] <= hi - 0.5 * (hi - lo):
                rec(i); lo, lo_i, hi, hi_i = r[3], i, None, None
    if hi is not None: rec(len(rows) - 1)
def show(name, g):
    if not g: return
    print(f"\n{name}: ходов {len(g)}")
    print(f"  наибольшее отношение получасовки к капе за ход: медиана {s_.median(m['rmax'] for m in g)*100:.0f}% · оно пришлось на вершину ±1 получасовку у {sum(abs(m['off']) <= 1 for m in g)}, раньше у {sum(m['off'] < -1 for m in g)}, позже у {sum(m['off'] > 1 for m in g)} · цена в этой получасовке забрала медиану {s_.median(m['got_max'] for m in g):.0f}% роста")
    for thr in (0.25, 0.5, 1.0):
        f = [m[f"f{thr}"] for m in g if m[f"f{thr}"]]
        if not f: print(f"  порог {thr*100:.0f}% капы: не было ни разу"); continue
        print(f"  порог {thr*100:.0f}% капы за получасовку: был в {len(f)} из {len(g)} · первый раз на вершине ±1 у {sum(abs(x['off']) <= 1 for x in f)}, раньше у {sum(x['off'] < -1 for x in f)}, позже у {sum(x['off'] > 1 for x in f)} · забрано роста медиана {s_.median(x['got'] for x in f):.0f}% · цена после первого раза ушла ещё выше на ≥15% у {sum(x['up'] >= 15 for x in f)}")
show("вершина ниже 60 млн $", [m for m in res if m["c1"] < 6e7])
show("вершина 60–125 млн $", [m for m in res if 6e7 <= m["c1"] < 1.25e8])
show("вершина выше 125 млн $", [m for m in res if m["c1"] >= 1.25e8])
show("все", res)
print("\nпо ходам ниже 125 млн $ (монета: наибольшее отношение, где оно относительно вершины в получасовках, сколько роста там забрано):")
print(", ".join(f"{m['sym']} {m['rmax']*100:.0f}% {m['off']:+d} {m['got_max']:.0f}%" for m in sorted([m for m in res if m['c1'] < 1.25e8], key=lambda m: -m['rmax'])))
