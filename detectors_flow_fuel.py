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

from detectors_flow_config import (
    FUEL_BREAKOUT_HOLD_BARS,
    FUEL_BREAKOUT_MARGIN,
    FUEL_CLEAR_SKY_WEIGHT,
    FUEL_MAX_DISTANCE,
    FUEL_MIN_CLEARED,
    GROWTH_LOAD_PEAK_DAYS,
    GROWTH_LOAD_X,
    ZONE_SINGLE_SCALE_WEIGHT,
)
from detectors_flow_core import FlowContext, Zone
from detectors_flow_signal import SubcaseSignal, veto_common

name = "flow_fuel"


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
        # broken для поддержки означает провал вниз — такой уровень
        # предложения не снимал, он его подтвердил с другой стороны.
        if z.broken:
            continue
        margin = (ctx.price - z.price) / ctx.price
        # plateau в ядре обнуляется, если не дотянул до
        # PLATEAU_MIN_BARS: величина «есть плато или нет», а не
        # длительность. Порог удержания меряем по последнему
        # касанию — сколько бар цена провела над уровнем после
        # того, как в последний раз к нему подходила.
        held = len(ctx.base) - 1 - z.last_touch_idx if z.last_touch_idx >= 0 else 0
        if margin >= FUEL_BREAKOUT_MARGIN and held >= FUEL_BREAKOUT_HOLD_BARS:
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
    if len(cleared) < FUEL_MIN_CLEARED:
        return None

    total_above = sum(_zone_weight(z, ctx) for z in above)
    if total_above >= FUEL_CLEAR_SKY_WEIGHT:
        return None

    # ── Скор ───────────────────────────────────────────────
    # Считаем по снятой массе, а не по числу уровней: важно,
    # сколько предложения ушло, а не сколько раз мы его пересекли.
    mass = _cleared_mass(cleared)
    # Насыщение при mass ≈ 1.63, потолок 72.0. Прежний множитель 7.5
    # насыщался при 4.53 — величине, которой на рынке не бывает:
    # один снятый уровень третьего тира даёт ровно 1.0, два слабых
    # односмасштабных 0.6. Замер 174 монет: cleared равен единице в
    # десяти случаях из одиннадцати, масса не превышала 0.8, и весь
    # верхний диапазон формулы простаивал.
    #
    # База снижена с 38 до 28: с направленной смертью зоны (правка 1)
    # уровней доживает больше, и без снижения базы подкейс упёрся бы
    # в потолок на любой фигуре.
    score = 28.0 + min(44.0, mass * 27.0)

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

    # ── Свежий рост перед падением ────────────────────────
    # Множитель, а не вето. Сильный рост означает, что выше рабочей
    # дистанции могут висеть застрявшие, которых карта не видит.
    #
    # Но давит только СВЕЖАЯ толпа. Тот, кто держит минус девяносто
    # процентов полгода, может держать его годами и предложением уже
    # не является — он не продаёт. Прежнее условие читало growth_x
    # без давности и штрафовало листинговые распилы, где толпы не
    # было вовсе: рост в сорок раз за неделю на пустом стакане.
    fresh_peak = ctx.drop.peak_age_days <= GROWTH_LOAD_PEAK_DAYS
    if fresh_peak and ctx.growth_x >= GROWTH_LOAD_X:
        sig.apply("growth_load", 0.85)
        # Множитель остаётся, но решает не он.
        #
        # Замер 13 августа: TUT сделал x42.6 за четыре дня до прогона,
        # сложился на 84% от вершины — и получил от семейства 94 балла
        # с подписью «экстремальный». Обоснование подкейса при этом
        # честно сообщало про свежий пик. Пятнадцать процентов штрафа
        # на такой картине ничего не решают: снимать надо не проценты,
        # а право представлять монету.
        #
        # Смысл fuel от этого не меняется — предложение действительно
        # снято. Меняется только то, чем монета подписана на экране,
        # если рядом собралась фигура входа.
        sig.late = True
        sig.add(
            f"свежий пик: рост x{ctx.growth_x:.1f} "
            f"{ctx.drop.peak_age_days} дней назад, выше могут быть "
            f"зоны за горизонтом карты",
            growth_x=ctx.growth_x,
            peak_age_days=float(ctx.drop.peak_age_days),
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
