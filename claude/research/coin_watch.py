#!/usr/bin/env python3
"""НАБЛЮДЕНИЕ ЗА МОНЕТОЙ РАЗ В 3 МИНУТЫ (28.09, владелец: «следи за sei», «каждые 3 минуты проверяй»).

Одна строка: цена и ход 3 мин / 1 ч / 24 ч, интерес 1 ч и за 5 мин, фандинг, толпа по счетам, покупатели за 15 мин, ликвидации по сторонам
за 3 мин (поток cq_v2/liq, OKX+Bybit), крупнейшие плиты стакана в ±5% (журнал output/depth_events.jsonl). Метки по правилам реестра —
без своих порогов, только сравнение с собой (прошлая проверка, максимум суток):
  ⚑ новый максимум 7 дн / суток;
  ⚑ R21 — вынос шортов за 3 мин — максимум за сутки у этой монеты;
  ⚑ интерес падает, цена растёт (закрываются) / интерес растёт, цена падает (набирают против);
  ⚑ фандинг сменил знак; толпа — новый максимум за сутки;
  ⚑ плита сверху/снизу в ±5% — крупнейшая за сутки по журналу.
Состояние — output/coin_watch_<монета>.json.

    .venv/bin/python claude/research/coin_watch.py SEIUSDT
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request as u
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
L = timezone(timedelta(hours=3))


def g(url):
    return json.loads(u.urlopen(url, timeout=15).read())


def main() -> int:
    S = (sys.argv[1] if len(sys.argv) > 1 else "SEIUSDT").upper()
    S = S if S.endswith("USDT") else S + "USDT"
    stp = ROOT / "output" / f"coin_watch_{S[:-4].lower()}.json"
    try:
        prev = json.loads(stp.read_text())
    except (OSError, ValueError):
        prev = {}
    k3 = g(f"https://fapi.binance.com/fapi/v1/klines?symbol={S}&interval=3m&limit=480")
    k30 = g(f"https://fapi.binance.com/fapi/v1/klines?symbol={S}&interval=30m&limit=336")
    c3 = [float(x[4]) for x in k3]; px = c3[-1]
    hi24 = max(float(x[2]) for x in k3[:-1]); hi7 = max(float(x[2]) for x in k30[:-1])
    oi = g(f"https://fapi.binance.com/futures/data/openInterestHist?symbol={S}&period=5m&limit=13")
    ov = [float(x["sumOpenInterestValue"]) for x in oi]
    oi1h = (ov[-1] / ov[0] - 1) * 100 if ov and ov[0] else 0.0
    oi5 = (ov[-1] / ov[-2] - 1) * 100 if len(ov) > 1 and ov[-2] else 0.0
    fund = float(g(f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={S}")["lastFundingRate"]) * 100
    crowd = [float(x["longShortRatio"]) for x in g(f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={S}&period=5m&limit=288")]
    buy15 = sum(float(x[10]) for x in k3[-5:]) / max(1.0, sum(float(x[7]) for x in k3[-5:])) * 100
    # ликвидации: за последние 3 мин и максимум 3-минутки за сутки
    now_ms = time.time() * 1000
    liq = []
    for d in {datetime.now(timezone.utc).date(), (datetime.now(timezone.utc) - timedelta(days=1)).date()}:
        p = ROOT / "cq_v2" / "liq" / f"{d}.jsonl"
        if p.exists():
            for ln in p.open(encoding="utf-8"):
                if f'"{S}"' in ln:
                    try:
                        liq.append(json.loads(ln))
                    except ValueError:
                        pass
    seen, bins = set(), {}
    for r in liq:
        key = (r["t"], r["side"], r["usd"], r.get("src"))
        if key in seen or r["t"] < now_ms - 86400_000:
            continue
        seen.add(key)
        b = int(r["t"]) // 180_000
        bins.setdefault(b, [0.0, 0.0])[0 if r["side"] == "long" else 1] += float(r["usd"])
    cur_b = int(now_ms) // 180_000
    lq_now = [bins.get(cur_b, [0, 0])[i] + bins.get(cur_b - 1, [0, 0])[i] for i in (0, 1)]
    sq_max = max((v[1] for b, v in bins.items() if b < cur_b - 1), default=0)
    # стакан: крупнейшие плиты в ±5% по последнему снимку фьючерса и максимум суток
    walls = {"ask": None, "bid": None}; wmax = {"ask": 0, "bid": 0}
    try:
        for ln in (ROOT / "output" / "depth_events.jsonl").open(encoding="utf-8"):
            if f'"{S}"' not in ln:
                continue
            r = json.loads(ln)
            if r.get("kind") != "perp" or r["t"] < now_ms - 86400_000:
                continue
            ws = [w for w in r["after"] if abs(w.get("dist") or 0) <= 5]
            big = max(ws, key=lambda w: w["usd"]) if ws else None
            if big:
                if r["t"] >= now_ms - 600_000:
                    walls[r["side"]] = big
                wmax[r["side"]] = max(wmax[r["side"]], big["usd"])
    except OSError:
        pass
    flags = []
    if px >= hi7: flags.append("⚑ новый максимум 7 дн")
    elif px >= hi24: flags.append("⚑ новый максимум суток")
    if lq_now[1] > 0 and lq_now[1] >= sq_max: flags.append(f"⚑ R21: вынос шортов ${lq_now[1] / 1e3:.0f}K — максимум суток")
    p3 = (px / c3[-2] - 1) * 100
    if oi5 < 0 and p3 > 0: flags.append("⚑ цена растёт, интерес падает — закрываются")
    if oi5 > 0 and p3 < 0: flags.append("⚑ цена падает, интерес растёт — набирают против")
    if prev.get("fund") is not None and (prev["fund"] > 0) != (fund > 0): flags.append(f"⚑ фандинг сменил знак: {fund:+.4f}%")
    if crowd and crowd[-1] >= max(crowd): flags.append(f"⚑ толпа — максимум суток {crowd[-1]:.2f}")
    for sd, nm in (("ask", "сверху"), ("bid", "снизу")):
        w = walls[sd]
        if w and w["usd"] >= wmax[sd] and (prev.get(f"w_{sd}") or 0) < w["usd"]:
            flags.append(f"⚑ плита {nm} {w['px']:.5g} ({w['dist']:+.1f}%) ${w['usd'] / 1e3:.0f}K — крупнейшая за сутки")
    wtxt = " · ".join(f"{'↑' if sd == 'ask' else '↓'}{w['px']:.5g} ${w['usd'] / 1e3:.0f}K" for sd, w in walls.items() if w)
    line = (f"{S[:-4]} {px:.5g} · 3м {p3:+.1f}% · 1ч {(px / c3[-21] - 1) * 100:+.1f}% · 24ч {(px / c3[0] - 1) * 100:+.1f}% · интерес 1ч {oi1h:+.1f}% / 5м {oi5:+.2f}% · "
            f"фанд {fund:+.4f}% · толпа {crowd[-1]:.2f} · покупки 15м {buy15:.0f}% · ликв L/S ${lq_now[0] / 1e3:.0f}K/${lq_now[1] / 1e3:.0f}K" + (f" · {wtxt}" if wtxt else ""))
    print(datetime.now(L).strftime("%H:%M ") + line)
    for f in flags:
        print("  " + f)
    stp.write_text(json.dumps(dict(t=int(time.time()), px=px, fund=fund, w_ask=(walls["ask"] or {}).get("usd"), w_bid=(walls["bid"] or {}).get("usd"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
