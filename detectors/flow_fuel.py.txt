"""FLOW · подкейс fuel — топливо сверху.

Фигура: крупный объём остался на уровнях ВЫШЕ текущей цены. Там
стоят те, кто покупал и не вышел. Каждый такой уровень — будущее
предложение: при подходе цены снизу часть застрявших выходит в
ноль, и движение упирается.

Подкейс читает карту предложения и срабатывает РОВНО в одном
случае: уровни пройдены вверх и удержаны, а сверху пусто. Это
положительная фигура — предложение снято, идти есть куда.

Обратная картина (завал над ценой) фигурой НЕ является и сигналом
не возвращается: «сверху стена» — довод против движения, а не за
него. Раньше эта ветка давала ослабленный положительный скор и
давала большинство ложных срабатываний семейства. Её оценка
осталась в коде как расчёт веса, но исход теперь — молчание.

Второе жёсткое условие: пустая карта зон означает отсутствие
информации, а не свободный путь. Без зон подкейс молчит.
"""

from __future__ import annotations

from detectors.flow_config import (
    EXTREME_GROWTH_X,
    ZONE_SINGLE_SCALE_WEIGHT,
)
from detectors.flow_core import FlowContext, Zone
from detectors.flow_signal import SubcaseSignal, veto_common

name = "flow_fuel"

# Дальше этой доли зона на горизонте не влияет: до неё цена
# успеет прийти и уйти несколько раз.
FUEL_MAX_DISTANCE = 0.60

# Пробой считается состоявшимся, если цена ушла над зоной
# заметно и там закрепилась.
BREAKOUT_MARGIN = 0.03
BREAKOUT_HOLD_BARS = 5

# Сколько уровней должно быть снято, чтобы это считалось картой,
# а не единичным касанием. Один пройденный уровень есть почти у
# любой монеты в умеренном росте.
MIN_CLEARED = 2

# Суммарный вес зон сверху, ниже которого небо считается чистым.
CLEAR_SKY_WEIGHT = 0.35


# ─────────────────────────────────────────────────────────────
# Сбор зон
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


def _cleared_mass(zones: list[Zone]) -> float:
    """Сколько предложения реально снято пройденными уровнями.

    Считаем по тем же тирам, что и давление сверху: снятый
    уровень третьего тира весит вдвое против первого. Два слабых
    касания не должны давать столько же, сколько две плиты.
    """
    total = 0.0
    for z in zones:
        if not z.events:
            continue
        top_tier = max(e.tier for e in z.events)
        mass = {1: 0.5, 2: 0.8, 3: 1.0}.get(top_tier, 0.5)
        scales = 1.0 if len(z.scales) >= 2 else ZONE_SINGLE_SCALE_WEIGHT
        total += mass * scales
    return total


# ─────────────────────────────────────────────────────────────
# Детект
# ─────────────────────────────────────────────────────────────

def detect(ctx: FlowContext) -> SubcaseSignal | None:
    """Собирает фигуру fuel либо возвращает None.

    Обвал дельты здесь не проверяется намеренно: fuel описывает
    расположение предложения, и при сливе оно расположено ровно
    там же, где при накоплении.
    """
    if veto_common(ctx):
        return None

    # Нет карты — нет вывода. Пустой список зон это незнание, а
    # не свободный путь наверх.
    if not ctx.zones:
        return None

    above = _zones_above(ctx)
    cleared = _cleared_zones(ctx)

    # Ниже порога карты фигуры нет. Сюда же попадает случай
    # «сверху завал»: подкейс описывает только снятое
    # предложение, стена над ценой доводом за движение не бывает.
    if len(cleared) < MIN_CLEARED:
        return None

    total_above = sum(_zone_weight(z, ctx) for z in above)
    if total_above >= CLEAR_SKY_WEIGHT:
        return None

    # ── Скор ───────────────────────────────────────────────
    # Считаем по снятой массе, а не по числу уровней: важно,
    # сколько предложения ушло, а не сколько раз мы его пересекли.
    mass = _cleared_mass(cleared)
    score = 38.0 + min(24.0, mass * 11.0)

    top = cleared[0]
    sig = SubcaseSignal(
        subcase=name,
        score=score,
        horizon_bars=ctx.horizon_bars,
        zone_price=top.price,
    )
    sig.add(
        f"топливо: {len(cleared)} уровня снято вверх, сверху свободно",
        cleared=float(len(cleared)),
        cleared_mass=round(mass, 3),
        weight_above=round(total_above, 3),
    )

    # ── Ретест ─────────────────────────────────────────────
    # Раньше это был бонус, который получали почти все, то есть
    # константа. Теперь наоборот: пробой без единого возврата к
    # уровню не подтверждён, и это штраф.
    tested = [z for z in cleared if z.tests >= 1]
    if tested:
        best = max(tested, key=lambda z: z.tests)
        if best.tests >= 2:
            sig.apply("retest_held", 1.12)
            sig.add(
                f"уровень {best.price:.6g} удержан на {best.tests} ретестах",
                retest_price=best.price,
                tests=float(best.tests),
            )
        else:
            sig.add(
                f"уровень {best.price:.6g} удержан на ретесте",
                retest_price=best.price,
                tests=float(best.tests),
            )
    else:
        sig.apply("no_retest", 0.85)
        sig.add("ни один пройденный уровень не тестировался сверху")

    # ── Свежесть пробоя ────────────────────────────────────
    # Пробой годовой давности картой предложения уже не управляет:
    # состав держателей сменился.
    if top.freshness > ctx.horizon_bars * 6:
        sig.apply("stale_breakout", 0.75)
        sig.add(
            f"пробой давний ({top.freshness} баров назад)",
            freshness=float(top.freshness),
        )

    # ── Рост перед падением ────────────────────────────────
    # Сильный рост в прошлом означает, что выше рабочей дистанции
    # всё равно висят застрявшие — просто мы их не видим.
    if ctx.growth_x >= EXTREME_GROWTH_X * 0.5:
        sig.apply("growth_load", 0.85)
        sig.add(
            f"рост перед падением x{ctx.growth_x:.1f}: выше могут быть "
            f"зоны за горизонтом карты",
            growth_x=ctx.growth_x,
        )

    # ── Восстановление объёма ──────────────────────────────
    # Снятое предложение ничего не даёт, если идти наверх некому.
    if ctx.volume_recovery and ctx.volume_recovery < 1.0:
        sig.apply("thin_volume", 0.8)
        sig.add(
            f"объём не восстановился (x{ctx.volume_recovery:.2f})",
            volume_recovery=ctx.volume_recovery,
        )

    return sig if not sig.weak else None
