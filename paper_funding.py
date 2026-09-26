#!/usr/bin/env python3
"""БУМАЖНАЯ КНИГА «ФАНДИНГ−» (R14, 27.09, владелец «всё делай»): фандинг ≤ FUNDING_LOW на баре смены выплаты и цена выше минимума 6 ч на 2 %
(шорты загружены и платят, отскок держится) → лонг. Фон как условие входа (trade_context.md, 13 побед против 34 провалов): интерес за сутки
растёт (> 0) и цена не ниже FUNDING_FON_HI24_MIN от максимума суток — провалы были при интересе −0.9 % и −19 % от максимума (сползание).
Цель +10 %, стоп −6 %, срок 48 получасовок. Журнал output/paper_funding.jsonl, состояние output/paper_funding.json.
    python3 paper_funding.py --only ONE      # без записи
    python3 paper_funding.py --write         # из прогона
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
try:
    from core_config import FUNDING_LOW, FUNDING_FON_HI24_MIN, FUNDING_SIZE, FUNDING_TARGET, FUNDING_STOP, FUNDING_HOLD, FUNDING_PAUSE_H
except ImportError:
    FUNDING_LOW, FUNDING_FON_HI24_MIN, FUNDING_SIZE, FUNDING_TARGET, FUNDING_STOP, FUNDING_HOLD, FUNDING_PAUSE_H = -0.30, -12.0, 500.0, 0.10, 0.06, 48, 8
from paper_book_base import run_book
from book_fon import fon, coin_fon

BOOK = "фандинг−"
STATE = BASE_DIR / "output" / "paper_funding.json"
LOG = BASE_DIR / "output" / "paper_funding.jsonl"


def signal(rows: list[dict], nums: dict) -> dict | None:
    i = len(rows) - 1
    if i < 50:
        return None
    f, f1 = rows[i].get("funding"), rows[i - 1].get("funding")
    if f is None or f1 is None or f == f1 or float(f) > FUNDING_LOW:
        return None
    C = [float(r["px"]) for r in rows]; L = [float(r.get("l") or r["px"]) for r in rows]
    lo6 = min(L[i - 12:i + 1])
    if not lo6 or C[i] <= lo6 * 1.02:
        return None
    cf = coin_fon(rows); bg = fon()
    if cf.get("oi24") is None or cf["oi24"] <= 0 or cf.get("from_hi24") is None or cf["from_hi24"] < FUNDING_FON_HI24_MIN:
        return None
    return {"t": rows[i]["t"], "px": C[i], "target": FUNDING_TARGET, "stop": FUNDING_STOP, "hold": FUNDING_HOLD, "funding": float(f),
            "fon": bg, "coin_fon": cf,
            "rule": f"фандинг− {float(f):+.2f}%: шорты платят, отскок держится; фон: интерес 24 ч {cf['oi24']:+.0f}%, {cf['from_hi24']:+.0f}% от макс 24 ч (R14)"}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--only"); ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    return run_book(BOOK, STATE, LOG, signal, FUNDING_SIZE, FUNDING_PAUSE_H, a.only, a.write)


if __name__ == "__main__":
    raise SystemExit(main())
