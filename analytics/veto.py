"""Вето: причины, по которым монета не идёт в работу.

Вето отделено от скоринга сознательно. Скор отвечает на вопрос «насколько
интересно», вето — на вопрос «можно ли вообще». Монета с высоким скором
и активным вето остаётся в отчёте видимой, но помеченной.
"""

from __future__ import annotations

from analytics.metrics import fmt_big
from core.config import (
    VETO_BLOCKING_SEVERITY,
    VETO_FUNDING_ABS,
    VETO_MAX_ATR_PCT,
    VETO_MIN_OI_USD,
    VETO_MIN_SPOT_RATIO,
)
from core.models import VetoReason


def evaluate_veto(m: dict, squeeze: dict | None) -> list[VetoReason]:
    """Проверяет монету по всем критериям вето."""
    out: list[VetoReason] = []

    # ── Squeeze: рост на выжимании шортов ──
    if squeeze and squeeze.get("detected"):
        lvl = str(squeeze.get("risk_level", ""))
        if lvl in ("high", "extreme"):
            out.append(VetoReason(
                code="squeeze",
                label="SQUEEZE",
                detail=f"риск {lvl.upper()}, скор {squeeze.get('risk_score', 0)}",
                severity="high" if lvl == "extreme" else "mid",
            ))

    # ── Фандинг: перегрев одной из сторон ──
    funding = m.get("funding")
    if funding is not None and abs(funding) >= VETO_FUNDING_ABS:
        side = "лонги перегреты" if funding > 0 else "шорты перегреты"
        out.append(VetoReason(
            code="funding",
            label="ФАНДИНГ",
            detail=f"{funding:+.4f}%, {side}",
            severity="mid",
        ))

    # ── Ликвидность: тонкий рынок ──
    oi_usd = m.get("oi_usd") or 0.0
    if oi_usd < VETO_MIN_OI_USD:
        out.append(VetoReason(
            code="liquidity",
            label="ЛИКВИДНОСТЬ",
            detail=f"OI {fmt_big(oi_usd)} ниже порога {fmt_big(VETO_MIN_OI_USD)}",
            severity="mid",
        ))

    # ── Волатильность: стоп невозможно поставить разумно ──
    atr = m.get("atr_pct")
    if atr is not None and atr > VETO_MAX_ATR_PCT:
        out.append(VetoReason(
            code="volatility",
            label="ВОЛАТИЛЬНОСТЬ",
            detail=f"ATR {atr:.1f}% в день",
            severity="mid",
        ))

    # ── Нет спота: движение живёт только в деривативах ──
    spot_ratio = m.get("spot_ratio")
    if spot_ratio is not None and spot_ratio < VETO_MIN_SPOT_RATIO:
        out.append(VetoReason(
            code="no_spot",
            label="НЕТ СПОТА",
            detail=f"спот {spot_ratio*100:.1f}% оборота",
            severity="low",
        ))

    return out


def is_blocking(veto: list[VetoReason]) -> bool:
    """Есть ли среди причин хотя бы одна блокирующая."""
    return any(v.severity in VETO_BLOCKING_SEVERITY for v in veto)


def veto_summary(veto: list[VetoReason]) -> str:
    """Короткая строка причин для таблицы."""
    if not veto:
        return "чисто"
    return " · ".join(v.label.lower() for v in veto[:2])
