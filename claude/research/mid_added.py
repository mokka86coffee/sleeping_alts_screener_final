"""Владелец 10.10: «200 млн это общая капа, после которой нихрена не идёт 3–5 дней». По дням: середина (капитализация дня 100–500 млн $) —
сколько капитализации добавлено в монетах, которые идут (закрытие дня ≥ +30 % к минимуму 7 дней, мерка Claude): сумма и кто."""
import json, glob
from pathlib import Path
from collections import defaultdict
tab = json.load(open("output/circ_supply.json"))
days = defaultdict(dict)   # day -> sym -> (close, low)
circ = {}
for p in sorted(glob.glob("cq_v2/intraday/*.jsonl")):
    base = Path(p).stem.upper(); t = tab.get(base + "USDT")
    if not t or base in ("BTC", "ETH"): continue
    circ[base] = t["circ"] / (1000 if base.startswith("1000") else 1)
    for line in open(p):
        try: r = json.loads(line)
        except Exception: continue
        if not (r.get("px") and r.get("l")): continue
        d = r["candle"][:10]; c, l = days[d].get(base, (None, 1e18))
        days[d][base] = (r["px"], min(l, r["l"]))
ds = sorted(days)
for i, d in enumerate(ds):
    if d < "2026-09-17": continue
    tot = 0; who = []; new = []
    for b, (c, l) in days[d].items():
        cap = circ[b] * c
        if not (1e8 <= cap < 5e8): continue
        low7 = min(days[x][b][1] for x in ds[max(0, i - 6):i + 1] if b in days[x])
        if c / low7 >= 1.3:
            add = circ[b] * (c - low7); tot += add; who.append((add, b, cap))
            y = ds[i - 1]
            if b in days[y]:
                low7y = min(days[x][b][1] for x in ds[max(0, i - 7):i] if b in days[x])
                if days[y][b][0] / low7y < 1.3: new.append(b)
    who.sort(reverse=True)
    print(f"{d[5:]} добавлено {tot/1e6:5.0f} млн $ · идут {len(who):2d} · " + ", ".join(f"{b} +{a/1e6:.0f} (капа {c/1e6:.0f})" for a, b, c in who[:5]) + (f" · новые: {', '.join(new)}" if new else ""))
