"""Построение торгового плана: уровни входа, стопа и целей.

Цели строятся от структуры рынка, а не от множителей риска. Если структура
не даёт цели с приемлемым соотношением, план помечается как непригодный —
лучше пропустить монету, чем нарисовать сделку с отрицательным ожиданием.
"""

from __future__ import annotations

from analytics_levels import build_stop, build_targets, clamp_stop
from core_config import MIN_RR_TRADABLE
from core_models import Levels, Strategy

# Множители ATR для стопа по сценариям
ATR_MULT_TAIKO = 1.6
ATR_MULT_TREND = 2.0
ATR_MULT_MOMENTUM = 1.8
ATR_MULT_BASE = 1.5

DEFAULT_ATR_PCT = 4.0

# Глубина поиска уровней по сценариям
LOOKBACK_REVERSAL = 240   # разворот после долгого падения — смотрим далеко
LOOKBACK_TREND = 120
LOOKBACK_RANGE = 90

NO_ENTRY = "БЕЗ ВХОДА"


def _levels(entry: float, stop: float, targets: tuple) -> Levels:
    return Levels(
        entry=round(entry, 10),
        stop=round(stop, 10),
        target1=round(targets[0], 10),
        target2=round(targets[1], 10),
        target3=round(targets[2], 10),
    )


def _rr_of(entry: float, stop: float, target: float) -> float:
    risk = entry - stop
    if risk <= 0 or target <= entry:
        return 0.0
    return (target - entry) / risk


def _downgrade(text: str, reason: str) -> Strategy:
    """План, который не стоит брать: уровни не строим вовсе."""
    return Strategy(
        text=f"{text} {reason}",
        size_hint=NO_ENTRY,
        kind="none",
    )


def build_strategy(m: dict, squeeze: dict | None, taiko, dexe) -> Strategy:
    """Выбирает сценарий и считает уровни от рыночной структуры."""
    price = m["price"]
    atr = m.get("atr_pct") or DEFAULT_ATR_PCT
    lows = m.get("lows_1d") or []
    highs = m.get("highs_1d") or []

    # ── TAIKO: разворот после глубокого падения ──
    if taiko and taiko.detected:
        base_low = min(lows[-20:]) if len(lows) >= 20 else price * 0.9
        atr_floor = price * (1 - atr / 100 * ATR_MULT_TAIKO)
        stop = clamp_stop(price, max(base_low * 0.985, atr_floor))

        targets, source = build_targets(price, stop, highs, atr, LOOKBACK_REVERSAL)
        rr = _rr_of(price, stop, targets[0])

        sq_level = (squeeze or {}).get("risk_level", "none")

        if sq_level in ("high", "extreme"):
            text = (
                f"Конфликт сигналов. TAIKO даёт разворот, но squeeze-риск "
                f"{sq_level.upper()} со скором {(squeeze or {}).get('risk_score', 0)} — "
                f"часть роста обеспечена ликвидациями шортов. Вход половинным "
                f"объёмом либо ожидание отката и повторного теста базы."
            )
            size = "½ ОБЪЁМА"
        else:
            where = "по уровням сопротивления" if source == "structure" else "по проекции ATR"
            text = (
                f"TAIKO Reversal. Вход лесенкой от текущей цены, стоп под минимум "
                f"базы, цели расставлены {where}."
            )
            size = "ПОЛНЫЙ"

        return Strategy(text=text, size_hint=size, kind="taiko",
                        levels=_levels(price, stop, targets))

    # ── DEXE: отскок после капитуляции ──
    if dexe and dexe.detected:
        bottom = dexe.bottom_price or price * 0.93
        stop = clamp_stop(price, bottom * 0.98)
        peak = dexe.peak_price or 0.0

        # Пик ниже текущей цены означает, что отскок уже отработан:
        # цели по откату к нему ушли бы под вход
        if peak > price * 1.05:
            targets = (
                price + (peak - price) * 0.236,
                price + (peak - price) * 0.382,
                price + (peak - price) * 0.618,
            )
            source = "retrace"
        else:
            targets, source = build_targets(price, stop, highs, atr, LOOKBACK_REVERSAL)

        rr = _rr_of(price, stop, targets[0])

        text = (
            f"DEXE Post-Pump. Дамп {dexe.dump_pct:.0f}% за {dexe.dump_hours:.0f}ч, "
            f"дно {dexe.bottom_hours_ago:.0f}ч назад. Кульминация объёма "
            f"×{dexe.volume_climax_ratio:.1f} — {dexe.climax_label}. Вход частями, "
            f"стоп под дно, цели {'по откату к пику' if source == 'retrace' else 'по структуре'}."
        )
        return Strategy(text=text, size_hint="⅓ ОБЪЁМА", kind="dexe",
                        levels=_levels(price, stop, targets))

    # ── Squeeze без разворотного сигнала: входа нет ──
    if squeeze and squeeze.get("detected"):
        return Strategy(
            text="Manipulated squeeze. Только наблюдение, входы против движения рискованны.",
            size_hint=NO_ENTRY,
            kind="none",
        )

    # ── По фазе рынка ──
    label = (m.get("vortex_4h") or {}).get("label", "")

    if label == "TREND":
        stop = build_stop(price, lows, atr, ATR_MULT_TREND, lookback=40)
        targets, source = build_targets(price, stop, highs, atr, LOOKBACK_TREND)
        rr = _rr_of(price, stop, targets[0])

        if rr < MIN_RR_TRADABLE:
            return _downgrade(
                "Тренд подтверждён, но цена подошла вплотную к сопротивлению.",
                f"Соотношение {rr:.1f} к 1 — ждём пробоя уровня или отката к EMA21.",
            )

        note = "цели на сопротивлениях" if source == "structure" else "цена у максимума, цели по ATR"
        return Strategy(
            text=f"Тренд. Работать по направлению, коррекции откупать от EMA21. {note}.",
            size_hint="ПОЛНЫЙ", kind="trend",
            levels=_levels(price, stop, targets),
        )

    if label == "MOMENTUM":
        stop = build_stop(price, lows, atr, ATR_MULT_MOMENTUM, lookback=40)
        targets, _ = build_targets(price, stop, highs, atr, LOOKBACK_TREND)
        rr = _rr_of(price, stop, targets[0])

        if rr < MIN_RR_TRADABLE:
            return _downgrade(
                "Импульс есть, но пространства до ближайшего сопротивления мало.",
                f"Соотношение {rr:.1f} к 1 — вход только после пробоя с объёмом.",
            )

        return Strategy(
            text="Импульс. Нужно подтверждение объёмом, вход по пробою локального максимума.",
            size_hint="⅔ ОБЪЁМА", kind="momentum",
            levels=_levels(price, stop, targets),
        )

    if label == "BASE":
        lo = min(lows[-30:]) if len(lows) >= 30 else price * 0.92
        atr_floor = price * (1 - atr / 100 * ATR_MULT_BASE)
        stop = clamp_stop(price, max(lo * 0.985, atr_floor))
        targets, _ = build_targets(price, stop, highs, atr, LOOKBACK_RANGE)
        rr = _rr_of(price, stop, targets[0])

        if rr < MIN_RR_TRADABLE:
            return _downgrade(
                "Диапазон, но цена ближе к верхней границе, чем к нижней.",
                f"Соотношение {rr:.1f} к 1 — ждём возврата к поддержке.",
            )

        return Strategy(
            text="База. Диапазон, торговля от нижней границы до верхней.",
            size_hint="⅓ ОБЪЁМА", kind="base",
            levels=_levels(price, stop, targets),
        )

    if label == "DECLINE":
        return Strategy(
            text="Снижение. Лонги рискованны, ждём разворотную формацию.",
            size_hint=NO_ENTRY, kind="none",
        )

    return Strategy(text="Наблюдение.", size_hint=NO_ENTRY, kind="none")
