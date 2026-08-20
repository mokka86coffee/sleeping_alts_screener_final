"""Генераторы SVG: градиенты, стеклянные панели, дуги, спарклайны.

Все фигуры самодостаточны: без внешних ссылок, без скриптов.
Идентификаторы градиентов уникализируются, чтобы несколько блоков
на одной странице не перетирали друг другу defs.
"""

from __future__ import annotations

from math import cos, pi, sin

from render_theme import AMBER, AMBER_LIGHT, GREEN, RUST, STEEL


def shared_defs() -> str:
    """Общие определения градиентов и фильтров для всей страницы."""
    return """
<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
<linearGradient id="d-am" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="#B87A18"/><stop offset="1" stop-color="#FFD98A"/></linearGradient>
<linearGradient id="d-glass" x1=".1" y1="0" x2=".9" y2="1">
  <stop offset="0" stop-color="#8FB4C8" stop-opacity=".07"/>
  <stop offset=".4" stop-color="#4A6070" stop-opacity=".03"/>
  <stop offset=".75" stop-color="#7FA8C0" stop-opacity=".05"/>
  <stop offset="1" stop-color="#3A4A58" stop-opacity=".02"/></linearGradient>
<linearGradient id="d-rim" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#C8DCE8" stop-opacity=".38"/>
  <stop offset=".35" stop-color="#7A8C9A" stop-opacity=".1"/>
  <stop offset=".65" stop-color="#C8DCE8" stop-opacity=".22"/>
  <stop offset="1" stop-color="#5A6A78" stop-opacity=".08"/></linearGradient>
<linearGradient id="d-top" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="#C8DCE8" stop-opacity="0"/>
  <stop offset=".28" stop-color="#C8DCE8" stop-opacity=".42"/>
  <stop offset=".72" stop-color="#C8DCE8" stop-opacity=".42"/>
  <stop offset="1" stop-color="#C8DCE8" stop-opacity="0"/></linearGradient>
<linearGradient id="d-spark-up" x1="0" y1="1" x2="0" y2="0">
  <stop offset="0" stop-color="#F5A623" stop-opacity="0"/>
  <stop offset="1" stop-color="#F5A623" stop-opacity=".28"/></linearGradient>
<radialGradient id="d-halo-am" cx="50%" cy="0%" r="70%">
  <stop offset="0" stop-color="#F5A623" stop-opacity=".4"/>
  <stop offset=".45" stop-color="#B36A10" stop-opacity=".1"/>
  <stop offset="1" stop-color="#F5A623" stop-opacity="0"/></radialGradient>
<radialGradient id="d-amb1" cx="50%" cy="50%">
  <stop offset="0" stop-color="#F5A623" stop-opacity=".05"/>
  <stop offset="1" stop-color="#F5A623" stop-opacity="0"/></radialGradient>
<radialGradient id="d-amb2" cx="50%" cy="50%">
  <stop offset="0" stop-color="#3E9BE0" stop-opacity=".04"/>
  <stop offset="1" stop-color="#3E9BE0" stop-opacity="0"/></radialGradient>
<filter id="d-blur-l" x="-90%" y="-90%" width="280%" height="280%">
  <feGaussianBlur stdDeviation="16"/></filter>
<filter id="d-blur-s" x="-90%" y="-90%" width="280%" height="280%">
  <feGaussianBlur stdDeviation="6"/></filter>
</defs></svg>"""


def sparkline(
    values: list[float],
    width: float = 100.0,
    height: float = 24.0,
    fill: bool = False,
) -> str:
    """Мини-график по ряду значений.

    Цвет выбирается по направлению: растущий ряд янтарный,
    падающий — приглушённый тёплый.
    """
    if not values or len(values) < 2:
        return ""

    lo, hi = min(values), max(values)
    span = hi - lo
    if span <= 0:
        span = 1.0

    step = width / (len(values) - 1)
    pad = 2.0
    usable = height - pad * 2

    points: list[str] = []
    for i, v in enumerate(values):
        x = i * step
        y = pad + (1 - (v - lo) / span) * usable
        points.append(f"{x:.1f},{y:.1f}")

    rising = values[-1] >= values[0]
    stroke = AMBER if rising else "#7a5a44"
    dot = AMBER_LIGHT if rising else RUST

    path = " ".join(points)
    last_x = (len(values) - 1) * step
    last_y = pad + (1 - (values[-1] - lo) / span) * usable

    area = ""
    if fill and rising:
        area = (f'<polyline points="{path} {last_x:.1f},{height} 0,{height}" '
                f'fill="url(#d-spark-up)"/>')

    return (
        f'<svg viewBox="0 0 {width:.0f} {height:.0f}" preserveAspectRatio="none" '
        f'aria-hidden="true">{area}'
        f'<polyline points="{path}" fill="none" stroke="{stroke}" '
        f'stroke-width="1.2" vector-effect="non-scaling-stroke"/>'
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="1.8" fill="{dot}"/>'
        f'</svg>'
    )


def arc_path(cx: float, cy: float, r: float, frac: float, start_deg: float = -90.0) -> str:
    """Дуга окружности на долю frac от полного круга."""
    frac = max(0.0, min(frac, 0.9999))
    if frac <= 0:
        return ""
    sweep = frac * 360.0
    a0 = start_deg * pi / 180
    a1 = (start_deg + sweep) * pi / 180
    x0, y0 = cx + r * cos(a0), cy + r * sin(a0)
    x1, y1 = cx + r * cos(a1), cy + r * sin(a1)
    large = 1 if sweep > 180 else 0
    return f"M{x0:.2f} {y0:.2f} A{r} {r} 0 {large} 1 {x1:.2f} {y1:.2f}"


def ring(
    cx: float,
    cy: float,
    r: float,
    frac: float,
    color: str = AMBER,
    track: str = "rgba(255,255,255,.07)",
    stroke_width: float = 3.0,
) -> str:
    """Кольцо с закрашенной дугой."""
    out = (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
           f'stroke="{track}" stroke-width="{stroke_width}"/>')
    path = arc_path(cx, cy, r, frac)
    if path:
        out += (f'<path d="{path}" fill="none" stroke="{color}" '
                f'stroke-width="{stroke_width}" stroke-linecap="round"/>')
    return out


def bar_row(
    x: float,
    y: float,
    width: float,
    frac: float,
    color: str = AMBER,
    height: float = 3.0,
) -> str:
    """Горизонтальная полоса заполнения."""
    frac = max(0.0, min(frac, 1.0))
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" '
        f'rx="{height/2}" fill="#ffffff" fill-opacity=".07"/>'
        f'<rect x="{x}" y="{y}" width="{width*frac:.1f}" height="{height}" '
        f'rx="{height/2}" fill="{color}"/>'
    )


def tone_for_score(score: int) -> str:
    """Цвет полосы скора по диапазону."""
    if score >= 70:
        return AMBER
    if score >= 50:
        return "#D9B84A"
    return STEEL


def tone_for_change(v: float | None) -> str:
    if v is None or v == 0:
        return STEEL
    return GREEN if v > 0 else RUST
