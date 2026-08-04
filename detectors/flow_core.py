"""FLOW · ядро семейства. Вся математика, общая для подкейсов.

Зависимости: core.binance (канонические загрузчики), detectors.flow_config
(пороги), analytics.indicators (общие расчёты). Другие детекторы и общий
config здесь не используются.

Контекст считается ОДИН раз на монету и передаётся во все подкейсы:
дневки берутся из RunCache, агрегаты строятся из них, поэтому
все масштабы бесплатны после первого обращения.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from core.binance import (
    K_CLOSE,
    K_CLOSE_TIME,
    K_HIGH,
    K_LOW,
    K_OPEN,
    K_OPEN_TIME,
    K_QUOTE_VOLUME,
    K_TAKER_BUY_QUOTE,
    klines_1d,
)
from analytics.indicators import window_ratio
from detectors.flow_config import (
    BOTTOM_LOOKBACK_DAYS,
    BOTTOM_LOOKBACK_DAYS,
    BOTTOM_MIN_BARS_AFTER,
    BOTTOM_MIN_DROP_PCT,
    DELTA_COLLAPSE_SLOPE,
    DELTA_WINDOW,
    EVENT_NORM_WINDOW,
    HORIZON_BARS_AHEAD,
    HORIZON_AMP_GAIN,
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
    PLATEAU_MULT_NONE_SOFT,
    RESPONSE_BARS,
    RESPONSE_FLAT_ATR,
    SCALES,
    TIER_1_SIGMA,
    TIER_2_SIGMA,
    TIER_3_SIGMA,
    VORTEX_PERIOD,
    VORTEX_EXTREMA_GAP,
    VORTEX_DELTA_GAIN,
    VORTEX_MIN_EXTREMA,
    VORTEX_MAX_EXTREMA,
    VORTEX_MULT_GAIN,
    VORTEX_PROMINENCE,
    VORTEX_MIN_TAIL,
    ZONE_BREAK_BARS,
    ZONE_BREAK_DEEP_PCT,
    ZONE_CONFIRM_SCALES,
    ZONE_DEAD_AFTER_BREAK,
    ZONE_MATCH_PCT,
    ZONE_MAX_AGE_UNTESTED,
    ZONE_MIN_EVENTS,
    ZONE_NEAR_PCT,
    ZONE_TEST_HOLD_PCT,
    ZONE_TEST_TOUCH_PCT,
)


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

def _slope_of_flow(cum: list[float], scale: float) -> float:
    """Наклон кумулятивного ряда, нормированный на внешний масштаб.

    Отдельная функция, а не параметр к _slope, и это принципиально.
    Обычный ряд нормируется на собственный средний уровень: для цены
    это верно, она положительна и её среднее задаёт естественный
    масштаб. Для кумулятивной дельты — неверно в принципе.

    Кумулятивная дельта пересекает ноль постоянно: сегодня набрали,
    завтра раздали. Средний уровень такого ряда — величина случайная
    и близкая к нулю, деление на неё даёт произвольно большие числа
    любого знака. Прогон это показал прямо: `collapsing` стоял у 36
    молчащих монет из 48, то есть у трёх четвертей рынка, включая
    те, где дельта росла.

    Масштабом обязан быть оборот: тогда величина читается как доля
    дневного оборота, на которую поток смещается за бар. Это
    сравнимо между монетами и устойчиво во времени.
    """
    n = len(cum)
    if n < 3 or scale <= 0:
        return 0.0

    mean_x = (n - 1) / 2.0
    mean_y = sum(cum) / n

    num = 0.0
    den = 0.0
    for i, y in enumerate(cum):
        dx = i - mean_x
        num += dx * (y - mean_y)
        den += dx * dx

    if den <= 0:
        return 0.0

    return (num / den) / scale


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

    1 — все бары вложились одинаково, 0 — весь сдвиг сделан одним
    баром. Считается через долю максимального вклада: скрытый набор
    по определению размазан, одиночный вброс скрытым не является.
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
    fill: float = 1.0       # доля набранного времени бара

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
    """Разбирает свечи Binance в бары с разложенным потоком.

    Заполнение последнего бара считается ПО ВРЕМЕНИ, а не по факту
    его наличия в ряду. Это единственный источник fill во всём
    семействе: агрегаты его наследуют, событийная логика на него
    опирается, и если он всегда равен единице — вся ветка
    PARTIAL_BAR_* становится мёртвым кодом, внешне неотличимым от
    рабочего.

    Ровно это и происходило: fill выставлялся безусловной единицей,
    а в aggregate вычислялся как len(chunk) / scale — величина,
    равная единице по построению, потому что остаток от деления
    собирается в головной бар. Незакрытый бар правого края
    сравнивался с нормой по полным барам как равный ей.

    Проявляется расхождением между масштабами в один момент
    времени: 3D показывал 52.66 B при 2283% RVOL, 4D в ту же
    секунду — 7.44 B при 276%. Более длинный бар с меньшим
    объёмом невозможен; различалась только стадия заполнения.
    """
    now_ms = time.time() * 1000.0
    out: list[Bar] = []
    for i, k in enumerate(raw):
        try:
            quote = float(k[K_QUOTE_VOLUME])
            buy = float(k[K_TAKER_BUY_QUOTE])
            o = float(k[K_OPEN])
            h = float(k[K_HIGH])
            lo = float(k[K_LOW])
            c = float(k[K_CLOSE])
            t_open = float(k[K_OPEN_TIME])
            t_close = float(k[K_CLOSE_TIME])
        except (TypeError, ValueError, IndexError):
            continue
        if c <= 0 or quote <= 0:
            continue

        # Закрытая свеча — полная по определению. Незакрытая
        # набрана ровно настолько, сколько прошло её времени.
        span = t_close - t_open
        if span > 0 and now_ms < t_close:
            fill = max(0.0, min(1.0, (now_ms - t_open) / span))
        else:
            fill = 1.0

        out.append(
            Bar(
                idx=i,
                open=o,
                high=h,
                low=lo,
                close=c,
                quote=quote,
                buy_quote=min(buy, quote),
                fill=fill,
            )
        )
    return out


def aggregate(bars: list[Bar], scale: int) -> list[Bar]:
    """Склеивает дневки в бары нужного масштаба.

    Порог аномалии строится от нормы объёма ВНУТРИ бара. Накопление,
    размазанное по десяти дням порциями ниже порога, на дневке не
    даёт ни одного события — а в десятидневном баре складывается в
    одно крупное. Крупный масштаб не показывает другое, он суммирует
    то, что тонуло в шуме.

    Хвост НЕ обрезается: последний бар может быть неполным, но он
    несёт самые свежие события. Вместо этого он помечается долей
    заполнения, а сигма считается по приведённому объёму.

    Заполнение бара НЕ равно доле присутствующих дневок. Оно равно
    средней доле их заполнения: последняя дневка сама может быть
    незакрытой, и на крупном масштабе это единственный источник
    неполноты — все предыдущие группы содержат ровно scale
    элементов, потому что остаток ушёл в головной бар.
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
                # Сумма долей, а не количество баров. Прежнее
                # len(head) / scale давало верный результат только
                # здесь — по случайности, потому что головной бар
                # действительно укорочен. Для всех остальных групп
                # оно возвращало единицу по построению.
                fill=sum(b.fill for b in head) / scale,
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
                # Правый край: k−1 закрытых дневок плюс текущая
                # своей долей. Именно здесь величина перестаёт быть
                # единицей — и именно здесь она нужна.
                fill=sum(b.fill for b in chunk) / scale,
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
    bar_idx: int        # позиция в ряду своего масштаба
    day_idx: int        # позиция конца бара в дневном ряду
    age: int            # сколько баров назад от правого края
    price: float        # уровень события
    side: str           # "buy" | "sell"
    sigma: float
    tier: int
    volume: float
    response: float     # движение цены после события, доли
    absorbed: bool      # масса приложена, цена не сдвинулась
    immature: bool      # окно отклика ещё не прошло

    @property
    def age_days(self) -> int:
        """Давность события в ДНЯХ.

        Единственная величина, пригодная для сравнения между масштабами.
        `age` меряется в барах своего ряда: на 10D значение 20 означает
        двести дней, а не двадцать. Ровно это и сравнивалось с дневными
        окнами подкейсов — spring с окном 24 принимал за свежее событие
        полугодовой давности.
        """
        return self.age * max(1, self.scale)

    def to_dict(self) -> dict:
        return {
            "scale": self.scale,
            "age": self.age,
            "age_days": self.age_days,
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


def vortex(bars: list[Bar], period: int = VORTEX_PERIOD) -> tuple[float, float]:
    """Классический Vortex: VI+ и VI- за период.

    VI+ строится на движении вверх от минимума предыдущего бара,
    VI- — на движении вниз от максимума. В плоской базе оба должны
    быть около единицы: направленного движения нет, есть работа.
    """
    if len(bars) < period + 1:
        return 0.0, 0.0

    tail = bars[-(period + 1):]
    vm_plus = 0.0
    vm_minus = 0.0
    tr_sum = 0.0

    for prev, cur in zip(tail, tail[1:]):
        vm_plus += abs(cur.high - prev.low)
        vm_minus += abs(cur.low - prev.high)
        tr_sum += max(
            cur.high - cur.low,
            abs(cur.high - prev.close),
            abs(cur.low - prev.close),
        )

    if tr_sum <= 0:
        return 0.0, 0.0
    return vm_plus / tr_sum, vm_minus / tr_sum


# ─────────────────────────────────────────────────────────────
# Зоны
# ─────────────────────────────────────────────────────────────

@dataclass
class Zone:
    """Кластер событий на одном ценовом уровне."""

    price: float                    # средневзвешенный по объёму центр
    events: list[Event] = field(default_factory=list)
    scales: set[int] = field(default_factory=set)

    # История уровня после события. Заполняется annotate_zone_history.
    tests: int = 0                  # успешных тестов уровня
    last_test_age: int = -1         # давность последнего теста, в днях
    broken: bool = False            # цена ушла под зону и осталась
    plateau_bars: int = 0           # длина плато над зоной, в днях
    zones_below: int = 0            # сколько живых зон ниже этой

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
        """Давность самого свежего события зоны, в днях."""
        if not self.events:
            return 10_000
        return min(e.age_days for e in self.events)

    @property
    def freshness(self) -> int:
        """Рабочая давность зоны.

        Событие стареет, зона — нет: она живёт, пока цена её не
        пробила. Каждый успешный тест обнуляет возраст. На KOMA между
        событием и выносом прошло ~200 дней, и всё это время зона
        была рабочей — цена ни разу не ушла под неё.
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

    def plateau_mult(self, soft: bool = False) -> float:
        """Множитель за выдержанное плато над зоной.

        Для churn плато обязательно: одиночное поглощение говорит
        «здесь столкнулись», но не говорит, кто победил, и победителя
        определяет то, что происходит потом.

        Для spring — нет. Там фигура это само сжатие, а долгое
        стояние над уровнем скорее признак затухания. Прогон показал
        цену прежнего единообразия: из семи ненулевых churn полный
        множитель не взял никто, spring дал два значения на рынок.
        """
        floor = PLATEAU_MULT_NONE_SOFT if soft else PLATEAU_MULT_NONE

        if self.plateau_bars < PLATEAU_MIN_BARS:
            return floor
        if self.plateau_bars >= PLATEAU_FULL_BARS:
            return PLATEAU_MULT_FULL

        span = PLATEAU_FULL_BARS - PLATEAU_MIN_BARS
        k = (self.plateau_bars - PLATEAU_MIN_BARS) / span
        return floor + k * (PLATEAU_MULT_FULL - floor)

    def absorbed_events(self, min_tier: int = 1) -> list[Event]:
        """Поглощённые события зоны не ниже заданного тира."""
        return [e for e in self.events if e.absorbed and e.tier >= min_tier]

    @property
    def confirmed(self) -> bool:
        return len(self.scales) >= ZONE_CONFIRM_SCALES

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
    масштабе остаётся в карте, но помечена неподтверждённой — решение
    о её весе принимает подкейс, а не ядро.
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

    Пробой [MMT] — цена ушла под уровень и ОСТАЛАСЬ там. Раньше он
    ставился по первому же проколу тенью, и это убивало длинные базы:
    за семь месяцев стояния под уровень заходят обязательно, зона
    умирала в первый месяц, монета выпадала из семейства целиком —
    ни churn, ни spring не собирались, потому что зон не оставалось.
    Тень под уровнем в базе это тест за ликвидностью, а не пробой,
    поэтому считаем по закрытиям и требуем серии подряд.

    Плато — непрерывная серия баров над зоной в узком диапазоне.

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
    deep = zone.price * (1 - ZONE_BREAK_DEEP_PCT)

    in_touch = False
    below_run = 0
    plateau_run = 0
    plateau_hi = 0.0
    plateau_lo = float("inf")
    best_plateau = 0

    for pos, b in enumerate(tail):
        # ── Пробой ─────────────────────────────────────────
        if b.close <= deep:
            # Ушли глубоко — подтверждения ждать незачем.
            zone.broken = True
            break

        if b.close <= breach:
            below_run += 1
            if below_run >= ZONE_BREAK_BARS:
                zone.broken = True
                break
            # Заход под уровень не сбрасывает историю: пока серия не
            # набралась, это ещё тест, а не смерть зоны.
            plateau_run = 0
            plateau_hi, plateau_lo = 0.0, float("inf")
            continue

        below_run = 0

        # ── Плато ──────────────────────────────────────────
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

        # ── Тест ───────────────────────────────────────────
        # Зашли в окрестность и вышли обратно вверх.
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

    growth_x: float = 0.0        # справка; решений по ней не принимается
    peak_age_days: int = 0       # давность пика — без неё growth_x нечитаем
    drop_pct: float = 0.0
    bars_since_bottom: int = 0
    volume_recovery: float = 0.0
    suspicious: bool = False     # пометка в срезе, множителей не режет
    valid: bool = False

    def to_dict(self) -> dict:
        return {
            "growth_x": round(self.growth_x, 2),
            "peak_age_days": self.peak_age_days,
            "drop_pct": round(self.drop_pct, 1),
            "bars_since_bottom": self.bars_since_bottom,
            "volume_recovery": round(self.volume_recovery, 2),
            "suspicious": self.suspicious,
        }


def build_drop_context(bars: list[Bar]) -> DropContext:
    """Считает контекст большого падения.

    Смотрим не глубину просадки, а поведение ПОСЛЕ дна: рост объёма
    при падающей цене — понижающий фактор, на тонких монетах это чаще
    перекладка, чем накопление.

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

    # Рост до пика считается ВСЕГДА и раньше всего остального. Ему не
    # нужны ни дно, ни падение: величина меряется от базы до вершины.
    #
    # Рядом обязательно считается ДАВНОСТЬ пика. Без неё growth_x
    # нечитаем: рост в сорок раз за неделю после листинга и рост в
    # сорок раз за год — разные вещи, а число одинаковое. Толпа с
    # убытком существует только пока она свежая; тот, кто держит
    # минус девяносто процентов полгода, может держать его годами и
    # предложением уже не является.
    before = window[:peak_i]
    if before:
        base_low = min(b.low for b in before)
        if base_low > 0:
            ctx.growth_x = peak / base_low
    ctx.peak_age_days = n - 1 - peak_i

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
    rel_volume: float = 1.0     # объём окна к своей норме

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

    # Масштаб — средний оборот бара в окне. Нормировать кумулятивную
    # дельту на её собственный уровень нельзя: он проходит через
    # ноль, и результат теряет смысл.
    avg_quote = sum(b.quote for b in tail) / len(tail) if tail else 0.0
    st.delta_slope = _slope_of_flow(st.cum_delta, avg_quote)
    st.price_slope = _slope([b.close for b in tail])
    st.homogeneity = homogeneity([b.delta for b in tail])

    total_q = sum(b.quote for b in tail)
    total_b = sum(b.buy_quote for b in tail)
    st.buy_share = total_b / total_q if total_q > 0 else 0.5

    # Фон: медиана окна против более длинной нормы. Считается той же
    # функцией, что и колонка отчёта, — иначе величины расходятся, и
    # какая из них врёт, выясняется только сравнением вручную.
    #
    # Хвост тоже нормируется по fill. Прежде медиана окна считалась
    # по сырому объёму, и незакрытый правый край её занижал: фон
    # выглядел тише, чем есть, ровно в момент свежей активности.
    st.rel_volume = window_ratio(
        [b.quote for b in bars],
        [b.fill for b in bars],
        window=window,
        norm_span=window * 3,
    )

    return st


# ─────────────────────────────────────────────────────────────
# Горизонт
# ─────────────────────────────────────────────────────────────

def pick_horizon(scales_bars: dict[int, list[Bar]]) -> tuple[int, str]:
    """Самый крупный масштаб, на котором картина ещё читается.

    Не про силу сигнала, а про то, сколько ждать. В скор не входит:
    это ярлык времени, а не аргумент за монету.

    Прежнее условие сравнивало амплитуду агрегата с константой,
    делённой на масштаб. Обе величины шли навстречу: амплитуда
    крупного бара больше по построению, а порог для него меньше.
    Условие выполнялось почти всегда на максимальном доступном
    масштабе, и горизонт различал не монеты, а длину их истории —
    у 24 сработавших монет из 31 он равнялся 25 дням.

    Здесь масштаб засчитывается, только если даёт существенный
    прирост амплитуды против дневки той же монеты. Случайное
    блуждание расширяет бар как корень масштаба; прирост в
    пределах этого не проявляет ничего.
    """
    base = scales_bars.get(1) or []
    if len(base) < 10:
        return 1, "дни"

    base_amp = _median(
        [b.amplitude / b.close for b in base[-30:] if b.close > 0]
    )
    if base_amp <= 0:
        return 1, "дни"

    best_scale = 1
    for scale in sorted(scales_bars):
        if scale <= 1:
            continue
        bars = scales_bars[scale]
        if len(bars) < _min_bars(scale):
            continue
        tail = bars[-30:]
        if len(tail) < 10:
            continue
        amp = _median([b.amplitude / b.close for b in tail if b.close > 0])
        if amp >= base_amp * math.sqrt(scale) * HORIZON_AMP_GAIN:
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
# Вортекс по форме кривых
# ─────────────────────────────────────────────────────────────
# Мгновенный спред VI+ и VI- не работает. VORTEX_SPREAD_MIN = 0.25
# при наблюдаемом разбросе 0.01–0.04 давал один diverging на 145
# монет: ветка присутствовала в пяти модулях из шести и не
# исполнялась ни в одном. На ZEREBRO, где разворот виден глазами,
# спред равен 0.09 — старое условие не увидело бы и его.
#
# Читается не значение, а ПОВЕДЕНИЕ. Каждый следующий пик VI- ниже
# предыдущего — продавец слабеет, предложение конечно. Каждый
# следующий лой VI+ выше предыдущего — покупатель крепнет. Величина
# накопительная и большого расхождения линий не требует вовсе:
# на ZEREBRO пик продаж под 2.0 больше не повторился, а линии при
# этом сошлись почти вплотную.
#
# Нет различимых пиков — молчим. Отсекать монету за невнятную
# картинку нельзя: вторым фильтром служит стратегия. На OP пики
# продаж идут вровень и последний даже выше — ждать там снижения
# бессмысленно, а движения тем временем проходят мимо.


# ─────────────────────────────────────────────────────────────
# Вортекс по форме кривых
# ─────────────────────────────────────────────────────────────
# Мгновенный спред VI+ и VI- не работает. VORTEX_SPREAD_MIN = 0.25
# при наблюдаемом разбросе 0.01–0.04 давал один diverging на 145
# монет: ветка присутствовала в пяти модулях из шести и не
# исполнялась ни в одном. На ZEREBRO, где разворот виден глазами,
# спред равен 0.09 — старое условие не увидело бы и его.
#
# Читается не значение, а ПОВЕДЕНИЕ. Каждый следующий пик VI- ниже
# предыдущего — продавец слабеет, предложение конечно. Каждый
# следующий лой VI+ выше предыдущего — покупатель крепнет. Величина
# накопительная и большого расхождения линий не требует вовсе:
# на ZEREBRO пик продаж под 2.0 больше не повторился, а линии при
# этом сошлись почти вплотную.
#
# Нет различимых пиков — молчим. Отсекать монету за невнятную
# картинку нельзя: вторым фильтром служит стратегия. На OP пики
# продаж идут вровень и последний даже выше — ждать там снижения
# бессмысленно, а движения тем временем проходят мимо.


def _local_extrema(
    values: list[float],
    kind: str,
    gap: int = VORTEX_EXTREMA_GAP,
    prominence: float = VORTEX_PROMINENCE,
) -> list[tuple[int, float]]:
    """Локальные экстремумы с минимальным разносом и порогом выраженности.

    prominence отсекает зубцы. Без него на любой кривой находятся
    десятки экстремумов, и сравнение последнего с предыдущим
    вырождается в сравнение двух случайных значений.
    """
    n = len(values)
    if n < gap * 2 + 1:
        return []

    found: list[tuple[int, float]] = []
    for i in range(gap, n - gap):
        win = values[i - gap : i + gap + 1]
        v = values[i]
        if kind == "high" and v >= max(win) and v - min(win) >= prominence:
            found.append((i, v))
        elif kind == "low" and v <= min(win) and max(win) - v >= prominence:
            found.append((i, v))

    # Схлопываем соседей на одном плато: широкая вершина иначе даёт
    # серию одинаковых пиков, и последний сравнивается сам с собой.
    merged: list[tuple[int, float]] = []
    for idx, val in found:
        if merged and idx - merged[-1][0] <= gap:
            better = val > merged[-1][1] if kind == "high" else val < merged[-1][1]
            if better:
                merged[-1] = (idx, val)
        else:
            merged.append((idx, val))
    return merged


def vortex_series(
    bars: list[Bar], period: int = VORTEX_PERIOD
) -> tuple[list[float], list[float]]:
    """Полные ряды VI+ и VI-.

    Прежняя vortex() возвращала одну точку — последнюю. Форму по
    одной точке не прочитать, поэтому нужен ряд.
    """
    n = len(bars)
    if n < period + 2:
        return [], []

    vm_p: list[float] = []
    vm_m: list[float] = []
    tr: list[float] = []
    for prev, cur in zip(bars, bars[1:]):
        vm_p.append(abs(cur.high - prev.low))
        vm_m.append(abs(cur.low - prev.high))
        tr.append(
            max(
                cur.high - cur.low,
                abs(cur.high - prev.close),
                abs(cur.low - prev.close),
            )
        )

    vi_p: list[float] = []
    vi_m: list[float] = []
    for i in range(period, len(tr) + 1):
        s_tr = sum(tr[i - period : i])
        if s_tr <= 0:
            continue
        vi_p.append(sum(vm_p[i - period : i]) / s_tr)
        vi_m.append(sum(vm_m[i - period : i]) / s_tr)
    return vi_p, vi_m


@dataclass
class VortexState:
    """Направление, прочитанное по форме VI."""

    scale: int = 0
    direction: str = "none"   # up | down | none
    strength: float = 0.0     # выраженность последнего сдвига, 0..1
    confidence: float = 0.0   # 0.5 — согласна одна линия, 1.0 — обе
    sell_peaks: int = 0
    buy_lows: int = 0
    vi_plus: float = 0.0      # последние значения, для отчёта
    vi_minus: float = 0.0

    def mult(self, gain: float = VORTEX_MULT_GAIN) -> float:
        """Множитель взамен прежнего `1 + spread * gain`.

        gain задаёт модуль: для hidden вортекс весит больше, чем для
        churn. Там это второй опережающий признак рядом с дельтой,
        здесь — ответ на вопрос «кто победил в столкновении».

        Молчание даёт ровно единицу: не усиливает и не ослабляет.
        """
        if self.direction == "none":
            return 1.0
        k = self.strength * self.confidence * gain
        return 1.0 + k if self.direction == "up" else max(0.0, 1.0 - k)

    def to_dict(self) -> dict:
        return {
            "scale": self.scale,
            "direction": self.direction,
            "strength": round(self.strength, 3),
            "confidence": round(self.confidence, 2),
            "sell_peaks": self.sell_peaks,
            "buy_lows": self.buy_lows,
            "vi_plus": round(self.vi_plus, 4),
            "vi_minus": round(self.vi_minus, 4),
            "mult": round(self.mult(), 3),
        }


def read_vortex(bars: list[Bar], scale: int) -> VortexState:
    """Направление по последним двум экстремумам каждой линии."""
    vi_p, vi_m = vortex_series(bars)
    if not vi_p or not vi_m:
        return VortexState(scale=scale)

    peaks = _local_extrema(vi_m, "high")   # пики продаж
    lows = _local_extrema(vi_p, "low")     # лои покупок

    st = VortexState(
        scale=scale,
        sell_peaks=len(peaks),
        buy_lows=len(lows),
        vi_plus=vi_p[-1],
        vi_minus=vi_m[-1],
    )

    votes: list[bool] = []
    deltas: list[float] = []

    if len(peaks) >= 2:
        prev, last = peaks[-2][1], peaks[-1][1]
        votes.append(last < prev)          # пик продаж ниже — вверх
        deltas.append(abs(last - prev) / max(prev, 1e-9))

    if len(lows) >= 2:
        prev, last = lows[-2][1], lows[-1][1]
        votes.append(last > prev)          # лой покупок выше — вверх
        deltas.append(abs(last - prev) / max(prev, 1e-9))

    if not votes:
        return st                          # пиков нет — молчим

    if all(votes):
        st.direction = "up"
    elif not any(votes):
        st.direction = "down"
    else:
        # Линии расходятся во мнении. Это не сигнал, а его
        # отсутствие: объявлять направление по одной против другой
        # значит выдумывать уверенность.
        return st

    st.confidence = 1.0 if len(votes) == 2 else 0.5
    st.strength = min(1.0, (sum(deltas) / len(deltas)) * VORTEX_DELTA_GAIN)
    return st


def build_vortex(scales_bars: dict[int, list[Bar]]) -> VortexState:
    """Масштаб — регулятор громкости шума, больше ничего.

    Берём самый мелкий масштаб, на котором пики уже различимы и их
    не слишком много. На мелком линии сливаются в кашу — COTI на 1D
    даёт сплошную сетку, на старшем те же данные расходятся и бугры
    читаются. На слишком крупном экстремумов остаётся один-два и
    сравнивать нечего.

    Верхнего предела нет. Читаемость важнее свежести масштаба: если
    структура проступила только на 10D, работаем с 10D.

    Требование плоской цены снято. Прежнее `if not flat: continue`
    отбрасывало масштаб, где цена уже пошла, — то есть ровно те
    случаи, ради которых признак и заводился.
    """
    fallback: VortexState | None = None

    for scale in sorted(scales_bars):
        bars = scales_bars[scale]
        if len(bars) < VORTEX_PERIOD + VORTEX_MIN_TAIL:
            continue

        st = read_vortex(bars, scale)
        if st.direction == "none":
            continue

        k = st.sell_peaks + st.buy_lows
        if VORTEX_MIN_EXTREMA <= k <= VORTEX_MAX_EXTREMA:
            return st
        if fallback is None:
            fallback = st

    return fallback or VortexState()


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
    vortex: VortexState = field(default_factory=VortexState)
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
        """Зона на заданном уровне, если есть."""
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
    def distrust_zones(self) -> int:
        """Сколько верхних опор считать ненадёжными.

        Раньше считалось от growth_x по шкале GROWTH_DISTRUST — то
        есть от того же числа, что стояло за снятым вето, и с той же
        подменой смысла. Держать две конструкции об одном не нужно.

        Теперь читается по форме вортекса: растущие пики продаж
        означают, что предложение не исчерпано, и ближние опоры под
        ценой ещё будут проверены сливом. Молчание вортекса даёт
        нуль — недоверие требует оснований, а не их отсутствия.
        """
        v = self.vortex
        if v.direction != "down":
            return 0
        return 2 if v.confidence >= 1.0 else 1

    @property
    def volume_recovery(self) -> float:
        return self.drop.volume_recovery

    def to_dict(self) -> dict:
        # Зоны отдаются ПОЛНОСТЬЮ, без фильтра по confirmed и без
        # среза. Прежний вариант — `if z.confirmed][:6]` — показывал
        # не ту карту, по которой работают подкейсы, и диагностика
        # получалась ложной: MU выглядела как монета без зон вообще,
        # хотя fuel насчитал на ней три снятых уровня, а churn нашёл
        # плато в 22 дня. Её зоны держатся на одном масштабе — для
        # модулей это законный материал, для сериализации они
        # исчезали.
        #
        # Признак confirmed остаётся внутри каждой зоны — фильтровать
        # по нему должен читатель среза, а не сам срез.
        #
        # fills — состояние ИЗМЕРИТЕЛЯ, а не рынка. Доля набранного
        # времени правого края по каждому масштабу. Поле выглядит
        # служебным, но именно его отсутствие держало мёртвой всю
        # ветку PARTIAL_BAR_*: fill был равен единице всегда, объём
        # незакрытого бара сравнивался с полной нормой как равный, и
        # система об этом сообщить не могла — она не показывала
        # величину, от которой зависела. Расхождение нашлось только
        # сравнением RVOL на пяти масштабах вручную.
        #
        # Правило: срез обязан показывать не только результат
        # измерения, но и состояние того, чем меряли.
        return {
            "price": round(self.price, 10),
            "scales": sorted(self.bars),
            "fills": {
                scale: round(bars[-1].fill, 3)
                for scale, bars in sorted(self.bars.items())
                if bars
            },
            "events_total": len(self.events),
            "zones": [z.to_dict() for z in self.zones],
            "zones_confirmed": sum(1 for z in self.zones if z.confirmed),
            "drop": self.drop.to_dict(),
            "flow": self.stats.to_dict(),
            "vortex": self.vortex.to_dict(),
            "horizon": self.horizon_label,
        }


def build_context(symbol: str, quote_volume_24h: float = 0.0) -> FlowContext:
    """Единая точка входа семейства.

    Все потребители обязаны ходить через канонические загрузчики,
    а не запрашивать произвольные лимиты: иначе кэш разойдётся по
    ячейкам и агрегаты перестанут быть бесплатными.
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

    ctx.vortex = build_vortex(ctx.bars)
    ctx.drop = build_drop_context(base)
    ctx.stats = build_flow_stats(base)
    ctx.horizon_scale, ctx.horizon_label = pick_horizon(ctx.bars)
    ctx.valid = True
    return ctx
