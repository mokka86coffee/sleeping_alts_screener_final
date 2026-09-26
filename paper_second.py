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
try:
    from core_config import SECOND_LOOKBACK, SECOND_STOP_OFF, SECOND_TARGET_FIXED, SECOND_PULLBACK_MAX
except ImportError:
    SECOND_LOOKBACK, SECOND_STOP_OFF, SECOND_TARGET_FIXED, SECOND_PULLBACK_MAX = 960, True, 0.20, 0.50
from paper_book_base import run_book

BOOK = "второй ход"
STATE = BASE_DIR / "output" / "paper_second.json"
LOG = BASE_DIR / "output" / "paper_second.jsonl"


def _med(v):
    v = sorted(x for x in v if x is not None)
    return v[len(v) // 2] if v else None


def signal(rows: list[dict], nums: dict) -> dict | None:
    """ВТОРОЙ ХОД С БАЗОЙ ЛЮБОЙ ДЛИНЫ (26.09, claude/research/book_replay.py на hist30, 30 дн, 158 монет): прежние окна
    (максимум 72 ч, минимум 7 дн, интерес 48 ч) дали 0 сигналов за 30 дн — у ARK база 9 дн, у RAYSOL 10, и к её концу ход
    от минимума 7 дн уже меньше порога. Здесь первая нога = максимум за SECOND_LOOKBACK баров и ≥ +SECOND_RUN% от минимума
    7 дн перед ним; база — цена ниже него на SECOND_PULLBACK и выше минимума после него (не сползание); фандинг за сутки ≈ 0;
    интерес сдулся на SECOND_OI_DEFLATE от интереса на вершине и развернулся +SECOND_OI_TURN за 12 баров; спот покупает
    (без спота на Binance — дельта тейкеров фьючерсов). Счёт: 21 сигнал, 10 в плюс, до первой вершины 6, депозит/4 слота +3.5K$/30 дн."""
    i = len(rows) - 1
    if i < 400:
        return None
    C = [float(r["px"]) for r in rows]; H = [float(r.get("h") or r["px"]) for r in rows]; L = [float(r.get("l") or r["px"]) for r in rows]
    OI = [float(r.get("oi") or 0) for r in rows]
    F = [r.get("funding") for r in rows]
    j0 = max(0, i - SECOND_LOOKBACK)
    jm = max(range(j0, i + 1), key=lambda j: H[j])
    if i - jm < 48 or jm - 336 < 0:
        return None
    lo_before = min(L[jm - 336:jm])
    run = (H[jm] / lo_before - 1) * 100 if lo_before else 0
    if run < SECOND_RUN:
        return None
    if C[i] > H[jm] * (1 - SECOND_PULLBACK) or C[i] < H[jm] * (1 - SECOND_PULLBACK_MAX):   # 26.09: глубже — сползание (0/3)
        return None
    lo_after = min(L[jm:i + 1])
    if C[i] < lo_after * 1.03:
        return None
    fm = _med(F[i - 48:i + 1])
    if fm is None or abs(fm) > SECOND_FUND_ZERO:
        return None
    oi_top = max(OI[max(0, jm - 6):jm + 7])
    if not (oi_top and OI[i] and OI[i - 12]):
        return None
    deflated = min(OI[jm:i + 1]) <= oi_top * (1 - SECOND_OI_DEFLATE)
    turned = OI[i] / OI[i - 12] - 1 >= SECOND_OI_TURN
    has_spot = any(isinstance(r.get("spot"), dict) and r["spot"].get("d") is not None for r in rows[i - 5:i + 1])
    spot = sum(float(((r.get("spot") or {}).get("d")) or 0) for r in rows[i - 5:i + 1]) if has_spot else \
        sum(float(((r.get("fut") or {}).get("d")) or 0) for r in rows[i - 5:i + 1])
    if deflated and turned and spot > 0:
        tgt = SECOND_TARGET_FIXED if SECOND_TARGET_FIXED else max(0.05, H[jm] / C[i] - 1)
        return {"t": rows[i]["t"], "px": C[i], "target": round(tgt, 4), "stop": None if SECOND_STOP_OFF else SECOND_STOP, "hold": SECOND_HOLD,
                "top_px": H[jm],
                "run_pct": round(run, 1), "base_days": round((i - jm) / 48, 1), "pullback_pct": round((1 - C[i] / H[jm]) * 100, 1),
                "funding_med": round(fm, 4), "oi_deflate_pct": round((min(OI[jm:i + 1]) / oi_top - 1) * 100, 1),
                "oi_turn_pct": round((OI[i] / OI[i - 12] - 1) * 100, 1), "spot_delta6": round(spot, 0), "spot_src": "спот" if has_spot else "тейкеры",
                "rule": f"второй ход: первая нога +{run:.0f}%, база {(i - jm) / 48:.0f} дн, −{(1 - C[i] / H[jm]) * 100:.0f}% от вершины, "
                        f"фандинг {fm:+.3f}% ≈ 0, интерес сдулся {(min(OI[jm:i + 1]) / oi_top - 1) * 100:.0f}% и развернулся "
                        f"+{(OI[i] / OI[i - 12] - 1) * 100:.0f}%, {'спот' if has_spot else 'тейкеры'} покупают"}
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    refresh_hist(a.only)
    return run_book(BOOK, STATE, LOG, signal, SECOND_SIZE, SECOND_PAUSE_H, a.only, a.write)


def refresh_hist(only: str | None) -> None:
    """26.09: история 30 дн (интерес/фандинг/спот) для монет с первой ногой — только им, чтобы не качать 158 монет каждые полчаса;
    файл свежее 6 ч не трогаем (hist30.py сам пропускает)."""
    try:
        sys.path.insert(0, str(BASE_DIR / "claude" / "research"))
        import hist30
        from paper_book_base import rows_of as _rows
    except Exception:  # noqa: BLE001
        return
    syms = ([x.strip().upper() + ("" if x.strip().upper().endswith("USDT") else "USDT") for x in only.split(",")] if only
            else sorted(p.stem.upper() + "USDT" for p in (BASE_DIR / "cq_v2" / "intraday").glob("*.jsonl")))
    todo = []
    for s_ in syms:
        rows = _rows(s_)
        if len(rows) < 400:
            continue
        H = [float(r.get("h") or r["px"]) for r in rows]; L = [float(r.get("l") or r["px"]) for r in rows]
        jm = max(range(max(0, len(rows) - 1 - SECOND_LOOKBACK), len(rows)), key=lambda j: H[j])
        if jm >= 336 and min(L[jm - 336:jm]) and H[jm] / min(L[jm - 336:jm]) - 1 >= SECOND_RUN / 100 and len(rows) - 1 - jm >= 48:
            todo.append(s_)
    out = BASE_DIR / "cq_v2" / "hist30"; out.mkdir(parents=True, exist_ok=True)
    import time as _t, json as _j
    for s_ in todo:
        p = out / f"{s_[:-4].lower()}.json"
        if p.exists() and _t.time() - p.stat().st_mtime < 6 * 3600:
            continue
        try:
            rows = hist30.build(s_)
            if rows:
                p.write_text(_j.dumps(rows, ensure_ascii=False), encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue


if __name__ == "__main__":
    raise SystemExit(main())
