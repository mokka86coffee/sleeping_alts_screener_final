#!/usr/bin/env python3
"""ЛИДЕРЫ ЗА 14 ДНЕЙ И ИХ ТРЁХМИНУТКИ (26.09, владелец: «возьми всю историю за две недели по всем лидерам по трёхминутным свечам»).
Лидеры — output/leaders.json проекта (144 монеты, владелец 26.09).
По каждому: 3м свечи (цена, объём, тейкер-покупки), интерес 5м (openInterestHist), фандинг, толпа по счетам 5м, топы 5м.
    python3 claude/research/hist3m.py            # → cq_v2/hist3m/<монета>.json
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
from core_http import get_json                                     # noqa: E402
OUT = BASE / "cq_v2" / "hist3m"; DAYS = 14
NOW = int(time.time() * 1000) // 180_000 * 180_000; START = NOW - DAYS * 86400_000


def klines(sym, interval, start, end, step):
    out, t = [], start
    while t < end:
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": interval, "startTime": t, "endTime": end, "limit": 1000}, quiet_400=True, weight=5) or []
        if not k: break
        out += k; t = int(k[-1][0]) + step
        if len(k) < 1000: break
    return out


def is_leader(sym):
    k = klines(sym, "1h", START - 48 * 3600_000, NOW, 3600_000)
    c = [float(x[4]) for x in k]
    best = 0.0
    for i in range(48, len(c)):
        lo = min(c[i - 48:i])
        if lo: best = max(best, c[i] / lo - 1)
    return (sym, best) if best >= 0.40 else None


def series(url, params, key_t, key_v, start, end, step, limit=500):
    out, e = {}, end
    while e > start:
        k = get_json(url, dict(params, limit=limit, endTime=e), quiet_400=True) or []
        if not k: break
        for r in k: out[int(r[key_t])] = float(r[key_v])
        e = int(k[0][key_t]) - step
        if len(k) < limit: break
    return out


def build(sym):
    k3 = klines(sym, "3m", START, NOW, 180_000)
    if len(k3) < 1000: return None
    oi = series("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": sym, "period": "5m"}, "timestamp", "sumOpenInterestValue", START, NOW, 300_000)
    ls = series("https://fapi.binance.com/futures/data/globalLongShortAccountRatio", {"symbol": sym, "period": "5m"}, "timestamp", "longShortRatio", START, NOW, 300_000)
    tp = series("https://fapi.binance.com/futures/data/topLongShortPositionRatio", {"symbol": sym, "period": "5m"}, "timestamp", "longShortRatio", START, NOW, 300_000)
    fr = sorted((int(r["fundingTime"]), float(r["fundingRate"]) * 100) for r in (get_json("https://fapi.binance.com/fapi/v1/fundingRate", {"symbol": sym, "startTime": START - 86400_000, "limit": 1000}, quiet_400=True) or []))
    rows, j = [], 0
    last = {"oi": None, "ls": None, "tp": None}
    for x in k3:
        t = int(x[0]); t5 = t // 300_000 * 300_000
        while j + 1 < len(fr) and fr[j + 1][0] <= t + 180_000: j += 1
        for key, src in (("oi", oi), ("ls", ls), ("tp", tp)):
            if t5 in src: last[key] = src[t5]
        rows.append([t, float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[7]), float(x[10]), last["oi"], (fr[j][1] if fr and fr[j][0] <= t + 180_000 else None), last["ls"], last["tp"]])
    return rows      # t, o, h, l, c, qv, taker_buy_q, oi_usd, funding_pct, crowd_ls, top_ls


def main():
    # 26.09 23:20 владелец: лидеры = output/leaders.json (144 монеты), без своего отбора
    ld = json.loads((BASE / "output" / "leaders.json").read_text(encoding="utf-8"))
    leaders = [(s, float((v or {}).get("max_change_pct") or 0)) for s, v in ld.items()]
    t0 = time.time()
    print(f"лидеров из output/leaders.json: {len(leaders)}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "_leaders.json").write_text(json.dumps(leaders), encoding="utf-8")
    def work(p):
        s, best = p
        f = OUT / f"{s[:-4].lower()}.json"
        if f.exists() and time.time() - f.stat().st_mtime < 6 * 3600: return s, "кэш"
        rows = build(s)
        if rows: f.write_text(json.dumps(rows), encoding="utf-8")
        return s, (len(rows) if rows else 0)
    with ThreadPoolExecutor(4) as ex:
        for n, (s, r) in enumerate(ex.map(work, leaders), 1):
            print(f"{n}/{len(leaders)} {s[:-4]} {r} · {time.time()-t0:.0f} с", flush=True)


if __name__ == "__main__":
    main()
