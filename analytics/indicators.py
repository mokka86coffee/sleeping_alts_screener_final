"""Технические индикаторы. Чистые функции без сетевых вызовов."""

from __future__ import annotations

import math

def median(values: list[float]) -> float:
    """Медиана ряда. Устойчива к выбросам, в отличие от среднего."""
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2

def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def ema_series(values: list[float], period: int) -> list[float]:
    """Полный ряд EMA — нужен для наклонов и пересечений."""
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi_series(closes: list[float], period: int = 14) -> list[float]:
    """RSI Уайлдера, линейная сложность."""
    if len(closes) < period + 1:
        return []

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    if len(gains) < period:
        return []

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    out: list[float] = []
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            out.append(100.0)
        else:
            rs = avg_gain / avg_loss
            out.append(100 - (100 / (1 + rs)))
    return out


def stoch_rsi(closes: list[float], period: int = 14) -> float | None:
    """Стохастик от RSI, значение 0..100."""
    rsis = rsi_series(closes, period)
    if len(rsis) < period:
        return None
    window = rsis[-period:]
    lo, hi = min(window), max(window)
    if hi == lo:
        return 50.0
    return (rsis[-1] - lo) / (hi - lo) * 100


def obv_series(closes: list[float], volumes: list[float]) -> list[float]:
    obv = [0.0]
    for i in range(1, min(len(closes), len(volumes))):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    return obv


def obv_slope_pct(closes: list[float], volumes: list[float], window: int = 20) -> float:
    """Наклон OBV за окно, в процентах.

    Если база близка к нулю, нормируем на средний объём — иначе
    получаются бессмысленные тысячи процентов.
    """
    obv = obv_series(closes, volumes)
    if len(obv) < window + 1:
        return 0.0

    old = obv[-window - 1]
    new = obv[-1]

    if abs(old) < 1e-9:
        avg_vol = sum(volumes[-window:]) / window if window else 0.0
        if avg_vol <= 0:
            return 0.0
        return ((new - old) / (avg_vol * window)) * 100

    return ((new - old) / abs(old)) * 100


def true_ranges(highs: list[float], lows: list[float], closes: list[float]) -> list[float]:
    trs: list[float] = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    return trs


def atr_pct(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float | None:
    """ATR в процентах от текущей цены."""
    if len(closes) < period + 1:
        return None
    trs = true_ranges(highs, lows, closes)
    if len(trs) < period:
        return None
    atr = sum(trs[-period:]) / period
    return (atr / closes[-1]) * 100 if closes[-1] > 0 else None


def bb_width_pct(closes: list[float], period: int = 20, mult: float = 2.0) -> float | None:
    """Ширина полос Боллинджера в процентах от средней."""
    if len(closes) < period:
        return None
    window = closes[-period:]
    m = sum(window) / period
    if m <= 0:
        return None
    var = sum((x - m) ** 2 for x in window) / period
    sd = math.sqrt(var)
    width = 2 * mult * sd
    return (width / m) * 100


def bb_width_rank(closes: list[float], period: int = 20, lookback: int = 120) -> float | None:
    """Процентиль текущей ширины BB против собственной истории.

    0 — самое узкое сжатие за период наблюдения, 100 — самое широкое.
    Абсолютная ширина без этого контекста мало о чём говорит: у волатильной
    монеты 12% это норма, у спокойной — экстремум.
    """
    if len(closes) < period + 10:
        return None

    widths: list[float] = []
    start = max(period, len(closes) - lookback)
    for i in range(start, len(closes) + 1):
        w = bb_width_pct(closes[:i], period)
        if w is not None:
            widths.append(w)

    if len(widths) < 10:
        return None

    current = widths[-1]
    below = sum(1 for w in widths if w < current)
    return (below / len(widths)) * 100


def vortex_phase(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> dict:
    """Индикатор Vortex и производная от него фаза рынка."""
    empty = {"vi_plus": 0.0, "vi_minus": 0.0, "phase": 0, "label": "no data"}
    if len(closes) < period + 1:
        return empty

    vm_plus: list[float] = []
    vm_minus: list[float] = []
    trs: list[float] = []

    for i in range(1, len(closes)):
        vm_plus.append(abs(highs[i] - lows[i - 1]))
        vm_minus.append(abs(lows[i] - highs[i - 1]))
        trs.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))

    if len(trs) < period:
        return empty

    sum_tr = sum(trs[-period:])
    if sum_tr <= 0:
        return empty

    vi_plus = sum(vm_plus[-period:]) / sum_tr
    vi_minus = sum(vm_minus[-period:]) / sum_tr
    diff = vi_plus - vi_minus

    if diff > 0.15:
        phase, label = 4, "TREND"
    elif diff > 0.05:
        phase, label = 3, "MOMENTUM"
    elif diff > -0.05:
        phase, label = 2, "BASE"
    else:
        phase, label = 1, "DECLINE"

    return {
        "vi_plus": round(vi_plus, 4),
        "vi_minus": round(vi_minus, 4),
        "phase": phase,
        "label": label,
    }


def pct_change(series: list[float], back: int) -> float | None:
    """Изменение в процентах на N баров назад."""
    if len(series) < back + 1:
        return None
    prev = series[-1 - back]
    if prev <= 0:
        return None
    return ((series[-1] / prev) - 1) * 100


def rvol(volumes: list[float], window: int = 24) -> float:
    """Относительный объём последнего бара против среднего за окно.

    Последний бар исключается из базы сравнения, иначе он занижает
    собственную аномальность.
    """
    if len(volumes) < window + 1:
        return 0.0
    base = volumes[-(window + 1):-1]
    avg = sum(base) / len(base) if base else 0.0
    if avg <= 0:
        return 0.0
    return volumes[-1] / avg


def drawdown_from_high(price: float, highs: list[float]) -> float:
    """Просадка от максимума ряда, в процентах (отрицательное число)."""
    if not highs:
        return 0.0
    peak = max(highs)
    if peak <= 0:
        return 0.0
    return ((price / peak) - 1) * 100

def volume_ratio(
    quotes: list[float],
    fills: list[float],
    window: int,
    min_fill: float,
    min_norm: int | None = None,
) -> float | None:
    """Объём последнего бара к медиане нормы, кратностью.

    Единственная реализация на проект. Существовало две: metrics и
    flow_core считали одно и то же над одной ячейкой кэша и
    расходились на два порядка — EUL показывала ×107 в колонке и
    «тихо» в семействе, в одной карточке, в один момент.

    Три правила, нарушение любого даёт расхождение: незакрытый бар
    достраивается по доле набранного времени; норма строится только
    по закрытым барам; нормы нет — возвращается None, а не отношение
    к пустоте.
    """
    n = min(len(quotes), len(fills))
    if n < 2:
        return None

    cur_q = quotes[n - 1]
    cur_fill = fills[n - 1]
    if cur_q <= 0 or cur_fill <= 0 or cur_fill < min_fill:
        return None

    lo = max(0, n - 1 - window)
    norm = [
        quotes[i]
        for i in range(lo, n - 1)
        if fills[i] >= 1.0 and quotes[i] > 0
    ]

    need = min_norm if min_norm is not None else max(2, window // 2)
    if len(norm) < need:
        return None

    med = median(norm)
    if med <= 0:
        return None

    return (cur_q / cur_fill) / med

# Потолок отношения окна к норме.
#
# Отношение выше десяти означает не аномальный фон, а отсутствие
# нормы: у монеты со свежим листингом срез нормы попадает в первые
# дни торгов с оборотом на два порядка ниже нынешнего. Медиана
# считается честно, отношение — тоже, но величина описывает возраст
# монеты, а не рынок. BANK давал 184.3, AKE 113.1 при разбросе
# остального рынка 0.12..1.79.
#
# Обрезаем, а не возвращаем единицу: фон у такой монеты
# действительно шумный относительно своей истории, просто мерить
# его нечем.
WINDOW_RATIO_CAP = 10.0
def window_ratio(
    quotes: list[float],
    fills: list[float],
    window: int,
    norm_span: int,
) -> float:
    """Медиана окна к медиане более длинной нормы.

    Отдельная функция, а не параметр к volume_ratio, и это по смыслу.
    Первая отвечает «аномален ли текущий бар», вторая — «шумный ли
    фон». Churn требует шумного, spring тихого, расходятся они именно
    по второй величине.

    Нейтральная единица при отсутствии нормы — честное «не знаю».
    """
    n = min(len(quotes), len(fills))

    # История обязана покрывать и окно, и всю норму целиком.
    # Прежнее n < window * 2 пропускало монеты, у которых норма
    # набиралась по длине, но целиком лежала в первых днях торгов.
    if n < window + norm_span:
        return 1.0

    tail = [
        quotes[i] / max(fills[i], 1e-9)
        for i in range(n - window, n)
        if quotes[i] > 0
    ]
    if not tail:
        return 1.0

    lo = max(0, n - window - norm_span)
    norm = [
        quotes[i]
        for i in range(lo, n - window)
        if fills[i] >= 1.0 and quotes[i] > 0
    ]
    if len(norm) < window:
        return 1.0

    med_norm = median(norm)
    if med_norm <= 0:
        return 1.0

    return min(median(tail) / med_norm, WINDOW_RATIO_CAP)
