"""FLOW · подкейс spring — пружина.

Фигура: серия событий на узком диапазоне при затухающем фоне.
Не одиночное столкновение, как в churn, а накопление, размазанное
по времени: каждое событие по отдельности ничего не решает, но
вместе они держат цену в тисках.

Обратное к churn требование к фону. Churn ищет поглощение в шуме:
поток идёт, цена стоит. Spring ищет сжатие в тишине: поток иссяк,
диапазон схлопнулся, амплитуда падает бар за баром. Поэтому один
и тот же участок не может дать оба подкейса — они расходятся по
rel_volume в противоположные стороны.

Сама по себе пружина направления не имеет: сжатие разряжается в
любую сторону. Направление задаёт зона под ней — spring без
опорной зоны не собирается.
"""

from __future__ import annotations

from detectors.flow_config import (
    HOMOGENEITY_MIN,
    PLATEAU_MAX_RANGE,
    SPRING_MIN_EVENTS,
    SPRING_QUIET_MAX,
    ZONE_NEAR_PCT,
    ZONE_SINGLE_SCALE_WEIGHT,
)
from detectors.flow_core import Bar, FlowContext, Zone
from detectors.flow_signal import SubcaseSignal, veto_bullish

name = "flow_spring"

# Окно, на котором меряется сжатие. Короче — ловится любая пауза,
# длиннее — пружина размывается трендом.
SQUEEZE_WINDOW = 24
SQUEEZE_HALVES = 2


# ─────────────────────────────────────────────────────────────
# Сжатие
# ─────────────────────────────────────────────────────────────

def _squeeze_ratio(base: list[Bar]) -> float:
    """Во сколько раз амплитуда сжалась к концу окна.

    Считается по половинам окна, а не регрессией: пружина редко
    сжимается равномерно, зато почти всегда даёт ступеньку между
    первой и второй половиной.

    Возвращает отношение свежей амплитуды к ранней. Меньше 1 —
    сжатие, около 1 — плоско, больше 1 — расширение.
    """
    tail = base[-SQUEEZE_WINDOW:]
    if len(tail) < SQUEEZE_WINDOW:
        return 1.0

    half = len(tail) // SQUEEZE_HALVES
    old, new = tail[:half], tail[half:]

    def amp(bars: list[Bar]) -> float:
        vals = [
            (b.high - b.low) / b.close
            for b in bars
            if b.close > 0
        ]
        return sum(vals) / len(vals) if vals else 0.0

    a_old, a_new = amp(old), amp(new)
    if a_old <= 0:
        return 1.0
    return a_new / a_old


def _range_width(base: list[Bar]) -> float:
    """Ширина диапазона окна к текущей цене."""
    tail = base[-SQUEEZE_WINDOW:]
    if not tail:
        return 1.0
    hi = max(b.high for b in tail)
    lo = min(b.low for b in tail)
    last = tail[-1].close
    if last <= 0:
        return 1.0
    return (hi - lo) / last


# ─────────────────────────────────────────────────────────────
# Зона-опора
# ─────────────────────────────────────────────────────────────

def _support_zone(ctx: FlowContext) -> Zone | None:
    """Зона, задающая направление разряда.

    В отличие от churn берётся не ближайшая, а самая насыщенная
    событиями: пружина опирается на уровень, где работа шла долго,
    даже если цена от него отошла.
    """
    below = [z for z in ctx.zones if z.price <= ctx.price]
    if not below:
        return None

    near = [
        z
        for z in below
        if (ctx.price - z.price) / ctx.price <= ZONE_NEAR_PCT * 1.5
    ]
    pool = near or below
    return max(pool, key=lambda z: (len(z.events), z.tests))


# ─────────────────────────────────────────────────────────────
# Базовый скор
# ─────────────────────────────────────────────────────────────

def _base_score(
    events: int,
    squeeze: float,
    width: float,
) -> tuple[float, dict[str, float]]:
    """Скор от плотности серии и глубины сжатия.

    Серия важнее одиночного тира: в spring нет события, которое
    решает исход само по себе.
    """
    score = 30.0 + min(18.0, (events - SPRING_MIN_EVENTS) * 4.5)

    # Сжатие вдвое и глубже — полноценная пружина.
    if squeeze <= 0.5:
        score += 22.0
    elif squeeze <= 0.7:
        score += 14.0
    elif squeeze <= 0.85:
        score += 7.0

    # Узкий диапазон усиливает: разряд из тисков резче.
    if width <= 0.12:
        score += 10.0
    elif width <= 0.20:
        score += 5.0

    facts = {
        "events": float(events),
        "squeeze": squeeze,
        "range_width": width,
    }
    return score, facts


# ─────────────────────────────────────────────────────────────
# Детект
# ─────────────────────────────────────────────────────────────

def detect(ctx: FlowContext) -> SubcaseSignal | None:
    """Собирает фигуру spring либо возвращает None."""

    if veto_bullish(ctx):
        return None

    # Фон обязан быть тихим. Шумный фон — территория churn:
    # там поток идёт и его принимают, здесь потока нет вовсе.
    if ctx.flow.rel_volume > SPRING_QUIET_MAX:
        return None

    zone = _support_zone(ctx)
    if zone is None:
        return None

    # Серия. Одиночное событие пружиной не является по определению.
    recent = [e for e in ctx.events if e.age <= SQUEEZE_WINDOW]
    if len(recent) < SPRING_MIN_EVENTS:
        return None

    squeeze = _squeeze_ratio(ctx.base)
    width = _range_width(ctx.base)

    # Расширение амплитуды — прямое опровержение фигуры.
    if squeeze >= 1.0:
        return None
    if width > PLATEAU_MAX_RANGE:
        return None

    score, facts = _base_score(len(recent), squeeze, width)
    facts["zone_price"] = zone.price

    sig = SubcaseSignal(
        subcase=name,
        score=score,
        horizon_bars=ctx.horizon_bars,
        zone_price=zone.price,
    )
    sig.add(
        f"сжатие x{1 / squeeze:.1f} на серии из {len(recent)} событий, "
        f"диапазон {width * 100:.1f}%",
        **facts,
    )

    # ── Опора ────────────────────────────────────────────────
    # Пружина над подтверждённой зоной — сильнейшее сочетание
    # семейства: сжатие даёт момент, зона даёт направление.
    sig.apply("zone_plateau", zone.plateau_mult)
    if zone.plateau_bars > 0:
        sig.add(
            f"опора: зона {zone.price:.6g}, плато {zone.plateau_bars} дней",
            plateau_bars=float(zone.plateau_bars),
        )

    if len(zone.scales) < 2:
        sig.apply("single_scale", ZONE_SINGLE_SCALE_WEIGHT)
        sig.add("опора подтверждена одним масштабом", scales=1.0)

    if zone.tests >= 2:
        sig.apply("tested", 1.12)
        sig.add(f"опора выдержала {zone.tests} теста", tests=float(zone.tests))

    # ── Однородность серии ───────────────────────────────────
    if ctx.flow.homogeneity < HOMOGENEITY_MIN:
        sig.apply("lumpy", 0.8)
        sig.add("серия неоднородна", homogeneity=ctx.flow.homogeneity)

    # ── Перекос потока ───────────────────────────────────────
    # В тишине небольшой, но устойчивый перекос в покупку весит
    # больше, чем крупный перекос в шуме: продавать некому.
    if ctx.flow.buy_share >= 0.55:
        sig.apply("buy_bias", 1.15)
        sig.add(
            f"перекос в покупку {ctx.flow.buy_share * 100:.0f}%",
            buy_share=ctx.flow.buy_share,
        )
    elif ctx.flow.buy_share <= 0.42:
        sig.apply("sell_bias", 0.7)
        sig.add(
            f"перекос в продажу {(1 - ctx.flow.buy_share) * 100:.0f}%",
            buy_share=ctx.flow.buy_share,
        )

    # ── Недоверие за рост ────────────────────────────────────
    need = ctx.distrust_zones
    if need and zone.zones_below < need:
        sig.apply("distrust", 0.7)
        sig.add(
            f"под опорой ещё {need - zone.zones_below} несработавших уровня",
            zones_below=float(zone.zones_below),
        )

    return sig if not sig.weak else None
