#!/usr/bin/env python3
"""ШАГ «ВЫНОСА»: 5 / 15 / 30 / 60 МИН (30.09, владелец «а почему с шагом 1 час?» → «проверь сейчас»).
Данные: события потока ликвидаций OKX+Bybit (cq_v2/liq, с 25.09) — время, монета, сторона, сумма; цены — 15-мин свечи Binance.
Вынос стороны в корзине шага B: сумма стороны в корзине ≥ самой крупной прошлой корзины монеты (история не короче 24 ч, прошлый максимум > 0) — как `_flush` бота, но с шагом B.
Реакция: после конца корзины (вынос лонгов → ждём разворот вверх, вынос шортов → вниз) ход цены через 1 и 2 ч в сторону разворота, %. Для сравнения — та же реакция на всех барах (без условия).
    .venv/bin/python claude/research/flush_bin_test.py"""
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
print("монет с ≥ 100 событий:", len(coins), " событий всего:", sum(len(ev[s]) for s in coins))
def kl(sym):
    k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "15m", "limit": 1000}, quiet_400=True) or []
    return sym, {int(x[0]): (float(x[1]), float(x[4])) for x in k}
with ThreadPoolExecutor(8) as ex: P = dict(ex.map(kl, coins))
def px_at(kd, t):                     # цена закрытия 15-мин бара, содержащего момент t
    b = t // 900_000 * 900_000
    return kd[b][1] if b in kd else None
BINS = {"5 мин": 300_000, "15 мин": 900_000, "30 мин": 1_800_000, "60 мин": 3_600_000}
res = {}
for name, B in BINS.items():
    for side in ("long", "short"):
        rows = []
        for sym in coins:
            kd = P.get(sym)
            if not kd: continue
            ts = sorted(t for t in kd)
            t_min = min(t for t, s_, u in ev[sym]) + 86_400_000          # первые сутки — разгон истории
            bins = {}
            for t, s_, u in ev[sym]:
                if s_ == side: bins[t // B] = bins.get(t // B, 0.0) + u
            prev = 0.0
            for b in sorted(bins):
                te = (b + 1) * B
                if b * B >= t_min and bins[b] >= prev > 0:
                    p0 = px_at(kd, te - 1)
                    r = []
                    for h in (1, 2):
                        p1 = px_at(kd, te + h * 3_600_000 - 1)
                        r.append(None if not p0 or not p1 else (p1 / p0 - 1) * 100 * (1 if side == "long" else -1))
                    if all(x is not None for x in r): rows.append(r)
                prev = max(prev, bins[b])
        res[(name, side)] = rows
# база: реакция на всех 15-мин барах
base = {"long": [], "short": []}
for sym in coins:
    kd = P.get(sym) or {}
    for t in sorted(kd)[::4]:
        p0 = kd[t][1]; p1 = kd.get(t + 3_600_000, (0, None))[1]; p2 = kd.get(t + 7_200_000, (0, None))[1]
        if p1 and p2:
            for side, sg in (("long", 1), ("short", -1)): base[side].append([(p1 / p0 - 1) * 100 * sg, (p2 / p0 - 1) * 100 * sg])
print("\nреакция цены В СТОРОНУ РАЗВОРОТА после конца корзины с выносом (лонги → вверх, шорты → вниз), % от цены на конце корзины")
for side in ("long", "short"):
    b = base[side]
    print(f"\n{'ВЫНОС ЛОНГОВ → вверх' if side == 'long' else 'ВЫНОС ШОРТОВ → вниз'}   (база — все бары: 1 ч {st.mean(x[0] for x in b):+.3f}% · 2 ч {st.mean(x[1] for x in b):+.3f}%, n={len(b)})")
    for name in BINS:
        r = res[(name, side)]
        if not r: print(f"  {name:6} нет событий"); continue
        m1 = st.mean(x[0] for x in r); m2 = st.mean(x[1] for x in r)
        med1 = st.median(x[0] for x in r); pos1 = sum(1 for x in r if x[0] > 0) * 100 // len(r); ge1 = sum(1 for x in r if x[0] >= 1) * 100 // len(r)
        print(f"  шаг {name:6} событий {len(r):5}   через 1 ч: среднее {m1:+.2f}% · медиана {med1:+.2f}% · в сторону разворота {pos1}% · ≥ +1% {ge1}%   | через 2 ч: среднее {m2:+.2f}%")
