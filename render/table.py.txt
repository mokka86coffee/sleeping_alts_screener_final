"""Таблица всей выборки: плотный обзор с сортировкой по скору."""

from __future__ import annotations

from core.models import Candidate
from render.blocks import render_caption
from render.card import tv_url
from render.svg import sparkline, tone_for_score
from render.theme import (
    GREEN, RUST, STEEL, esc, metric_val, sign_class,
)

VISIBLE_ROWS = 40      # сколько строк показываем сразу
FADE_TAIL = 6          # последние строки приглушаются


def _risk_cell(c: Candidate) -> str:
    """Индикатор риска: точка плюс подпись."""
    if not c.veto:
        return (f'<div class="st-risk"><span class="st-dot" style="--rt:{GREEN}"></span>'
                f'<span class="st-rl" style="--rl:#4a6a58">чисто</span></div>')

    top = c.veto[0]
    if top.severity == "high":
        color, label_color = RUST, "#8a6a58"
        filled = " filled"
    elif top.severity == "mid":
        color, label_color = "#D9B84A", "#6a6242"
        filled = ""
    else:
        color, label_color = STEEL, "#4a5058"
        filled = ""

    label = top.label.lower()
    return (f'<div class="st-risk">'
            f'<span class="st-dot{filled}" style="--rt:{color}"></span>'
            f'<span class="st-rl" style="--rl:{label_color}">{esc(label)}</span></div>')


def _pattern_cell(c: Candidate) -> str:
    """Название паттерна и его состояние."""
    if c.taiko:
        name = "taiko"
        note = "подтверждён" if (c.taiko or {}).get("confirmed_breakout") else "разворот"
    elif c.dexe:
        name = "dexe"
        note = "после дампа"
    elif c.surge:
        name = "surge"
        note = (c.surge or {}).get("strength_label", "")
    elif c.phase.get("num", 0) == 2:
        name = "база"
        note = "формируется"
    else:
        return '<div class="st-txt" style="color:#4e5158">—</div>'

    return (f'<div><div class="st-txt">{esc(name)}</div>'
            f'<div class="st-txt-d">{esc(note)}</div></div>')


def _action_cell(c: Candidate) -> str:
    """Кнопка действия либо метка вето."""
    if c.vetoed:
        return '<div class="st-act mut">под вето</div>'
    if c.tradable:
        return '<div class="st-act">открыть</div>'
    return '<div class="st-arrow">→</div>'


def render_scan_table(candidates: list[Candidate]) -> str:
    """Полная выборка одной таблицей."""
    if not candidates:
        return ""

    ordered = sorted(candidates, key=lambda c: -c.score)
    shown = ordered[:VISIBLE_ROWS]
    total = len(ordered)

    header = (
        '<div class="sth">'
        '<b>#</b><b>тикер</b><b>score</b><b>rvol</b><b>24ч</b><b>паттерн</b>'
        '<b>r:r</b><b>от ath</b><b>риск</b><b>динамика 24ч</b><b>вход</b><b></b>'
        '</div>'
    )

    rows = ""
    fade_from = max(len(shown) - FADE_TAIL, 0)

    for i, c in enumerate(shown, 1):
        ch24 = c.raw.get("ch_24h")
        rr = c.rr
        classes = ["strow"]
        if c.vetoed:
            classes.append("vetoed")
        if i - 1 >= fade_from:
            classes.append("faded")

        score_color = tone_for_score(c.score)
        score_frac = min(c.score / 100.0, 1.0)

        rr_class = "up" if rr >= 2.0 else ("am" if rr >= 1.5 else "mut")
        rr_text = f"1:{rr:.1f}" if rr > 0 else "—"

        sector = c.sector.lower() if c.sector else "—"
        spark = sparkline(c.raw.get("spark_1d") or [], fill=True)

        rows += f"""
<a class="{' '.join(classes)}" href="{esc(tv_url(c.symbol))}" target="_blank" rel="noopener">
  <div class="st-idx">{i:02d}</div>
  <div><div class="st-sym">{esc(c.symbol)}</div>
       <div class="st-sub">{esc(sector)} · перп</div></div>
  <div class="st-score">
    <svg viewBox="0 0 86 3" preserveAspectRatio="none" style="width:86px;height:3px">
      <rect width="86" height="3" rx="1.5" fill="#ffffff" fill-opacity=".07"/>
      <rect width="{86*score_frac:.1f}" height="3" rx="1.5" fill="{score_color}"/>
    </svg>
    <span class="st-num" style="color:{score_color}">{c.score}</span>
  </div>
  <div class="st-num am">{esc(metric_val(c.metrics, "RVOL 1H"))}</div>
  <div class="st-num {sign_class(ch24)}">{esc(metric_val(c.metrics, "24h"))}</div>
  {_pattern_cell(c)}
  <div class="st-num {rr_class}">{esc(rr_text)}</div>
  <div class="st-num mut">{esc(metric_val(c.metrics, "От ATH"))}</div>
  {_risk_cell(c)}
  <div class="st-spark">{spark}</div>
  <div class="st-num">{esc(metric_val(c.metrics, "Цена"))}</div>
  {_action_cell(c)}
</a>"""

    more = ""
    if total > len(shown):
        more = '<div class="stf-more">показано ' \
               f'{len(shown)} из {total}</div>'

    footer = f"""
<div class="stf">
  <span class="stf-l">всего {total} монет</span>
  {more}
  <span class="stf-l">сортировка по score</span>
</div>"""

    legend = f"""
<div class="stf-legend">
  <span><svg width="7" height="7"><circle cx="3.5" cy="3.5" r="3"
    fill="none" stroke="{GREEN}" stroke-opacity=".5"/></svg>чисто</span>
  <span><svg width="7" height="7"><circle cx="3.5" cy="3.5" r="3"
    fill="none" stroke="#D9B84A" stroke-opacity=".5"/></svg>внимание</span>
  <span><svg width="7" height="7"><circle cx="3.5" cy="3.5" r="3"
    fill="rgba(196,112,58,.18)" stroke="{RUST}" stroke-opacity=".5"/></svg>под вето</span>
  <span style="margin-left:auto">score = объём · структура · импульс</span>
</div>"""

    return (
        '<div class="scan">'
        + render_caption("ВСЯ ВЫБОРКА", "полный список после отбора", f"{total} монет")
        + f'<div class="stbl">{header}{rows}{footer}</div>'
        + legend
        + "</div>"
    )
