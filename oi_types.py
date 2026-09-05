#!/usr/bin/env python3
"""Прирост плеча ПО ТИПУ (05.09) — подсказал Leviathan: бар красится не
«интерес вырос/упал», а тем, КТО это сделал, по знаку прироста интереса
против знака цены за тот же час:

    интерес ↑ цена ↑  — ЛОНГИ ОТКРЫВАЮТ      (long_open)
    интерес ↑ цена ↓  — ШОРТЫ ОТКРЫВАЮТ      (short_open)
    интерес ↓ цена ↑  — ШОРТЫ ЗАКРЫВАЮТ      (short_close)  — сквиз
    интерес ↓ цена ↓  — ЛОНГИ ЗАКРЫВАЮТ      (long_close)   — вынос

Час, где интерес или цена сдвинулись меньше порога, — «тихо» (flat).
Считается по часовому интересу и часовым свечам Binance (core_binance),
глубина 14 дней. Пишет output/oi_types.json:
  {"at":…, "coins": {"BLESSUSDT": {"hours":[[t_ms, type, doi_pct, dp_pct, close, quote_usd], …],
                                    "last24": {type: часов}, "dominant": type,
                                    "read": "строка словами"}}}

    python3 oi_types.py --only BLESS         # одна монета, печать
    python3 oi_types.py --write              # все монеты cq_v2 → output/oi_types.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

OUT = BASE_DIR / "output" / "oi_types.json"
HOURS = 14 * 24
OI_MIN = 0.15      # % — прирост интереса меньше этого за час — тихо
PX_MIN = 0.10      # % — ход цены меньше этого за час — тихо

NAMES = {"long_open": "лонги открывают", "short_open": "шорты открывают",
         "short_close": "шорты закрывают", "long_close": "лонги закрывают", "flat": "тихо"}


def classify(doi: float, dp: float) -> str:
    if abs(doi) < OI_MIN or abs(dp) < PX_MIN:
        return "flat"
    if doi > 0:
        return "long_open" if dp > 0 else "short_open"
    return "short_close" if dp > 0 else "long_close"


def coin_types(sym_usdt: str) -> dict | None:
    from core_binance import get_oi_history, klines_1h, ohlcv
    kl = klines_1h(sym_usdt)
    oh = get_oi_history(sym_usdt, "1h", min(500, HOURS + 2))
    if not kl or not oh:
        return None
    k = ohlcv(kl, tail=len(oh))
    oi = [float(r.get("sumOpenInterestValue") or 0) for r in oh]
    ts = [int(r.get("timestamp") or 0) for r in oh]
    m = min(len(k["close"]), len(oi))
    c, oi, ts = k["close"][-m:], oi[-m:], ts[-m:]
    qv = (k.get("quote") or k.get("q") or k.get("qv") or [0.0] * m)[-m:]   # оборот часа в долларах
    hours = []
    for i in range(1, m):
        if not oi[i - 1] or not c[i - 1]:
            continue
        doi = (oi[i] / oi[i - 1] - 1) * 100
        dp = (c[i] / c[i - 1] - 1) * 100
        hours.append([ts[i], classify(doi, dp), round(doi, 2), round(dp, 2), c[i], round(float(qv[i] or 0), 0)])   # [t, тип, Δинтерес %, Δцена %, close, оборот $]
    hours = hours[-HOURS:]
    last = hours[-24:]
    cnt: dict[str, int] = {}
    for h in last:
        cnt[h[1]] = cnt.get(h[1], 0) + 1
    live = {k: v for k, v in cnt.items() if k != "flat"}
    dom = max(live, key=live.get) if live else "flat"
    # словами: две главные доли за сутки
    top = sorted(live.items(), key=lambda kv: -kv[1])[:2]
    read = ("за сутки " + ", ".join(f"{NAMES[t]} {n} ч" for t, n in top)) if top else "за сутки плечо не двигалось"
    # доли за 14 дней — для счётчика доски
    tot: dict[str, int] = {}
    for h in hours:
        tot[h[1]] = tot.get(h[1], 0) + 1
    return {"hours": hours, "last24": cnt, "dominant": dom, "read": read, "days14": tot}


def build(only: list[str] | None = None) -> dict:
    coins = only or sorted(p.stem.upper() for p in (BASE_DIR / "cq_v2").glob("*.json") if not p.name.startswith("_"))
    out: dict = {"at": datetime.now().strftime("%Y-%m-%d %H:%M"), "coins": {}, "missing": []}
    for i, b in enumerate(coins, 1):
        sym = b.upper() + ("" if b.upper().endswith("USDT") else "USDT")
        try:
            r = coin_types(sym)
        except Exception as e:  # noqa: BLE001
            r = None
            out["missing"].append(f"{sym}: {type(e).__name__}: {e}")
        if r:
            out["coins"][sym] = r
        if i % 20 == 0:
            print(f"  плечо по типу: {i}/{len(coins)}", flush=True)
    # счётчик доски: сколько монет с каким доминирующим типом за сутки
    board: dict[str, int] = {}
    for v in out["coins"].values():
        board[v["dominant"]] = board.get(v["dominant"], 0) + 1
    out["board"] = board
    # штамп свечи (05.09): какую закрытую получасовку описывают часы; missing — монеты без данных
    try:
        import candle_gate as _cg
        out["stamp"] = _cg.stamp(_cg.boundary())
    except Exception:  # noqa: BLE001
        out["stamp"] = {"note": "candle_gate не найден"}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="одна или несколько монет через запятую")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    only = [x.strip() for x in a.only.split(",")] if a.only else None
    res = build(only)
    for sym, v in res["coins"].items():
        print(f"{sym}: {v['read']} · доминирует: {NAMES[v['dominant']]}")
    if res["missing"]:
        print("нет данных: " + "; ".join(res["missing"][:5]))
    b = res["board"]
    print("доска: " + ", ".join(f"{NAMES[k]} {v}" for k, v in sorted(b.items(), key=lambda kv: -kv[1])))
    if a.write:
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        print(f"oi_types: записано {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
