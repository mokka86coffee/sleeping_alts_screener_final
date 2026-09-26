"""ВЫНОС ЛОНГОВ ВНИЗУ → ВВЕРХ, ВЫНОС ШОРТОВ ВВЕРХУ → ВНИЗ (26.09, владелец по PLAY 3h: «ликвидация лонгов — поход вверх, ликвидация шортов — поход вниз»).
Проверка на дневках cq_v2/<coin>.json (liq: long/short_liquidations_usd, ohlcv), ~200 дней, все монеты. Мерки разметки, не правила:
  всплеск — ликвидации стороны за день ≥ SPIKE_X к медиане предыдущих 20 дней и ≥ MIN_USD;
  «внизу» — закрытие дня в пределах 10% от минимума закрытий за 20 дней; «вверху» — в пределах 10% от максимума за 20 дней.
Исход: закрытие через 3 и 5 дней к закрытию дня всплеска; доля «+10% раньше −10%» за 5 дней (по закрытиям). База — все дни.
    .venv/bin/python claude/research/liq_side.py
"""
import json, statistics as st
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
SPIKE_X, MIN_USD = 3.0, 5000.0
def series(d, key):
    rows = sorted((r for r in d.get(key, []) if r.get("datetime")), key=lambda r: r["datetime"])
    return rows
def fwd(closes, i, k): return (closes[i + k] / closes[i] - 1) * 100 if i + k < len(closes) else None
def first10(closes, i):
    for j in range(i + 1, min(i + 6, len(closes))):
        r = closes[j] / closes[i] - 1
        if r >= 0.10: return "плюс10"
        if r <= -0.10: return "минус10"
    return "ни то"
sigL, sigS, base = [], [], []
for p in sorted((ROOT / "cq_v2").glob("*.json")):
    if p.stem.startswith("_") or p.stem in ("btc",): continue
    try: d = json.loads(p.read_text())
    except Exception: continue
    o = series(d, "ohlcv"); lq = {r["datetime"][:10]: r for r in d.get("liq", [])}
    if len(o) < 40: continue
    closes = [float(r["close"]) for r in o]; days = [r["datetime"][:10] for r in o]
    for i in range(25, len(o) - 6):
        r = lq.get(days[i]); 
        if not r: continue
        L = float(r.get("long_liquidations_usd") or 0); S = float(r.get("short_liquidations_usd") or 0)
        prevL = [float((lq.get(days[j]) or {}).get("long_liquidations_usd") or 0) for j in range(i - 20, i)]
        prevS = [float((lq.get(days[j]) or {}).get("short_liquidations_usd") or 0) for j in range(i - 20, i)]
        mL = st.median(prevL) or 0; mS = st.median(prevS) or 0
        lo20, hi20 = min(closes[i - 20:i + 1]), max(closes[i - 20:i + 1])
        at_low = closes[i] <= lo20 * 1.10; at_high = closes[i] >= hi20 * 0.90
        rec = dict(sym=p.stem, day=days[i], f3=fwd(closes, i, 3), f5=fwd(closes, i, 5), first=first10(closes, i))
        base.append(rec)
        if L >= MIN_USD and (mL == 0 or L >= SPIKE_X * mL) and L > S:
            sigL.append(dict(rec, at_low=at_low, at_high=at_high, x=L / mL if mL else 99))
        if S >= MIN_USD and (mS == 0 or S >= SPIKE_X * mS) and S > L:
            sigS.append(dict(rec, at_low=at_low, at_high=at_high, x=S / mS if mS else 99))
def stat(name, g):
    g = [x for x in g if x["f5"] is not None]
    if len(g) < 8: print(f"  {name:<48} n={len(g):5d} — мало"); return
    f3 = [x["f3"] for x in g if x["f3"] is not None]; f5 = [x["f5"] for x in g]; c = Counter(x["first"] for x in g)
    print(f"  {name:<48} n={len(g):5d} · через 3 дн выше {sum(1 for v in f3 if v > 0) / len(f3) * 100:3.0f}% (мед {st.median(f3):+.1f}%) · через 5 дн выше {sum(1 for v in f5 if v > 0) / len(f5) * 100:3.0f}% (мед {st.median(f5):+.1f}%)"
          f" · +10% раньше −10% {c['плюс10'] / len(g) * 100:3.0f}% · −10% раньше {c['минус10'] / len(g) * 100:3.0f}%")
print(f"дней всего {len(base)}; всплесков лонгов {len(sigL)}, шортов {len(sigS)}\n")
stat("БАЗА — все дни", base)
stat("ВЫНОС ЛОНГОВ (≥×3 к медиане 20 дн, лонгов больше шортов)", sigL)
stat("  вынос лонгов ВНИЗУ (закрытие ≤ +10% от минимума 20 дн)", [x for x in sigL if x["at_low"]])
stat("  вынос лонгов ВВЕРХУ", [x for x in sigL if x["at_high"]])
stat("  вынос лонгов внизу, сильный (≥×10)", [x for x in sigL if x["at_low"] and x["x"] >= 10])
stat("ВЫНОС ШОРТОВ (≥×3, шортов больше лонгов)", sigS)
stat("  вынос шортов ВВЕРХУ (закрытие ≥ −10% от максимума 20 дн)", [x for x in sigS if x["at_high"]])
stat("  вынос шортов ВНИЗУ", [x for x in sigS if x["at_low"]])
stat("  вынос шортов вверху, сильный (≥×10)", [x for x in sigS if x["at_high"] and x["x"] >= 10])
print("\nПримеры «вынос лонгов внизу» за сентябрь (монета · день · ×медиана · через 3 дн · через 5 дн):")
for x in sorted([x for x in sigL if x["at_low"] and x["day"] >= "2026-09-01"], key=lambda x: -x["x"])[:12]:
    print(f"  {x['sym'].upper():<10} {x['day']} · ×{x['x']:5.1f} · {x['f3']:+6.1f}% · {x['f5']:+6.1f}%")
