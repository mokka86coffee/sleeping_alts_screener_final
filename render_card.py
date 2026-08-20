"""Карточка монеты. Вёрстка перенесена без изменений, добавлен блок вето."""

from __future__ import annotations

from analytics_rr import build_rr, fmt_price
from core_models import Candidate
from render_theme import (
    arc_dash, big, esc, metric_cls, metric_num, metric_val, ticker_font,
)

TW_SVG = (
    '<svg viewBox="0 0 24 24"><path d="M23 4.9c-.8.4-1.7.6-2.6.8 1-.6 1.7-1.5 2-2.6'
    '-.9.5-1.9.9-3 1.1a4.7 4.7 0 0 0-8 4.3C7.5 8.3 4 6.5 1.7 3.7a4.7 4.7 0 0 0 1.5 6.3'
    'c-.8 0-1.5-.2-2.1-.6 0 2.3 1.6 4.2 3.8 4.6-.4.1-.8.2-1.2.2-.3 0-.6 0-.9-.1'
    '.6 1.9 2.4 3.3 4.4 3.3A9.5 9.5 0 0 1 0 19.5a13.3 13.3 0 0 0 7.2 2.1'
    'c8.7 0 13.4-7.2 13.4-13.4v-.6c.9-.7 1.7-1.5 2.4-2.7z"/></svg>'
)

SIGNAL_ICON = {
    "taiko": "✓",
    "dexe": "◉",
    "surge": "📊",
    "viral": "🚀",
    "euphoria": "!",
}

LINK_ICON = {
    "tradingview": "📈",
    "binance": "🅱",
    "coingecko": "🦎",
    "twitter": "𝕏",
}


def tv_url(symbol: str) -> str:
    return f"https://www.tradingview.com/chart/?symbol=BINANCE:{symbol}.P"


def _signal_note(kind: str, c: Candidate) -> str:
    """Пояснение под названием сигнала."""
    if kind == "taiko":
        return "разворот подтверждён на старшем ТФ"
    if kind == "dexe":
        d = c.dexe or {}
        return (f"дамп {d.get('dump_pct', 0):.0f}% · "
                f"дно {d.get('bottom_hours_ago', 0):.0f}ч назад")
    if kind == "surge":
        s = c.surge or {}
        return f"{big(s.get('current_vol_usd'))} против {big(s.get('avg_vol_usd'))}"
    if kind == "euphoria":
        return "сжатие волатильности, риск выброса"
    if kind == "viral":
        return "всплеск внимания и объёма"
    return ""


def _render_chips(c: Candidate, risky: bool) -> str:
    cats = [t for t in c.tags if "tag-cat" in t.get("class", "")]
    out = ""
    for t in cats[:4]:
        out += f'<span class="chip">{esc(t.get("text", ""))}</span>'
    if risky:
        out += '<span class="chip risk">HIGH RISK</span>'
    extra = len(cats) - 4
    if extra > 0:
        out += f'<span class="chip more">+{extra}</span>'
    return out


def _render_signals(c: Candidate) -> str:
    wide: list[str] = []
    for t in c.tags:
        cls = t.get("class", "")
        if not cls.startswith("tag-pattern"):
            continue
        kind = cls.replace("tag-pattern", "").strip() or "surge"
        text = t.get("text", "")
        note = _signal_note(kind, c)
        red = " rd" if kind == "euphoria" else ""
        icon = SIGNAL_ICON.get(kind, "◉")
        wide.append(
            f'<div class="sig{red}"><span class="sig-i">{icon}</span>'
            f'<div style="min-width:0"><div class="sig-t">{esc(text)}</div>'
            f'<div class="sig-d">{esc(note)}</div></div></div>'
        )

    half = [
        f'<div class="sig half"><span class="sig-i">≈</span><div style="min-width:0">'
        f'<div class="sig-t">FUNDING</div>'
        f'<div class="sig-d">{esc(metric_val(c.metrics, "Funding"))}</div></div></div>',
        f'<div class="sig half"><span class="sig-i">↑</span><div style="min-width:0">'
        f'<div class="sig-t">OPEN INTEREST</div>'
        f'<div class="sig-d">{esc(metric_val(c.metrics, "OI"))}</div></div></div>',
    ]

    return "".join(wide) + '<div class="sig-row">' + "".join(half) + "</div>"


def _render_veto(c: Candidate) -> str:
    if not c.veto:
        return ""
    rows = "".join(
        f'<div class="veto-row"><span class="veto-k">{esc(v.label)}</span>'
        f'<span class="veto-v">{esc(v.detail)}</span></div>'
        for v in c.veto
    )
    return (f'<div class="veto"><div class="veto-h">ПОД ВЕТО · {len(c.veto)}</div>'
            f'{rows}</div>')


def _render_perf(c: Candidate) -> str:
    out = ""
    for key, label in (("7d", "7D"), ("30d", "30D"), ("От ATH", "ATH"), ("OBV", "OBV")):
        val = metric_val(c.metrics, key)
        cls = "up" if metric_cls(c.metrics, key) == "up" else "dn"
        out += (f'<div><div class="perf-k">{label}</div>'
                f'<div class="perf-v {cls}">{esc(val)}</div></div>')
    return out


def _render_block_01(c: Candidate) -> str:
    buzz = c.buzz or {}
    level = str(buzz.get("level", "cold"))
    return f"""
<div class="blk b1"><div class="blk-n">01</div><div class="b1-in">
  <div class="b1-h"><span class="tw">{TW_SVG}</span>
    <span class="b1-t">TWITTER BUZZ</span>
    <span class="b1-lv lv-{esc(level)}">{esc(buzz.get("level_text", "—"))}</span></div>
  <div class="b1-d">{esc(buzz.get("text", ""))}</div>
</div></div>"""


def _render_block_02(c: Candidate) -> str:
    analysis = (c.analysis or "").strip()
    squeeze_verdict = ((c.squeeze or {}).get("verdict") or "").strip()
    paras = [p for p in (analysis, squeeze_verdict) if p]
    if not paras:
        return ""

    preview = paras[0]
    if len(preview) > 64:
        preview = preview[:61].rstrip() + "…"

    body = "".join(f"<p>{esc(p)}</p>" for p in paras)
    plural = "А" if len(paras) > 1 else ""

    return f"""
<details class="blk b2">
  <summary>
    <div class="blk-n">02</div>
    <div class="b2-in">
      <div class="b2-t">АНАЛИЗ · {len(paras)} БЛОК{plural}</div>
      <div class="b2-p">{esc(preview)}</div>
    </div>
    <span class="b2-c"></span>
  </summary>
  <div class="b2-body">{body}</div>
</details>"""


def _render_block_03(c: Candidate) -> str:
    levels = c.strategy.levels
    rr = build_rr(levels.entry, levels.stop, levels.target1)

    if rr.ok:
        dash, circumference = arc_dash(rr.fill)
        body = f"""
    <div class="b3-grid">
      <div class="rr-dial rr-{rr.grade}">
        <svg viewBox="0 0 100 100" aria-hidden="true">
          <circle class="rr-trk" cx="50" cy="50" r="42"/>
          <circle class="rr-arc" cx="50" cy="50" r="42"
                  stroke-dasharray="{dash} {circumference}"/>
        </svg>
        <div class="rr-val">{rr.rr_text}</div>
        <div class="rr-cap">R : R</div>
      </div>
      <div class="rr-nums">
        <div class="rr-c"><span class="rr-l">ВХОД</span>
          <span class="rr-p rr-e">{fmt_price(rr.entry)}</span></div>
        <div class="rr-c"><span class="rr-l">СТОП</span>
          <span class="rr-p rr-s">{fmt_price(rr.stop)}</span>
          <span class="rr-d">{rr.stop_pct:+.1f}%</span></div>
        <div class="rr-c"><span class="rr-l">ЦЕЛЬ 1</span>
          <span class="rr-p rr-t">{fmt_price(rr.target)}</span>
          <span class="rr-d">{rr.target_pct:+.1f}%</span></div>
      </div>
    </div>"""
    else:
        body = ""

    size_chip = (f'<span class="b3-chip">{esc(c.strategy.size_hint)}</span>'
                 if c.strategy.size_hint else "")
    tv_link = (f'<a class="b3-tv" href="{esc(tv_url(c.symbol))}" target="_blank" '
               f'rel="noopener">TV ↗</a>')

    return f"""
<div class="blk b3">
  <div class="blk-n">03</div>
  <div class="b3-in">
    <div class="b3-hd">
      <span class="b3-t">СТРАТЕГИЯ</span>{size_chip}{tv_link}
    </div>
    {body}
    <div class="b3-d">{esc(c.strategy.text)}</div>
  </div>
</div>"""


def _render_links(c: Candidate) -> str:
    if not c.links:
        return ""
    out = ""
    for i, link in enumerate(c.links):
        text = str(link.get("text", ""))
        icon = LINK_ICON.get(text.lower().replace(" ", ""), "↗")
        primary = " pri" if i == 0 else ""
        out += (f'<a class="lnk{primary}" href="{esc(link.get("url", ""))}" '
                f'target="_blank" rel="noopener">'
                f'<i>{icon}</i>{esc(text.upper())} ↗</a>')
    return f'<div class="lnks">{out}</div>'


def render_card(c: Candidate) -> str:
    """Полная карточка монеты."""
    rank = (c.rank or "").lstrip("#")
    score = min(int(c.score or 0), 100)
    ch24 = metric_num(c.metrics, "24h")
    price = metric_val(c.metrics, "Цена")
    phase_label = str(c.phase.get("label", "—")).lower()

    risky = c.vetoed or c.phase.get("num", 0) <= 1
    tone = "red" if (risky and ch24 <= 0) else "amber"

    has_signal = c.is_viral or any(
        t.get("class", "").startswith("tag-pattern") for t in c.tags
    )
    glow = ("g-rd" if tone == "red" else "g-am") if has_signal else ""

    font_size, letter_spacing = ticker_font(c.symbol)
    ghost = metric_val(c.metrics, "24h")
    tv = tv_url(c.symbol)

    rvol_value = metric_num(c.metrics, "RVOL 1H")
    rvol_note = "выше нормы" if rvol_value >= 1.5 else "в норме"

    tech = " · ".join([
        f'SRSI {metric_val(c.metrics, "StochRSI 4H")}',
        f'ATR {metric_val(c.metrics, "ATR %")}',
        f'BB {metric_val(c.metrics, "BB width")}',
        f'SPOT {metric_val(c.metrics, "Spot ratio")}',
        f'VI+ {c.phase.get("vi_plus", "—")}/{c.phase.get("vi_minus", "—")}',
    ])

    inner = f"""
<div class="card-in">
  <div class="hdr {tone}">
    <div class="hdr-cl"><div class="hdr-gh">{esc(ghost)}</div></div>
    <div class="hdr-in">
      <div class="hdr-rk"><b>RANK {esc(rank)}</b><i></i></div>
      <a class="hdr-sym-a" href="{esc(tv)}" target="_blank" rel="noopener">
        <div class="hdr-sym" style="font-size:{font_size};letter-spacing:{letter_spacing}">{esc(c.symbol)}</div>
      </a>
      <div class="hdr-ph">{esc(phase_label)}</div>
    </div>
    <div class="hdr-pr">{esc(price)}</div>
  </div>
  <div class="med-link"></div>
  <div class="med {"red" if tone == "red" else ""}" style="--p:{score}">
    <div class="med-i"><div class="med-v">{score}</div><div class="med-l">SCORE</div></div>
  </div>
  <div class="chips">{_render_chips(c, risky)}</div>
  <div class="wrap">
    <div class="rvol">
      <div class="rvol-i">📊</div>
      <div class="rvol-v">{esc(metric_val(c.metrics, "RVOL 1H"))}</div>
      <div class="rvol-l">RVOL 1H</div>
      <div class="rvol-d">{rvol_note}</div>
    </div>
    <div class="sigs">{_render_signals(c)}</div>
  </div>
  {_render_veto(c)}
  <div class="perf">{_render_perf(c)}</div>
  <div class="tech">{esc(tech)}</div>
  {_render_block_01(c)}{_render_block_02(c)}{_render_block_03(c)}
  {_render_links(c)}
</div>"""

    if glow:
        return f'<div class="card glow {glow}">{inner}</div>'
    return f'<div class="card">{inner}</div>'


def render_grid(candidates: list[Candidate]) -> str:
    """Сетка карточек, отсортированная по скору."""
    if not candidates:
        return ""
    ordered = sorted(candidates, key=lambda c: -c.score)
    cards = "\n".join(render_card(c) for c in ordered)
    return f'<div class="grid">{cards}</div>'
