"""Крупные блоки страницы: шапка, панель приборов, легенда, заголовки секций."""

from __future__ import annotations

from datetime import datetime

from core.config import (
    MAX_SYMBOLS, MIN_QUOTE_VOLUME_24H, MIN_RR_TRADABLE,
    VETO_FUNDING_ABS, VETO_MAX_ATR_PCT, VETO_MIN_OI_USD,
)
from core.models import RunSnapshot
from render.theme import big, esc

STAGE_LABEL = "STAGE 3"


def _fmt_timestamp(iso: str) -> str:
    """ISO в человеческий вид."""
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return iso


def render_dashboard(snapshot: RunSnapshot) -> str:
    """Панель приборов: сводка по категориям."""
    c = snapshot.counts
    cells = [
        ("VIRAL", c.get("viral", 0), "вирусный разгон", "dc-1"),
        ("TAIKO", c.get("taiko", 0), "разворот HTF", "dc-1"),
        ("DEXE", c.get("dexe", 0), "после дампа", "dc-2"),
        ("STRONG", c.get("strong", 0), "сильная связка", "dc-2"),
        ("GOOD", c.get("good", 0), "рабочие сетапы", "dc-3"),
        ("SCOUT", c.get("scout", 0), "ранняя стадия", "dc-4"),
        ("WATCH", c.get("watch", 0), "наблюдение", "dc-5"),
    ]
    out = ""
    for label, count, desc, tone in cells:
        empty = " empty" if count == 0 else ""
        out += (f'<div class="dcell {tone}{empty}">'
                f'<div class="dcell-l">{esc(label)}</div>'
                f'<div class="dcell-v">{count}</div>'
                f'<div class="dcell-d">{esc(desc)}</div></div>')
    return f'<div class="dash">{out}</div>'


def render_legend(snapshot: RunSnapshot) -> str:
    """Раскрывающаяся легенда с категориями и порогами."""
    categories = [
        ("VIRAL", "спекулятивный сектор, всплеск внимания и объёма"),
        ("TAIKO", "разворот на старшем таймфрейме подтверждён"),
        ("DEXE", "отскок после дампа, post-pump капитуляция"),
        ("STRONG", "совпало несколько независимых условий"),
        ("GOOD", "сетап пригоден к торговле, риск умеренный"),
        ("SCOUT", "ранняя стадия, вход преждевременен"),
        ("WATCH", "только наблюдение, действий нет"),
    ]

    thresholds = [
        ("RVOL 1H", "≥ 1.8×", "относительный объём часа"),
        ("VOL SURGE", "≥ 3.0×", "против среднего за 30 дней"),
        ("SQUEEZE", "≥ 60", "риск ликвидационного выброса"),
        ("ОБОРОТ 24H", big(MIN_QUOTE_VOLUME_24H), "минимальная ликвидность"),
        ("R:R", f"≥ {MIN_RR_TRADABLE:.0f}", "иначе сетап не берём в работу"),
        ("ФАНДИНГ", f"< {VETO_FUNDING_ABS}%", "выше — вето по перегреву"),
        ("OI МИН", big(VETO_MIN_OI_USD), "ниже — вето по ликвидности"),
        ("ATR МАКС", f"{VETO_MAX_ATR_PCT:.0f}%", "выше — вето по волатильности"),
        ("ПОД ВЕТО", f"{snapshot.counts.get('vetoed', 0)}", "монет исключено"),
        ("ЛИМИТ", f"{MAX_SYMBOLS}", "монет в обработке"),
    ]

    cats_html = "".join(
        f'<div class="lg-row"><span class="lg-k">{esc(k)}</span>'
        f'<span class="lg-v">{esc(v)}</span></div>'
        for k, v in categories
    )
    thr_html = "".join(
        f'<div class="lg-row"><span class="lg-k" style="width:96px">{esc(k)}</span>'
        f'<span class="lg-n">{esc(v)}</span>'
        f'<span class="lg-v">{esc(d)}</span></div>'
        for k, v, d in thresholds
    )

    return f"""
<details class="lg">
  <summary>
    <span class="lg-q">?</span>
    <span class="lg-t">ЛЕГЕНДА И ПОРОГИ</span>
    <span class="lg-d">описание категорий, метрик и условий отбора</span>
    <span class="lg-c"></span>
  </summary>
  <div class="lg-body">
    <div><div class="lg-h">КАТЕГОРИИ</div>{cats_html}</div>
    <div class="lg-sep"></div>
    <div><div class="lg-h">УСЛОВИЯ ОТБОРА</div>{thr_html}</div>
  </div>
</details>"""


def render_section(name: str, count: int, desc: str, tier: int) -> str:
    """Заголовок секции."""
    return f"""
<div class="sec t{tier}">
  <div class="sec-p">
    <span class="sec-n">{esc(name)}</span>
    <span class="sec-c">{count}</span>
  </div>
  <span class="sec-d">{esc(desc)}</span>
  <span class="sec-l"></span>
</div>"""


def render_caption(title: str, desc: str = "", note: str = "") -> str:
    """Подпись над стеклянным блоком."""
    desc_html = f'<span class="gcap-d">{esc(desc)}</span>' if desc else ""
    note_html = f'<span class="gcap-n">{esc(note)}</span>' if note else ""
    return (f'<div class="gcap"><span class="gcap-t">{esc(title)}</span>'
            f'{desc_html}{note_html}</div>')
