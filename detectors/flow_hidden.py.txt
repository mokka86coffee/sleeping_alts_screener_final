"""FLOW · подкейс hidden — скрытый набор.

Фигура: кумулятивная дельта растёт, цена не идёт. Кто-то забирает
поток, не двигая рынок вверх — либо не хочет платить за движение,
либо не может себе позволить его показать.

Единственный ОПЕРЕЖАЮЩИЙ подкейс семейства. Остальные читают то,
что уже случилось: событие произошло, зона выдержала, уровень
пройден. Hidden читает намерение до результата — расхождение между
потоком и ценой существует ровно до того момента, как набор
закончится и цена пойдёт.

Отсюда высший потолок (CAP_HIDDEN) и самые жёсткие требования.
Цена опережающего признака — его ненадёжность: дивергенция дельты
шумит, и без фильтров по однородности, длине и подтверждению
вортексом даёт мусор.

Отличие от spring: там сжатие амплитуды при иссякшем потоке, здесь
поток идёт и он односторонний. Отличие от churn: там объём приходит
разовыми аномалиями на уровень, здесь набор размазан и событий
может не быть вовсе.
"""

from __future__ import annotations

from detectors.flow_config import (
    HIDDEN_DELTA_SLOPE_MIN,
    HIDDEN_LOWS_TOLERANCE,
    HIDDEN_MAX_BARS,
    HIDDEN_MIN_BARS,
    HIDDEN_BUY_BIAS,
    HIDDEN_PRICE_SLOPE_MAX,
    HIDDEN_WINDOW,
    HOMOGENEITY_GOOD,
    HOMOGENEITY_MIN,
    VORTEX_MULT_MAX,
    ZONE_NEAR_PCT,
)
from detectors.flow_core import (
    Bar,
    FlowContext,
    Zone,
    _slope,
    _slope_of_flow,
    homogeneity,
)
from detectors.flow_signal import SubcaseSignal, veto_bullish

name = "flow_hidden"

def _flow_slope(window: list[Bar]) -> float:
    """Наклон кумулятивной дельты окна в долях оборота.

    Нормировка обязана совпадать с той, что применяется в
    build_flow_stats: иначе HIDDEN_DELTA_SLOPE_MIN и
    DELTA_COLLAPSE_SLOPE окажутся в разных единицах и перестанут
    быть сравнимыми, хотя описывают одну и ту же величину.
    """
    acc = 0.0
    cum: list[float] = []
    for b in window:
        acc += b.delta
        cum.append(acc)

    avg_quote = sum(b.quote for b in window) / len(window) if window else 0.0
    return _slope_of_flow(cum, avg_quote)


# ─────────────────────────────────────────────────────────────
# Длина дивергенции
# ─────────────────────────────────────────────────────────────

def _divergence_span(bars: list[Bar]) -> int:
    """Сколько баров подряд дельта росла, а цена — нет.

    Идём от правого края влево и расширяем окно, пока условие
    держится. Длина фигуры — не украшение: набор в пятнадцать
    баров и набор в сто говорят о разной величине позиции и о
    разном сроке до разряда.
    """
    n = len(bars)
    if n < HIDDEN_MIN_BARS:
        return 0

    best = 0
    for span in range(HIDDEN_MIN_BARS, min(n, HIDDEN_MAX_BARS) + 1):
        window = bars[-span:]

        d_slope = _flow_slope(window)
        p_slope = _slope([b.close for b in window])

        if d_slope >= HIDDEN_DELTA_SLOPE_MIN and p_slope <= HIDDEN_PRICE_SLOPE_MAX:
            best = span

    return best


def _higher_lows(bars: list[Bar]) -> bool:
    """Минимумы перестали обновляться вниз.

    Слабое, но важное подтверждение: набор при продолжающемся
    сползании минимумов — это ловля падающего ножа, а не
    накопление. Допуск нужен, потому что идеальных higher lows
    в живом рынке не бывает.
    """
    if len(bars) < 6:
        return False

    half = len(bars) // 2
    early = min(b.low for b in bars[:half])
    late = min(b.low for b in bars[half:])
    if early <= 0:
        return False

    return (late - early) / early >= -HIDDEN_LOWS_TOLERANCE


# ─────────────────────────────────────────────────────────────
# Зона под набором
# ─────────────────────────────────────────────────────────────

def _floor_zone(ctx: FlowContext) -> Zone | None:
    """Уровень, от которого идёт набор.

    Не обязателен: hidden — единственный подкейс, который может
    собраться без зоны, потому что скрытый набор по определению
    не оставляет крупных следов в карте уровней. Но если зона
    есть, она превращает догадку в конструкцию: известно, откуда
    защищают.
    """
    below = [z for z in ctx.zones if z.price <= ctx.price]
    if not below:
        return None

    near = [
        z for z in below
        if (ctx.price - z.price) / ctx.price <= ZONE_NEAR_PCT
    ]
    if not near:
        return None

    return max(near, key=lambda z: (z.tests, z.tier_sum))


# ─────────────────────────────────────────────────────────────
# Базовый скор
# ─────────────────────────────────────────────────────────────

def _base_score(
    span: int,
    d_slope: float,
    p_slope: float,
) -> tuple[float, dict[str, float]]:
    """Скор от величины расхождения и его длительности.

    Основа — насколько круто дельта уходит вверх при стоящей цене.
    Длительность добавляет: короткая дивергенция чаще совпадение,
    длинная — работа.
    """
    score = 34.0

    # Крутизна набора относительно порога.
    excess = d_slope / HIDDEN_DELTA_SLOPE_MIN
    if excess >= 4.0:
        score += 20.0
    elif excess >= 2.5:
        score += 14.0
    elif excess >= 1.5:
        score += 8.0

    # Длительность. Потолок нужен: за HIDDEN_MAX_BARS набор
    # перестаёт быть подготовкой к движению.
    score += min(14.0, (span - HIDDEN_MIN_BARS) * 0.35)

    # Цена не просто стоит, а сползает при растущей дельте —
    # это сильнее плоскости: покупателю отдают дешевле.
    if p_slope <= HIDDEN_PRICE_SLOPE_MAX * 2:
        score += 6.0

    facts = {
        "span": float(span),
        "delta_slope": d_slope,
        "price_slope": p_slope,
        "excess": excess,
    }
    return score, facts


# ─────────────────────────────────────────────────────────────
# Детект
# ─────────────────────────────────────────────────────────────

def detect(ctx: FlowContext) -> SubcaseSignal | None:
    """Собирает фигуру hidden либо возвращает None."""
    if veto_bullish(ctx, require_zones=False):
        return None

    base = ctx.base
    if len(base) < HIDDEN_MIN_BARS * 2:
        return None

    span = _divergence_span(base)
    if span < HIDDEN_MIN_BARS:
        return None

    window = base[-span:]


    d_slope = _flow_slope(window)
    p_slope = _slope([b.close for b in window])

    # ── Однородность: жёсткий фильтр, не множитель ───────────
    # Скрытый набор размазан по определению. Если весь прирост
    # дельты сделан одним баром — это не набор, а разовый вброс,
    # и фигуры нет вообще. В остальных подкейсах неоднородность
    # штрафует, здесь она опровергает.
    hom = homogeneity([b.delta for b in window])
    if hom < HOMOGENEITY_MIN:
        return None

    score, facts = _base_score(span, d_slope, p_slope)

    sig = SubcaseSignal(
        subcase=name,
        score=score,
        horizon_bars=ctx.horizon_bars,
        zone_price=ctx.price,
    )
    sig.add(
        f"скрытый набор: дельта растёт {span} баров, цена стоит "
        f"({p_slope * 100:+.2f}% за бар)",
        **facts,
    )

    # ── Качество размазывания ────────────────────────────────
    if hom >= HOMOGENEITY_GOOD:
        sig.apply("even_flow", 1.15)
        sig.add(
            f"набор равномерный (однородность {hom:.2f})",
            homogeneity=hom,
        )
    else:
        sig.add(f"однородность {hom:.2f}", homogeneity=hom)

    # ── Минимумы ─────────────────────────────────────────────
    if _higher_lows(window):
        sig.apply("higher_lows", 1.12)
        sig.add("минимумы перестали обновляться вниз")
    else:
        # Набирают в падающий рынок. Бывает и это работает, но
        # ждать разряда придётся дольше и просадка вероятна.
        sig.apply("falling_lows", 0.78)
        sig.add("минимумы продолжают сползать")

    # ── Опора ────────────────────────────────────────────────
    zone = _floor_zone(ctx)
    if zone is not None:
        mult = 1.2 if zone.tests >= 2 else 1.1
        sig.apply("floor_zone", mult)
        sig.add(
            f"набор идёт от зоны {zone.price:.6g} "
            f"({zone.tests} тестов)",
            zone_price=zone.price,
            tests=float(zone.tests),
        )
        sig.zone_price = zone.price
    else:
        # Без зоны фигура держится только на потоке. Это
        # допустимо — скрытый набор следов в карте не оставляет —
        # но уверенности меньше.
        sig.apply("no_floor", 0.88)
        sig.add("опорной зоны под набором нет")

    # ── Вортекс на своём масштабе [MMT] ──────────────────────
    # Здесь совпадение двух опережающих признаков: дельта
    # показывает намерение, вортекс — что перевес уже сложился на
    # старшем масштабе, хотя цена его не отражает. Вортекс
    # надёжнее: он накопительный, дельта шумит. Поэтому вес выше,
    # чем в churn и spring.
    vx = ctx.vortex
    if vx.diverging and vx.vi_plus > vx.vi_minus:
        mult = min(VORTEX_MULT_MAX, 1.0 + vx.spread * 0.6)
        sig.apply("vortex_up", mult)
        sig.add(
            f"вортекс на масштабе {vx.scale}D подтверждает: "
            f"{vx.vi_plus:.2f} против {vx.vi_minus:.2f}",
            vortex_scale=float(vx.scale),
            vortex_spread=vx.spread,
        )
    elif vx.diverging and vx.vi_minus > vx.vi_plus:
        # Прямое противоречие: дельта растёт, а направленное
        # движение перевешивает вниз. Один из двух признаков
        # врёт, и это повод не брать монету.
        sig.apply("vortex_conflict", 0.6)
        sig.add(
            f"вортекс на масштабе {vx.scale}D противоречит набору",
            vortex_scale=float(vx.scale),
            vortex_spread=vx.spread,
        )

    # ── Доля покупок ─────────────────────────────────────────
    # Наклон дельты может расти и при доле около половины, если
    # объём нарастает. Устойчивый перевес — отдельное
    # свидетельство.
    #
    # Порог привязан к наблюдаемому разбросу (0.479..0.509).
    # Прежние 0.53 лежали выше рыночного максимума: ветка была
    # мёртвым кодом.
    if ctx.flow.buy_share >= HIDDEN_BUY_BIAS:
        sig.apply("buy_bias", 1.1)
        sig.add(
            f"доля покупок {ctx.flow.buy_share * 100:.1f}%",
            buy_share=ctx.flow.buy_share,
        )

    # ── Объём после дна ──────────────────────────────────────
    if ctx.volume_recovery and ctx.volume_recovery >= 1.0:
        sig.apply("recovery", 1.1)
        sig.add(
            f"объём восстановился (x{ctx.volume_recovery:.2f})",
            volume_recovery=ctx.volume_recovery,
        )

    # ── Подозрительный контекст ──────────────────────────────
    # Объём растёт при падающей цене. Для hidden это особенно
    # опасно: ровно так выглядит и распределение сверху вниз.
    if ctx.drop.suspicious:
        sig.apply("suspicious", 0.75)
        sig.add("объём нарастает при падающей цене")

    return sig if not sig.weak else None
