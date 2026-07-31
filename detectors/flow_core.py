"""FLOW · ядро семейства.

Вся математика, общая для подкейсов: агрегация масштабов, поток
по сторонам, события, зоны, контекст падения и роста.

Модуль ни от чего в проекте не зависит, кроме core.binance (канонические
загрузчики) и detectors.flow_config (пороги). Другие детекторы, analytics
и общий config здесь не используются — это правило семейства.

Контекст считается ОДИН раз на монету и передаётся во все подкейсы:
дневки берутся из RunCache, агрегаты строятся из них, поэтому
все масштабы бесплатны после первого обращения.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from core.binance import (
    K_CLOSE,
    K_HIGH,
    K_LOW,
    K_OPEN,
    K_QUOTE_VOLUME,
    K_VOLUME,
    klines_1d,
    series,
)
from detectors.flow_config import (
    BOTTOM_LOOKBACK_DAYS,
    BOTTOM_MIN_BARS_AFTER,
    BOTTOM_MIN_DROP_PCT,
    DELTA_COLLAPSE_SLOPE,
    DELTA_WINDOW,
    EVENT_NORM_WINDOW,
    EXTREME_GROWTH_X,
    GROWTH_DISTRUST,
    HORIZON_BARS_AHEAD,
    HORIZON_MIN_AMPLITUDE,
    IMMATURE_BODY_MAX,
    IMMATURE_MIN_TIER,
    MIN_BARS_BASE,
    MIN_BARS_HTF,
    PARTIAL_BAR_MIN_FILL,
    PARTIAL_BAR_NORMALIZE,
    PLATEAU_FULL_BARS,
    PLATEAU_MAX_RANGE,
    PLATEAU_MIN_BARS,
    PLATEAU_MULT_FULL,
    PLATEAU_MULT_NONE,
    RESPONSE_BARS,
    RESPONSE_FLAT_ATR,
    SCALES,
    TIER_1_SIGMA,
    TIER_2_SIGMA,
    TIER_3_SIGMA,
    VOLUME_RECOVERY_GOOD,
    ZONE_DEAD_AFTER_BREAK,
    ZONE_MATCH_PCT,
    ZONE_MAX_AGE_UNTESTED,
    ZONE_MIN_EVENTS,
    ZONE_NEAR_PCT,
    ZONE_TEST_HOLD_PCT,
    ZONE_TEST_TOUCH_PCT,
)

# Индекс поля taker buy quote volume в свече Binance.
# В core.binance объявлены константы до K_QUOTE_VOLUME = 7; это поле
# нужно только семейству, поэтому живёт здесь, а не в общем модуле.
K_TAKER_BUY_QUOTE = 10


# ─────────────────────────────────────────────────────────────
# Устойчивая статистика
# ─────────────────────────────────────────────────────────────
# Среднее и стандартное отклонение непригодны: один памп задирает
# норму так, что последующие аномалии перестают быть аномалиями.
# Везде используется медиана и MAD.


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def _mad(values: list[float], med: float | None = None) -> float:
    """Median absolute deviation, приведённый к масштабу сигмы."""
    if not values:
        return 0.0
    m = _median(values) if med is None else med
    dev = [abs(v - m) for v in values]
    return _median(dev) * 1.4826


def robust_sigma(value: float, sample: list[float]) -> float:
    """Насколько значение аномально относительно выборки, в сигмах."""
    if not sample:
        return 0.0
    med = _median(sample)
    mad = _mad(sample, med)
    if mad <= 0:
        # Вырожденный случай: половина выборки одинаковая.
        # Падать на нуль нельзя, но и аномалию объявлять не за что.
        return 0.0
    return (value - med) / mad


def _slope(values: list[float]) -> float:
    """Наклон линейной регрессии, нормированный на средний уровень.

    Нормировка обязательна: иначе наклон зависит от цены монеты,
    и пороги пришлось бы задавать для каждой отдельно.
    """
    n = len(values)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2
    mean_y = sum(values) / n
    num = sum((i - mean_x) * (v - mean_y) for i, v in enumerate(values))
    den = sum((i - mean_x) ** 2 for i in range(n))
    if den <= 0:
        return 0.0
    slope = num / den
    scale = abs(mean_y) if abs(mean_y) > 1e-12 else 1.0
    return slope / scale


def homogeneity(values: list[float]) -> float:
    """Насколько равномерно распределён вклад по окну.

    1 — все бары вложились одинаково, 0 — весь сдвиг сделан одним баром.
    Считается через долю максимального вклада: скрытый набор по
    определению размазан, одиночный вброс скрытым не является.
    """
    pos = [v for v in values if v > 0]
    if not pos:
        return 0.0
    total = sum(pos)
    if total <= 0:
        return 0.0
    share_max = max(pos) / total
    ideal = 1.0 / len(pos)
    if share_max <= ideal:
        return 1.0
    return max(0.0, min(1.0, (1.0 - share_max) / (1.0 - ideal)))


# ─────────────────────────────────────────────────────────────
# Свеча и агрегация
# ─────────────────────────────────────────────────────────────


@dataclass
class Bar:
    """Свеча с разложенным потоком по сторонам."""

    idx: int
    open: float
    high: float
    low: float
    close: float
    quote: float
    buy_quote: float
    buy_quote: float
    fill: float = 1.0   # доля набранного времени бара

    @property
    def scale_factor(self) -> float:
        """Множитель приведения объёма к полному бару.

        Незакрытый бар нельзя сравнивать с нормой напрямую: 6D
        показывал 16% относительного объёма там, где 4D в тот же
        момент показывал 327% — разница целиком в заполнении.
        """
        if not PARTIAL_BAR_NORMALIZE or self.fill >= 1.0 or self.fill <= 0:
            return 1.0
        return 1.0 / self.fill

    @property
    def normalized_quote(self) -> float:
        return self.quote * self.scale_factor

    @property
    def sell_quote(self) -> float:
        return max(0.0, self.quote - self.buy_quote)

    @property
    def delta(self) -> float:
        return self.buy_quote - self.sell_quote

    @property
    def buy_share(self) -> float:
        return self.buy_quote / self.quote if self.quote > 0 else 0.5

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def amplitude(self) -> float:
        return max(0.0, self.high - self.low)


def _to_bars(raw: list[list]) -> list[Bar]:
    out: list[Bar] = []
    for i, k in enumerate(raw):
        try:
            quote = float(k[K_QUOTE_VOLUME])
            buy = float(k[K_TAKER_BUY_QUOTE])
        except (TypeError, ValueError, IndexError):
            continue
        try:
            o = float(k[K_OPEN])
            h = float(k[K_HIGH])
            lo = float(k[K_LOW])
            c = float(k[K_CLOSE])
        except (TypeError, ValueError, IndexError):
            continue
        if c <= 0 or quote <= 0:
            continue
        out.append(
            Bar(
                idx=i,
                open=o,
                high=h,
                low=lo,
                close=c,
                quote=quote,
                buy_quote=min(buy, quote),
            )
        )
    return out


def aggregate(bars: list[Bar], scale: int) -> list[Bar]:
    """Склеивает дневки в бары нужного масштаба.

    Порог аномалии строится от нормы объёма ВНУТРИ бара. Накопление,
    размазанное по десяти дням порциями ниже порога, на дневке не даёт
    ни одного события — а в десятидневном баре складывается в одно
    крупное. Крупный масштаб не показывает другое, он суммирует то,
    что тонуло в шуме.

    Хвост НЕ обрезается: последний бар может быть неполным, но он
    несёт самые свежие события. Вместо этого он помечается долей
    заполнения, а сигма считается по приведённому объёму.
    """
    if scale <= 1:
        return bars
    n = len(bars)
    if n < scale:
        return []

    # Выравнивание с начала: правый край обязан заканчиваться
    # текущим баром, иначе свежие события теряют масштаб.
    start = n % scale
    out: list[Bar] = []

    if start:
        head = bars[:start]
        out.append(
            Bar(
                idx=head[0].idx,
                open=head[0].open,
                high=max(b.high for b in head),
                low=min(b.low for b in head),
                close=head[-1].close,
                quote=sum(b.quote for b in head),
                buy_quote=sum(b.buy_quote for b in head),
                fill=len(head) / scale,
            )
        )

    for i in range(start, n, scale):
        chunk = bars[i : i + scale]
        out.append(
            Bar(
                idx=chunk[0].idx,
                open=chunk[0].open,
                high=max(b.high for b in chunk),
                low=min(b.low for b in chunk),
                close=chunk[-1].close,
                quote=sum(b.quote for b in chunk),
                buy_quote=sum(b.buy_quote for b in chunk),
                fill=len(chunk) / scale,
            )
        )
    return out


def _min_bars(scale: int) -> int:
    return MIN_BARS_BASE if scale <= 1 else MIN_BARS_HTF


# ─────────────────────────────────────────────────────────────
# События
# ─────────────────────────────────────────────────────────────


@dataclass
class Event:
    """Аномальный объём одной стороны."""

    scale: int
    bar_idx: int    # позиция в ряду своего масштаба
    day_idx: int    # позиция конца бара в дневном ряду
    age: int              # сколько баров назад от правого края
    price: float          # уровень события
    side: str             # "buy" | "sell"
    sigma: float
    tier: int
    volume: float
    response: float       # движение цены после события, доли
    absorbed: bool        # масса приложена, цена не сдвинулась
    immature: bool        # окно отклика ещё не прошло

    def to_dict(self) -> dict:
        return {
            "scale": self.scale,
            "age": self.age,
            "price": round(self.price, 10),
            "side": self.side,
            "sigma": round(self.sigma, 2),
            "tier": self.tier,
            "response": round(self.response * 100, 2),
            "absorbed": self.absorbed,
            "immature": self.immature,
        }


def _tier(sigma: float) -> int:
    if sigma >= TIER_3_SIGMA:
        return 3
    if sigma >= TIER_2_SIGMA:
        return 2
    if sigma >= TIER_1_SIGMA:
        return 1
    return 0


def _atr_share(bars: list[Bar], upto: int, window: int = 14) -> float:
    """Нормальная амплитуда бара в долях цены, устойчиво."""
    lo = max(0, upto - window)
    sample = [b.amplitude / b.close for b in bars[lo:upto] if b.close > 0]
    if not sample:
        return 0.0
    return _median(sample)


def find_events(bars: list[Bar], scale: int) -> list[Event]:
    """Ищет аномальные объёмы сторон и меряет отклик.

    Отклик считается ОДИН раз: для зрелых событий — по движению цены
    за окно, для незрелых — по телу бара против нормальной амплитуды.
    Порог берётся тот, который соответствует способу измерения.
    """
    n = len(bars)
    if n < _min_bars(scale):
        return []

    events: list[Event] = []
    atr_norm = _atr_share(bars, n)

    for i in range(EVENT_NORM_WINDOW, n):
        bar = bars[i]

        # Бар набран меньше чем на треть — судить не о чем.
        if bar.fill < PARTIAL_BAR_MIN_FILL:
            continue

        lo = max(0, i - EVENT_NORM_WINDOW)
        # Норма строится только по полным барам: неполный в выборке
        # занижает медиану и делает аномалией любой обычный объём.
        norm = [b for b in bars[lo:i] if b.fill >= 1.0]
        if len(norm) < EVENT_NORM_WINDOW // 2:
            continue

        buys = [b.buy_quote for b in norm]
        sells = [b.sell_quote for b in norm]

        k = bar.scale_factor
        sig_buy = robust_sigma(bar.buy_quote * k, buys)
        sig_sell = robust_sigma(bar.sell_quote * k, sells)

        # Обе стороны аномальны — берём доминирующую.
        if sig_buy >= sig_sell:
            side, sigma = "buy", sig_buy
        else:
            side, sigma = "sell", sig_sell

        tier = _tier(sigma)
        if tier <= 0:
            continue

        age = n - 1 - i
        immature = age < RESPONSE_BARS

        if immature:
            # Окно отклика не прошло. Поглощение меряется внутри бара:
            # крупный объём при узком теле — это ровно то, что ищем.
            # Требования строже: только верхний тир.
            if tier < IMMATURE_MIN_TIER:
                continue
            body_share = bar.body / bar.close if bar.close > 0 else 0.0
            limit = atr_norm * IMMATURE_BODY_MAX
            response = body_share if bar.close >= bar.open else -body_share
            absorbed = body_share <= limit and limit > 0
        else:
            end = bars[i + RESPONSE_BARS]
            response = (end.close - bar.close) / bar.close if bar.close > 0 else 0.0
            # Порог случайного блуждания: размах растёт как корень времени.
            limit = atr_norm * RESPONSE_FLAT_ATR * math.sqrt(RESPONSE_BARS)
            absorbed = abs(response) <= limit and limit > 0

        events.append(
            Event(
                scale=scale,
                bar_idx=i,
                day_idx=bar.idx + max(1, scale) - 1,
                age=age,
                price=bar.close,
                side=side,
                sigma=sigma,
                tier=tier,
                volume=bar.buy_quote if side == "buy" else bar.sell_quote,
                response=response,
                absorbed=absorbed,
                immature=immature,
            )
        )

    return events


# ─────────────────────────────────────────────────────────────
# Зоны
# ─────────────────────────────────────────────────────────────


@dataclass
class Zone:
    """Кластер событий на одном ценовом уровне."""

    price: float                  # средневзвешенный по объёму центр
    events: list[Event] = field(default_factory=list)
    scales: set[int] = field(default_factory=set)

    # История уровня после события. Заполняется annotate_zone_history.
    tests: int = 0            # успешных тестов уровня
    last_test_age: int = -1   # давность последнего теста, в днях
    broken: bool = False      # цена уходила под зону
    plateau_bars: int = 0     # длина плато над зоной, в днях
    zones_below: int = 0      # сколько живых зон ниже этой

    @property
    def strength(self) -> float:
        return sum(e.volume for e in self.events)

    @property
    def tier_sum(self) -> int:
        return sum(e.tier for e in self.events)

    @property
    def absorbed_ratio(self) -> float:
        if not self.events:
            return 0.0
        return sum(1 for e in self.events if e.absorbed) / len(self.events)

    @property
    def buy_ratio(self) -> float:
        if not self.events:
            return 0.0
        return sum(1 for e in self.events if e.side == "buy") / len(self.events)

    @property
    def event_age(self) -> int:
        """Давность самого события, в дневных барах."""
        if not self.events:
            return 10_000
        return min(e.age * max(1, e.scale) for e in self.events)

    @property
    def freshness(self) -> int:
        """Рабочая давность зоны.

        Событие стареет, зона — нет: она живёт, пока цена её не
        пробила. Каждый успешный тест обнуляет возраст. На KOMA
        между событием и выносом прошло ~200 дней, и всё это время
        зона была рабочей — цена ни разу не ушла под неё.
        """
        if self.broken and ZONE_DEAD_AFTER_BREAK:
            return 10_000
        if self.last_test_age >= 0:
            return self.last_test_age
        return self.event_age

    @property
    def alive(self) -> bool:
        if self.broken and ZONE_DEAD_AFTER_BREAK:
            return False
        if self.tests > 0:
            return True
        return self.event_age <= ZONE_MAX_AGE_UNTESTED

    @property
    def plateau_mult(self) -> float:
        """Множитель за выдержанное плато над зоной.

        Одиночное поглощение — заготовка. Фигуру закрывает то, что
        цена осталась выше уровня: значит принимавший победил.
        """
        if self.plateau_bars < PLATEAU_MIN_BARS:
            return PLATEAU_MULT_NONE
        if self.plateau_bars >= PLATEAU_FULL_BARS:
            return PLATEAU_MULT_FULL
        span = PLATEAU_FULL_BARS - PLATEAU_MIN_BARS
        k = (self.plateau_bars - PLATEAU_MIN_BARS) / span
        return PLATEAU_MULT_NONE + k * (PLATEAU_MULT_FULL - PLATEAU_MULT_NONE)

    def absorbed_events(self, min_tier: int = 1) -> list[Event]:
        """Поглощённые события зоны не ниже заданного тира."""
        return [
            e for e in self.events
            if e.absorbed and e.tier >= min_tier
        ]

    @property
    def confirmed(self) -> bool:
        return len(self.scales) >= 2

    def to_dict(self) -> dict:
        return {
            "price": round(self.price, 10),
            "events": len(self.events),
            "scales": sorted(self.scales),
            "confirmed": self.confirmed,
            "tier_sum": self.tier_sum,
            "absorbed_ratio": round(self.absorbed_ratio, 2),
            "buy_ratio": round(self.buy_ratio, 2),
            "freshness": self.freshness,
            "tests": self.tests,
            "plateau_bars": self.plateau_bars,
            "broken": self.broken,
        }


def build_zones(events: list[Event]) -> list[Zone]:
    """Сводит события всех масштабов в общую карту уровней.

    Зона, видимая на нескольких масштабах, реальна. Зона на одном
    масштабе остаётся в карте, но помечена неподтверждённой —
    решение о её весе принимает подкейс, а не ядро.
    """
    if not events:
        return []

    ordered = sorted(events, key=lambda e: e.price)
    zones: list[Zone] = []
    current: list[Event] = []

    for ev in ordered:
        if not current:
            current = [ev]
            continue
        base = current[0].price
        if base > 0 and abs(ev.price - base) / base <= ZONE_MATCH_PCT:
            current.append(ev)
        else:
            zones.append(_make_zone(current))
            current = [ev]
    if current:
        zones.append(_make_zone(current))

    return [z for z in zones if len(z.events) >= ZONE_MIN_EVENTS]

def annotate_zone_history(zone: Zone, base: list[Bar]) -> None:
    """Проходит дневки после события и заполняет тесты, пробой, плато.

    Тест — заход цены в окрестность зоны с последующим уходом вверх.
    Пробой — закрытие или прокол заметно ниже уровня. Плато —
    непрерывная серия баров над зоной в узком диапазоне.

    Отсчёт ведётся от КОНЦА самого позднего события зоны: пока бар
    события не закрылся, судить о том, удержался уровень или нет,
    нельзя.
    """
    if zone.price <= 0 or not zone.events:
        return

    start = max(e.day_idx for e in zone.events)
    tail = [b for b in base if b.idx > start]
    if len(tail) < 3:
        return

    touch = zone.price * (1 + ZONE_TEST_TOUCH_PCT)
    breach = zone.price * (1 - ZONE_TEST_HOLD_PCT)

    in_touch = False
    plateau_run = 0
    plateau_hi = 0.0
    plateau_lo = float("inf")
    best_plateau = 0

    for pos, b in enumerate(tail):
        if b.close <= breach or b.low <= breach:
            zone.broken = True
            plateau_run = 0
            plateau_hi, plateau_lo = 0.0, float("inf")
            in_touch = False
            continue

        # Плато: бар держится над зоной, диапазон не разъезжается.
        plateau_run += 1
        plateau_hi = max(plateau_hi, b.high)
        plateau_lo = min(plateau_lo, b.low)
        width = (plateau_hi - plateau_lo) / b.close if b.close > 0 else 1.0
        if width > PLATEAU_MAX_RANGE:
            best_plateau = max(best_plateau, plateau_run - 1)
            plateau_run = 1
            plateau_hi, plateau_lo = b.high, b.low
        else:
            best_plateau = max(best_plateau, plateau_run)

        # Тест: зашли в окрестность и вышли обратно вверх.
        if b.low <= touch:
            in_touch = True
        elif in_touch and b.close > touch:
            zone.tests += 1
            zone.last_test_age = len(tail) - 1 - pos
            in_touch = False

    zone.plateau_bars = best_plateau


def _make_zone(events: list[Event]) -> Zone:
    total = sum(e.volume for e in events)
    if total > 0:
        price = sum(e.price * e.volume for e in events) / total
    else:
        price = _median([e.price for e in events])
    return Zone(
        price=price,
        events=list(events),
        scales={e.scale for e in events},
    )


def zone_role(zone: Zone, price: float) -> str:
    """Роль зоны определяется положением цены, а не цветом событий.

    Цена выше зоны — опора: там набирали, там будут защищать.
    Цена ниже зоны — завал: там застряли, оттуда будут выходить в ноль.
    Цена внутри — неопределённость, худший момент для суждения.
    """
    if price <= 0 or zone.price <= 0:
        return "unknown"
    dist = (price - zone.price) / zone.price
    if abs(dist) <= ZONE_MATCH_PCT:
        return "inside"
    return "support" if dist > 0 else "overhead"


# ─────────────────────────────────────────────────────────────
# Контекст падения и роста
# ─────────────────────────────────────────────────────────────


@dataclass
class DropContext:
    """Что было до текущего состояния: рост, падение, поведение объёма."""

    growth_x: float = 0.0          # во сколько раз вырос перед падением
    drop_pct: float = 0.0
    bars_since_bottom: int = 0
    volume_recovery: float = 0.0   # объём после дна к объёму до него
    suspicious: bool = False       # объём рос при падающей цене
    extreme_growth: bool = False   # жёсткое вето семейства
    distrust_zones: int = 0        # сколько верхних зон обязано провалиться
    valid: bool = False

    def to_dict(self) -> dict:
        return {
            "growth_x": round(self.growth_x, 2),
            "drop_pct": round(self.drop_pct, 1),
            "bars_since_bottom": self.bars_since_bottom,
            "volume_recovery": round(self.volume_recovery, 2),
            "suspicious": self.suspicious,
            "extreme_growth": self.extreme_growth,
            "distrust_zones": self.distrust_zones,
        }


def _distrust_count(growth_x: float) -> int:
    count = 0
    for threshold, zones in GROWTH_DISTRUST:
        if growth_x >= threshold:
            count = zones
    return count


def build_drop_context(bars: list[Bar]) -> DropContext:
    """Считает контекст большого падения.

    Смотрим не глубину просадки, а поведение ПОСЛЕ дна: рост объёма
    при падающей цене — понижающий фактор, на тонких монетах это
    чаще перекладка, чем накопление.

    Если дно поставлено только что — судить рано, возвращается
    нейтральный результат. Подкейсы обязаны это уважать.
    """
    ctx = DropContext()
    if len(bars) < BOTTOM_MIN_BARS_AFTER * 2:
        return ctx

    window = bars[-BOTTOM_LOOKBACK_DAYS:] if len(bars) > BOTTOM_LOOKBACK_DAYS else bars
    n = len(window)

    peak_i = max(range(n), key=lambda i: window[i].high)
    peak = window[peak_i].high
    if peak <= 0:
        return ctx

    after = window[peak_i:]
    if len(after) < BOTTOM_MIN_BARS_AFTER:
        return ctx

    bottom_rel = min(range(len(after)), key=lambda i: after[i].low)
    bottom_i = peak_i + bottom_rel
    bottom = after[bottom_rel].low
    if bottom <= 0:
        return ctx

    ctx.drop_pct = (peak - bottom) / peak * 100
    if ctx.drop_pct < BOTTOM_MIN_DROP_PCT:
        return ctx

    # Рост до пика: от минимума на подходе к вершине.
    before = window[:peak_i] if peak_i > 0 else []
    if before:
        base = min(b.low for b in before)
        if base > 0:
            ctx.growth_x = peak / base

    ctx.extreme_growth = ctx.growth_x >= EXTREME_GROWTH_X
    ctx.distrust_zones = _distrust_count(ctx.growth_x)

    ctx.bars_since_bottom = n - 1 - bottom_i
    if ctx.bars_since_bottom < BOTTOM_MIN_BARS_AFTER:
        # Дно только что — о развороте потока судить рано.
        return ctx

    pre = window[max(0, bottom_i - 20) : bottom_i]
    post = window[bottom_i:]
    vol_pre = _median([b.quote for b in pre]) if pre else 0.0
    vol_post = _median([b.quote for b in post]) if post else 0.0
    if vol_pre > 0:
        ctx.volume_recovery = vol_post / vol_pre

    # Подозрительный случай: объём нарастает, а цена продолжает падать.
    if len(post) >= BOTTOM_MIN_BARS_AFTER:
        price_slope = _slope([b.close for b in post])
        vol_slope = _slope([b.quote for b in post])
        ctx.suspicious = price_slope < 0 and vol_slope > 0

    ctx.valid = True
    return ctx


# ─────────────────────────────────────────────────────────────
# Поток по сторонам
# ─────────────────────────────────────────────────────────────


@dataclass
class FlowStats:
    """Состояние потока за окно."""

    cum_delta: list[float] = field(default_factory=list)
    delta_slope: float = 0.0
    price_slope: float = 0.0
    homogeneity: float = 0.0
    buy_share: float = 0.5
    rel_volume: float = 1.0   # объём окна к своей норме

    @property
    def collapsing(self) -> bool:
        """Дельта валится вертикально.

        Пока идёт слив, поглощение на дне остаётся заготовкой:
        столкновение состоялось, победитель не определён.
        """
        return self.delta_slope <= DELTA_COLLAPSE_SLOPE

    def to_dict(self) -> dict:
        return {
            "delta_slope": round(self.delta_slope, 4),
            "price_slope": round(self.price_slope, 4),
            "homogeneity": round(self.homogeneity, 2),
            "buy_share": round(self.buy_share, 3),
            "collapsing": self.collapsing,
            "rel_volume": round(self.rel_volume, 2),
        }


def build_flow_stats(bars: list[Bar], window: int = DELTA_WINDOW) -> FlowStats:
    """Кумулятивная дельта и её характер.

    Дельта берётся из taker-поля напрямую — это то, что OBV пытается
    приблизить по знаку закрытия. Преимущество перед оригинальным
    индикатором: он имитирует CVD из price action, мы читаем факт.
    """
    st = FlowStats()
    tail = bars[-window:] if len(bars) > window else bars
    if len(tail) < 3:
        return st

    acc = 0.0
    for b in tail:
        acc += b.delta
        st.cum_delta.append(acc)

    st.delta_slope = _slope(st.cum_delta)
    st.price_slope = _slope([b.close for b in tail])
    st.homogeneity = homogeneity([b.delta for b in tail])

    total_q = sum(b.quote for b in tail)
    total_b = sum(b.buy_quote for b in tail)
    st.buy_share = total_b / total_q if total_q > 0 else 0.5

    # Фон: объём окна против более длинной нормы. Churn требует
    # шумного фона, spring — тихого; на этом они и расходятся.
    norm_src = bars[-window * 4 : -window] if len(bars) > window * 2 else []
    med_norm = _median([b.quote for b in norm_src]) if norm_src else 0.0
    med_tail = _median([b.quote for b in tail])
    st.rel_volume = med_tail / med_norm if med_norm > 0 else 1.0

    return st


# ─────────────────────────────────────────────────────────────
# Горизонт
# ─────────────────────────────────────────────────────────────


def pick_horizon(scales_bars: dict[int, list[Bar]]) -> tuple[int, str]:
    """Самый крупный масштаб, на котором картина ещё читается.

    Не про силу сигнала, а про то, сколько ждать. В скор не входит:
    это ярлык времени, а не аргумент за монету.
    """
    best_scale = 1
    for scale in sorted(scales_bars):
        bars = scales_bars[scale]
        if len(bars) < _min_bars(scale):
            continue
        tail = bars[-30:]
        if len(tail) < 10:
            continue
        amp = _median([b.amplitude / b.close for b in tail if b.close > 0])
        if amp >= HORIZON_MIN_AMPLITUDE / max(1, scale):
            best_scale = scale

    days = int(best_scale * HORIZON_BARS_AHEAD)
    if days <= 3:
        label = "дни"
    elif days <= 10:
        label = "неделя"
    elif days <= 25:
        label = "недели"
    else:
        label = "месяц+"
    return best_scale, label


# ─────────────────────────────────────────────────────────────
# Сборка контекста
# ─────────────────────────────────────────────────────────────


@dataclass
class FlowContext:
    """Всё, что подкейсы читают вместо собственных расчётов.

    Считается один раз на монету. Дневки приходят из RunCache,
    агрегаты строятся из них, поэтому масштабы бесплатны.
    """

    symbol: str
    price: float = 0.0
    bars: dict[int, list[Bar]] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    zones: list[Zone] = field(default_factory=list)
    drop: DropContext = field(default_factory=DropContext)
    stats: FlowStats = field(default_factory=FlowStats)
    horizon_scale: int = 1
    horizon_label: str = "дни"
    quote_volume_24h: float = 0.0
    valid: bool = False

    def zones_below(self) -> list[Zone]:
        return sorted(
            (z for z in self.zones if zone_role(z, self.price) == "support"),
            key=lambda z: -z.price,
        )

    def zones_above(self) -> list[Zone]:
        return sorted(
            (z for z in self.zones if zone_role(z, self.price) == "overhead"),
            key=lambda z: z.price,
        )

    def trusted_zones_below(self) -> list[Zone]:
        """Зоны под ценой с учётом недоверия после сильного роста.

        Чем сильнее был рост, тем больше зон обязано провалиться:
        толпа с прибылью продавливает любой уровень.
        """
        below = self.zones_below()
        skip = self.drop.distrust_zones
        return below[skip:] if skip < len(below) else []

    def zone_at(self, price: float) -> Zone | None:
        """Подтверждённая зона на заданном уровне, если есть."""
        for z in self.zones:
            if z.price > 0 and abs(price - z.price) / z.price <= ZONE_MATCH_PCT:
                return z
        return None

    def near_zone(self) -> Zone | None:
        below = self.trusted_zones_below()
        for z in below:
            if self.price > 0 and (self.price - z.price) / self.price <= ZONE_NEAR_PCT:
                return z
        return below[0] if below else None

    # ── Алиасы для подкейсов ─────────────────────────────────
    # Подкейсы читают контекст короткими именами. Держим их здесь,
    # чтобы имя поля в ядре можно было менять, не трогая пять
    # модулей семейства.

    @property
    def flow(self) -> FlowStats:
        return self.stats

    @property
    def base(self) -> list[Bar]:
        """Дневной ряд — основа всех измерений времени."""
        return self.bars.get(1, [])

    @property
    def ready(self) -> bool:
        return self.valid

    @property
    def horizon_bars(self) -> int:
        return max(1, int(self.horizon_scale * HORIZON_BARS_AHEAD))

    @property
    def growth_x(self) -> float:
        return self.drop.growth_x

    @property
    def extreme_growth_x(self) -> float:
        return EXTREME_GROWTH_X

    @property
    def distrust_zones(self) -> int:
        return self.drop.distrust_zones

    @property
    def volume_recovery(self) -> float:
        return self.drop.volume_recovery

    def to_dict(self) -> dict:
        return {
            "price": round(self.price, 10),
            "scales": sorted(self.bars),
            "events_total": len(self.events),
            "zones": [z.to_dict() for z in self.zones if z.confirmed][:6],
            "drop": self.drop.to_dict(),
            "flow": self.stats.to_dict(),
            "horizon": self.horizon_label,
        }


def build_context(symbol: str, quote_volume_24h: float = 0.0) -> FlowContext:
    """Единая точка входа семейства.

    Все потребители обязаны ходить через канонические загрузчики,
    а не запрашивать произвольные лимиты: иначе кэш разойдётся
    по ячейкам и агрегаты перестанут быть бесплатными.
    """
    ctx = FlowContext(symbol=symbol, quote_volume_24h=quote_volume_24h)

    raw = klines_1d(symbol)
    if not raw:
        return ctx

    base = _to_bars(raw)
    if len(base) < MIN_BARS_BASE:
        return ctx

    ctx.price = base[-1].close
    if ctx.price <= 0:
        return ctx

    for scale in SCALES:
        agg = aggregate(base, scale)
        if len(agg) >= _min_bars(scale):
            ctx.bars[scale] = agg

    if not ctx.bars:
        return ctx

    for scale, bars in ctx.bars.items():
        ctx.events.extend(find_events(bars, scale))

    ctx.zones = build_zones(ctx.events)
    for z in ctx.zones:
        annotate_zone_history(z, base)
    ctx.zones = [z for z in ctx.zones if z.alive]

    # Сколько живых зон лежит ниже каждой — нужно для недоверия
    # после сильного роста.
    ordered = sorted(ctx.zones, key=lambda z: z.price)
    for i, z in enumerate(ordered):
        z.zones_below = i

    ctx.drop = build_drop_context(base)
    ctx.stats = build_flow_stats(base)
    ctx.horizon_scale, ctx.horizon_label = pick_horizon(ctx.bars)
    ctx.valid = True
    return ctx
