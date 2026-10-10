"""Иксы с 19.09 и капитализация на вершине — по таблице «монеты в обороте», сверенной ценой (output/circ_supply.json).
Ход: от низа (минимум с конца прошлого хода) до вершины; кончился, когда цена отдала половину роста (мерка Claude). Иксы — вершина/низ ≥ 2."""
import json, glob, pickle, statistics as s_
from pathlib import Path
S = Path(__file__).parent
tab = json.load(open("output/circ_supply.json"))
moves = []
for p in sorted(glob.glob("cq_v2/intraday/*.jsonl")):
    base = Path(p).stem.upper(); t = tab.get(base + "USDT")
    if not t or base in ("BTC", "ETH"): continue
    mult = 1000 if base.startswith("1000") else 1
    circ = t["circ"] / mult
    rows = []
    for line in open(p):
        try: r = json.loads(line)
        except Exception: continue
        if r.get("px") and r.get("h") and r.get("l"): rows.append((r["candle"], r["px"], r["h"], r["l"], ((r.get("kv") or {}).get("qv")) or 0))
    if len(rows) < 100: continue
    lo, lo_i, hi, hi_i = rows[0][3], 0, None, None
    def rec(done):
        x = hi / lo
        if x >= 2 and rows[hi_i][0] >= "2026-09-19":
            v24 = sum(r[4] for r in rows[max(0, hi_i - 47):hi_i + 1])
            bar = max(r[4] for r in rows[max(0, hi_i - 1):hi_i + 3])
            moves.append(dict(sym=base, t0=rows[lo_i][0], t1=rows[hi_i][0], x=x, c0=circ * lo, c1=circ * hi, done=done, v24=v24, bar=bar, now=circ * rows[-1][1]))
    for i, r in enumerate(rows):
        if hi is None:
            if r[3] < lo: lo, lo_i = r[3], i
            if r[2] >= lo * 1.5: hi, hi_i = r[2], i
        else:
            if r[2] > hi: hi, hi_i = r[2], i
            if r[3] <= hi - 0.5 * (hi - lo):
                rec(True); lo, lo_i, hi, hi_i = r[3], i, None, None
    if hi is not None: rec(False)
pickle.dump(moves, open(S / "x_moves2.pkl", "wb"))
def M(v): return f"{v/1e6:.0f}"
print(f"ходов ×2 и больше с вершиной от 19.09: {len(moves)} · монет {len({m['sym'] for m in moves})}")
for m in sorted(moves, key=lambda m: -m["c1"]):
    print(f"{m['sym']:9} ×{m['x']:4.1f} · {m['t0'][5:10]} → {m['t1'][5:10]} · {M(m['c0']):>4} → {M(m['c1']):>5} млн $ · оборот суток вершины {m['v24']/m['c1']*100:5.0f}% капы · получасовка вершины {M(m['bar']):>4} млн ({m['bar']/m['c1']*100:4.0f}% капы) · " + ("отдала половину" if m["done"] else "не закрыт") + f" · сейчас {M(m['now'])}")
for name, f in (("старт ниже 100 млн", lambda m: m["c0"] < 1e8), ("старт 100–500 млн", lambda m: 1e8 <= m["c0"] < 5e8), ("старт выше 500 млн", lambda m: m["c0"] >= 5e8)):
    g = [m for m in moves if f(m)]
    if not g: continue
    pk = sorted(m["c1"] for m in g)
    print(f"\n{name}: ходов {len(g)} · вершина: медиана {M(s_.median(pk))} млн $, от {M(pk[0])} до {M(pk[-1])} · кончились ниже 100 млн {sum(c < 1e8 for c in pk)}, в 100–500 млн {sum(1e8 <= c < 5e8 for c in pk)}, выше 500 млн {sum(c >= 5e8 for c in pk)}"
          f" · оборот суток вершины к капе: медиана {s_.median(m['v24']/m['c1'] for m in g)*100:.0f}% · получасовка вершины к капе: медиана {s_.median(m['bar']/m['c1'] for m in g)*100:.0f}%, больше капы у {sum(m['bar'] >= m['c1'] for m in g)}")
pk = [m["c1"] for m in moves]
for a, b in ((0, 5e7), (5e7, 7.5e7), (7.5e7, 1.25e8), (1.25e8, 2.5e8), (2.5e8, 4.5e8), (4.5e8, 1e9), (1e9, 1e12)):
    g = [m for m in moves if a <= m["c1"] < b]
    print(f"вершина {M(a)}–{M(b) if b < 1e11 else '…'} млн $: {len(g)} · " + ", ".join(f"{m['sym']} {M(m['c1'])}" for m in sorted(g, key=lambda m: m['c1'])))
