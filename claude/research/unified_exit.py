#!/usr/bin/env python3
"""ЕДИНЫЙ ВЫХОД ДЛЯ ОБЕИХ СТОРОН (29.09, владелец: «мы выходим не всегда когда надо… я это уже больше 5 дней тебе прислал»): вынос ПРОТИВОПОЛОЖНОЙ стороны — выход
(лонг: вынесли шорты, шорт: вынесли лонги; в плюсе), стоп — за началом хода (лонг: минимум часа до входа, шорт: максимум часа до входа), срок — запас.
Данные — Coinglass Binance 15m (cgx/), ликвидации всех бирж. «Вынос» = час с ликвидациями стороны ≥ крупнейшего часа монеты за историю до входа (~10 дн).
Все 125 закрытых сделок быстрого бота 27–28.09; не проверено (те же дни)."""
import json
from pathlib import Path
H = Path(__file__).parent
T = json.load(open(H / "cgr" / "trades.json"))
def clean(v): return v if isinstance(v, (int, float)) and v == v else 0.0
def run(x, cap, hold_h, stop_mode, fuel, tp=None, pad=0.001):
    f = H / f"cgx/{x['sym']}_15.json"
    if not f.exists(): return None
    R = [r for r in json.load(open(f))["rows"] if r.get("c")]
    side, t0, e = x["side"], x["t_in"], x["px_in"]
    key = "liq_short" if side == 1 else "liq_long"
    hs = {}
    for r in R:
        h = int(r["t"] // 3600 * 3600); hs[h] = hs.get(h, 0) + clean(r.get(key))
    h0 = int(t0 // 3600 * 3600)
    past = [v for h, v in hs.items() if h < h0]
    top = max(past) if past and h0 - min(hs) >= 3 * 86400 else None
    pre = [r for r in R if t0 - 3600 - 900 <= r["t"] < t0]
    if stop_mode == "pct":
        stop = e * (1 - side * cap)
    else:                                                   # за началом хода, но не дальше cap
        base = min((r["l"] for r in pre), default=e) if side == 1 else max((r["h"] for r in pre), default=e)
        stop = base * (1 - side * pad)
        stop = max(stop, e * (1 - cap)) if side == 1 else min(stop, e * (1 + cap))
    end = t0 + hold_h * 3600
    for r in R:
        if r["t"] <= t0 or r["t"] > end: continue
        if (r["l"] <= stop) if side == 1 else (r["h"] >= stop): return ((stop / e - 1) * side) * 100
        if tp and ((r["h"] >= e * (1 + tp)) if side == 1 else (r["l"] <= e * (1 - tp))): return tp * 100
        h = int(r["t"] // 3600 * 3600)
        if fuel and top and h >= h0 and hs.get(h, 0) >= top and (r["c"] - e) * side > 0: return ((r["c"] / e - 1) * side) * 100
    last = [r for r in R if t0 < r["t"] <= end]
    return ((last[-1]["c"] / e - 1) * side) * 100 if last else None
def show(name, fn):
    out = {}
    for side, nm in ((1, "лонг"), (-1, "шорт")):
        v = [(x, fn(x)) for x in T if x["side"] == side]
        v = [(x, r) for x, r in v if r is not None]
        out[nm] = v
    line = name.ljust(52)
    for nm in ("лонг", "шорт"):
        r = [z[1] for z in out[nm]]
        line += f" | {nm} n={len(r)} +{sum(1 for z in r if z > 0)} {sum(r) * 10:+5.0f}$ худш {min(r):+.1f}%"
    tot = sum(z[1] for nm in out for z in out[nm]) * 10
    print(line, f"| всего {tot:+.0f}$")
    return out
show("факт бота", lambda x: x["res"])
for hold in (4, 24):
    for cap in (0.10, 0.15):
        show(f"вынос противоп. + стоп за началом хода (≤{cap*100:.0f}%) срок {hold}ч", lambda x: run(x, cap, hold, "start", True))
    show(f"вынос противоп. + стоп −10% срок {hold}ч", lambda x: run(x, 0.10, hold, "pct", True))
    show(f"вынос противоп. + стоп −10% + цель +5% срок {hold}ч", lambda x: run(x, 0.10, hold, "pct", True, 0.05))
show("только стоп за началом ≤15% + срок 24ч (без выноса)", lambda x: run(x, 0.15, 24, "start", False))
