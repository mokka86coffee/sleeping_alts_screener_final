"""Поиск структурных уровней: сопротивления, поддержки, границы диапазона.

Цели сделки должны стоять там, где цена уже разворачивалась, а не на
произвольном множителе риска. Но одной структуры мало: цель, которая
ближе стопа, торгово бессмысленна, сколько бы раз её ни тестировали.
Поэтому уровни здесь ещё и фильтруются по соотношению риска.
"""

from __future__ import annotations

# Уровни ближе этого расстояния считаются одним и тем же
CLUSTER_GAP_PCT = 1.8

# Цель ближе этого расстояния к входу бессмысленна: съест комиссия
MIN_TARGET_DISTANCE_PCT = 2.5

# Минимальное соотношение для первой цели. Уровень, дающий меньше,
# в качестве цели не рассматривается — берём следующий выше.
MIN_TARGET_RR = 1.2

# Стоп не может быть ближе этого расстояния: иначе его снимет рыночный шум
MIN_STOP_DISTANCE_PCT = 2.0

# Стоп не может быть дальше этого: риск на сделку становится неуправляемым
MAX_STOP_DISTANCE_PCT = 14.0

# Множители ATR, если структурных уровней выше цены нет
ATR_PROJECTION = (2.5, 4.0, 6.5)


def swing_highs(highs: list[float], lookback: int = 3) -> list[int]:
    """Индексы локальных максимумов."""
    out: list[int] = []
    for i in range(lookback, len(highs) - lookback):
        if highs[i] <= 0:
            continue
        left = highs[i - lookback:i]
        right = highs[i + 1:i + 1 + lookback]
        if all(highs[i] >= x for x in left) and all(highs[i] >= x for x in right):
            out.append(i)
    return out


def swing_lows(lows: list[float], lookback: int = 3) -> list[int]:
    """Индексы локальных минимумов."""
    out: list[int] = []
    for i in range(lookback, len(lows) - lookback):
        if lows[i] <= 0:
            continue
        left = lows[i - lookback:i]
        right = lows[i + 1:i + 1 + lookback]
        if all(lows[i] <= x for x in left) and all(lows[i] <= x for x in right):
            out.append(i)
    return out


def cluster_levels(values: list[float], gap_pct: float = CLUSTER_GAP_PCT) -> list[dict]:
    """Схлопывает близкие уровни в один, считая число касаний.

    Уровень, который тестировали трижды, сильнее одиночного экстремума —
    это отражается в поле touches.
    """
    if not values:
        return []

    ordered = sorted(values)
    clusters: list[list[float]] = [[ordered[0]]]

    for v in ordered[1:]:
        anchor = clusters[-1][0]
        if anchor > 0 and (v - anchor) / anchor * 100 <= gap_pct:
            clusters[-1].append(v)
        else:
            clusters.append([v])

    return [
        {"price": sum(g) / len(g), "touches": len(g)}
        for g in clusters
    ]


def find_resistances(
    highs: list[float],
    price: float,
    lookback: int = 180,
    limit: int = 5,
) -> list[dict]:
    """Уровни сопротивления выше текущей цены, снизу вверх."""
    if not highs or price <= 0:
        return []

    window = highs[-lookback:] if len(highs) > lookback else highs
    peaks_idx = swing_highs(window, lookback=3)
    peaks = [window[i] for i in peaks_idx]

    if window:
        peaks.append(max(window))

    floor = price * (1 + MIN_TARGET_DISTANCE_PCT / 100)
    above = [p for p in peaks if p > floor]
    if not above:
        return []

    clustered = cluster_levels(above)
    clustered.sort(key=lambda c: c["price"])
    return clustered[:limit]


def find_support(
    lows: list[float],
    price: float,
    lookback: int = 60,
) -> float | None:
    """Ближайшая поддержка ниже цены."""
    if not lows or price <= 0:
        return None

    window = lows[-lookback:] if len(lows) > lookback else lows
    troughs_idx = swing_lows(window, lookback=3)
    troughs = [window[i] for i in troughs_idx]

    below = [t for t in troughs if 0 < t < price * 0.995]
    return max(below) if below else None


def clamp_stop(price: float, stop: float) -> float:
    """Удерживает стоп в разумном коридоре.

    Слишком узкий снимет шумом, слишком широкий делает риск
    неуправляемым — оба случая одинаково бесполезны.
    """
    if price <= 0:
        return 0.0

    nearest = price * (1 - MIN_STOP_DISTANCE_PCT / 100)
    farthest = price * (1 - MAX_STOP_DISTANCE_PCT / 100)

    if stop <= 0:
        return nearest
    return max(min(stop, nearest), farthest)


def build_stop(
    price: float,
    lows: list[float],
    atr_pct: float,
    atr_mult: float = 1.8,
    lookback: int = 60,
) -> float:
    """Стоп под ближайшей поддержкой, ограниченный коридором."""
    if price <= 0:
        return 0.0

    atr_stop = price * (1 - max(atr_pct, 1.0) / 100 * atr_mult)
    support = find_support(lows, price, lookback=lookback)

    if support is None:
        return clamp_stop(price, atr_stop)

    # Небольшой зазор под уровень: стопы прямо на уровне снимают первыми
    structural = support * 0.985

    # Берём более близкий из двух, чтобы не расширять риск сверх меры
    return clamp_stop(price, max(structural, atr_stop))


def build_targets(
    price: float,
    stop: float,
    highs: list[float],
    atr_pct: float,
    lookback: int = 180,
) -> tuple[tuple[float, float, float], str]:
    """Три цели по структуре либо, если её нет, по проекции ATR.

    Уровни, дающие соотношение ниже MIN_TARGET_RR, пропускаются: цель
    ближе стопа не цель, а ловушка. Возвращает цели и код источника.
    """
    if price <= 0 or stop <= 0 or stop >= price:
        return (0.0, 0.0, 0.0), "none"

    risk = price - stop
    levels = find_resistances(highs, price, lookback=lookback, limit=5)

    # Оставляем только те уровни, ради которых стоит рисковать
    viable = [
        lv["price"] for lv in levels
        if (lv["price"] - price) / risk >= MIN_TARGET_RR
    ]

    if viable:
        prices = viable[:3]
        # Достраиваем недостающие цели шагом от последнего интервала
        while len(prices) < 3:
            last = prices[-1]
            prev = prices[-2] if len(prices) >= 2 else price
            prices.append(last + max(last - prev, risk))
        return (prices[0], prices[1], prices[2]), "structure"

    # Структура есть, но вся слишком близко: цена зажата под сопротивлением.
    # Такой сетап отдаём с проекцией, стратегия сама решит, брать ли.
    atr_abs = price * max(atr_pct, 1.0) / 100
    projected = tuple(price + atr_abs * k for k in ATR_PROJECTION)

    source = "projection" if not levels else "capped"
    return projected, source
