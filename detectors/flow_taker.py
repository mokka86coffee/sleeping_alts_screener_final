"""FLOW · подкейс taker — смена стороны агрессора.

Фигура: доля рыночных покупок устойчиво сдвинулась вверх, а цена
за этим не пошла. Тот, кто раньше продавал в стакан, начал в него
покупать — и делает это ровно, а не одним заходом.

Отличие от hidden: там кумулятивная дельта в абсолюте, здесь —
ДОЛЯ покупок в обороте. Разница существенная. Дельта растёт и при
неизменной доле, если растёт оборот; доля растёт и при падающем
обороте. Hidden отвечает на вопрос «сколько набрали», taker — на
вопрос «кто теперь агрессор». Первое про объём позиции, второе про
смену намерения, и совпадать они не обязаны.

Отличие от churn: там объём приходит аномальными выбросами на
уровень, здесь никакой аномалии нет — обычный фон, но с другим
составом. Событий может не быть вовсе, и зона не требуется.

Подкейс самый слабый в семействе по потолку (CAP_TAKER) и это
осознанно: эталонного кейса под него нет, сдвиг доли на тонком
рынке возникает случайно, а отличить смену агрессора от смены
маркет-мейкера по одному полю свечи нельзя.
"""

from __future__ import annotations

from detectors.flow_config import (
    HOMOGENEITY_MIN,
    TAKER_BASE_WINDOW,
    TAKER_GAP,
    TAKER_LATE_WINDOW,
    TAKER_MIN_EVENTS,
    TAKER_MIN_QUOTE_VOL,
    TAKER_SHIFT_MIN,
    TAKER_STABILITY_MAX,
    TAKER_TREND_PENALTY,
    VORTEX_MULT_MAX,
    ZONE_NEAR_PCT,
)
from detectors.flow_core import (
    Bar,
    FlowContext,
    Zone,
    _median,
    _slope,
    homogeneity,
)
from detectors.flow_signal import SubcaseSignal, veto_bullish

name = "flow_taker"

# Масштабного фильтра здесь нет намеренно. Горизонт — ярлык
# времени, а не масштаб расчёта: доля покупок всегда считается
# по дневкам, и то, что pick_horizon вернул 5D, на состав
# потока не влияет. Прежняя проверка ctx.horizon_scale > 3
# отсекала половину выборки до всех расчётов — в прогоне у
# сработавших монет horizon_days равнялся 25, то есть масштаб
# был 5 или 10.

# Цена «пошла за сдвигом» — фигуры больше нет: смена агрессора уже
# отыграна, входить поздно. Порог в долях за окно.
TAKER_PRICE_MOVED = 0.12

# Отвесное движение вниз. Сдвиг доли покупок на таком фоне обычно
# означает не набор, а ловлю ножа встречными лимитами.
TAKER_STEEP_DROP = -0.006


# ─────────────────────────────────────────────────────────────
# Доля покупок по окнам
# ─────────────────────────────────────────────────────────────

def _buy_share(bars: list[Bar]) -> float:
    """Доля рыночных покупок в обороте окна.

    Считается по суммам, а не как среднее из побарных долей: иначе
    тихий бар с долей 0.9 весит столько же, сколько крупный с 0.5,
    и картина переворачивается на пустом месте.
    """
    total = sum(b.quote for b in bars)
    if total <= 0:
        return 0.5
    return sum(b.buy_quote for b in bars) / total


def _windows(base: list[Bar]) -> tuple[list[Bar], list[Bar]] | None:
    """Раннее и позднее окна с разрывом между ними.

    Разрыв обязателен: без него окна соприкасаются, и плавный дрейф
    доли читается как ступенька. Нас интересует именно смена
    состояния, а не медленное сползание.
    """
    need = TAKER_BASE_WINDOW + TAKER_GAP + TAKER_LATE_WINDOW
    if len(base) < need:
        return None

    late = base[-TAKER_LATE_WINDOW:]
    end_early = len(base) - TAKER_LATE_WINDOW - TAKER_GAP
    early = base[end_early - TAKER_BASE_WINDOW : end_early]

    if len(early) < TAKER_BASE_WINDOW or len(late) < TAKER_LATE_WINDOW:
        return None
    return early, late


def _stability(bars: list[Bar]) -> float:
    """Разброс доли покупок внутри окна.

    Устойчивый сдвиг — это когда КАЖДЫЙ бар позднего окна покупает
    больше обычного. Если доля скачет от 0.2 до 0.8 и в среднем
    даёт сдвиг, это не смена агрессора, а совпадение.

    Считается через медианное отклонение: одиночный выброс не
    должен объявлять устойчивую картину нестабильной.
    """
    shares = [b.buy_share for b in bars if b.quote > 0]
    if len(shares) < 3:
        return 1.0
    med = _median(shares)
    return _median([abs(s - med) for s in shares])


# ─────────────────────────────────────────────────────────────
# Зона
# ─────────────────────────────────────────────────────────────

def _context_zone(ctx: FlowContext) -> Zone | None:
    """Уровень под сдвигом, если он есть.

    Не обязателен: смена агрессора не оставляет следов в карте
    уровней, потому что аномалий объёма в фигуре нет по построению.
    Но зона под ней превращает наблюдение в конструкцию.
    """
    below = [
        z for z in ctx.zones
        if z.price <= ctx.price
        and (ctx.price - z.price) / ctx.price <= ZONE_NEAR_PCT
    ]
    if not below:
        return None
    return max(below, key=lambda z: (z.tests, z.tier_sum))


# ─────────────────────────────────────────────────────────────
# Базовый скор
# ─────────────────────────────────────────────────────────────

def _base_score(
    shift: float,
    late_share: float,
    stability: float,
) -> tuple[float, dict[str, float]]:
    """Скор от величины сдвига и его устойчивости.

    Величина даёт основу, устойчивость — надбавку. Ровный сдвиг на
    полтора пункта надёжнее рваного на три: первый описывает
    поведение, второй — событие.

    Шкала пересчитана под реальный масштаб величины. Прежние ступени
    0.10 и 0.15 брались из общих соображений и оказались недостижимы:
    на 222 монетах весь разброс доли покупок по рынку уложился в три
    процентных пункта, а сдвиг внутри одной монеты меньше того. Любой
    прошедший сигнал попадал бы в нижнюю ветку и получал одну и ту же
    прибавку — первое слагаемое выродилось бы в константу, как это
    уже случилось с fuel.
    """
    score = 30.0

    # Ступени в долях единицы: 0.008 — порог входа, 0.015 — заметное
    # смещение состава, 0.025 — смена режима, редкость.
    if shift >= 0.025:
        score += 20.0
    elif shift >= 0.015:
        score += 14.0
    elif shift >= TAKER_SHIFT_MIN:
        score += 7.0

    # Абсолютный уровень: сдвиг с 0.30 до 0.40 и с 0.50 до 0.60 —
    # разные вещи. Во втором случае покупатель уже доминирует.
    #
    # Границы опущены к наблюдаемым: доля выше 0.55 на дневках не
    # встречается вовсе, максимум по выборке — 0.509. Порог, которого
    # нет в данных, эквивалентен его отсутствию.
    if late_share >= 0.510:
        score += 10.0
    elif late_share >= 0.500:
        score += 5.0

    # Чем плотнее доля держится вокруг медианы, тем меньше шанс,
    # что сдвиг собран парой баров.
    if stability <= TAKER_STABILITY_MAX * 0.5:
        score += 10.0
    elif stability <= TAKER_STABILITY_MAX:
        score += 5.0

    facts = {
        "shift": shift,
        "late_share": late_share,
        "stability": stability,
    }
    return score, facts


# ─────────────────────────────────────────────────────────────
# Детект
# ─────────────────────────────────────────────────────────────

def detect(ctx: FlowContext) -> SubcaseSignal | None:
    """Собирает фигуру taker либо возвращает None."""
    # Зона не требуется: фигура строится на составе потока, а не
    # на карте уровней.
    if veto_bullish(ctx, require_zones=False):
        return None

    # ── Область определения ─────────────────────────────────
    # Не строгость, а граница применимости, и разница
    # принципиальна. Доля покупок считается по любым барам,
    # поэтому подкейс формально работает и там, где ядро не
    # нашло ни одной аномалии объёма. Но такая монета не даёт
    # материала для суждения о составе потока: величина сдвига
    # может быть какой угодно, если рынка нет.
    #
    # LITEUSDT прошла с тремя событиями за всю историю и нулём
    # зон, набрав 47 баллов на сдвиге, который целиком
    # объясняется парой заявок. Рядом ROBOUSDT — двенадцать
    # событий, те же 47.
    #
    # Проверка стоит ДО всех расчётов: считать сдвиг на трёх
    # событиях бессмысленно независимо от результата.
    if len(ctx.events) < TAKER_MIN_EVENTS:
        return None

    base = ctx.base
    pair = _windows(base)
    if pair is None:
        return None
    early, late = pair

    # ── Ликвидность ──────────────────────────────────────────
    # На тонком рынке доля покупок скачет от одной заявки. Считаем
    # по медиане позднего окна, а не по 24h: суточный оборот мог
    # быть разовым.
    med_quote = _median([b.quote for b in late])
    if med_quote < TAKER_MIN_QUOTE_VOL:
        return None

    early_share = _buy_share(early)
    late_share = _buy_share(late)
    shift = late_share - early_share

    if shift < TAKER_SHIFT_MIN:
        return None

    stability = _stability(late)
    if stability > TAKER_STABILITY_MAX * 1.5:
        # Доля скачет слишком сильно — сдвиг случайный.
        return None

    # ── Цена ещё не пошла ────────────────────────────────────
    # Смысл подкейса в опережении. Если цена уже отработала смену
    # агрессора, фигура превратилась в констатацию.
    price_move = 0.0
    if late[0].close > 0:
        price_move = (late[-1].close - late[0].close) / late[0].close
    if price_move >= TAKER_PRICE_MOVED:
        return None

    score, facts = _base_score(shift, late_share, stability)
    facts["early_share"] = early_share
    facts["price_move"] = price_move

    sig = SubcaseSignal(
        subcase=name,
        score=score,
        horizon_bars=ctx.horizon_bars,
        zone_price=ctx.price,
    )
    sig.add(
        f"агрессор сменился: доля покупок {early_share * 100:.0f}% → "
        f"{late_share * 100:.0f}% при цене {price_move * 100:+.1f}%",
        **facts,
    )

    # ── Однородность ─────────────────────────────────────────
    hom = homogeneity([b.delta for b in late])
    if hom < HOMOGENEITY_MIN:
        sig.apply("lumpy", 0.75)
        sig.add("сдвиг собран неравномерно", homogeneity=hom)
    else:
        sig.add(f"однородность {hom:.2f}", homogeneity=hom)

    # ── Наклон цены ──────────────────────────────────────────
    p_slope = _slope([b.close for b in late])
    if p_slope <= TAKER_STEEP_DROP:
        # Отвесное падение. Рост доли покупок здесь чаще означает
        # встречные лимиты под ножом, а не смену намерения.
        sig.apply("steep_drop", TAKER_TREND_PENALTY)
        sig.add(
            f"сдвиг на отвесном падении ({p_slope * 100:.2f}% за бар)",
            price_slope=p_slope,
        )
    elif p_slope >= 0:
        sig.apply("price_holds", 1.1)
        sig.add("цена перестала сползать", price_slope=p_slope)

    # ── Опора ────────────────────────────────────────────────
    zone = _context_zone(ctx)
    if zone is not None:
        mult = 1.2 if zone.tests >= 2 else 1.1
        sig.apply("zone", mult)
        sig.add(
            f"под сдвигом зона {zone.price:.6g} ({zone.tests} тестов)",
            zone_price=zone.price,
            tests=float(zone.tests),
        )
        sig.zone_price = zone.price

    # ── Вортекс [MMT] ────────────────────────────────────────
    # Проверка сдвига независимым способом: доля покупок читает
    # состав потока, вортекс — направленность движения. Совпадение
    # двух разных измерений сильнее любого из них.
    vx = ctx.vortex
    if vx.diverging and vx.vi_plus > vx.vi_minus:
        mult = min(VORTEX_MULT_MAX, 1.0 + vx.spread * 0.4)
        sig.apply("vortex_up", mult)
        sig.add(
            f"вортекс на масштабе {vx.scale}D подтверждает сдвиг",
            vortex_scale=float(vx.scale),
            vortex_spread=vx.spread,
        )
    elif vx.diverging and vx.vi_minus > vx.vi_plus:
        sig.apply("vortex_conflict", 0.7)
        sig.add(
            f"вортекс на масштабе {vx.scale}D противоречит сдвигу",
            vortex_scale=float(vx.scale),
            vortex_spread=vx.spread,
        )

    # ── Подозрительный контекст ──────────────────────────────
    if ctx.drop.suspicious:
        sig.apply("suspicious", 0.8)
        sig.add("объём нарастает при падающей цене")

    return sig if not sig.weak else None
