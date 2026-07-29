"""Воронка отбора и сводка по секторам в стеклянном стиле."""

from __future__ import annotations

from core.models import RunSnapshot
from render.blocks import render_caption
from render.svg import bar_row, ring, tone_for_change
from render.theme import AMBER, AMBER_LIGHT, GREEN, RUST, STEEL, esc

# Геометрия воронки
FUNNEL_W = 1200.0
FUNNEL_H = 260.0
NODE_Y = 118.0
NODE_R_MAX = 46.0
NODE_R_MIN = 20.0


def render_funnel(snapshot: RunSnapshot) -> str:
    """Путь отбора: от всей выборки до монет в работе.

    Размер кольца пропорционален доле от исходной выборки, дуга — той же доле.
    Между узлами подписан процент прошедших и абсолютный отсев.
    """
    stages = snapshot.funnel
    if not stages:
        return ""

    n = len(stages)
    left, right = 80.0, FUNNEL_W - 80.0
    step = (right - left) / max(n - 1, 1)

    nodes = ""
    arrows = ""

    for i, st in enumerate(stages):
        cx = left + i * step
        share = st.share_pct / 100.0
        # Радиус по квадратному корню доли: площадь читается честнее диаметра
        radius = NODE_R_MIN + (NODE_R_MAX - NODE_R_MIN) * (share ** 0.5)

        is_last = i == n - 1
        color = GREEN if is_last and st.count > 0 else AMBER
        if st.count == 0:
            color = STEEL

        nodes += f'<g>{ring(cx, NODE_Y, radius, share, color=color, stroke_width=2.4)}'
        nodes += (
            f'<text x="{cx}" y="{NODE_Y + 4}" text-anchor="middle" '
            f'fill="#f2f2f5" font-size="17" font-weight="200" '
            f'letter-spacing="1">{st.count}</text>'
        )
        nodes += (
            f'<text x="{cx}" y="{NODE_Y + NODE_R_MAX + 24}" text-anchor="middle" '
            f'fill="#5a606a" font-size="7.5" font-weight="300" '
            f'letter-spacing="2">{esc(st.label.upper())}</text>'
        )
        nodes += (
            f'<text x="{cx}" y="{NODE_Y + NODE_R_MAX + 38}" text-anchor="middle" '
            f'fill="#33333c" font-size="6.5" font-weight="300" '
            f'letter-spacing="1.5">{st.share_pct:.0f}% выборки</text>'
        )
        nodes += "</g>"

        # Стрелка к следующему узлу
        if not is_last:
            nxt = stages[i + 1]
            x0 = cx + radius + 8
            x1 = cx + step - NODE_R_MAX - 8
            if x1 > x0:
                mid = (x0 + x1) / 2
                arrows += (
                    f'<path d="M{x0:.0f} {NODE_Y} H{x1:.0f}" stroke="#2a2a33" '
                    f'stroke-width="1" fill="none"/>'
                    f'<path d="M{x1-5:.0f} {NODE_Y-3} l4 3 l-4 3" stroke="#3a3a44" '
                    f'stroke-width="1" fill="none" stroke-linecap="round" '
                    f'stroke-linejoin="round"/>'
                    f'<text x="{mid:.0f}" y="{NODE_Y - 12}" text-anchor="middle" '
                    f'fill="#8a95a0" font-size="8" font-weight="300" '
                    f'letter-spacing="1">{nxt.pass_pct:.0f}%</text>'
                    f'<text x="{mid:.0f}" y="{NODE_Y + 20}" text-anchor="middle" '
                    f'fill="#43434e" font-size="6.5" font-weight="300" '
                    f'letter-spacing="1">−{nxt.dropped}</text>'
                )

    regime = snapshot.market_regime
    note = (f"{regime.get('regime', '—')} · аппетит {regime.get('appetite', 0)}/5")

    svg = f"""
<svg viewBox="0 0 {FUNNEL_W:.0f} {FUNNEL_H:.0f}" xmlns="http://www.w3.org/2000/svg"
     font-family="Inter, Helvetica Neue, Arial, sans-serif">
  <circle cx="180" cy="60" r="260" fill="url(#d-amb1)"/>
  <circle cx="1020" cy="220" r="260" fill="url(#d-amb2)"/>
  <ellipse cx="{FUNNEL_W/2:.0f}" cy="10" rx="420" ry="30"
           fill="url(#d-halo-am)" filter="url(#d-blur-l)" opacity=".45"/>
  {arrows}
  {nodes}
</svg>"""

    return (
        '<div class="gwrap">'
        + render_caption("ВОРОНКА ОТБОРА", "каждый узел — подмножество предыдущего", note)
        + f'<div class="gpanel">{svg}</div>'
        + "</div>"
    )


def render_sectors(snapshot: RunSnapshot) -> str:
    """Сектора по средней динамике за сутки."""
    sectors = snapshot.sectors
    if not sectors:
        return ""

    rows = ""
    max_abs = max(abs(s["avg_change_24h"]) for s in sectors) or 1.0
    width = 420.0
    row_h = 30.0
    top = 26.0

    for i, s in enumerate(sectors):
        y = top + i * row_h
        change = s["avg_change_24h"]
        frac = abs(change) / max_abs
        color = tone_for_change(change)

        rows += (
            f'<text x="26" y="{y + 4:.0f}" fill="#c8ccd4" font-size="9" '
            f'font-weight="300" letter-spacing="2">{esc(s["sector"])}</text>'
            f'<text x="124" y="{y + 4:.0f}" fill="#43434e" font-size="7" '
            f'font-weight="300" letter-spacing="1">{s["count"]} монет</text>'
            + bar_row(196, y - 1, width, frac, color=color)
            + f'<text x="{196 + width + 16:.0f}" y="{y + 4:.0f}" fill="{color}" '
              f'font-size="10" font-weight="200" letter-spacing="1">'
              f'{change:+.1f}%</text>'
            + f'<text x="{196 + width + 92:.0f}" y="{y + 4:.0f}" fill="#3a3a44" '
              f'font-size="7" font-weight="300" letter-spacing="1">'
              f'лучший {s["best"]:+.0f}% · худший {s["worst"]:+.0f}%</text>'
        )

    height = top + len(sectors) * row_h + 16

    svg = f"""
<svg viewBox="0 0 1200 {height:.0f}" xmlns="http://www.w3.org/2000/svg"
     font-family="Inter, Helvetica Neue, Arial, sans-serif">
  {rows}
</svg>"""

    leader = sectors[0]["sector"]
    return (
        '<div class="gwrap">'
        + render_caption("СЕКТОРА", "средняя динамика за 24 часа", f"лидер {leader}")
        + f'<div class="gpanel">{svg}</div>'
        + "</div>"
    )
