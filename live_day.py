#!/usr/bin/env python3
"""ЖИВОЙ ДЕНЬ — ОДИН МОДУЛЬ НА ВСЕХ (06.09, владелец: «а как ты это забываешь постоянно?
третий раз за день приходится напоминать»).

Правило: всё, что смотрит «сейчас», читает живой день; дневки кванта — только для истории.
Чтобы это было сложнее забыть, чем вспомнить, живой день собирается ЗДЕСЬ и только здесь:

    from live_day import live_rows, load_live
    src  = load_live()                       # срез Coinglass + пульс, один раз на прогон
    row  = live_rows("4USDT", src)           # строка сегодняшнего незакрытого дня или None

Строка — в формате дневки cq_v2, чтобы дописываться к архиву последней:
    ohlcv:  datetime, open, high, low, close, quote_volume (в темпе суток)
    trade:  quote_buy_volume, quote_sell_volume, buy_sell_ratio (по барам с полуночи UTC)
    oi:     open_interest (срез сейчас)
    funding: funding_rate (пульс, последняя)
    liq:    short_liquidations_usd, long_liquidations_usd (24 ч из списка ликвидаций)
и флаг _live=True. Раньше 03:36 UTC и меньше 4 баров — None: день ещё не читается.

Кто пользуется: reputation_cq.live_day (шаблоны), near_move (близкие), любой новый скрипт.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent

LIVE_MIN_FRACTION = 0.15   # 03:36 UTC — раньше день не читается
LIVE_MIN_BARS = 4          # полчасовых баров с полуночи


def load_live() -> dict:
    """Срез Coinglass и пульс — один раз на прогон, дальше передавать в live_rows."""
    out: dict = {}
    for name, key in (("output/coinglass_fetch.json", "cg"), ("pulse.json", "pulse")):
        try:
            out[key] = json.loads((BASE_DIR / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            out[key] = {}
    return out


def live_rows(sym_usdt: str, src: dict, now: datetime | None = None) -> dict | None:
    """Строка сегодняшнего незакрытого дня или None."""
    now = now or datetime.now(timezone.utc)
    frac = (now.hour * 60 + now.minute) / 1440.0
    if frac < LIVE_MIN_FRACTION:
        return None
    c = ((src.get("cg") or {}).get("coins") or {}).get(sym_usdt) or {}
    if not c:
        return None
    mid = int(datetime(now.year, now.month, now.day, tzinfo=timezone.utc).timestamp() * 1000)
    ser = (c.get("fut") or {}).get("series") or []
    upto = int(now.timestamp() * 1000)
    bars = [b for b in ser if b.get("t") and mid <= b["t"] < upto and b.get("b") is not None and b.get("s") is not None]
    if len(bars) < LIVE_MIN_BARS:
        return None
    pace = 1.0 / max(frac, LIVE_MIN_FRACTION)
    buy = sum(float(b["b"] or 0) for b in bars) * pace
    sell = sum(float(b["s"] or 0) for b in bars) * pace
    pr = [r for r in ((src.get("pulse") or {}).get(sym_usdt) or []) if r.get("price")]
    pr.sort(key=lambda r: r.get("t") or 0)
    if not pr:
        return None
    day_rows = [r for r in pr if (r.get("t") or 0) * 1000 >= mid] or pr[-1:]
    px = float(pr[-1]["price"])
    liq = c.get("liq") or {}
    return {
        "datetime": now.strftime("%Y-%m-%d 00:00:00"), "_live": True,
        "open": float(day_rows[0]["price"]), "high": max(float(r["price"]) for r in day_rows),
        "low": min(float(r["price"]) for r in day_rows), "close": px,
        "quote_volume": buy + sell,
        "quote_buy_volume": buy, "quote_sell_volume": sell,
        "buy_sell_ratio": (buy / sell) if sell else None,
        "open_interest": c.get("oiUsd") if c.get("oiUsd") is not None else pr[-1].get("oi_usd"),
        "funding_rate": pr[-1].get("funding") if pr[-1].get("funding") is not None else c.get("funding"),
        "short_liquidations_usd": liq.get("short24h"), "long_liquidations_usd": liq.get("long24h"),
        "bars": len(bars), "frac": round(frac, 3),
    }


if __name__ == "__main__":
    import sys
    src = load_live()
    for s in (sys.argv[1:] or ["4USDT"]):
        s = s.upper() + ("" if s.upper().endswith("USDT") else "USDT")
        print(s, json.dumps(live_rows(s, src), ensure_ascii=False))
