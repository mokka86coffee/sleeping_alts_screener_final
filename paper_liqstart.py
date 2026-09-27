#!/usr/bin/env python3
"""БУМАЖНАЯ КНИГА «ВЫНОС ЛОНГОВ У ДНА» (27.09 п.4, владелец: «каждый слом это вынос; ход вверх начинается с первого выноса лонгов у дна»;
ARK 24.09, LSK 23.09, AGI 23.09; NIL 27.09 — отрицательный пример: вынос был, интерес не пришёл). Данные — наш поток ликвидаций
output/liq_sides.json (OKX+Bybit, получасовые корзины за сутки). Вход лонг: вынос лонгов за последний час — максимум за сутки и ≥ LIQSTART_MIN_USD,
цена не выше минимума 48 ч на LIQSTART_NEAR_LOW %, интерес за 6 ч ≥ 0 (деньги не уходят). Цель +10 %, стоп −6 %, срок 48 получасовок,
размер LIQSTART_SIZE (малый — счёта нет, поток два дня). Журнал output/paper_liqstart.jsonl.
    python3 paper_liqstart.py --only NIL     # без записи
    python3 paper_liqstart.py --write        # из прогона
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
try:
    from core_config import LIQSTART_MIN_USD, LIQSTART_NEAR_LOW, LIQSTART_SIZE, LIQSTART_TARGET, LIQSTART_STOP, LIQSTART_HOLD, LIQSTART_PAUSE_H
except ImportError:
    LIQSTART_MIN_USD, LIQSTART_NEAR_LOW, LIQSTART_SIZE, LIQSTART_TARGET, LIQSTART_STOP, LIQSTART_HOLD, LIQSTART_PAUSE_H = 5000.0, 3.0, 250.0, 0.10, 0.06, 48, 8
from paper_book_base import run_book
from book_fon import fon, coin_fon

BOOK = "вынос лонгов у дна"
STATE = BASE_DIR / "output" / "paper_liqstart.json"
LOG = BASE_DIR / "output" / "paper_liqstart.jsonl"
_LS: dict = {}


def liq_sides() -> dict:
    if not _LS:
        try:
            d = json.loads((BASE_DIR / "output" / "liq_sides.json").read_text(encoding="utf-8"))
            _LS.update(d.get("coins") or {})
        except (OSError, ValueError):
            pass
    return _LS


def signal(rows: list[dict], nums: dict) -> dict | None:
    i = len(rows) - 1
    if i < 96:
        return None
    v = liq_sides().get(rows[i].get("sym") or "", None)
    if not v:
        return None
    bars = v.get("bars") or []
    if len(bars) < 6:
        return None
    long1h = float(v.get("long1h") or 0)
    longs = [float(b[1]) for b in bars]
    max1h = max(float(bars[j][1]) + float(bars[j + 1][1]) for j in range(len(bars) - 1))
    if long1h < LIQSTART_MIN_USD or long1h < max1h * 0.999:
        return None
    C = [float(r["px"]) for r in rows]; L = [float(r.get("l") or r["px"]) for r in rows]
    lo48 = min(L[i - 96:i + 1])
    if not lo48 or C[i] > lo48 * (1 + LIQSTART_NEAR_LOW / 100):
        return None
    OI = [float(r.get("oi") or 0) for r in rows]
    if not OI[i] or not OI[i - 12] or OI[i] < OI[i - 12]:
        return None
    return {"t": rows[i]["t"], "px": C[i], "target": LIQSTART_TARGET, "stop": LIQSTART_STOP, "hold": LIQSTART_HOLD, "long1h_usd": round(long1h),
            "fon": fon(), "coin_fon": coin_fon(rows),
            "rule": f"вынос лонгов у дна: {long1h / 1e3:.0f}K$ за час — максимум за сутки, цена у минимума 48 ч, интерес за 6 ч {(OI[i] / OI[i - 12] - 1) * 100:+.1f}% (R35, наблюдение)"}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--only"); ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    return run_book(BOOK, STATE, LOG, signal, LIQSTART_SIZE, LIQSTART_PAUSE_H, a.only, a.write)


if __name__ == "__main__":
    raise SystemExit(main())
