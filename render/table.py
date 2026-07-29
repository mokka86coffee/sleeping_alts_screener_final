"""Таблица всей выборки: плотный терминальный обзор.

Колонки собраны в тематические группы с цветовым кодом дашборда:
объём — янтарный, внимание — синий, паттерн — золотой, риск — белый/охра,
сделка — зелёный.

Первые четыре колонки закреплены при горизонтальном скролле:
тикер (ссылка на TradingView), соцсети, аномальный объём, taiko.
"""

from __future__ import annotations

from core.models import Candidate
from render.blocks import render_caption
from render.card import tv_url
from render.svg import tone_for_score
from render.theme import GREEN, RUST, STEEL, esc

VISIBLE_ROWS = 60
FADE_TAIL = 6

AMBER = "#F5A623"
AMBER_L = "#FFD98A"
BLUE = "#3E9BE0"
BLUE_L = "#BFE4FF"
GOLD = "#D9B84A"


# ─────────────────────────────────────────────────────────────
# Безопасные геттеры
# ─────────────────────────────────────────────────────────────
def _raw(c: Candidate, key: str, default: float = 0.0) -> float:
    try:
        return float((c.raw or {}).get(key) or default)
    except (TypeError, ValueError):
        return default


def _seq(c: Candidate, key: str) -> list[float]:
    src = (c.raw or {}).get(key) or []
    out = []
    for v in src:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            pass
    return out


def _tick(c: Candidate) -> str:
    return esc(c.symbol.replace("USDT", ""))


def _arc(pct: float, r: float) -> str:
    circ = 2 * 3.14159265 * r
    on = circ * max(0.0, min(100.0, pct)) / 100
    return f"{on:.2f} {circ - on:.2f}"


# ─────────────────────────────────────────────────────────────
# Графические примитивы
# ─────────────────────────────────────────────────────────────
def _ring(value: float, pct: float, color: str, r: float = 13,
          size: float = 32, dim: bool = False) -> str:
    """Кольцо со значением в центре."""
    op = ".35" if dim else "1"
    half = size / 2
    return (
        f'<svg class="sx-ring" viewBox="-{half} -{half} {size} {size}">'
        f'<circle r="{r}" fill="none" stroke="#1d2127" stroke-width="2.5"/>'
        f'<circle r="{r}" fill="none" stroke="{color}" stroke-width="2.5"'
        f' stroke-opacity="{op}" stroke-linecap="round"'
        f' stroke-dasharray="{_arc(pct, r)}" transform="rotate(-90)"/>'
        f'<text class="sx-ring-v" y="3.5" text-anchor="middle">{value:.0f}</text>'
        f'</svg>'
    )


def _bar(pct: float, color: str, width: int = 52) -> str:
    """Горизонтальная шкала."""
    w = max(0.0, min(100.0, pct))
    return (
        f'<span class="sx-bar" style="width:{width}px">'
        f'<i style="width:{w:.0f}%;background:{color}"></i></span>'
    )


def _badge(text: str, color: str, on: bool = True) -> str:
    """Пилюля-бейдж."""
    cls = "sx-badge" if on else "sx-badge off"
    return f'<span class="{cls}" style="--bc:{color}">{esc(text)}</span>'


def _steps(active: int, total: int, color: str) -> str:
    """Степ-индикатор фазы."""
    out = "".join(
        f'<i class="{"on" if i < active else ""}"></i>' for i in range(total)
    )
    return f'<span class="sx-steps" style="--sc:{color}">{out}</span>'


def _sparkbars(values: list[float], color: str, n: int = 7) -> str:
    """Столбики истории, последний акцентный."""
    vals = values[-n:] if values else []
    if not vals:
        return '<span class="sx-sb empty"></span>'
    peak = max(vals) or 1
    bars = "".join(
        f'<i class="{"last" if i == len(vals) - 1 else ""}"'
        f' style="height:{max(12, v / peak * 100):.0f}%"></i>'
        for i, v in enumerate(vals)
    )
    return f'<span class="sx-sb" style="--sbc:{color}">{bars}</span>'


def _sparkline(values: list[float], up: bool, w: int = 72, h: int = 26) -> str:
    """Линия истории с маркером на конце."""
    if len(values) < 2:
        return '<span class="sx-sl empty"></span>'
    lo, hi = min(values), max(values)
    span = hi - lo
    pad = 3.0
    step = w / (len(values) - 1)
    pts = []
    for i, v in enumerate(values):
        k = 0.5 if span < 1e-9 else (v - lo) / span
        pts.append((i * step, (h - pad) - k * (h - pad * 2)))
    coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    color = GREEN if up else RUST
    lx, ly = pts[-1]
    return (
        f'<svg class="sx-sl" viewBox="0 0 {w} {h}">'
        f'<polyline points="{coords}" fill="none" stroke="{color}"'
        f' stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2" fill="{color}"/></svg>'
    )


def _bipolar(value: float, cap: float = 0.1) -> str:
    """Биполярная шкала со знаком относительно нуля."""
    k = max(-1.0, min(1.0, value / cap if cap else 0))
    color = RUST if k > 0 else STEEL
    width = abs(k) * 50
    side = "left:50%" if k >= 0 else f"right:50%"
    sign = "+" if value >= 0 else ""
    return (
        f'<span class="sx-bp">'
        f'<i style="{side};width:{width:.0f}%;background:{color}"></i></span>'
        f'<b class="sx-bp-v" style="color:{color}">{sign}{value:.3f}%</b>'
    )


def _levels(entry: float, stop: float, take: float) -> str:
    """Шкала уровней: стоп — вход — цель."""
    if not entry:
        return '<span class="sx-lv empty">уровней нет</span>'
    lo = min(stop or entry, entry, take or entry)
    hi = max(stop or entry, entry, take or entry)
    span = (hi - lo) or 1
    pos = (entry - lo) / span * 100
    return (
        f'<span class="sx-lv"><i class="s"></i>'
        f'<i class="e" style="left:{pos:.0f}%"></i><i class="t"></i></span>'
        f'<b class="sx-lv-v">{_price(entry)}</b>'
    )


def _price(v: float) -> str:
    if not v:
        return "—"
    return f"{v:.4f}" if v < 100 else f"{v:,.2f}".replace(",", " ")


# ─────────────────────────────────────────────────────────────
# Ячейки
# ─────────────────────────────────────────────────────────────
def _cell_social(c: Candidate) -> str:
    """ВНИМАНИЕ · кольцо buzz плюс уровень."""
    buzz = _raw(c, "social_score")
    mult = _raw(c, "social_mult")
    hot = bool(getattr(c, "is_viral", False))
    if buzz <= 0 and not hot:
        return '<div class="sx-mut">—</div>'
    label = "hot" if buzz >= 60 or hot else ("warm" if buzz >= 30 else "cold")
    return (
        f'<div class="sx-soc">{_ring(buzz, buzz, BLUE, dim=not hot)}'
        f'<span class="sx-soc-l {label}">{label}'
        f'{f"<b>×{mult:.1f}</b>" if mult else ""}</span></div>'
    )


def _cell_surge(c: Candidate) -> str:
    """ОБЪЁМ · бейдж всплеска плюс множитель."""
    rvol = _raw(c, "rvol_1h")
    if not c.surge:
        return f'<div class="sx-mut">{rvol:.1f}×</div>' if rvol else '<div class="sx-mut">—</div>'
    strength = (c.surge or {}).get("strength_label", "") if isinstance(c.surge, dict) else ""
    return (
        f'<div class="sx-surge">{_badge(f"×{rvol:.1f}" if rvol else "surge", AMBER)}'
        f'{f"<span class=sx-sub2>{esc(strength)}</span>" if strength else ""}</div>'
    )


def _cell_taiko(c: Candidate) -> str:
    """ПАТТЕРН · taiko со статусом подтверждения."""
    if not c.taiko:
        return '<div class="sx-mut">—</div>'
    confirmed = bool((c.taiko or {}).get("confirmed_breakout"))
    color = GREEN if confirmed else AMBER_L
    note = "подтв." if confirmed else "разворот"
    return (
        f'<div class="sx-taiko">{_badge("taiko", color)}'
        f'<span class="sx-sub2">{note}</span></div>'
    )


def _cell_signals(c: Candidate) -> str:
    """Прочие паттерны чипами."""
    chips = []
    if c.dexe:
        chips.append(_badge("dexe", RUST))
    if (c.phase or {}).get("num", 0) == 2:
        chips.append(_badge("база", GOLD))
    if _raw(c, "rvol_1h") >= 3.0:
        chips.append(_badge("импульс", AMBER))
    if not chips:
        return '<div class="sx-mut">—</div>'
    return f'<div class="sx-chips">{"".join(chips)}</div>'


def _cell_veto(c: Candidate) -> str:
    """РИСК · точки по числу вето плюс причина."""
    veto = getattr(c, "veto", None) or []
    dots = ""
    for i in range(3):
        if i < len(veto):
            sev = getattr(veto[i], "severity", "low")
            col = RUST if sev == "high" else (GOLD if sev == "mid" else STEEL)
            dots += f'<i class="on" style="background:{col}"></i>'
        else:
            dots += "<i></i>"
    if not veto:
        return (f'<div class="sx-veto"><span class="sx-dots">{dots}</span>'
                f'<span class="sx-veto-l ok">чисто</span></div>')
    label = str(getattr(veto[0], "label", "вето")).lower()
    if len(veto) > 1:
        label = f"{len(veto)} вето"
    return (f'<div class="sx-veto"><span class="sx-dots">{dots}</span>'
            f'<span class="sx-veto-l bad">{esc(label)}</span></div>')


def _cell_action(c: Candidate) -> str:
    if c.vetoed:
        return '<div class="sx-act mut">под вето</div>'
    if getattr(c, "tradable", False):
        return '<div class="sx-act go">открыть</div>'
    return '<div class="sx-act">→</div>'


# ─────────────────────────────────────────────────────────────
# Сборка
# ─────────────────────────────────────────────────────────────
GROUPS = [
    ("", 1), ("база", 3), ("внимание", 1), ("объём", 4),
    ("цена", 3), ("паттерн", 3), ("риск", 3), ("сделка", 3),
]

HEAD_COLS = [
    ("#", "sx-idx"), ("монета", "sx-c-sym"), ("соцсети", "sx-c-soc"),
    ("объём", "sx-c-surge"), ("taiko", "sx-c-taiko"),
    ("score", ""), ("rvol 1ч", ""), ("объём 7д", ""), ("импульс", ""),
    ("24ч", ""), ("цена 7д", ""), ("от ath", ""),
    ("фаза", ""), ("сигналы", ""), ("сектор", ""),
    ("вето", ""), ("фандинг", ""), ("r:r", ""),
    ("уровни", ""), ("цена", ""), ("", ""),
]


def render_scan_table(candidates: list[Candidate]) -> str:
    """Полная выборка одной таблицей."""
    if not candidates:
        return ""

    ordered = sorted(candidates, key=lambda c: -c.score)
    shown = ordered[:VISIBLE_ROWS]
    total = len(ordered)

    head = "".join(
        f'<th class="{cls}">{esc(label)}</th>' for label, cls in HEAD_COLS
    )

    rows = ""

    # Хвост приглушаем только когда список длинный: иначе на коротком срезе
    # (2-5 строк) под fade попадает вся таблица целиком.
    fade_from = total_shown if total_shown <= FADE_TAIL * 2 else total_shown - FADE_TAIL

    for i, c in enumerate(shown, 1):
        ch24 = _raw(c, "ch_24h")
        rr = getattr(c, "rr", 0) or 0
        lv = getattr(c.strategy, "levels", None)
        entry = float(getattr(lv, "entry", 0) or 0)
        stop = float(getattr(lv, "stop", 0) or 0)
        take = float(getattr(lv, "take", 0) or 0)

        cls = ["sxr"]
        if c.vetoed:
            cls.append("vetoed")
        if i - 1 >= fade_from:
            cls.append("faded")

        # цвет риски слева = доминирующий сигнал строки
        if c.vetoed:
            accent = RUST
        elif getattr(c, "tradable", False):
            accent = GREEN
        elif c.taiko:
            accent = AMBER_L
        elif c.surge:
            accent = AMBER
        else:
            accent = STEEL

        score_c = tone_for_score(c.score)
        ath = _raw(c, "from_ath")
        rvol = _raw(c, "rvol_1h")
        imp = _raw(c, "rvol_1h")
        phase_n = int((c.phase or {}).get("num", 0) or 0)
        phase_l = str((c.phase or {}).get("label", "—")).lower()
        sector = (c.sector or "—").lower()
        up = ch24 >= 0
        rr_cls = "up" if rr >= 3 else ("am" if rr >= 2 else "mut")

        rows += f"""
<tr class="{' '.join(cls)}" style="--acc:{accent}">
  <td class="sx-idx">{i:02d}</td>
  <td class="sx-c-sym">
    <a class="sx-sym" href="{esc(tv_url(c.symbol))}" target="_blank"
       rel="noopener">{_tick(c)}<svg viewBox="0 0 8 8"><path d="M2 6 L6 2 M3 2h3v3"
       fill="none" stroke="currentColor" stroke-width="1"/></svg></a>
    <span class="sx-sub">{esc(sector)} · перп</span>
  </td>
  <td class="sx-c-soc">{_cell_social(c)}</td>
  <td class="sx-c-surge">{_cell_surge(c)}</td>
  <td class="sx-c-taiko">{_cell_taiko(c)}</td>

  <td>{_ring(c.score, min(c.score, 100), score_c, r=15, size=36)}</td>
  <td><b class="sx-n am">{rvol:.1f}×</b>{_bar(min(rvol / 10 * 100, 100), AMBER)}</td>
  <td>{_sparkbars(_seq(c, "vol_7d"), AMBER)}</td>
  <td>{_bar(min(imp / 6 * 100, 100), AMBER_L, 40)}</td>

  <td><b class="sx-n {'up' if up else 'dn'}">{ch24:+.1f}%</b></td>
  <td>{_sparkline(_seq(c, "spark_1d"), up)}</td>
  <td><b class="sx-n mut">{ath:.0f}%</b>{_bar(max(0, 100 + ath), RUST, 40)}</td>

  <td>{_steps(phase_n, 4, GOLD)}<span class="sx-sub2">{esc(phase_l)}</span></td>
  <td>{_cell_signals(c)}</td>
  <td><span class="sx-sub2">{esc(sector)}</span></td>

  <td>{_cell_veto(c)}</td>
  <td>{_bipolar(_raw(c, "funding") * 100)}</td>
  <td><b class="sx-rr {rr_cls}">{f"1:{rr:.1f}" if rr else "—"}</b></td>

  <td>{_levels(entry, stop, take)}</td>
  <td><b class="sx-n">{_price(_raw(c, "price"))}</b></td>
  <td>{_cell_action(c)}</td>
</tr>"""

    more = (f'<span class="sx-f-m">показано {len(shown)} из {total}</span>'
            if total > len(shown) else "")

    return (
        '<div class="scan">'
        + render_caption("ВСЯ ВЫБОРКА", "полный список после отбора",
                         f"{total} монет")
        + '<div class="sx-hint">колонки прокручиваются вбок · '
          'первые четыре закреплены</div>'
        + '<div class="sx-wrap"><table class="sx">'
        + f'<thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'
        + f'<div class="sx-f"><span>всего {total} монет</span>{more}'
          f'<span class="sx-f-r">score = объём · структура · импульс</span></div>'
        + "</div>"
    )

def _rows(shown: list[Candidate], total_shown: int) -> str:
    """Строки таблицы. Хвост приглушается, чтобы взгляд не тянуло вниз."""
    rows = ""
    # Хвост приглушаем только когда список длинный: иначе на коротком срезе
    # (2-5 строк) под fade попадает вся таблица целиком.
    fade_from = total_shown if total_shown <= FADE_TAIL * 2 else total_shown - FADE_TAIL

    for i, c in enumerate(shown, 1):
        ch24 = _raw(c, "ch_24h")
        rr = getattr(c, "rr", 0) or 0
        lv = getattr(c.strategy, "levels", None)
        entry = float(getattr(lv, "entry", 0) or 0)
        stop = float(getattr(lv, "stop", 0) or 0)
        take = float(getattr(lv, "take", 0) or 0)

        cls = ["sxr"]
        if c.vetoed:
            cls.append("vetoed")
        if i - 1 >= fade_from:
            cls.append("faded")

        if c.vetoed:
            accent = RUST
        elif getattr(c, "tradable", False):
            accent = GREEN
        elif c.taiko:
            accent = AMBER_L
        elif c.surge:
            accent = AMBER
        else:
            accent = STEEL

        score_c = tone_for_score(c.score)
        ath = _raw(c, "from_ath")
        rvol = _raw(c, "rvol_1h")
        phase_n = int((c.phase or {}).get("num", 0) or 0)
        phase_l = str((c.phase or {}).get("label", "—")).lower()
        sector = (c.sector or "—").lower()
        up = ch24 >= 0
        rr_cls = "up" if rr >= 3 else ("am" if rr >= 2 else "mut")

        rows += f"""
<tr class="{' '.join(cls)}" style="--acc:{accent}" data-coin="{esc(c.symbol)}">
  <td class="sx-idx">{i:02d}</td>
  <td class="sx-c-sym">
    <a class="sx-sym" href="{esc(tv_url(c.symbol))}" target="_blank"
       rel="noopener">{_tick(c)}<svg viewBox="0 0 8 8"><path d="M2 6 L6 2 M3 2h3v3"
       fill="none" stroke="currentColor" stroke-width="1"/></svg></a>
    <span class="sx-sub">{esc(sector)} · перп</span>
  </td>
  <td class="sx-c-soc">{_cell_social(c)}</td>
  <td class="sx-c-surge">{_cell_surge(c)}</td>
  <td class="sx-c-taiko">{_cell_taiko(c)}</td>

  <td>{_ring(c.score, min(c.score, 100), score_c, r=15, size=36)}</td>
  <td><b class="sx-n am">{rvol:.1f}×</b>{_bar(min(rvol / 10 * 100, 100), AMBER)}</td>
  <td>{_sparkbars(_seq(c, "vol_7d"), AMBER)}</td>
  <td>{_bar(min(rvol / 6 * 100, 100), AMBER_L, 40)}</td>

  <td><b class="sx-n {'up' if up else 'dn'}">{ch24:+.1f}%</b></td>
  <td>{_sparkline(_seq(c, "spark_1d"), up)}</td>
  <td><b class="sx-n mut">{ath:.0f}%</b>{_bar(max(0, 100 + ath), RUST, 40)}</td>

  <td>{_steps(phase_n, 4, GOLD)}<span class="sx-sub2">{esc(phase_l)}</span></td>
  <td>{_cell_signals(c)}</td>
  <td><span class="sx-sub2">{esc(sector)}</span></td>

  <td>{_cell_veto(c)}</td>
  <td>{_bipolar(_raw(c, "funding") * 100)}</td>
  <td><b class="sx-rr {rr_cls}">{f"1:{rr:.1f}" if rr else "—"}</b></td>

  <td>{_levels(entry, stop, take)}</td>
  <td><b class="sx-n">{_price(_raw(c, "price"))}</b></td>
  <td>{_cell_action(c)}</td>
</tr>"""
    return rows



# ─────────────────────────────────────────────────────────────
# Публичные рендеры
# ─────────────────────────────────────────────────────────────
def render_table(items: list[Candidate], limit: int = VISIBLE_ROWS) -> str:
    """Тело таблицы без обёрток. Используется и полной выборкой,
    и панелями срезов дашборда."""
    if not items:
        return '<div class="sx-empty">в этом срезе монет нет</div>'

    ordered = sorted(items, key=lambda c: -c.score)
    shown = ordered[:limit]

    head = "".join(
        f'<th class="{cls}">{esc(label)}</th>' for label, cls in HEAD_COLS
    )
    rows = _rows(shown, total_shown=len(shown))

    return (
        '<div class="sx-wrap"><table class="sx">'
        f'<thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'
    )


def render_slice_pane(s: dict, limit: int = VISIBLE_ROWS) -> str:
    """Панель среза для дашборда: шапка с кнопкой возврата плюс таблица."""
    items = s.get("items") or []
    total = len(items)
    more = (f'<span class="sx-f-m">показано {min(total, limit)} из {total}</span>'
            if total > limit else "")

    return f"""
<div class="pane" data-pane="{esc(s['id'])}">
  <div class="pane-hd">
    <button class="pane-back">← назад</button>
    <span class="pane-t">{esc(str(s.get('label', '')).lower())}</span>
    <span class="pane-c">{total}</span>
    <span class="pane-n">{esc(str(s.get('note', '')))}</span>
  </div>
  {render_table(items, limit)}
  <div class="sx-f"><span>всего {total} монет</span>{more}
    <span class="sx-f-r">score = объём · структура · импульс</span></div>
</div>"""
