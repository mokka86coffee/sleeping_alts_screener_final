#!/usr/bin/env python3
"""ВЫНОС ПРИ УСЛОВИЯХ (30.09, владелец «да»: усиливается ли реакция цены после выноса, если вынос у вершины 90 дн / крупный / при падении цены до него / при росте интереса).
Шаг корзины 30 мин (шаг не важен — flush_bin_test.py). Вынос стороны = корзина ≥ самой крупной прошлой корзины монеты (история ≥ 24 ч). Реакция — ход цены в сторону разворота
(вынос лонгов → вверх, шортов → вниз) через 1 и 2 ч после конца корзины, %. Признаки: сумма выноса ($) — верхняя треть против остальных; у вершины 90 дн (цена не ниже 10% от максимума);
ход цены за час до выноса (в сторону выноса ≥ 1.5%: падение перед выносом лонгов / рост перед выносом шортов); интерес Binance за час на конце корзины (≥ +1% / ≤ −1%). Пороги признаков взяты для проверки, не для решений.
    .venv/bin/python claude/research/flush_cond_test.py"""
import json, sys, statistics as st
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from core_http import get_json
ev = {}
for p in sorted((ROOT / "cq_v2" / "liq").glob("*.jsonl")):
    for ln in p.open(encoding="utf-8", errors="ignore"):
        try: r = json.loads(ln)
        except ValueError: continue
        if r.get("side") in ("long", "short"): ev.setdefault(r["sym"], []).append((int(r["t"]), r["side"], float(r.get("usd") or 0)))
coins = [s for s, v in ev.items() if len(v) >= 100]
def load(sym):
    k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "15m", "limit": 1000}, quiet_400=True) or []
    d = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "1d", "limit": 120}, quiet_400=True) or []
    oi = get_json("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": sym, "period": "1h", "limit": 500}, quiet_400=True) or []
    return sym, dict(k={int(x[0]): (float(x[1]), float(x[4])) for x in k}, d=[(int(x[0]), float(x[2])) for x in d],
                     oi={int(x["timestamp"]) // 3_600_000 * 3_600_000: float(x["sumOpenInterestValue"]) for x in oi})
with ThreadPoolExecutor(8) as ex: D = dict(ex.map(load, coins))
B = 1_800_000
def px(kd, t):
    b = t // 900_000 * 900_000
    return kd[b][1] if b in kd else None
rows = []
for sym in coins:
    d = D[sym]; kd = d["k"]
    if not kd: continue
    t_min = min(t for t, s, u in ev[sym]) + 86_400_000
    for side in ("long", "short"):
        bins = {}
        for t, s, u in ev[sym]:
            if s == side: bins[t // B] = bins.get(t // B, 0.0) + u
        prev = 0.0
        for b in sorted(bins):
            te = (b + 1) * B
            if b * B >= t_min and bins[b] >= prev > 0:
                p0 = px(kd, te - 1); pm = px(kd, te - 1 - 3_600_000); p1 = px(kd, te + 3_600_000 - 1); p2 = px(kd, te + 7_200_000 - 1)
                if p0 and pm and p1 and p2:
                    sg = 1 if side == "long" else -1
                    hi = max((h for t, h in d["d"] if t <= te), default=None)
                    ho = te // 3_600_000 * 3_600_000; o1, o0 = d["oi"].get(ho), d["oi"].get(ho - 3_600_000)
                    rows.append(dict(side=side, usd=bins[b], r1=(p1 / p0 - 1) * 100 * sg, r2=(p2 / p0 - 1) * 100 * sg,
                                     pre=(p0 / pm - 1) * 100 * (-sg),               # ход цены за час до выноса в сторону выноса: для лонгов — падение (+), для шортов — рост (+)
                                     top=(p0 >= hi * 0.9) if hi else None, oi=((o1 / o0 - 1) * 100 if o1 and o0 else None)))
            prev = max(prev, bins[b])
def line(name, g):
    if len(g) < 15: return f"  {name:52} n={len(g):3} — мало"
    m1 = st.mean(x["r1"] for x in g); m2 = st.mean(x["r2"] for x in g); pos = sum(1 for x in g if x["r1"] > 0) * 100 // len(g); ge = sum(1 for x in g if x["r1"] >= 1) * 100 // len(g)
    return f"  {name:52} n={len(g):3}  1 ч: среднее {m1:+.2f}% · разворот {pos}% · ≥+1% {ge}%  | 2 ч: среднее {m2:+.2f}%"
for side, ttl in (("long", "ВЫНОС ЛОНГОВ → ждём вверх"), ("short", "ВЫНОС ШОРТОВ → ждём вниз")):
    G = [r for r in rows if r["side"] == side]
    q = sorted(r["usd"] for r in G)[2 * len(G) // 3] if G else 0
    print(f"\n{ttl}")
    print(line("все", G))
    print(line(f"сумма выноса — верхняя треть (≥ {q / 1e3:.0f}K$)", [r for r in G if r["usd"] >= q])); print(line("сумма выноса — остальные", [r for r in G if r["usd"] < q]))
    print(line("у вершины 90 дн (≥ −10% от макс.)", [r for r in G if r["top"]])); print(line("не у вершины 90 дн", [r for r in G if r["top"] is False]))
    print(line("до выноса цена шла в сторону выноса ≥ 1.5% за час", [r for r in G if r["pre"] >= 1.5])); print(line("до выноса цена шла в сторону выноса < 1.5%", [r for r in G if r["pre"] < 1.5]))
    print(line("интерес за час ≥ +1%", [r for r in G if r["oi"] is not None and r["oi"] >= 1])); print(line("интерес за час ≤ −1%", [r for r in G if r["oi"] is not None and r["oi"] <= -1]))
