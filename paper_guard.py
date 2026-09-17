#!/usr/bin/env python3
"""ЗАЩИТА БУМАЖНЫХ ШОРТОВ (17.09, случай AVA: за день монета ×2 при фандинге −0.5…−1.1%, «толпа» шортила её
каждый бар — 18 сделок, 9 стопов подряд, −61.8% с весом, 70% всех потерь книги; «конец» добавил два стопа).
Правила из чтения владельца, которых в ботах не было:
  • ЛИДЕРА НЕ ШОРТИМ. Ход ≥ PAPER_SHORT_BLOCK_24H за сутки (мерка памп-лидера) или живая запись в
    pump_leaders.json — это лестница «поднять и трясти»: тряска после ступени — покупка, а не конец.
  • ЛЕСТНИЦА ПО ПЛЕЧУ. «Различать по плечу: растёт ли интерес быстрее цены» — интерес за PAPER_LADDER_BARS
    вырос на PAPER_LADDER_OI_PCT и больше при растущей цене и фандинге ≤ 0 (шорты платят и заходят новые
    руки) — конец не считается, «это тряска внутри лестницы».
  • ПАУЗА ПОСЛЕ СТОПА. Стоп по монете — та же сторона не берётся PAPER_STOP_COOLDOWN_BARS баров; второй стоп
    за сутки — PAPER_STOP_COOLDOWN_LONG_BARS. Иначе один вынос разложен на девять сделок.
Факты не отсекаются: бот пишет пропуск в журнал (kind=skip, причина, сигнал) — лаборатория считает исход
пропущенных так же, как взятых.
"""
from __future__ import annotations

import json
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
try:
    from core_config import (PAPER_SHORT_BLOCK_24H, PAPER_LADDER_BARS, PAPER_LADDER_OI_PCT,
                             PAPER_STOP_COOLDOWN_BARS, PAPER_STOP_COOLDOWN_LONG_BARS, PAPER_STOPS_PER_DAY)
except ImportError:
    PAPER_SHORT_BLOCK_24H, PAPER_LADDER_BARS, PAPER_LADDER_OI_PCT = 0.40, 12, 10.0
    PAPER_STOP_COOLDOWN_BARS, PAPER_STOP_COOLDOWN_LONG_BARS, PAPER_STOPS_PER_DAY = 6, 24, 2

BAR_MS = 1_800_000


def _leaders() -> set:
    """живые памп-лидеры из pump_leaders.json (retired не считаются)"""
    try:
        from core_config import PUMP_LEADERS_PATH as _pl
    except ImportError:
        _pl = BASE_DIR / "output" / "pump_leaders.json"
    try:
        recs = json.loads(Path(_pl).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {str(r["symbol"]).upper() for r in (recs.values() if isinstance(recs, dict) else recs)
            if isinstance(r, dict) and r.get("symbol") and not r.get("retired_at")}


def short_blocked(sym: str, rows: list[dict]) -> str | None:
    """почему шорт по монете сейчас закрыт; None — можно. rows — получасовки архива по порядку свечей"""
    sym = sym.upper()
    if sym in _leaders():
        return "лидер: живая запись в pump_leaders — лестницу не шортим"
    if len(rows) < 49:
        return None
    C = [float(r["px"]) for r in rows]
    i = len(rows) - 1
    r24 = C[i] / C[i - 48] - 1
    if r24 >= PAPER_SHORT_BLOCK_24H:
        return f"лидер: +{r24 * 100:.0f}% за сутки — лестницу не шортим"
    ois = [float(r["oi"]) for r in rows[i - PAPER_LADDER_BARS:i + 1] if r.get("oi")]
    fund = rows[i].get("funding")
    if len(ois) >= 2 and ois[0] and fund is not None and fund <= 0 and C[i] > C[i - PAPER_LADDER_BARS]:
        oi_up = (ois[-1] / ois[0] - 1) * 100
        if oi_up >= PAPER_LADDER_OI_PCT:
            return f"лестница: интерес +{oi_up:.0f}% за {PAPER_LADDER_BARS} баров при фандинге {fund:+.3f} — тряска внутри хода"
    return None


def note_stop(state: dict, sym: str, side: int, t_bar: int) -> None:
    """записать стоп в состояние книги: state['stops'][sym] — список [t, side] за последние сутки"""
    st = state.setdefault("stops", {})
    lst = [x for x in st.get(sym, []) if t_bar - x[0] <= 48 * BAR_MS]
    lst.append([t_bar, side])
    st[sym] = lst


def cooldown(state: dict, sym: str, side: int, t_bar: int) -> str | None:
    """почему вход по стороне сейчас на паузе после стопов; None — можно"""
    lst = [x for x in (state.get("stops") or {}).get(sym, []) if x[1] == side and t_bar - x[0] <= 48 * BAR_MS]
    if not lst:
        return None
    last = max(x[0] for x in lst)
    bars_ago = (t_bar - last) // BAR_MS
    if len(lst) >= PAPER_STOPS_PER_DAY and bars_ago < PAPER_STOP_COOLDOWN_LONG_BARS:
        return f"пауза: {len(lst)}-й стоп за сутки, ждём {PAPER_STOP_COOLDOWN_LONG_BARS - bars_ago} баров"
    if bars_ago < PAPER_STOP_COOLDOWN_BARS:
        return f"пауза после стопа: ждём {PAPER_STOP_COOLDOWN_BARS - bars_ago} баров"
    return None


def skip_row(sym: str, sig: dict, why: str, now: int, book: str) -> dict:
    """строка журнала о пропущенном сигнале — чтобы исход пропущенных считался"""
    return {"kind": "skip", "book": book, "sym": sym, "at": now, "why_skip": why,
            "rule": str(sig.get("rule") or "").split(":")[0], "side": sig.get("side"), "t": sig.get("t"),
            "px": sig.get("px"), "fund": sig.get("fund") if "fund" in sig else sig.get("funding"),
            "r2": sig.get("r2"), "r6": sig.get("r6"), "r24": sig.get("r24"), "run_pct": sig.get("run_pct")}
