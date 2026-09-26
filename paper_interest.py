#!/usr/bin/env python3
"""БУМАЖНАЯ КНИГА «ИНТЕРЕС» (26.09, владелец «правь пока только бота»; R34 — claude/research/start_signs.py, oi_base_rate.py, intraday_catch.py).
Признак начала, который видит 42 лидера из 43 за сутки до первого +40%, а бывает лишь в 12% любых суток: интерес +INTEREST_OI_3H% за 3 ч при покупках
по рынку (средний тейкер трёх получасовок ≥ INTEREST_TAKER) у СПЯЩЕЙ монеты (ход от минимума 7 дн < INTEREST_SLEEP%), цена за три бара не упала.
Ожидание по истории (oi_base_rate.py, спящие, 140 сигналов): +10% за 48 ч у 50%, +40% у 11% (база 26 / 4); провал −10% раньше +10% ~20%. Это повод, не вход — потому книга бумажная
и малым размером: лонг INTEREST_SIZE $, цель +INTEREST_TARGET, стоп −INTEREST_STOP, срок INTEREST_HOLD получасовок; максимум за сделку пишется в журнал
(mfe), чтобы считать долю +40%. Одна позиция на монету, после выхода пауза INTEREST_PAUSE_H ч.
    python3 paper_interest.py --only RARE        # без записи
    python3 paper_interest.py --write            # из прогона
Журнал output/paper_interest.jsonl, состояние output/paper_interest.json."""
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
    from core_config import INTEREST_OI_3H, INTEREST_TAKER, INTEREST_SLEEP, INTEREST_SIZE, INTEREST_TARGET, INTEREST_STOP, INTEREST_HOLD, INTEREST_PAUSE_H
except ImportError:
    INTEREST_OI_3H, INTEREST_TAKER, INTEREST_SLEEP = 15.0, 1.2, 20.0
    INTEREST_SIZE, INTEREST_TARGET, INTEREST_STOP, INTEREST_HOLD, INTEREST_PAUSE_H = 500.0, 0.10, 0.10, 96, 48
from paper_book_base import run_book

BOOK = "интерес"
STATE = BASE_DIR / "output" / "paper_interest.json"
LOG = BASE_DIR / "output" / "paper_interest.jsonl"


def signal(rows: list[dict], nums: dict) -> dict | None:
    i = len(rows) - 1
    OI = [float(r.get("oi") or 0) for r in rows]
    if not OI[i] or not OI[i - 6]:
        return None
    oi3 = (OI[i] / OI[i - 6] - 1) * 100
    tk = [((r.get("fut") or {}).get("tk")) for r in rows[i - 2:i + 1]]
    if any(x is None for x in tk):
        return None
    tkm = sum(float(x) for x in tk) / 3
    run = float(nums.get("run_from_low7") or 0)
    C = [float(r["px"]) for r in rows]
    if oi3 >= INTEREST_OI_3H and tkm >= INTEREST_TAKER and run < INTEREST_SLEEP and C[i] >= C[i - 3]:
        return {"t": rows[i]["t"], "px": C[i], "target": INTEREST_TARGET, "stop": INTEREST_STOP, "hold": INTEREST_HOLD,
                "oi_3h_pct": round(oi3, 1), "taker3": round(tkm, 2), "run_from_low7": round(run, 1),
                "rule": f"интерес +{oi3:.0f}% за 3 ч, тейкер {tkm:.2f}, монета спит (+{run:.0f}% от мин 7 дн) — R34: +10% у 50%, +40% у 11%"}
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    return run_book(BOOK, STATE, LOG, signal, INTEREST_SIZE, INTEREST_PAUSE_H, a.only, a.write)


if __name__ == "__main__":
    raise SystemExit(main())
