#!/usr/bin/env python3
"""БУМАЖНАЯ КНИГА «ВТОРОЙ ХОД» (26.09, владелец «правь пока только бота»; R3/R18/R19 — ARK 24.09 и PHA 25.09, 2/2; claude/research/moves.md).
После первого хода (ход от минимума 7 дн ≥ SECOND_RUN%) монета на пиле ниже максимума 72 ч на SECOND_PULLBACK и больше; фандинг за сутки вернулся
к нулю (|медиана| ≤ SECOND_FUND_ZERO — не шортовое топливо и не толпа в лонге); интерес сдулся на пиле (минимум за 48 ч ниже максимума за 96 ч
на SECOND_OI_DEFLATE) и развернулся вверх (+SECOND_OI_TURN за 12 баров); спот покупает (сумма дельты спота за 6 баров > 0) → лонг SECOND_SIZE $,
цель — максимум 72 ч (первая вершина), стоп −SECOND_STOP, срок SECOND_HOLD баров, пауза SECOND_PAUSE_H ч. Счёт мал (2/2) — книга нужна, чтобы его набрать.
    python3 paper_second.py --only ARK          # без записи
    python3 paper_second.py --write             # из прогона
Журнал output/paper_second.jsonl, состояние output/paper_second.json."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
try:
    from core_config import SECOND_RUN, SECOND_PULLBACK, SECOND_FUND_ZERO, SECOND_OI_DEFLATE, SECOND_OI_TURN, SECOND_SIZE, SECOND_STOP, SECOND_HOLD, SECOND_PAUSE_H
except ImportError:
    SECOND_RUN, SECOND_PULLBACK, SECOND_FUND_ZERO, SECOND_OI_DEFLATE, SECOND_OI_TURN = 40.0, 0.15, 0.02, 0.20, 0.05
    SECOND_SIZE, SECOND_STOP, SECOND_HOLD, SECOND_PAUSE_H = 500.0, 0.12, 192, 96
from paper_book_base import run_book

BOOK = "второй ход"
STATE = BASE_DIR / "output" / "paper_second.json"
LOG = BASE_DIR / "output" / "paper_second.jsonl"


def _med(v):
    v = sorted(x for x in v if x is not None)
    return v[len(v) // 2] if v else None


def signal(rows: list[dict], nums: dict) -> dict | None:
    i = len(rows) - 1
    if i < 96:
        return None
    run = float(nums.get("run_from_low7") or 0)
    if run < SECOND_RUN:
        return None
    C = [float(r["px"]) for r in rows]; H = [float(r.get("h") or r["px"]) for r in rows]
    OI = [float(r.get("oi") or 0) for r in rows]
    F = [r.get("funding") for r in rows]
    hi72 = max(H[i - 144:i + 1]) if i >= 144 else max(H[: i + 1])
    if C[i] > hi72 * (1 - SECOND_PULLBACK):
        return None
    fm = _med(F[i - 48:i + 1])
    if fm is None or abs(fm) > SECOND_FUND_ZERO:
        return None
    if not (OI[i] and OI[i - 12] and min(OI[i - 48:i + 1]) and max(OI[i - 96:i - 48])):
        return None
    deflated = min(OI[i - 48:i + 1]) <= max(OI[i - 96:i - 48]) * (1 - SECOND_OI_DEFLATE)
    turned = OI[i] / OI[i - 12] - 1 >= SECOND_OI_TURN
    spot = sum(float(((r.get("spot") or {}).get("d")) or 0) for r in rows[i - 5:i + 1])
    if deflated and turned and spot > 0:
        tgt = max(0.05, hi72 / C[i] - 1)
        return {"t": rows[i]["t"], "px": C[i], "target": round(tgt, 4), "stop": SECOND_STOP, "hold": SECOND_HOLD,
                "run_from_low7": round(run, 1), "pullback_pct": round((1 - C[i] / hi72) * 100, 1), "funding_med": round(fm, 4),
                "oi_turn_pct": round((OI[i] / OI[i - 12] - 1) * 100, 1), "spot_delta6": round(spot, 0),
                "rule": f"второй ход: после +{run:.0f}% пила −{(1 - C[i] / hi72) * 100:.0f}%, фандинг {fm:+.3f}% ≈ 0, интерес сдулся и +{(OI[i] / OI[i - 12] - 1) * 100:.0f}% за 6 ч, спот +{spot / 1e3:.0f}K — R18/R19 (ARK, PHA 2/2)"}
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    return run_book(BOOK, STATE, LOG, signal, SECOND_SIZE, SECOND_PAUSE_H, a.only, a.write)


if __name__ == "__main__":
    raise SystemExit(main())
