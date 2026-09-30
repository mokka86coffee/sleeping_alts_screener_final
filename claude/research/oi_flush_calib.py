#!/usr/bin/env python3
"""КАЛИБРОВКА ПРИБЛИЖЕНИЯ «ВЫНОС ПО ИНТЕРЕСУ» (30.09, владелец «да»: потока ликвидаций Binance с этой машины нет — считаем вынос по падению интереса на баре).
Для монет, где поток OKX+Bybit даёт события: 5-мин бары Binance за ~40 ч — изменение интереса на баре (%), ход цены (%), и ликвидации из потока в эти 5 минут (сторона:
лонги — при падении цены, шорты — при росте). Смотрим, при каком падении интереса на баре ликвидации в потоке действительно есть — порог берём из этого счёта.
    .venv/bin/python claude/research/oi_flush_calib.py"""
import json, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from core_http import get_json
ev = {}
for p in sorted((ROOT / "cq_v2" / "liq").glob("*.jsonl"))[-3:]:
    for ln in p.open(encoding="utf-8", errors="ignore"):
        try: r = json.loads(ln)
        except ValueError: continue
        if r.get("side") in ("long", "short"): ev.setdefault(r["sym"], []).append((int(r["t"]), r["side"], float(r.get("usd") or 0)))
coins = [s for s, v in ev.items() if len(v) >= 20]
print("монет с потоком ≥ 20 событий:", len(coins))
def bars(sym):
    oi = get_json("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": sym, "period": "5m", "limit": 500}, quiet_400=True) or []
    k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "5m", "limit": 500}, quiet_400=True) or []
    if len(oi) < 50 or len(k) < 50: return sym, []
    kd = {int(x[0]): (float(x[1]), float(x[4])) for x in k}
    o = {int(x["timestamp"]) // 300_000 * 300_000: float(x["sumOpenInterestValue"]) for x in oi}
    ts = sorted(t for t in o if t in kd)
    out = []
    for a, b in zip(ts, ts[1:]):
        if b - a != 300_000 or o[a] <= 0: continue
        oc = (o[b] / o[a] - 1) * 100; op, cp = kd[b]; ret = (cp / op - 1) * 100
        e = [x for x in ev.get(sym, []) if b <= x[0] < b + 300_000]
        out.append((sym, b, oc, ret, sum(x[2] for x in e if x[1] == "long"), sum(x[2] for x in e if x[1] == "short")))
    return sym, out
with ThreadPoolExecutor(8) as ex: R = [r for s, rs in ex.map(bars, coins) for r in rs]
print("баров 5 мин:", len(R), "с ликвидациями в потоке:", sum(1 for r in R if r[4] + r[5] > 0))
for thr in (-0.2, -0.3, -0.5, -0.75, -1.0, -1.5, -2.0):
    sel = [r for r in R if r[2] <= thr]
    hit = [r for r in sel if r[4] + r[5] >= 1000]
    hitL = [r for r in sel if r[3] < 0 and r[4] >= 1000]; hitS = [r for r in sel if r[3] > 0 and r[5] >= 1000]
    base = [r for r in R if r[2] > thr]; bh = [r for r in base if r[4] + r[5] >= 1000]
    print(f"падение интереса на баре ≤ {thr:+.2f}%: баров {len(sel):5}  с ликвидациями ≥ 1K$ в потоке {len(hit):4} ({(len(hit) * 100 // max(1, len(sel)))}%)  "
          f"| у остальных {len(bh) * 100 // max(1, len(base))}%  | лонги при падении цены {len(hitL)}, шорты при росте {len(hitS)}")
