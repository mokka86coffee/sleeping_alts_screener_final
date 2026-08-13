"""FLOW · подкейс leverage — перекос в плече.

Фигура: шорты перегружены. Фандинг устойчиво отрицательный, открытый
интерес растёт, цена стоит. Позиция набрана против движения, которого
нет, и держать её стоит денег — каждый интервал шорты платят лонгам
за право оставаться в позиции.

Такая конструкция сама себе топливо. Ей не нужен покупатель: хватит
отсутствия продавца, чтобы вынести стопы, а вынесенные стопы — это
рыночные покупки, которые выносят следующие. Отсюда характерная
форма выноса: вертикаль без объёмной подготовки.

Отличие от detect_squeeze: там перегрев ЛОНГОВ и охота за ними,
положительный экстремальный фандинг. Здесь зеркальная сторона —
перегруженность шортов.

Единственный модуль семейства, который ходит в сеть сверх дневок.
Поэтому он ленивый: без сработавшего дневного ядра запросы не
делаются вовсе — detected всё равно был бы ложью.

Каждый отказ проходит через ctx.reject(): возврат остаётся None, но
причина попадает в ctx.notes и дальше в rejects сигнала. Прежде
подкейс выходил голым return None, и в прогоне 13 августа это дало
ноль срабатываний при нуле объяснений — отличить «пороги не пустили»
от «вышел на первом же гейте» было нечем, а пороги LEV_* при этом
никогда не калибровались и стоят наугад.
"""

from __future__ import annotations

from core.binance import get_funding_history, get_oi_history
from detectors.flow_config import (
    LEV_FUNDING_EXTREME_APR,
    LEV_FUNDING_HOT_APR,
    LEV_FUNDING_NEG_APR,
    LEV_HISTORY_DAYS,
    LEV_BUY_BIAS,
    LEV_MIN_OI_USD,
    LEV_OI_GROWTH_MIN,
    LEV_PRICE_FLAT_PCT,
    LEV_REQUIRE_CORE,
    VORTEX_MULT_MAX,
    ZONE_NEAR_PCT,
    LEV_FUNDING_PER_DAY,
    LEV_NEG_SHARE_MIN,
    LEV_OI_WINDOW,
)
from detectors.flow_core import (
    FlowContext,
    Zone,
    _median,
    _slope,
)
from detectors.flow_signal import SubcaseSignal, veto_bullish

name = "flow_leverage"


# ─────────────────────────────────────────────────────────────
# Фандинг
# ─────────────────────────────────────────────────────────────

def _to_apr(rate: float, interval_hours: float = 8.0) -> float:
    """Приводит сырую ставку к годовым процентам.

    Внутри семейства сырая ставка не используется НИГДЕ: 0.01% за
    восемь часов и 0.01% за час — принципиально разные вещи, а
    выглядят одинаково. Все пороги заданы в APR.
    """
    if interval_hours <= 0:
        interval_hours = 8.0
    return rate * (24.0 / interval_hours) * 365.0 * 100.0


def _funding_interval(raw: list[dict]) -> float:
    """Интервал выплат в часах, выведенный из самих данных.

    Восемь часов — не константа биржи, а частый случай: у части
    контрактов интервал четырёхчасовой, и на них зашитая восьмёрка
    занижает APR ровно вдвое. Настоящий перекос −40% читается как
    −20% и не проходит ступень LEV_FUNDING_EXTREME_APR.

    Медиана, а не разность крайних: в истории бывают пропуски и
    смена интервала биржей, и одна дыра сдвинула бы оценку.
    """
    times: list[float] = []
    for item in raw:
        try:
            times.append(float(item["fundingTime"]))
        except (KeyError, TypeError, ValueError):
            continue

    gaps = [
        (times[i] - times[i - 1]) / 3_600_000.0
        for i in range(1, len(times))
        if times[i] > times[i - 1]
    ]
    return _median(gaps) if len(gaps) >= 3 else 8.0


def _funding_state(symbol: str) -> dict | None:
    """Состояние фандинга за доступную историю.

    Возвращает медианный APR, долю отрицательных интервалов и
    минимум — либо None, если данных нет.
    """
    limit = int(LEV_HISTORY_DAYS * LEV_FUNDING_PER_DAY)
    try:
        raw = get_funding_history(symbol, limit=limit)
    except Exception:
        return None
    if not raw or len(raw) < 6:
        return None

    rates: list[float] = []
    for item in raw:
        try:
            rates.append(float(item["fundingRate"]))
        except (KeyError, TypeError, ValueError):
            continue

    if len(rates) < 6:
        return None

    interval_h = _funding_interval(raw)
    aprs = [_to_apr(r, interval_h) for r in rates]
    neg = sum(1 for a in aprs if a < 0)

    return {
        "median_apr": _median(aprs),
        "min_apr": min(aprs),
        "last_apr": aprs[-1],
        "neg_share": neg / len(aprs),
        "samples": float(len(aprs)),
        "slope": _slope(aprs),
        # Наружу — чтобы величина была видна в фактах сигнала, а не
        # влияла на все пороги молча.
        "interval_h": interval_h,
    }


def _oi_state(symbol: str) -> dict | None:
    """Динамика открытого интереса в долларах.

    Берём именно долларовую величину, а не количество контрактов:
    при движении цены счёт контрактов растёт и падает сам по себе,
    и рост OI в штуках может означать сокращение позиции в деньгах.

    История доступна только за 30 дней — жёсткий потолок Binance,
    поэтому окно сравнения короткое по построению.
    """
    try:
        raw = get_oi_history(symbol, period="1d", limit=30)
    except Exception:
        return None
    if not raw or len(raw) < LEV_OI_WINDOW:
        return None

    values: list[float] = []
    for item in raw:
        try:
            values.append(float(item["sumOpenInterestValue"]))
        except (KeyError, TypeError, ValueError):
            continue

    if len(values) < LEV_OI_WINDOW:
        return None

    tail = values[-LEV_OI_WINDOW:]
    half = LEV_OI_WINDOW // 2
    first = _median(tail[:half])
    last = _median(tail[half:])

    growth = (last - first) / first if first > 0 else 0.0

    return {
        "current": values[-1],
        "growth": growth,
        "slope": _slope(tail),
    }


# ─────────────────────────────────────────────────────────────
# Цена
# ─────────────────────────────────────────────────────────────

def _price_flat(ctx: FlowContext, window: int = LEV_OI_WINDOW) -> tuple[bool, float]:
    """Стоит ли цена, пока набирается позиция.

    Смысл фигуры именно в расхождении: OI растёт, цена не идёт.
    Если цена уже падает вместе с ростом OI — шорт работает, и
    это не перекос, а тренд.
    """
    base = ctx.base
    if len(base) < window:
        return False, 0.0

    tail = base[-window:]
    if tail[0].close <= 0:
        return False, 0.0

    move = (tail[-1].close - tail[0].close) / tail[0].close * 100
    return abs(move) <= LEV_PRICE_FLAT_PCT, move


# ─────────────────────────────────────────────────────────────
# Зона
# ─────────────────────────────────────────────────────────────

def _floor_zone(ctx: FlowContext) -> Zone | None:
    """Уровень, от которого шортам будет больно.

    Не обязателен, но важен: перекос без опоры разряжается куда
    угодно, перекос над выдержанным уровнем — вверх.
    """
    below = [
        z for z in ctx.zones
        if z.price <= ctx.price
        and (ctx.price - z.price) / ctx.price <= ZONE_NEAR_PCT
    ]
    if not below:
        return None
    return max(below, key=lambda z: (z.tests, z.plateau_bars))


# ─────────────────────────────────────────────────────────────
# Базовый скор
# ─────────────────────────────────────────────────────────────

def _base_score(
    fund: dict,
    oi: dict,
    flat: bool,
) -> tuple[float, dict[str, float]]:
    """Скор от глубины перекоса и подтверждённости набора.

    Основа — фандинг: он прямо измеряет, сколько стоит держать
    позицию. Рост OI показывает, что позицию всё равно набирают,
    несмотря на цену.
    """
    apr = fund["median_apr"]
    score = 28.0

    if apr <= LEV_FUNDING_EXTREME_APR:
        score += 26.0
    elif apr <= LEV_FUNDING_NEG_APR * 2:
        score += 18.0
    elif apr <= LEV_FUNDING_NEG_APR:
        score += 10.0

    # Устойчивость перекоса важнее его глубины: один экстремальный
    # интервал бывает от разовой ликвидации.
    if fund["neg_share"] >= 0.85:
        score += 12.0
    elif fund["neg_share"] >= LEV_NEG_SHARE_MIN:
        score += 6.0

    # Позицию продолжают набирать.
    growth = oi["growth"]
    if growth >= LEV_OI_GROWTH_MIN * 3:
        score += 14.0
    elif growth >= LEV_OI_GROWTH_MIN * 2:
        score += 9.0
    elif growth >= LEV_OI_GROWTH_MIN:
        score += 5.0

    if flat:
        score += 8.0

    facts = {
        "funding_apr": apr,
        "funding_min_apr": fund["min_apr"],
        "funding_interval_h": fund["interval_h"],
        "neg_share": fund["neg_share"],
        "oi_growth": growth,
        "oi_usd": oi["current"],
    }
    return score, facts


# ─────────────────────────────────────────────────────────────
# Детект
# ─────────────────────────────────────────────────────────────

def detect(ctx: FlowContext) -> SubcaseSignal | None:
    """Собирает фигуру leverage либо возвращает None.

    Сетевые запросы делаются ТОЛЬКО после того, как отработали все
    дешёвые проверки: без валидного контекста и живых зон результат
    всё равно был бы отброшен, а запросов — двести штук впустую.
    Порядок отсечек ниже — это и порядок расходов, менять его без
    нужды нельзя.
    """
    # Зона желательна, но не обязательна: перекос в плече существует
    # независимо от карты уровней.
    stop = veto_bullish(ctx, require_zones=False)
    if stop:
        return ctx.reject(name, stop)

    # ── Ленивая загрузка ─────────────────────────────────────
    # Требование дневного ядра: без зон под ценой фигура не имеет
    # направления, и платить за сеть незачем.
    if LEV_REQUIRE_CORE and not ctx.zones:
        return ctx.reject(name, "нет живых зон, сеть не запрашивалась")

    flat, move = _price_flat(ctx)
    if not flat:
        # Цена идёт — перекос либо уже отработал, либо шорт прав.
        return ctx.reject(
            name,
            f"цена идёт: {move:+.1f}% за {LEV_OI_WINDOW} баров "
            f"> {LEV_PRICE_FLAT_PCT}%",
        )

    fund = _funding_state(ctx.symbol)
    if fund is None:
        return ctx.reject(name, "истории фандинга нет")

    # ── Знак фандинга ────────────────────────────────────────
    # Раньше здесь стояли две отсечки подряд: сначала по
    # LEV_FUNDING_HOT_APR, потом по LEV_FUNDING_NEG_APR. Вторая
    # строго шире первой — любой APR, прошедший горячий порог, всё
    # равно отсекался следующей строкой, и разграничение с
    # detect_squeeze существовало как комментарий, но решения не
    # принимало никогда.
    #
    # Теперь отсечка одна, а константа выбирает ФОРМУЛИРОВКУ: в
    # причине видно, чужая это территория или просто не тот знак.
    apr = fund["median_apr"]
    if apr > LEV_FUNDING_NEG_APR:
        why = (
            "перегрев лонгов, территория squeeze"
            if apr >= LEV_FUNDING_HOT_APR
            else "фандинг не отрицательный"
        )
        return ctx.reject(
            name, f"{why}: {apr:.1f}% APR > {LEV_FUNDING_NEG_APR}%",
        )

    if fund["neg_share"] < LEV_NEG_SHARE_MIN:
        return ctx.reject(
            name,
            f"перекос неустойчив: в минусе {fund['neg_share']:.2f} "
            f"< {LEV_NEG_SHARE_MIN}",
        )

    oi = _oi_state(ctx.symbol)
    if oi is None:
        return ctx.reject(name, "истории открытого интереса нет")

    # ── Ликвидность позиции ──────────────────────────────────
    # Если OI меньше порога, закрывать позицию некуда: сквиз
    # упрётся в пустой стакан и не даст движения, на котором
    # можно выйти.
    if oi["current"] < LEV_MIN_OI_USD:
        return ctx.reject(
            name,
            f"открытый интерес {oi['current']:,.0f} < {LEV_MIN_OI_USD:,.0f}",
        )

    if oi["growth"] < LEV_OI_GROWTH_MIN:
        return ctx.reject(
            name,
            f"позицию не набирают: OI {oi['growth']:.3f} "
            f"< {LEV_OI_GROWTH_MIN}",
        )

    score, facts = _base_score(fund, oi, flat)
    facts["price_move_pct"] = move

    sig = SubcaseSignal(
        subcase=name,
        score=score,
        horizon_bars=ctx.horizon_bars,
        zone_price=ctx.price,
    )
    sig.add(
        f"шорты перегружены: фандинг {facts['funding_apr']:.0f}% APR "
        f"({fund['neg_share'] * 100:.0f}% интервалов в минусе), "
        f"OI +{oi['growth'] * 100:.0f}% при цене {move:+.1f}%",
        **facts,
    )

    # ── Углубление перекоса ──────────────────────────────────
    # Фандинг уходит всё ниже — значит перекос не рассасывается,
    # а нарастает. Разряд ближе.
    if fund["slope"] < 0:
        sig.apply("deepening", 1.12)
        sig.add(
            "перекос углубляется",
            funding_slope=fund["slope"],
        )

    # ── Опора ────────────────────────────────────────────────
    zone = _floor_zone(ctx)
    if zone is not None:
        mult = 1.2 if zone.tests >= 2 else 1.1
        sig.apply("floor_zone", mult)
        sig.add(
            f"под перекосом зона {zone.price:.6g} "
            f"({zone.tests} тестов, плато {zone.plateau_bars} дней)",
            zone_price=zone.price,
            tests=float(zone.tests),
        )
        sig.zone_price = zone.price
    else:
        # Разряд возможен в любую сторону.
        sig.apply("no_floor", 0.85)
        sig.add("опорной зоны под перекосом нет")

    # ── Вортекс [MMT] ────────────────────────────────────────
    vx = ctx.vortex
    if vx.direction == "up":
        sig.apply("vortex_up", min(VORTEX_MULT_MAX, vx.mult(0.4)))
        sig.add(
            f"вортекс на масштабе {vx.scale}D подтверждает сторону разряда",
            vortex_scale=float(vx.scale),
            vortex_strength=vx.strength,
            vortex_confidence=vx.confidence,
        )
    elif vx.direction == "down":
        # Шорт может оказаться прав.
        sig.apply("vortex_conflict", 0.7)
        sig.add(
            f"вортекс на масштабе {vx.scale}D указывает вниз",
            vortex_scale=float(vx.scale),
            vortex_strength=vx.strength,
        )

    # ── Поток ──────────────────────────────────────────────
    # Перекос в плече плюс перекос в потоке — две независимые
    # стороны одной картины.
    #
    # Порог привязан к наблюдаемому разбросу (0.479..0.509).
    # Прежние 0.52 лежали выше рыночного максимума.
    if ctx.flow.buy_share >= LEV_BUY_BIAS:
        sig.apply("buy_bias", 1.1)
        sig.add(
            f"доля покупок {ctx.flow.buy_share * 100:.1f}%",
            buy_share=ctx.flow.buy_share,
        )

    if sig.weak:
        return ctx.reject(
            name, f"фигура собралась, но скор {sig.score:.1f} < 20 после множителей",
        )
    return sig
