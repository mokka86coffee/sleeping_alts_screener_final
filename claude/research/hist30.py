#!/usr/bin/env python3
"""ИСТОРИЯ 30 ДНЕЙ ПО ПОЛУЧАСАМ С BINANCE (26.09) — для денежных прогонов книг «второй ход» и «конец», которым в
архиве cq_v2/intraday не хватает полей: спот есть только с 23.09, фандинг с ~23.09, интерес с ~18.09.
Собирает по каждой монете архива: фьючерсные свечи 30м (px/h/l, оборот, дельта тейкеров), историю интереса
(openInterestHist 30м, глубина Binance — 30 дн), спотовые свечи 30м (дельта спота = 2×тейкер-покупки − оборот),
фандинг (в %, последняя выплата на момент свечи). Формат строк — как в архиве, чтобы signal() книг работал без правок.
    python3 claude/research/hist30.py            # все монеты архива → cq_v2/hist30/<монета>.json
    python3 claude/research/hist30.py ARK PHA    # только эти
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
from core_http import get_json                                      # noqa: E402

ARCH = BASE / "cq_v2" / "intraday"
OUT = BASE / "cq_v2" / "hist30"
DAYS = 30
BAR = 1_800_000


def klines(url, sym, start, end):
    out = []
    t = start
    while t < end:
        k = get_json(url, {"symbol": sym, "interval": "30m", "startTime": t, "endTime": end, "limit": 1000}, quiet_400=True, weight=5)
        if not k:
            break
        out += k
        t = int(k[-1][0]) + BAR
        if len(k) < 1000:
            break
    return out


def oi_hist(sym, start, end):
    out = {}
    e = end
    while e > start:
        k = get_json("https://fapi.binance.com/futures/data/openInterestHist",
                     {"symbol": sym, "period": "30m", "limit": 500, "endTime": e}, quiet_400=True, weight=1)
        if not k:
            break
        for r in k:
            out[int(r["timestamp"])] = float(r["sumOpenInterest"])
        e = int(k[0]["timestamp"]) - BAR
        if len(k) < 500:
            break
    return out


def funding(sym, start):
    k = get_json("https://fapi.binance.com/fapi/v1/fundingRate", {"symbol": sym, "startTime": start, "limit": 1000}, quiet_400=True) or []
    return sorted((int(r["fundingTime"]), float(r["fundingRate"]) * 100) for r in k)


def build(sym):
    now = int(time.time() * 1000) // BAR * BAR
    start = now - DAYS * 86400_000
    fut = klines("https://fapi.binance.com/fapi/v1/klines", sym, start, now)
    if not fut:
        return None
    spot = {int(k[0]): k for k in klines("https://api.binance.com/api/v3/klines", sym, start, now)}
    oi = oi_hist(sym, start, now)
    fr = funding(sym, start - 86400_000)
    rows, j = [], 0
    for k in fut:
        t = int(k[0])
        if t + BAR > now:
            continue
        while j + 1 < len(fr) and fr[j + 1][0] <= t + BAR:
            j += 1
        f = fr[j][1] if fr and fr[j][0] <= t + BAR else None
        qv, tbq = float(k[7]), float(k[10])
        s = spot.get(t)
        rows.append({"t": t, "px": float(k[4]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]),
                     "oi": oi.get(t), "funding": f, "kv": {"v": float(k[5]), "qv": qv},
                     "fut": {"b": tbq, "s": qv - tbq, "d": 2 * tbq - qv},
                     "spot": ({"qv": float(s[7]), "d": 2 * float(s[10]) - float(s[7])} if s else None)})
    return rows


def main():
    syms = [a.upper() + ("" if a.upper().endswith("USDT") else "USDT") for a in sys.argv[1:]] or \
           sorted(p.stem.upper() + "USDT" for p in ARCH.glob("*.jsonl"))
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    for n, s in enumerate(syms, 1):
        p = OUT / f"{s[:-4].lower()}.json"
        if p.exists() and time.time() - p.stat().st_mtime < 6 * 3600:
            continue
        rows = build(s)
        if rows:
            p.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        print(f"{n}/{len(syms)} {s[:-4]} · строк {len(rows) if rows else 0} · с интересом {sum(1 for r in rows if r['oi']) if rows else 0} "
              f"· со спотом {sum(1 for r in rows if r['spot']) if rows else 0} · {time.time() - t0:.0f} с", flush=True)


if __name__ == "__main__":
    main()
