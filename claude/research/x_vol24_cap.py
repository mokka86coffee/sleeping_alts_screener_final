"""Владелец 10.10: «у мелкокапов оборот к капитализации практически и есть конец хода, дальше ход идёт только у более фундаментальных монет».
Те же ходы ×2 с 19.09 (низ → вершина, конец — отдана половина роста, мерка Claude). Оборот фьючерсов Binance за 24 часа к капитализации той же
получасовки: когда он впервые дошёл до порога, сколько роста уже было и сколько цена прошла после."""
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
    cum = [0.0]
    for r in rows: cum.append(cum[-1] + r[4])
    r24 = lambda i: (cum[i + 1] - cum[max(0, i - 47)]) / (circ * rows[i][1])
    lo, lo_i, hi, hi_i = rows[0][3], 0, None, None
    def rec():
        if hi / lo >= 2 and rows[hi_i][0] >= "2026-09-19":
            d = dict(sym=base, c1=circ * hi, x=hi / lo, at_peak=r24(hi_i), mx=max(r24(i) for i in range(lo_i, hi_i + 1)))
            for thr in (0.5, 1.0, 3.0):
                f = next((i for i in range(lo_i, hi_i + 1) if r24(i) >= thr), None)
                d[thr] = None if f is None else dict(got=(rows[f][1] - lo) / (hi - lo) * 100, up=(hi / rows[f][1] - 1) * 100, h=(hi_i - f) / 2)
            res.append(d)
    for i, r in enumerate(rows):
        if hi is None:
            if r[3] < lo: lo, lo_i = r[3], i
            if r[2] >= lo * 1.5: hi, hi_i = r[2], i
        else:
            if r[2] > hi: hi, hi_i = r[2], i
            if r[3] <= hi - 0.5 * (hi - lo):
                rec(); lo, lo_i, hi, hi_i = r[3], i, None, None
    if hi is not None: rec()
def show(name, g):
    print(f"\n{name}: ходов {len(g)} · оборот за 24 ч к капитализации на вершине: медиана {s_.median(m['at_peak'] for m in g)*100:.0f}%, меньше 100% у {sum(m['at_peak'] < 1 for m in g)}")
    for thr in (0.5, 1.0, 3.0):
        f = [m[thr] for m in g if m[thr]]
        if not f: print(f"  порог {thr*100:.0f}%: не доходил ни разу"); continue
        print(f"  оборот суток дошёл до {thr*100:.0f}% капы: в {len(f)} из {len(g)} · в этот момент пройдено роста: медиана {s_.median(x['got'] for x in f):.0f}% · цена после этого прошла ещё: медиана +{s_.median(x['up'] for x in f):.0f}%, меньше +15% у {sum(x['up'] < 15 for x in f)}, больше +50% у {sum(x['up'] >= 50 for x in f)} · до вершины оставалось: медиана {s_.median(x['h'] for x in f):.0f} ч")
show("вершина ниже 100 млн $", [m for m in res if m["c1"] < 1e8])
show("вершина 100–500 млн $", [m for m in res if 1e8 <= m["c1"] < 5e8])
show("вершина выше 500 млн $", [m for m in res if m["c1"] >= 5e8])
