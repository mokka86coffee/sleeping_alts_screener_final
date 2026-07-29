"""Расчёт соотношения риска к прибыли.

Только математика. Геометрия дуги, цвета и SVG живут в render/,
чтобы одни и те же числа можно было нарисовать по-разному.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from math import log

from core.config import MIN_RR_TRADABLE

# R:R, при котором индикатор заполнен целиком
RR_CAP = 6.0

GRADE_POOR = 1.5
GRADE_FAIR = 3.0


@dataclass
class RiskReward:
    ok: bool = False
    rr: float = 0.0
    rr_text: str = ""
    fill: float = 0.0           # 0..1, логарифмическая шкала
    grade: str = "none"         # poor | fair | good
    tradable: bool = False

    entry: float = 0.0
    stop: float = 0.0
    target: float = 0.0
    stop_pct: float = 0.0
    target_pct: float = 0.0
    risk_abs: float = 0.0
    reward_abs: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def build_rr(entry: float, stop: float, target: float) -> RiskReward:
    """Считает R:R по абсолютным ценам.

    Шкала заполнения логарифмическая: разница между 1:1 и 1:2 воспринимается
    сильнее, чем между 1:8 и 1:9, и индикатор должен это отражать.
    """
    if not (entry and stop and target):
        return RiskReward()

    risk = entry - stop
    reward = target - entry
    if risk <= 0 or reward <= 0:
        return RiskReward()

    rr = reward / risk
    fill = min(log(1 + rr) / log(1 + RR_CAP), 1.0)

    if rr < GRADE_POOR:
        grade = "poor"
    elif rr < GRADE_FAIR:
        grade = "fair"
    else:
        grade = "good"

    return RiskReward(
        ok=True,
        rr=round(rr, 2),
        rr_text=f"1:{rr:.1f}".rstrip("0").rstrip("."),
        fill=round(fill, 4),
        grade=grade,
        tradable=rr >= MIN_RR_TRADABLE,
        entry=entry,
        stop=stop,
        target=target,
        stop_pct=round((stop / entry - 1) * 100, 1),
        target_pct=round((target / entry - 1) * 100, 1),
        risk_abs=risk,
        reward_abs=reward,
    )


def fmt_price(p: float) -> str:
    """Формат цены под моноширинный шрифт: разрядность по масштабу."""
    if p <= 0:
        return "—"
    if p >= 100:
        return f"${p:,.2f}"
    if p >= 1:
        return f"${p:.4f}"
    if p >= 0.01:
        return f"${p:.5f}"
    if p >= 0.0001:
        return f"${p:.6f}"
    return f"${p:.8f}"


def fmt_usd(v: float | None) -> str:
    """Компактный формат больших сумм."""
    if v is None:
        return "—"
    if v >= 1e9:
        return f"${v/1e9:.2f}B"
    if v >= 1e6:
        return f"${v/1e6:.2f}M"
    if v >= 1e3:
        return f"${v/1e3:.1f}K"
    return f"${v:.0f}"
