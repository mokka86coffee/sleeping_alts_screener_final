"""Скоринг монеты. Каждое слагаемое именовано и сохраняется отдельно,
чтобы карточка могла показать разбор, а не только итоговое число.
"""

from __future__ import annotations

from core.config import (
    BUCKET_GOOD, BUCKET_SCOUT, BUCKET_STRONG,
    OBV_STRONG, RVOL_HOT, SURGE_STRONG,
)
from core.models import ScorePart


class ScoreBuilder:
    """Накопитель баллов с расшифровкой."""

    def __init__(self) -> None:
        self.parts: list[ScorePart] = []

    def add(self, points: int, code: str, label: str) -> None:
        if points <= 0:
            return
        self.parts.append(ScorePart(code=code, label=label, points=int(points)))

    @property
    def total(self) -> int:
        return sum(p.points for p in self.parts)

    def capped(self, limit: int = 100) -> int:
        return min(self.total, limit)


def score_candidate(
    m: dict,
    surge,
    squeeze: dict | None,
    taiko,
    dexe,
    flow=None,
) -> ScoreBuilder:
    """Собирает скор из всех источников сигнала."""
    sb = ScoreBuilder()

    # ... surge, squeeze, taiko, dexe без изменений ...

    # ── FLOW: внутренний скор 45..100 отображаем в 14..34 ──
    # Семейство смотрит на характер потока, а не на цену: вклад
    # сопоставим с TAIKO, но чуть скромнее — подкейсы разной зрелости.
    if flow and flow.detected:
        sb.add(int(14 + (flow.score - 45) * 0.36), "flow", f"FLOW {flow.case}")

    # ── Всплеск объёма ──
    if surge and surge.detected:
        points = 12 if surge.surge_ratio >= SURGE_STRONG else 8
        sb.add(points, "surge", "Всплеск объёма")

    # ── Squeeze: сам факт аномалии добавляет внимания ──
    if squeeze and squeeze.get("detected"):
        lvl = squeeze.get("risk_level", "high")
        sb.add(12 if lvl == "extreme" else 8, "squeeze", "Squeeze-аномалия")

    # ── TAIKO: внутренний скор 45..100 отображаем в 15..35 ──
    if taiko and taiko.detected:
        sb.add(int(15 + (taiko.score - 45) * 0.36), "taiko", "TAIKO разворот")

    # ── DEXE: внутренний скор 55..100 отображаем в 15..35 ──
    if dexe and dexe.detected:
        sb.add(int(15 + (dexe.score - 55) * 0.44), "dexe", "DEXE post-pump")

    # ── Фаза рынка ──
    phase_num = (m.get("vortex_4h") or {}).get("phase", 0)
    if phase_num == 4:
        sb.add(15, "phase", "Фаза TREND")
    elif phase_num == 3:
        sb.add(10, "phase", "Фаза MOMENTUM")
    elif phase_num == 2:
        sb.add(4, "phase", "Фаза BASE")

    # ── Накопление ──
    if (m.get("obv_slope") or 0) > OBV_STRONG:
        sb.add(6, "obv", "Накопление по OBV")

    # ── Относительный объём часа ──
    if (m.get("rvol_1h") or 0) >= RVOL_HOT:
        sb.add(6, "rvol", "Высокий RVOL")

    return sb


def classify_bucket(score: int, has_pattern: bool) -> str:
    """Раскладывает монету по группам отчёта."""
    if score >= BUCKET_STRONG:
        return "strong"
    if score >= BUCKET_GOOD:
        return "good"
    if score >= BUCKET_SCOUT:
        return "scout"
    # Монета с распознанным паттерном не падает ниже разведки
    return "scout" if has_pattern else "watch"
