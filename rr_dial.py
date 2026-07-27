"""
Подкова R:R для блока 03 «Стратегия».
Считает геометрию дуги и цветовую ступень.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import log, cos, sin, pi

R_CAP = 6.0          # R:R, при котором дуга замыкается
ARC_START = -90.0    # 12 часов
ARC_SWEEP = 360.0    # полный круг


@dataclass
class RrDial:
    ok: bool = False
    rr: float = 0.0
    rr_text: str = ""
    fill: float = 0.0        # 0..1
    grade: str = ""          # poor / fair / good
    entry: float = 0.0
    stop: float = 0.0
    target: float = 0.0
    stop_pct: float = 0.0
    target_pct: float = 0.0
    dash: float = 0.0        # длина закрашенной дуги
    circumference: float = 0.0


def build_dial(entry: float, stop: float, target: float,
               radius: float = 42.0, stroke: float = 9.5) -> RrDial:
    """entry / stop / target — абсолютные цены."""
    if not (entry and stop and target):
        return RrDial()
    risk = entry - stop
    reward = target - entry
    if risk <= 0 or reward <= 0:
        return RrDial()

    rr = reward / risk
    fill = min(log(1 + rr) / log(1 + R_CAP), 1.0)

    if rr < 1.5:
        grade = "poor"
    elif rr < 3.0:
        grade = "fair"
    else:
        grade = "good"

    circ = 2 * pi * radius
    return RrDial(
        ok=True,
        rr=round(rr, 2),
        rr_text=f"1:{rr:.1f}".rstrip("0").rstrip("."),
        fill=round(fill, 4),
        grade=grade,
        entry=entry, stop=stop, target=target,
        stop_pct=round((stop / entry - 1) * 100, 1),
        target_pct=round((target / entry - 1) * 100, 1),
        dash=round(circ * fill, 2),
        circumference=round(circ, 2),
    )


def fmt_price(p: float) -> str:
    """单 формат цены под моноширинный шрифт."""
    if p >= 100:
        return f"${p:,.2f}"
    if p >= 1:
        return f"${p:.4f}"
    if p >= 0.01:
        return f"${p:.5f}"
    return f"${p:.6f}"
