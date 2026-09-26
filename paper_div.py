#!/usr/bin/env python3
"""БУМАЖНАЯ КНИГА «ДИВЕРГЕНЦИЯ» (R32, 27.09, владелец «всё делай»): новый максимум 24 ч при интересе не выше 0.8 × интереса на прошлом
максимуме 24 ч (тот не ближе 6 ч) — новый максимум при сдутом интересе не вершина (видео, DEXE; R32) → лонг, продолжение хода.
Цель +10 %, стоп −5 %, срок 48 получасовок. Журнал output/paper_div.jsonl, состояние output/paper_div.json.
    python3 paper_div.py --only ARK          # без записи
    python3 paper_div.py --write             # из прогона
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
    from core_config import DIV_SIZE, DIV_TARGET, DIV_STOP, DIV_HOLD, DIV_PAUSE_H
except ImportError:
    DIV_SIZE, DIV_TARGET, DIV_STOP, DIV_HOLD, DIV_PAUSE_H = 500.0, 0.10, 0.05, 48, 8
from paper_book_base import run_book
from book_fon import fon, coin_fon

BOOK = "дивергенция"
STATE = BASE_DIR / "output" / "paper_div.json"
LOG = BASE_DIR / "output" / "paper_div.jsonl"


def signal(rows: list[dict], nums: dict) -> dict | None:
    i = len(rows) - 1
    if i < 50:
        return None
    H = [float(r.get("h") or r["px"]) for r in rows]; OI = [float(r.get("oi") or 0) for r in rows]; C = [float(r["px"]) for r in rows]
    if H[i] < max(H[i - 48:i]) or not OI[i]:
        return None
    jprev = max(range(i - 48, i - 12), key=lambda j: H[j])
    if not OI[jprev] or OI[i] > 0.8 * OI[jprev]:
        return None
    return {"t": rows[i]["t"], "px": C[i], "target": DIV_TARGET, "stop": DIV_STOP, "hold": DIV_HOLD, "oi_ratio": round(OI[i] / OI[jprev], 2),
            "fon": fon(), "coin_fon": coin_fon(rows),
            "rule": f"дивергенция: новый максимум 24 ч при интересе {OI[i] / OI[jprev] * 100:.0f}% от прошлого максимума — не вершина (R32)"}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--only"); ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    return run_book(BOOK, STATE, LOG, signal, DIV_SIZE, DIV_PAUSE_H, a.only, a.write)


if __name__ == "__main__":
    raise SystemExit(main())
