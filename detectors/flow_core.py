"""Общие примитивы семейства FLOW.

Импортируется ТОЛЬКО модулями flow_*. Детекторы taiko, dexe,
volume_surge и buzz остаются полностью независимыми и считают своё.

Три группы примитивов:
  1. Агрегация таймфреймов из дневных свечей — без сетевых запросов.
  2. Разделение потока на стороны по реальным taker-данным.
  3. События агрессии: z-оценка от EMA, три тира по образцу
     Market Order Bubbles.
"""

from __future__ import annotations

import math

from dataclasses import dataclass

from core.binance import (
    K_CLOSE, K_CLOSE_TIME, K_HIGH, K_LOW, K_OPEN, K_OPEN_TIME,
    K_QUOTE_VOLUME,
)

# Индекс takerBuyQuoteVolume в свече Binance.
# В core.binance константа не объявлена — держим здесь, чтобы
# не трогать общий модуль ради одного семейства.
K_TAKER_BUY_QUOTE = 10

NEUTRAL_RATIO = 0.5

# Тело незакрытого бара как доля обычного дневного хода.
# Ниже этого — движения нет, объём поглощён внутри дня.
INTRABAR_FLAT_RATIO = 0.6

# Тиры события по образцу индикатора: 1σ / 2σ / 3σ над EMA
TIER_SIGMAS = (1.0, 2.0, 3.0)


# ─────────────────────────────────────────────────────────────
# Базовая математика
# ─────────────────────────────────────────────────────────────
def mean(seq) -> float:
    seq = list(seq)
    return sum(seq) / len(seq) if seq else 0.0


def median(seq) -> float:
    s = sorted(seq)
    n = len(s)
    if not n:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def stdev(seq) -> float:
    """Выборочное стандартное отклонение.

    Оставлено как общий примитив. В detect_events не используется:
    на молодых монетах даёт сотни сигм, см. robust_sigma.
    """
    s = list(seq)
    n = len(s)
    if n < 2:
        return 0.0
    m = sum(s) / n
    var = sum((x - m) ** 2 for x in s) / (n - 1)
    return var ** 0.5


def robust_sigma(vols: list[float]) -> float:
    """Разброс через медианное абсолютное отклонение.

    Обычное stdev на молодых монетах схлопывается: первые бары
    после листинга почти пустые, разброс около нуля, и любое
    нормальное событие даёт сотни сигм. MAD устойчив к этому.

    Коэффициент 1.4826 приводит MAD к масштабу стандартного
    отклонения нормального распределения — чтобы пороги в сигмах
    остались привычными.
    """
    if len(vols) < 5:
        return 0.0
    med = median(vols)
    mad = median([abs(v - med) for v in vols])
    return mad * 1.4826 if mad > 0 else 0.0


def ema_series(seq: list[float], period: int) -> list[float]:
    """Экспоненциальная скользящая, выровненная по длине входа.

    Первое значение — простое среднее первого окна, дальше рекуррентно.
    """
    n = len(seq)
    out = [0.0] * n
    if n == 0 or period < 1:
        return out
    if n < period:
        acc = 0.0
        for i, v in enumerate(seq):
            acc += v
            out[i] = acc / (i + 1)
        return out

    k = 2.0 / (period + 1)
    seed = sum(seq[:period]) / period
    for i in range(period):
        out[i] = seed
    prev = seed
    for i in range(period, n):
        prev = seq[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def slope(seq: list[float]) -> float:
    """Наклон линейной регрессии на единицу индекса.

    Отличает нарастающую серию от одиночного выброса: один крупный
    бар наклон почти не двигает, последовательность — двигает.
    """
    n = len(seq)
    if n < 3:
        return 0.0
    xm = (n - 1) / 2
    ym = sum(seq) / n
    num = sum((i - xm) * (seq[i] - ym) for i in range(n))
    den = sum((i - xm) ** 2 for i in range(n))
    return num / den if den > 0 else 0.0


def pct_change(a: float, b: float) -> float:
    """Изменение от a к b в процентах. Ноль при нулевой базе."""
    return (b / a - 1) * 100 if a > 0 else 0.0

def _atr_at(kl: list, idx: int, period: int = 30) -> float:
    """Средний истинный диапазон на позиции idx, в долях цены."""
    lo = max(1, idx - period)
    if idx <= lo:
        return 0.0
    trs = []
    for i in range(lo, idx):
        try:
            h, l = float(kl[i][K_HIGH]), float(kl[i][K_LOW])
            pc = float(kl[i - 1][K_CLOSE])
        except (TypeError, ValueError, IndexError):
            continue
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    try:
        price = float(kl[idx][K_CLOSE])
    except (TypeError, ValueError, IndexError):
        return 0.0
    return (mean(trs) / price * 100) if price > 0 else 0.0


def response_threshold(kl: list, idx: int, bars: int, atr_mult: float = 1.2) -> float:
    """Порог «цена не сдвинулась», нормированный на волатильность монеты.

    Фиксированные проценты не работают: для монеты с дневным ходом
    в один процент движение на восемь — это выстрел, а для монеты
    с ходом в четырнадцать — обычный вторник. Отклик сравнивается
    с тем, что нормально ДЛЯ НЕЁ.

    Корень из числа баров — потому что случайное блуждание
    накапливает размах пропорционально корню из времени.
    """
    atr_pct = _atr_at(kl, idx, period=30)
    return max(atr_pct * atr_mult * (bars ** 0.5), 3.0)

def intrabar_absorption(kl: list, idx: int) -> tuple[float, bool]:
    """Поглощение ВНУТРИ бара: тело свечи против нормальной амплитуды.

    Нужна для незакрытого бара, где отклика по следующим дням ещё
    нет по построению. Если объём аномален, а тело свечи заметно
    меньше обычного дневного хода — массу приняли здесь же,
    не сдвинув цену. Ждать закрытия, чтобы это увидеть, незачем:
    само отсутствие движения при экстремальном объёме уже факт.

    Возвращает (тело в долях ATR, признак поглощения).
    """
    try:
        o = float(kl[idx][K_OPEN])
        c = float(kl[idx][K_CLOSE])
    except (TypeError, ValueError, IndexError):
        return 0.0, False
    if o <= 0:
        return 0.0, False

    body_pct = abs(c / o - 1) * 100
    atr_pct = _atr_at(kl, idx, period=30)
    if atr_pct <= 0:
        return 0.0, False

    ratio = body_pct / atr_pct
    return ratio, ratio <= INTRABAR_FLAT_RATIO

# ─────────────────────────────────────────────────────────────
# Агрегация таймфреймов из дневных свечей
# ─────────────────────────────────────────────────────────────
def aggregate(kl: list, days: int) -> list[list]:
    """Склеивает дневные свечи в N-дневные без сетевых запросов.

    Выравнивание по ПОСЛЕДНЕМУ ЗАКРЫТОМУ дню: группы набираются
    с конца, поэтому свежий бар всегда актуален. Историческая
    граница при этом не совпадает с сеткой TradingView — принято
    сознательно, нам важна свежесть правого края.

    Неполный остаток слева отбрасывается: бар из трёх дней вместо
    десяти исказит и диапазон, и объём.
    """
    if days <= 1:
        return list(kl)
    if not kl or len(kl) < days:
        return []

    out: list[list] = []
    n = len(kl)
    start = n % days
    for i in range(start, n, days):
        chunk = kl[i:i + days]
        if len(chunk) < days:
            break
        try:
            o = float(chunk[0][K_OPEN])
            c = float(chunk[-1][K_CLOSE])
            h = max(float(x[K_HIGH]) for x in chunk)
            l = min(float(x[K_LOW]) for x in chunk)
            q = sum(float(x[K_QUOTE_VOLUME]) for x in chunk)
            tb = sum(_taker_buy(x) for x in chunk)
            t_open = chunk[0][K_OPEN_TIME]
            t_close = chunk[-1][K_CLOSE_TIME]
        except (TypeError, ValueError, IndexError):
            continue

        # Позиции 5, 8, 9 не используются семейством — заполняем нулями
        out.append([t_open, o, h, l, c, 0.0, t_close, q, 0, 0, tb, 0])

    return out


def drop_forming(kl: list, days: int = 1) -> list[list]:
    """Убирает формирующийся бар.

    Незакрытый бар нельзя оценивать по отклику: окно оценки
    ещё не прошло, движение получится нулевым, и событие
    ложно пометится поглощённым.
    """
    if not kl:
        return []
    return kl[:-1] if len(kl) > 1 else []

def slice_as_of(kl: list, bars_ago: int) -> list:
    """Обрезает историю до состояния N баров назад.

    Нужна для проверки на отработавших кейсах: детектор обязан
    находить фигуру ДО движения, а не после. Прогон на полной
    истории AKE бессмыслен — пружина там уже разжалась.
    """
    if bars_ago <= 0:
        return list(kl)
    return kl[:-bars_ago] if bars_ago < len(kl) else []


# ─────────────────────────────────────────────────────────────
# Разделение потока по сторонам
# ─────────────────────────────────────────────────────────────
def _taker_buy(k) -> float:
    try:
        return float(k[K_TAKER_BUY_QUOTE])
    except (TypeError, ValueError, IndexError):
        return 0.0


def _quote(k) -> float:
    try:
        return float(k[K_QUOTE_VOLUME])
    except (TypeError, ValueError, IndexError):
        return 0.0


def side_volumes(kl: list, tail: int | None = None) -> tuple[list[float], list[float]]:
    """Объём агрессивных покупок и продаж по каждому бару, в USD.

    Покупки — takerBuyQuoteVolume: реальный объём, прошедший через
    маркет-ордера покупателей. Продажи — остаток.

    БЕЛОЕ (набор лонга) = покупки, КРАСНОЕ (набор шорта) = продажи.
    Знак зафиксирован и одинаков во всех модулях семейства.
    """
    src = kl[-tail:] if tail else kl
    buys: list[float] = []
    sells: list[float] = []
    for k in src:
        total = _quote(k)
        b = _taker_buy(k)
        if total <= 0 or b < 0 or b > total:
            buys.append(0.0)
            sells.append(0.0)
            continue
        buys.append(b)
        sells.append(total - b)
    return buys, sells


def taker_ratios(kl: list, tail: int | None = None) -> list[float]:
    """Доля агрессивных покупок в объёме бара."""
    buys, sells = side_volumes(kl, tail)
    out: list[float] = []
    for b, s in zip(buys, sells):
        total = b + s
        out.append(b / total if total > 0 else NEUTRAL_RATIO)
    return out


def taker_delta_usd(kl: list, tail: int | None = None) -> list[float]:
    """Дельта тейкеров по бару: покупки минус продажи, в USD."""
    buys, sells = side_volumes(kl, tail)
    return [b - s for b, s in zip(buys, sells)]


def cvd(kl: list, tail: int | None = None) -> list[float]:
    """Кумулятивная дельта.

    Отличие от OBV: OBV приписывает бару весь объём по знаку
    закрытия, здесь берётся фактическое соотношение агрессоров
    внутри бара.
    """
    out: list[float] = []
    acc = 0.0
    for d in taker_delta_usd(kl, tail):
        acc += d
        out.append(acc)
    return out


def flow_homogeneity(kl: list, tail: int) -> float:
    """Насколько ровно распределено давление внутри окна.

    Дельта −10% за окно может быть одним сбросом в один день или
    двадцатью ровными барами. Первое — вышел держатель, второе —
    устойчивое давление, которое кто-то методично поглощает.

    Возвращает 0..1: ближе к единице — поток однородный.
    """
    deltas = taker_delta_usd(kl, tail)
    if len(deltas) < 3:
        return 0.0
    total = sum(abs(d) for d in deltas)
    if total <= 0:
        return 0.0
    shares = [abs(d) / total for d in deltas]
    n = len(shares)
    even = 1.0 / n
    dispersion = sum(abs(s - even) for s in shares) / (2 * (1 - even)) if n > 1 else 1.0
    return max(0.0, min(1.0 - dispersion, 1.0))


# ─────────────────────────────────────────────────────────────
# События агрессии
# ─────────────────────────────────────────────────────────────
@dataclass
class FlowEvent:
    """Попытка развернуть тренд: аномальный объём одной стороны.

    Пузырь НЕ предсказывает направление. Он фиксирует, что крупный
    участник применил силу. Смысл появляется только вместе
    с откликом цены.
    """
    idx: int = 0
    bars_ago: int = 0
    side: str = ""              # buy (белое, лонг) | sell (красное, шорт)
    tier: int = 0
    sigma: float = 0.0
    price: float = 0.0
    volume_usd: float = 0.0
    response_pct: float = 0.0
    absorbed: bool = False
    fresh: bool = False           # окно отклика ещё не прошло
    body_ratio: float = 0.0       # тело в долях ATR, для fresh

    def to_dict(self) -> dict:
        return {
            "bars_ago": self.bars_ago,
            "side": self.side,
            "tier": self.tier,
            "sigma": round(self.sigma, 2),
            "price": self.price,
            "volume_usd": round(self.volume_usd, 2),
            "response_pct": round(self.response_pct, 2),
            "absorbed": self.absorbed,
            "fresh": self.fresh,
            "body_ratio": self.body_ratio,
        }


def _tier_of(sigma: float) -> int:
    if sigma >= TIER_SIGMAS[2]:
        return 3
    if sigma >= TIER_SIGMAS[1]:
        return 2
    if sigma >= TIER_SIGMAS[0]:
        return 1
    return 0


def is_absorbed(resp_pct: float, flat_pct: float) -> bool:
    """Поглощение — это ОТСУТСТВИЕ отклика, в любую сторону.

    Ход в сторону агрессора означает, что сила сработала.
    Ход ПРОТИВ агрессора означает, что её смяла встречная
    сторона и событие уже разрешилось. Ни то ни другое нам
    не интересно: ищем случай, когда massa приложена, а цена
    осталась на месте.
    """
    return abs(resp_pct) <= flat_pct

def volume_zscore(vols: list[float], cur: float) -> float:
    """Аномальность объёма в логарифмическом масштабе.

    Объём распределён логнормально: разница между барами — это
    разы, а не единицы. Линейная нормировка на таком распределении
    либо схлопывается, либо упирается в потолок, теряя различие
    между «сильным» и «экстремальным».

    Медиана и MAD берутся от логарифмов — устойчиво к выбросам
    и к пустым барам молодых монет.
    """
    lv = [math.log(v) for v in vols if v > 0]
    if len(lv) < 10 or cur <= 0:
        return 0.0
    med = median(lv)
    mad = median([abs(x - med) for x in lv])
    dev = mad * 1.4826
    if dev <= 0:
        return 0.0
    return (math.log(cur) - med) / dev

def detect_events(
    kl: list,
    ema_period: int = 21,
    dev_window: int = 50,
    response_bars: int = 3,
    response_flat_pct: float = 6.0,
) -> list[FlowEvent]:
    """Журнал попыток разворота по ряду свечей.

    Сила события — отклонение объёма СВОЕЙ стороны от собственной
    EMA, нормированное робастным разбросом. Такая нормировка делает
    события сравнимыми между монетами любого размера.

    События в конце ряда, у которых окно отклика ещё не прошло,
    пропускаются: судить о поглощении там не по чему.

    ВАЖНО: провал попытки не является самостоятельным сигналом.
    Шорт набирают и под смену тренда, и под локальный сквиз.
    Решает совокупность подтверждений.
    """
    n = len(kl)
    if n < ema_period + 5:
        return []

    buys, sells = side_volumes(kl)
    closes = [float(k[K_CLOSE]) if k else 0.0 for k in kl]

    events: list[FlowEvent] = []

    # Незрелые бары не выбрасываем: событие «прямо сейчас» —
    # самое ценное, что может найти детектор. Для них отклик
    # меряется внутри бара, а не по следующим дням.
    for i in range(ema_period, n):
        lo = max(0, i - dev_window)

        # Одна сторона на бар. Если аномальны обе — берём ту, что
        # реально доминировала: событие имеет направление, и
        # приписывать одному бару и покупку и продажу означает
        # удвоить статистику из ничего.
        cand = []
        for side, vols in (("buy", buys), ("sell", sells)):
            z = volume_zscore(vols[lo:i], vols[i])
            if _tier_of(z) > 0:
                cand.append((z, side, vols[i]))
        if not cand:
            continue
        sigma, side, vol_usd = max(cand)

        price = closes[i]
        if price <= 0:
            continue
        end = min(i + response_bars, n - 1)
        resp = pct_change(price, closes[end])

        # Порог поглощения — от волатильности самой монеты,
        # а не фиксированный процент
        flat = response_threshold(kl, i, response_bars)

        # ── отклик ──
        mature = (n - 1 - i) >= response_bars
        if mature:
            end = i + response_bars
            resp = pct_change(price, closes[end])
            flat = response_threshold(kl, i, response_bars)
            absorbed = is_absorbed(resp, flat)
            body_ratio = 0.0
        else:
            resp = 0.0
            body_ratio, absorbed = intrabar_absorption(kl, i)

        events.append(FlowEvent(
            idx=i,
            bars_ago=n - 1 - i,
            side=side,
            tier=_tier_of(sigma),
            sigma=sigma,
            price=price,
            volume_usd=vol_usd,
            response_pct=resp,
            absorbed=is_absorbed(resp, flat),
        ))

    return events

# ─────────────────────────────────────────────────────────────
# Зоны агрегации
# ─────────────────────────────────────────────────────────────
@dataclass
class FlowZone:
    """Ценовой уровень, где крупный участник работал.

    Мощная зона означает «готовиться к развороту», а НЕ «здесь дно».
    Проверено на BEAT: сильнейший откуп был на 0.74, цена ушла
    на 0.15; развернулась там, где событий меньше всего.
    """
    level: float = 0.0
    side: str = ""
    events: int = 0
    tier_sum: int = 0
    volume_usd: float = 0.0
    absorbed_count: int = 0
    tfs: tuple = ()             # на каких агрегатах зона видна
    last_bars_ago: int = 0

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "side": self.side,
            "events": self.events,
            "tier_sum": self.tier_sum,
            "volume_usd": round(self.volume_usd, 2),
            "absorbed_count": self.absorbed_count,
            "tfs": list(self.tfs),
            "last_bars_ago": self.last_bars_ago,
        }


def cluster_zones(
    events: list[FlowEvent],
    tolerance_pct: float = 30.0,
    tf_label: str = "",
) -> list[FlowZone]:
    """Собирает события в ценовые зоны.

    Допуск ±30%: уровни 0.0041 и 0.0044 — одна зона.
    Хранится ЦЕНОВОЙ УРОВЕНЬ, не время.

    Счётчик НЕ обнуляется после пробоя уровня вниз: зона остаётся
    на карте как место, где крупный работал.
    """
    if not events:
        return []

    zones: list[FlowZone] = []
    for side in ("buy", "sell"):
        side_events = sorted(
            (e for e in events if e.side == side),
            key=lambda e: e.price,
        )
        if not side_events:
            continue

        bucket: list[FlowEvent] = []
        for ev in side_events:
            if not bucket:
                bucket = [ev]
                continue
            anchor = bucket[0].price
            if anchor > 0 and abs(ev.price / anchor - 1) * 100 <= tolerance_pct:
                bucket.append(ev)
            else:
                zones.append(_make_zone(bucket, side, tf_label))
                bucket = [ev]
        if bucket:
            zones.append(_make_zone(bucket, side, tf_label))

    zones.sort(key=lambda z: z.tier_sum, reverse=True)
    return zones


def _make_zone(bucket: list[FlowEvent], side: str, tf_label: str) -> FlowZone:
    vol_total = sum(e.volume_usd for e in bucket)
    # Уровень зоны — средневзвешенный по объёму: крупные события
    # тянут его к себе сильнее мелких
    if vol_total > 0:
        level = sum(e.price * e.volume_usd for e in bucket) / vol_total
    else:
        level = mean(e.price for e in bucket)
    return FlowZone(
        level=level,
        side=side,
        events=len(bucket),
        tier_sum=sum(e.tier for e in bucket),
        volume_usd=vol_total,
        absorbed_count=sum(1 for e in bucket if e.absorbed),
        tfs=(tf_label,) if tf_label else (),
        last_bars_ago=min(e.bars_ago for e in bucket),
    )


def merge_zones(
    groups: list[list[FlowZone]],
    tolerance_pct: float = 30.0,
) -> list[FlowZone]:
    """Сводит зоны с разных агрегатов в общую карту.

    Зона, подтверждённая несколькими таймфреймами, реальна.
    Видимая только на дневке — шум.

    Причина, по которой крупный ТФ проявляет зоны лучше: порог
    аномалии строится от EMA объёма внутри бара, поэтому
    накопление, размазанное по десяти дням порциями ниже 1σ,
    в десятидневном баре складывается в одно событие на 3σ.
    """
    flat = [z for g in groups for z in g]
    if not flat:
        return []

    merged: list[FlowZone] = []
    for side in ("buy", "sell"):
        items = sorted(
            (z for z in flat if z.side == side),
            key=lambda z: z.level,
        )
        bucket: list[FlowZone] = []
        for z in items:
            if not bucket:
                bucket = [z]
                continue
            anchor = bucket[0].level
            if anchor > 0 and abs(z.level / anchor - 1) * 100 <= tolerance_pct:
                bucket.append(z)
            else:
                merged.append(_merge_bucket(bucket))
                bucket = [z]
        if bucket:
            merged.append(_merge_bucket(bucket))

    merged.sort(key=lambda z: (len(z.tfs), z.tier_sum), reverse=True)
    return merged


def _merge_bucket(bucket: list[FlowZone]) -> FlowZone:
    """Сводит одну и ту же зону, увиденную на разных агрегатах."""
    vol_total = sum(z.volume_usd for z in bucket)
    if vol_total > 0:
        level = sum(z.level * z.volume_usd for z in bucket) / vol_total
    else:
        level = mean(z.level for z in bucket)

    tfs: list[str] = []
    for z in bucket:
        for t in z.tfs:
            if t and t not in tfs:
                tfs.append(t)

    return FlowZone(
        level=level,
        side=bucket[0].side,
        events=sum(z.events for z in bucket),
        tier_sum=sum(z.tier_sum for z in bucket),
        volume_usd=vol_total,
        absorbed_count=sum(z.absorbed_count for z in bucket),
        tfs=tuple(tfs),
        last_bars_ago=min(z.last_bars_ago for z in bucket),
    )


def zone_confirmed(zone: FlowZone, min_tfs: int = 2) -> bool:
    """Зона реальна, если видна на нескольких агрегатах.

    Видимая только на дневке — шум.
    """
    return len(zone.tfs) >= min_tfs


# ─────────────────────────────────────────────────────────────
# Контекст: OBV после дна, экстремальный рост, горизонт
# ─────────────────────────────────────────────────────────────
OBV_WINDOW_DAYS_MAX = 240        # максимум 8 месяцев
EXTREME_GROWTH_MULT = 8.0        # вето на первые зоны


def obv_recovery(kl: list, window_days: int = OBV_WINDOW_DAYS_MAX) -> dict:
    """Поведение объёма ПОСЛЕ дна, а не глубина его просадки.

    Договорённость: считаем от дна после большого падения, окно
    максимум 8 месяцев. Важен ВОЗВРАТ объёма или его НАРАСТАНИЕ,
    а не отношение просадки OBV к просадке цены — последнее было
    частным случаем BEAT и в пороги не выносится.

    Рост OBV при падающей цене трактуется как ПОДОЗРИТЕЛЬНЫЙ:
    на тонких монетах это чаще перекладка между кошельками,
    чем накопление. Помечается отдельным флагом.
    """
    tail = min(window_days, len(kl))
    if tail < 40:
        return {
            "ok": False, "recovering": False, "rising": False,
            "suspicious": False, "bottom_bars_ago": 0,
            "obv_from_bottom": 0.0, "price_from_bottom": 0.0,
        }

    closes = [float(k[K_CLOSE]) for k in kl[-tail:]]
    d = taker_delta_usd(kl, tail)
    acc = 0.0
    obv: list[float] = []
    for x in d:
        acc += x
        obv.append(acc)

    low_idx = closes.index(min(closes))
    bars_after = len(closes) - 1 - low_idx
    if bars_after < 3:
        # Дно только что, судить о восстановлении рано
        return {
            "ok": True, "recovering": False, "rising": False,
            "suspicious": False, "bottom_bars_ago": bars_after,
            "obv_from_bottom": 0.0, "price_from_bottom": 0.0,
        }

    obv_at_low = obv[low_idx]
    obv_min = min(obv)
    span = max(abs(obv_min), abs(max(obv)), 1.0)

    obv_from_bottom = (obv[-1] - obv_at_low) / span
    price_from_bottom = pct_change(closes[low_idx], closes[-1])

    seg = obv[low_idx:]
    rising = slope(seg) > 0 and obv[-1] > obv_at_low

    # Возврат: объём отыграл заметную часть того, что потерял
    recovering = obv_from_bottom > 0.15

    # Объём растёт, а цена не идёт — перекладка вероятнее накопления
    suspicious = rising and price_from_bottom < 0

    return {
        "ok": True,
        "recovering": recovering,
        "rising": rising,
        "suspicious": suspicious,
        "bottom_bars_ago": bars_after,
        "obv_from_bottom": round(obv_from_bottom, 3),
        "price_from_bottom": round(price_from_bottom, 2),
    }


def extreme_growth_before(kl: list, lookback: int = 400) -> dict:
    """Был ли кратный рост перед падением.

    От ×8 и выше действует ВЕТО на первые зоны: держателей
    с прибылью слишком много, толпа в панике продавливает любой
    уровень. Чем сильнее был рост, тем больше зон обязано
    провалиться, прежде чем найдётся настоящее дно.

    Проверено на BEAT: откуп на 0.74 и на 0.31 провалились именно
    по этой причине, разворот случился только на 0.15.
    """
    tail = min(lookback, len(kl))
    if tail < 60:
        return {"mult": 0.0, "extreme": False, "zones_to_skip": 0}

    highs = [float(k[K_HIGH]) for k in kl[-tail:]]
    lows = [float(k[K_LOW]) for k in kl[-tail:]]

    peak_idx = highs.index(max(highs))
    if peak_idx < 5:
        return {"mult": 0.0, "extreme": False, "zones_to_skip": 0}

    base = min(lows[:peak_idx])
    mult = highs[peak_idx] / base if base > 0 else 0.0
    extreme = mult >= EXTREME_GROWTH_MULT

    # Грубая шкала недоверия: каждое удвоение сверх порога
    # добавляет одну зону, которая должна провалиться
    skip = 0
    if extreme:
        skip = 1
        m = mult
        while m >= EXTREME_GROWTH_MULT * 2 and skip < 4:
            m /= 2
            skip += 1

    return {"mult": round(mult, 1), "extreme": extreme, "zones_to_skip": skip}


def vortex_noise(highs, lows, closes, period: int = 14) -> dict:
    """Читаемость таймфрейма через шум Vortex.

    Пересечения нормируются НА БАР: на десятидневках за полгода
    всего восемнадцать точек, абсолютный счёт несопоставим
    с дневками.

    Таймфрейм НЕ входит ни в один порог и ни в один скор. Его
    единственная роль — горизонт ожидания: чем крупнее чистый ТФ,
    тем дольше ждать движения.
    """
    n = len(closes)
    if n < period + 10:
        return {"crossings_per_bar": 1.0, "amplitude": 0.0, "readable": False}

    vm_p: list[float] = []
    vm_m: list[float] = []
    tr: list[float] = []
    for i in range(1, n):
        vm_p.append(abs(highs[i] - lows[i - 1]))
        vm_m.append(abs(lows[i] - highs[i - 1]))
        tr.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))

    vp: list[float] = []
    vm: list[float] = []
    for i in range(period, len(vm_p) + 1):
        s = sum(tr[i - period:i])
        if s <= 0:
            continue
        vp.append(sum(vm_p[i - period:i]) / s)
        vm.append(sum(vm_m[i - period:i]) / s)

    if len(vp) < 5:
        return {"crossings_per_bar": 1.0, "amplitude": 0.0, "readable": False}

    crossings = sum(
        1 for i in range(1, len(vp))
        if (vp[i] > vm[i]) != (vp[i - 1] > vm[i - 1])
    )
    per_bar = crossings / len(vp)
    amplitude = mean(abs(vp[i] - vm[i]) for i in range(len(vp)))

    readable = per_bar <= 0.15 and amplitude >= 0.12
    return {
        "crossings_per_bar": round(per_bar, 3),
        "amplitude": round(amplitude, 3),
        "readable": readable,
    }


HORIZON_BARS = 2.5   # 2–3 бара чистого ТФ


def pick_horizon(kl_1d: list, tf_days: tuple = (1, 2, 3, 5, 10, 14, 30)) -> dict:
    """Выбирает самый крупный читаемый агрегат и переводит его в дни.

    Результат НЕ влияет на пороги и скор — это ярлык времени.
    """
    best = {"tf_days": 1, "label": "1d", "wait_days": 0, "readable": False}
    for d in tf_days:
        agg = drop_forming(aggregate(kl_1d, d), d)
        if len(agg) < 40:
            continue
        h = [float(k[K_HIGH]) for k in agg]
        l = [float(k[K_LOW]) for k in agg]
        c = [float(k[K_CLOSE]) for k in agg]
        q = vortex_noise(h, l, c)
        if q["readable"]:
            best = {
                "tf_days": d,
                "label": f"{d}d",
                "wait_days": int(d * HORIZON_BARS),
                "readable": True,
            }
    return best

# ─────────────────────────────────────────────────────────────
# Общий контекст семейства
# ─────────────────────────────────────────────────────────────
# Собирается диспетчером ОДИН раз и передаётся во все подкейсы.
# Подкейсы контекст только читают: агрегаты, события и зоны
# считаются тяжело, шесть независимых пересчётов недопустимы.

AGG_DAYS = (1, 2, 3, 5, 10)      # агрегаты для карты зон
ZONE_TOLERANCE_PCT = 30.0


@dataclass
class FlowContext:
    """Всё, что нужно подкейсам, посчитанное однократно."""
    symbol: str = ""
    ok: bool = False

    kl_1d: list = None            # сырые дневные свечи
    closes: list = None
    highs: list = None
    lows: list = None
    quotes: list = None           # объём в USD
    price: float = 0.0

    ratios: list = None           # доля тейкер-покупок по барам
    deltas: list = None           # дельта в USD
    cvd: list = None

    events_by_tf: dict = None     # {days: [FlowEvent]}
    zones: list = None            # сведённая карта зон
    obv: dict = None              # obv_recovery
    growth: dict = None           # extreme_growth_before
    horizon: dict = None          # pick_horizon

    def zones_by_side(self, side: str) -> list:
        return [z for z in (self.zones or []) if z.side == side]

    def confirmed_zones(self, side: str, min_tfs: int = 2) -> list:
        return [z for z in self.zones_by_side(side) if zone_confirmed(z, min_tfs)]


def build_context(symbol: str, kl_1d: list, min_days: int = 60) -> FlowContext:
    """Единая подготовка данных для всего семейства.

    Сетевых запросов не делает: дневные свечи уже лежат в кэше
    прогона после collect_metrics. Всё остальное — арифметика
    поверх них, включая старшие таймфреймы.
    """
    ctx = FlowContext(symbol=symbol)
    if not kl_1d or len(kl_1d) < min_days:
        return ctx

    ctx.kl_1d = kl_1d
    ctx.closes = [float(k[K_CLOSE]) for k in kl_1d]
    ctx.highs = [float(k[K_HIGH]) for k in kl_1d]
    ctx.lows = [float(k[K_LOW]) for k in kl_1d]
    ctx.quotes = [_quote(k) for k in kl_1d]
    ctx.price = ctx.closes[-1] if ctx.closes else 0.0
    if ctx.price <= 0:
        return ctx

    ctx.ratios = taker_ratios(kl_1d)
    ctx.deltas = taker_delta_usd(kl_1d)
    ctx.cvd = cvd(kl_1d)

    # События на каждом агрегате. Крупный ТФ суммирует то, что
    # на дневке тонуло ниже порога аномалии — именно поэтому
    # места агрегации на нём видны отчётливее.
    ctx.events_by_tf = {}
    zone_groups: list[list[FlowZone]] = []
    for d in AGG_DAYS:
        agg = drop_forming(aggregate(kl_1d, d), d)
        if len(agg) < 35:
            continue
        evs = detect_events(agg)
        if not evs:
            continue
        ctx.events_by_tf[d] = evs
        zone_groups.append(cluster_zones(evs, ZONE_TOLERANCE_PCT, tf_label=f"{d}d"))

    ctx.zones = merge_zones(zone_groups, ZONE_TOLERANCE_PCT)
    ctx.obv = obv_recovery(kl_1d)
    ctx.growth = extreme_growth_before(kl_1d)
    ctx.horizon = pick_horizon(kl_1d)
    ctx.ok = True
    return ctx
