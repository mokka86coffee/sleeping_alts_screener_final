"""FLOW · подкейс fuel — топливо сверху.

Фигура: крупный объём остался на уровнях ВЫШЕ текущей цены. Там
стоят те, кто покупал и не вышел. Каждый такой уровень — будущее
предложение: при подходе цены снизу часть застрявших выходит в
ноль, и движение упирается.

Один подкейс, две роли, и это не двусмысленность, а свойство самой
структуры:

  сопротивление — цена подходит снизу, зона гасит движение;
  топливо       — зона уже пробита вверх, застрявшие вышли,
                  над уровнем предложения больше нет.

Роль определяется не зоной, а тем, где цена относительно неё и
пробивала ли она уровень. Поэтому fuel — единственный подкейс
семейства, читающий зоны сверху, и единственный, для которого
обвал дельты не помеха: он описывает препятствие, а не разворот.
"""

from __future__ import annotations

from detectors.flow_config import (
    EXTREME_GROWTH_X,
    ZONE_NEAR_PCT,
    ZONE_SINGLE_SCALE_WEIGHT,
)
from detectors.flow_core import FlowContext, Zone
from detectors.flow_signal import FlowSignal, veto_common

name = "flow_fuel"

# Дальше этой доли зона на горизонте не влияет: до неё цена
# успеет прийти и уйти несколько раз.
FUEL_MAX_DISTANCE = 0.60

# Пробой считается состоявшимся, если цена ушла над зоной
# заметно и там закрепилась.
BREAKOUT_MARGIN = 0.03
BREAKOUT_HOLD_BARS = 5


# ─────────────────────────────────────────────────────────────
# Сбор зон сверху
# ─────────────────────────────────────────────────────────────

def _zones_above(ctx: FlowContext) -> list[Zone]:
    """Живые зоны над ценой в пределах рабочей дистанции."""
    out = []
    for z in ctx.zones:
        if z.price <= ctx.price:
            continue
        dist = (z.price - ctx.price) / ctx.price
        if dist <= FUEL_MAX_DISTANCE:
            out.append(z)
    return sorted(out, key=lambda z: z.price)


def _cleared_zones(ctx: FlowContext) -> list[Zone]:
    """Зоны, которые цена уже прошла вверх и удержала.

    Пройденная зона меняет знак: пока она была сверху — давила,
    после пробоя предложение с неё снято.
    """
    out = []
    for z in ctx.zones:
        if z.price > ctx.price:
            continue
        if z.broken:
            continue
        margin = (ctx.price - z.price) / ctx.price
        if margin >= BREAKOUT_MARGIN and z.plateau_bars >= BREAKOUT_HOLD_BARS:
            out.append(z)
    return sorted(out, key=lambda z: -z.price)


# ─────────────────────────────────────────────────────────────
# Вес зоны
# ─────────────────────────────────────────────────────────────

def _zone_weight(zone: Zone, ctx: FlowContext) -> float:
    """Насколько тяжело зона давит сверху.

    Складывается из массы события, близости к цене и того,
    сколько раз уровень уже отбивал подход.
    """
    events = zone.events
    if not events:
        return 0.0

    top_tier = max(e.tier for e in events)
    mass = {1: 0.5, 2: 0.8, 3: 1.0}.get(top_tier, 0.5)

    dist = (zone.price - ctx.price) / ctx.price
    # Ближняя зона мешает сильнее дальней, спад плавный.
    proximity = max(0.25, 1.0 - dist / FUEL_MAX_DISTANCE)

    # Отбитые подходы — прямое свидетельство работающего
    # предложения, а не предположение о нём.
    rejections = 1.0 + min(0.4, zone.tests * 0.15)

    scales = 1.0 if len(zone.scales) >= 2 else ZONE_SINGLE_SCALE_WEIGHT

    return mass * proximity * rejections * scales


# ─────────────────────────────────────────────────────────────
# Детект
# ─────────────────────────────────────────────────────────────

def detect(ctx: FlowContext) -> FlowSignal | None:
    """Собирает фигуру fuel либо возвращает None.

    Обвал дельты здесь не проверяется намеренно: fuel описывает
    расположение предложения, и при сливе оно расположено ровно
    там же, где при накоплении.
    """

    if veto_common(ctx):
        return None

    above = _zones_above(ctx)
    cleared = _cleared_zones(ctx)

    if not above and not cleared:
        return None

    # ── Роль ─────────────────────────────────────────────────
    total_above = sum(_zone_weight(z, ctx) for z in above)
    nearest = above[0] if above else None

    # Чистое небо: сверху ничего, снизу пройденные уровни.
    clear_sky = total_above < 0.35 and bool(cleared)

    if clear_sky:
        score = 42.0 + min(20.0, len(cleared) * 7.0)
        role = "топливо"
        zone_price = cleared[0].price
    else:
        # Сопротивление вычитает, а не добавляет: чем тяжелее
        # сверху, тем меньше вклад. Скор здесь — оценка того,
        # насколько путь свободен.
        score = max(0.0, 62.0 - total_above * 34.0)
        role = "сопротивление"
        zone_price = nearest.price if nearest else 0.0

    sig = FlowSignal(
        subcase=name,
        score=score,
        horizon_bars=ctx.horizon_bars,
        zone_price=zone_price,
    )

    if clear_sky:
        sig.add(
            f"{role}: {len(cleared)} уровня пройдено вверх, "
            f"сверху свободно",
            cleared=float(len(cleared)),
            weight_above=total_above,
        )
        # Ближайший пройденный уровень становится опорой.
        top = cleared[0]
        if top.tests >= 1:
            sig.apply("retest_held", 1.15)
            sig.add(
                f"пройденный уровень {top.price:.6g} удержан на ретесте",
                retest_price=top.price,
                tests=float(top.tests),
            )
    else:
        dist_pct = (nearest.price - ctx.price) / ctx.price * 100
        sig.add(
            f"{role}: {len(above)} зон сверху, ближайшая "
            f"{nearest.price:.6g} (+{dist_pct:.1f}%)",
            zones_above=float(len(above)),
            weight_above=total_above,
            nearest_dist=dist_pct / 100,
        )

        # Плотный завал прямо над ценой — движение упрётся почти
        # сразу, горизонт до этого не доживёт.
        if nearest and (nearest.price - ctx.price) / ctx.price <= ZONE_NEAR_PCT:
            sig.apply("wall_close", 0.65)
            sig.add("завал вплотную к цене")

        if nearest and nearest.tests >= 2:
            sig.apply("proven_wall", 0.75)
            sig.add(
                f"ближайшая зона уже отбила {nearest.tests} подхода",
                nearest_tests=float(nearest.tests),
            )

    # ── Рост перед падением ──────────────────────────────────
    # Зоны сверху тем тяжелее, чем сильнее был рост: у застрявших
    # выше цена входа, и выходить они будут агрессивнее.
    if ctx.growth_x >= EXTREME_GROWTH_X * 0.5 and not clear_sky:
        sig.apply("growth_load", 0.8)
        sig.add(
            f"рост перед падением x{ctx.growth_x:.1f} утяжеляет зоны",
            growth_x=ctx.growth_x,
        )

    # ── Восстановление объёма ────────────────────────────────
    # Проходить завал нужно на объёме. Без него подход к зоне
    # гасится даже небольшим предложением.
    if ctx.volume_recovery < 1.0 and not clear_sky:
        sig.apply("thin_volume", 0.8)
        sig.add(
            f"объём не восстановился (x{ctx.volume_recovery:.2f})",
            volume_recovery=ctx.volume_recovery,
        )

    return sig if not sig.weak else None
