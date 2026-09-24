"""Расстановка толпы с Binance — замена crowd_coinglass (24.09).

Две перспективы на монету, как и было: доля лонг-счетов среди всех (globalLongShortAccountRatio) и доля
лонга в позициях топов (topLongShortPositionRatio). У Binance эти ряды бесплатные и отдаются по паре
напрямую. Бар 4 часа, восемь баров: последняя точка и сдвиг за сутки (шесть баров назад).

Пишет output/binance_crowd.json и тот же срез в output/coinglass_crowd.json — его читают экраны
(crowd_coinglass.for_screens), вид среза прежний. Файл crowd_coinglass.py не трогается.

    python3 binance_crowd.py             # показать
    python3 binance_crowd.py --write     # записать
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR, BINANCE_FAPI
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
    BINANCE_FAPI = "https://fapi.binance.com"
from core_http import get_json
from binance_fetch import _journal_coins, _base_coin

OUT_PATH = BASE_DIR / "output" / "binance_crowd.json"
COMPAT_PATH = BASE_DIR / "output" / "coinglass_crowd.json"
INTERVAL = "4h"
BARS = 8
DAY_BACK = 6


def _side(rows: list, ) -> dict | None:
    rows = [r for r in (rows or []) if isinstance(r, dict) and r.get("longAccount") is not None]
    if not rows:
        return None
    rows.sort(key=lambda r: int(r.get("timestamp") or 0))
    last = float(rows[-1]["longAccount"]) * 100
    out = {"longPct": round(last, 1)}
    if len(rows) > DAY_BACK:
        out["chg1d"] = round(last - float(rows[-1 - DAY_BACK]["longAccount"]) * 100, 1)
    return out


def collect(symbols: list[str] | None = None, verbose: bool = True) -> dict:
    coins = [_base_coin(s) for s in symbols] if symbols else _journal_coins()[0]
    state: dict = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "binance",
                   "exchange": "Binance", "interval": INTERVAL, "coins": {}, "absent": [], "errors": {}, "requests": 0}
    for coin in coins:
        pair = coin + "USDT"
        rec: dict = {}
        for path, field in (("/futures/data/globalLongShortAccountRatio", "crowd"),
                            ("/futures/data/topLongShortPositionRatio", "top")):
            data = get_json(f"{BINANCE_FAPI}{path}", {"symbol": pair, "period": INTERVAL, "limit": BARS},
                            quiet_400=True, weight=1)
            state["requests"] += 1
            side = _side(data if isinstance(data, list) else [])
            if side:
                rec[field] = side
        if rec:
            state["coins"][coin] = rec
        else:
            state["absent"].append(coin)
        if verbose and rec:
            print(f"  {coin}: толпа {rec.get('crowd', {}).get('longPct')}% · топы {rec.get('top', {}).get('longPct')}%",
                  file=sys.stderr)
    return state


def auto_update(max_age_hours: float = 24.0) -> str:
    """Суточный контур для run.py: свежий срез — пропуск без сети."""
    try:
        age_h = (time.time() - OUT_PATH.stat().st_mtime) / 3600
        if age_h < max_age_hours:
            return f"срез свеж ({age_h:.0f} ч) — пропуск"
    except OSError:
        pass
    st = collect(verbose=False)
    txt = json.dumps(st, ensure_ascii=False, indent=1)
    for p in (OUT_PATH, COMPAT_PATH):
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(txt, encoding="utf-8")
        except OSError as e:
            return f"✗ не записался {p.name}: {e}"
    return f"монет {len(st['coins'])}, без пары {len(st['absent'])}, запросов {st['requests']} · Binance"


def main() -> int:
    ap = argparse.ArgumentParser(description="Расстановка толпы с Binance")
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    st = collect(a.symbols or None)
    print(f"монет {len(st['coins'])} · без пары {len(st['absent'])} · запросов {st['requests']}")
    if a.write:
        txt = json.dumps(st, ensure_ascii=False, indent=1)
        for p in (OUT_PATH, COMPAT_PATH):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(txt, encoding="utf-8")
        print("записано:", OUT_PATH.name, "и", COMPAT_PATH.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
