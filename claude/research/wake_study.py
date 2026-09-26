#!/usr/bin/env python3
"""ПРОБУЖДЕНИЕ КАК ВХОД (26.09, владелец: Q +71%, US +32% за 3 ч, MARSCOIN — все вне очереди; «сейчас ты ещё в первых добавишь и что?»).
Событие по часовым свечам всех USDT-перпов Binance за 30 дн: оборот часа ≥ WAKE_X × медианы оборота предыдущих 24 ч,
оборот часа ≥ MIN_H $, закрытие часа ≥ +WAKE_PCT% к прошлому закрытию, и это первое такое событие за 48 ч (не продолжение).
Исход: вход по закрытию часа события, максимум за следующие 24 ч (+20%? +40%?), минимум за 24 ч (просадка), закрытие через 24 ч.
Разрез: оборот суток до события (спящая < 5M$ / наша ≥ 5M$), возраст листинга (< 180 / ≥ 180), ход до события за 24 ч.
    python3 claude/research/wake_study.py
"""
from __future__ import annotations
import json, statistics as stt, sys, time, datetime as dt
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
from core_http import get_json                                     # noqa: E402

WAKE_X, WAKE_PCT, MIN_H = 5.0, 3.0, 300_000
DAYS = 30


def hourly(sym):
    end = int(time.time() * 1000); start = end - DAYS * 86400_000
    out, t = [], start
    while t < end:
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "1h", "startTime": t, "endTime": end, "limit": 1000}, quiet_400=True, weight=5) or []
        if not k: break
        out += k; t = int(k[-1][0]) + 3600_000
        if len(k) < 1000: break
    return [(int(x[0]), float(x[4]), float(x[2]), float(x[3]), float(x[7])) for x in out]


def events(sym, k, onboard):
    ev = []
    last_ev = -10**18
    for i in range(25, len(k) - 24):
        t, c, h, l, qv = k[i]
        prev = [x[4] for x in k[i - 24:i]]
        med = stt.median(prev); day = sum(prev)
        if med <= 0 or qv < MIN_H or qv < WAKE_X * med:
            continue
        chg = (c / k[i - 1][1] - 1) * 100
        if chg < WAKE_PCT or t - last_ev < 48 * 3600_000:
            continue
        last_ev = t
        nxt = k[i + 1:i + 25]
        mx = max(x[2] for x in nxt) / c - 1; mn = min(x[3] for x in nxt) / c - 1; c24 = nxt[-1][1] / c - 1
        run24 = (c / k[i - 24][1] - 1) * 100
        age = (t - onboard) / 86400_000 if onboard else None
        ev.append(dict(sym=sym, t=t, chg=chg, x=qv / med, day_vol=day, age=age, run24=run24, mx=mx * 100, mn=mn * 100, c24=c24 * 100))
    return ev


def main():
    info = get_json("https://fapi.binance.com/fapi/v1/exchangeInfo") or {}
    syms = [(s["symbol"], int(s.get("onboardDate") or 0)) for s in info.get("symbols", []) if s["symbol"].endswith("USDT") and s.get("status") == "TRADING"]
    print(f"перпов {len(syms)} · качаю часовые за {DAYS} дн…", flush=True)
    allev = []
    def work(p):
        s, ob = p
        try: return events(s, hourly(s), ob)
        except Exception: return []
    with ThreadPoolExecutor(6) as ex:
        for r in ex.map(work, syms): allev += r
    Path(BASE / "claude/research/wake_events.json").write_text(json.dumps(allev, ensure_ascii=False), encoding="utf-8")
    def rep(name, rows):
        if not rows: print(f"  {name:34} n=0"); return
        p20 = sum(1 for r in rows if r["mx"] >= 20) / len(rows) * 100; p40 = sum(1 for r in rows if r["mx"] >= 40) / len(rows) * 100
        neg = sum(1 for r in rows if r["c24"] < 0) / len(rows) * 100
        print(f"  {name:34} n={len(rows):4} · +20% за сутки {p20:4.0f}% · +40% {p40:4.0f}% · закрытие через сутки ниже входа {neg:3.0f}% · "
              f"медиана макс {stt.median(r['mx'] for r in rows):+5.1f}% · медиана мин {stt.median(r['mn'] for r in rows):+5.1f}% · медиана закр {stt.median(r['c24'] for r in rows):+5.1f}%")
    print(f"событий {len(allev)} (оборот часа ≥ ×{WAKE_X:.0f} медианы суток, ≥ {MIN_H/1e3:.0f}K$, час ≥ +{WAKE_PCT:.0f}%, первое за 48 ч)")
    rep("все", allev)
    rep("спящая (сутки до < 5M$)", [r for r in allev if r["day_vol"] < 5e6])
    rep("наша (сутки до ≥ 5M$)", [r for r in allev if r["day_vol"] >= 5e6])
    rep("листинг < 180 дн", [r for r in allev if r["age"] is not None and r["age"] < 180])
    rep("листинг ≥ 180 дн", [r for r in allev if r["age"] is None or r["age"] >= 180])
    rep("час ≥ +10%", [r for r in allev if r["chg"] >= 10])
    rep("час +3…10%", [r for r in allev if r["chg"] < 10])
    rep("оборот ×5…10", [r for r in allev if r["x"] < 10])
    rep("оборот ≥ ×10", [r for r in allev if r["x"] >= 10])
    rep("до события за сутки < +5%", [r for r in allev if r["run24"] < 5])
    rep("до события за сутки ≥ +5%", [r for r in allev if r["run24"] >= 5])
    rep("спящая · час ≥ +10% · ×10", [r for r in allev if r["day_vol"] < 5e6 and r["chg"] >= 10 and r["x"] >= 10])


if __name__ == "__main__":
    main()
