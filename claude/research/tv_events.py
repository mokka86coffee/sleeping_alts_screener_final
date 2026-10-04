#!/usr/bin/env python3
"""ВСЕ ХОДЫ ×2 ЗА ПЕРИОД: ЧТО БЫЛО ДО СТАРТА (03.10, владелец: «ищи закономерности по всем монетам, которые дали x2-5, ищи почему и какая может быть следующей»).
Ход: от дневного минимума до максимума в следующие 30 дней ≥ ×2; по монете ходы не пересекаются; монета ≥ 180 дней истории на день старта.
День старта s = день минимума. Признаки берутся по закрытию дня s−1 (до минимума ещё никто не знает) и переводятся в место на доске в тот же день (0 = самое низкое значение на доске, 100 = самое высокое).
Если признак не отличает лидеров, медиана места ≈ 50. Дальше: «зажигание» = первый день после s с закрытием ≥ +25 % от минимума; сколько хода остаётся после него.
Данные TradingView (tvd/*_1D.json). Только запись."""
import sys, math, json
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict, Counter
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from tv_rules import load, D
from tv_leaders import feats
X = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
def main():
    C = load(); B = {}
    for k in (7, 30):
        acc = defaultdict(list)
        for F in C.values():
            for i in range(k, F["n"]):
                if F["c"][i - k] > 0: acc[int(F["t"][i])].append(F["c"][i] / F["c"][i - k] - 1)
        for t, a in acc.items(): B[(t, k)] = float(np.median(a))
    byd = defaultdict(dict)
    for sym, F in C.items():
        for i in range(180, F["n"]): byd[int(F["t"][i])][sym] = feats(F, i, B)
    keys = list(next(iter(next(iter(byd.values())).values())).keys())
    def pct(t, sym, k):
        g = byd.get(t)
        if not g or sym not in g or math.isnan(g[sym][k]): return float("nan")
        vals = [r[k] for r in g.values() if not math.isnan(r[k])]
        return sum(1 for v in vals if v < g[sym][k]) / max(1, len(vals) - 1) * 100
    ev = []
    for sym, F in C.items():
        n = F["n"]; i = 181
        while i < n - 3:
            lo = F["l"][i]
            if lo > F["l"][max(181, i - 10):i].min() if i > 181 else False: i += 1; continue      # минимум не ниже прошлых 10 дн — не старт
            j1 = min(n, i + 31); k = i + int(np.argmax(F["h"][i:j1])); hi = F["h"][k]
            if hi / lo >= X and F["l"][i:k + 1].min() >= lo * 0.999:
                ig = next((j for j in range(i, k + 1) if F["c"][j] >= lo * 1.25), None)
                ev.append(dict(sym=sym, s=i, e=k, t=int(F["t"][i]), x=hi / lo, days=k - i, ig=ig, left=(hi / F["c"][ig] - 1) if ig is not None else float("nan"),
                               igdd=(F["l"][ig + 1:k + 1].min() / F["c"][ig] - 1) if ig is not None and k > ig else 0.0,
                               pc={kk: pct(int(F["t"][i - 1]), sym, kk) for kk in keys}, raw=byd[int(F["t"][i - 1])].get(sym, {})))
                i = k + 1
            else: i += 1
    print(f"ходов ×{X:g}+: {len(ev)} у {len({e['sym'] for e in ev})} монет из {len(C)}")
    cm = Counter(datetime.fromtimestamp(e["t"], timezone.utc).strftime("%y-%m") for e in ev); print("по месяцам старта:", " ".join(f"{m}:{c}" for m, c in sorted(cm.items())))
    cd = Counter(datetime.fromtimestamp(e["t"], timezone.utc).strftime("%d.%m.%y") for e in ev); print("дни с наибольшим числом стартов:", ", ".join(f"{d} — {c}" for d, c in cd.most_common(8)))
    print(f"размер: медиана ×{np.median([e['x'] for e in ev]):.2f}; ×3+ — {sum(1 for e in ev if e['x'] >= 3)}; ×5+ — {sum(1 for e in ev if e['x'] >= 5)}; дней от минимума до максимума: медиана {np.median([e['days'] for e in ev]):.0f}")
    print("\nМЕСТО НА ДОСКЕ ЗА ДЕНЬ ДО СТАРТА (0–100; 50 = как все): медиана · доля в верхней пятой · доля в нижней пятой")
    out = []
    for k in keys:
        v = [e["pc"][k] for e in ev if not math.isnan(e["pc"][k])]
        if len(v) < 30: continue
        out.append((abs(np.median(v) - 50), k, np.median(v), sum(1 for x in v if x >= 80) / len(v) * 100, sum(1 for x in v if x <= 20) / len(v) * 100, len(v)))
    for _, k, m, hi, lo, n in sorted(out, reverse=True): print(f"  {k:17s} медиана {m:5.1f} · верх {hi:4.1f}% · низ {lo:4.1f}% (n={n})")
    print("\nСЫРЫЕ ЗНАЧЕНИЯ ЗА ДЕНЬ ДО СТАРТА (медиана; 25–75 %):")
    for k in ("mom7", "mom30", "mom90", "pos30", "pos90", "up_from_lo90", "flat14", "atr", "oi7", "oi14", "oi30", "f7", "fneg7", "liq_short_share7", "vol3_20", "sq"):
        v = [e["raw"].get(k, float("nan")) for e in ev]; v = [x for x in v if not math.isnan(x)]
        if v: print(f"  {k:17s} {np.median(v):+.3f} ({np.percentile(v, 25):+.3f} … {np.percentile(v, 75):+.3f})")
    ig = [e for e in ev if e["ig"] is not None]
    print(f"\nПОСЛЕ ЗАЖИГАНИЯ (первое закрытие ≥ +25 % от минимума), n={len(ig)}: дней от минимума до зажигания — медиана {np.median([e['ig'] - e['s'] for e in ig]):.0f}; "
          f"остаток хода до максимума — медиана +{np.median([e['left'] for e in ig]) * 100:.0f}%; худшая просадка от цены зажигания до максимума — медиана {np.median([e['igdd'] for e in ig]) * 100:.0f}%")
    json.dump([{k: v for k, v in e.items() if k != "raw"} | dict(date=datetime.fromtimestamp(e["t"], timezone.utc).strftime("%d.%m.%y")) for e in ev], open(D / f"_events_x{X:g}.json", "w"), ensure_ascii=False)
    print("\nкрупнейшие:", ", ".join(f"{e['sym']} ×{e['x']:.1f} ({datetime.fromtimestamp(e['t'], timezone.utc):%d.%m.%y}, {e['days']} дн)" for e in sorted(ev, key=lambda e: -e["x"])[:25]))
    print("последние:", ", ".join(f"{e['sym']} ×{e['x']:.1f} ({datetime.fromtimestamp(e['t'], timezone.utc):%d.%m.%y})" for e in sorted(ev, key=lambda e: -e["t"])[:25]))
if __name__ == "__main__": main()
