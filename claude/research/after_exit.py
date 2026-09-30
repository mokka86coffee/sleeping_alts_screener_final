#!/usr/bin/env python3
"""ЧТО СЛУЧИЛОСЬ С ЦЕНОЙ ПОСЛЕ ВЫХОДА (30.09, владелец: «ждать твоего анализа по коингласс — куда и что ушло через 2 и через 4 часа после сделки»).
Для каждой закрытой сделки обоих книг (по каждой книге отдельно): цены Binance 3m после выхода — за 2 ч и за 4 ч после выхода: максимум и минимум от ЦЕНЫ ВЫХОДА в сторону сделки (+ — дальше в нашу пользу, − — против),
закрытие через 2 и 4 ч; результат «если бы держали»: по закрытию через 2 и 4 ч от ЦЕНЫ ВХОДА. Фон Coinglass — из trade_facts.json (вершина 90 дн, ×90, CVD, интерес, вынос).
    .venv/bin/python claude/research/after_exit.py   → claude/research/after_exit.json, after_exit.md"""
import json, time, urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
H = Path(__file__).parent; L = timezone(timedelta(hours=3))
T = json.load(open(H / "cgr" / "trades.json"))
F = {f["tid"]: f for f in json.load(open(H / "trade_facts.json"))}
def tid(x): return f"{x['sym'][:-4]}_{datetime.fromtimestamp(x['t_in'], L):%m%d_%H%M}"
def one(x):
    if time.time() - x["t_out"] < 2 * 3600: return None
    t0 = int(x["t_out"] * 1000); e = x["px_in"]; xo = x["px_out"] or e; sd = x["side"]
    try:
        k = json.load(urllib.request.urlopen(f"https://fapi.binance.com/fapi/v1/klines?symbol={x['sym']}&interval=3m&startTime={t0}&endTime={t0 + 4 * 3600_000}&limit=100000".replace("&limit=100000", "&limit=1000"), timeout=20))
    except Exception:
        return None
    if not k: return None
    out = dict(tid=tid(x), sym=x["sym"], book=x["book"], side=sd, res=x["res"], why=x["why"], t_in=x["t_in"], t_out=x["t_out"])
    for h in (2, 4):
        w = [b for b in k if int(b[0]) < t0 + h * 3600_000]
        if len(w) < h * 15: continue                                                     # 4 ч ещё не прошло — не считаем
        hi = max(float(b[2]) for b in w); lo = min(float(b[3]) for b in w); c = float(w[-1][4])
        fav = (hi / xo - 1) * 100 if sd == 1 else (1 - lo / xo) * 100                    # лучший ход от цены выхода в нашу сторону
        adv = (lo / xo - 1) * 100 if sd == 1 else (1 - hi / xo) * 100                    # худший (против)
        out[f"fav{h}"] = round(fav, 2); out[f"adv{h}"] = round(adv, 2)
        out[f"cl{h}"] = round((c / xo - 1) * 100 * sd, 2)                                # закрытие от цены выхода
        out[f"hold{h}"] = round((c / e - 1) * 100 * sd, 2)                                # если бы держали: от цены входа
    return out
with ThreadPoolExecutor(8) as ex: R = [r for r in ex.map(one, T) if r]
for r in R: r.update({k: F[r["tid"]].get(k) for k in ("x90", "from_hi90", "cvd_s7", "cvd_f7", "oi7", "basis", "fund", "long_pre", "short_pre")} if r["tid"] in F else {})
json.dump(R, open(H / "after_exit.json", "w"), ensure_ascii=False, indent=0)
print(len(R), "сделок с ходом после выхода; с 4 ч:", sum(1 for r in R if "fav4" in r))
