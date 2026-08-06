"""Сбор метрик по монете: сырые числа плюс форматированные значения."""

from __future__ import annotations
import time

from analytics.indicators import (
    atr_pct, bb_width_pct, bb_width_rank, drawdown_from_high,
    obv_slope_pct, pct_change, rvol, stoch_rsi, vortex_phase,
    median, volume_ratio,
)
from core.binance import (
    K_CLOSE, K_HIGH, K_LOW, K_QUOTE_VOLUME, K_VOLUME, K_CLOSE_TIME, K_OPEN_TIME,
    get_funding_rate, get_open_interest, get_spot_ticker,
    klines_1d, klines_1h, klines_4h, klines_1w, series,
)
from core.config import MIN_HISTORY_DAYS, VOL_MEDIAN_WINDOW, MIN_BAR_FILL, ANOMALY_WINDOW

# Короткие ряды, которые остаются в снимке для отрисовки спарклайнов
KEEP_SERIES = ("spark_1d", "spark_vol")
SPARK_POINTS = 24


def fmt_pct(x: float | None, digits: int = 1) -> str:
    if x is None:
        return "—"
    sign = "+" if x > 0 else ""
    return f"{sign}{x:.{digits}f}%"


def fmt_num(x: float | None, digits: int = 2) -> str:
    if x is None:
        return "—"
    return f"{x:.{digits}f}"


def fmt_big(x: float | None) -> str:
    if x is None:
        return "—"
    if x >= 1e9:
        return f"${x/1e9:.2f}B"
    if x >= 1e6:
        return f"${x/1e6:.2f}M"
    if x >= 1e3:
        return f"${x/1e3:.1f}K"
    return f"${x:.0f}"


def fmt_price_short(p: float) -> str:
    """Цена для плотных мест: значащие цифры, без лишних нулей."""
    if p <= 0:
        return "—"
    return f"${p:.4g}"


def _thin(values: list[float], points: int = SPARK_POINTS) -> list[float]:
    """Прореживает ряд до нужного числа точек, сохраняя форму."""
    if not values:
        return []
    tail = values[-points:] if len(values) > points else values
    return [round(v, 10) for v in tail]

def bar_fill(kline: list) -> float:
    """Доля набранного времени свечи.

    Закрытая свеча — единица по определению. Незакрытая набрана
    ровно настолько, сколько прошло её времени.

    Считать по факту наличия бара в ряду нельзя: последний бар
    присутствует всегда, и величина выродится в константу.
    Источник — временные поля свечи, других у нас нет.
    """
    now_ms = time.time() * 1000.0
    try:
        t_open = float(kline[K_OPEN_TIME])
        t_close = float(kline[K_CLOSE_TIME])
    except (TypeError, ValueError, IndexError):
        return 1.0
    span = t_close - t_open
    if span <= 0 or now_ms >= t_close:
        return 1.0
    return max(0.0, min(1.0, (now_ms - t_open) / span))


def vol_ratio(klines: list[list]) -> float | None:
    """Объём текущего бара к медиане предыдущих, кратностью.

    Текущий бар почти всегда незакрыт, и его объём достраивается по
    доле набранного времени. Без этого величина занижена тем сильнее,
    чем крупнее масштаб: дневка, открытая три часа назад, покажет
    восьмую часть оборота — и соврёт ровно тогда, когда колонка
    нужнее всего, на свежем движении.

    Расчёт вынесен в core.volume: та же функция обслуживает
    rel_volume в ядре семейства. Две реализации расходились на два
    порядка, и понять, какая врёт, можно было только вручную.
    """
    if not klines or len(klines) < VOL_MEDIAN_WINDOW + 1:
        return None

    quotes = series(klines, K_QUOTE_VOLUME)
    fills = [bar_fill(k) for k in klines]

    return volume_ratio(
        quotes,
        fills,
        window=VOL_MEDIAN_WINDOW,
        min_fill=MIN_BAR_FILL,
    )

def aggregate_quote_fill(klines: list[list], scale: int) -> tuple[list[float], list[float]]:
    """Группирует часовые клайны по N штук, свежий край всегда полный.

    Остаток обрезается СНИЗУ (со старой стороны) явно — если этого не
    сделать, при len % scale != 0 самая свежая группа окажется короче
    scale и её fill будет занижен не рынком, а арифметикой.
    """
    if scale <= 1:
        return series(klines, K_QUOTE_VOLUME), [bar_fill(k) for k in klines]

    trimmed = klines[len(klines) % scale:]
    quotes: list[float] = []
    fills: list[float] = []
    for i in range(0, len(trimmed), scale):
        chunk = trimmed[i:i + scale]
        quotes.append(sum(float(k[K_QUOTE_VOLUME]) for k in chunk))
        fills.append(min(1.0, sum(bar_fill(k) for k in chunk) / scale))
    return quotes, fills


def volume_ratios_5(kl_1h: list[list], kl_4h: list[list], kl_1d: list[list]) -> dict[str, float]:
    """Кратность текущего бара к медиане ANOMALY_WINDOW предыдущих
    закрытых — на пяти масштабах: 2ч/4ч/6ч/12ч/1д. Источник — уже
    загруженные для других целей клайны, дополнительной сети ноль.
    """
    out: dict[str, float] = {}

    for label, hours in (("2h", 2), ("6h", 6), ("12h", 12)):
        quotes, fills = aggregate_quote_fill(kl_1h, hours) if kl_1h else ([], [])
        r = volume_ratio(quotes, fills, window=ANOMALY_WINDOW, min_fill=MIN_BAR_FILL)
        out[label] = round(r, 2) if r is not None else 0.0

    for label, kl in (("4h", kl_4h), ("1d", kl_1d)):
        quotes = series(kl, K_QUOTE_VOLUME) if kl else []
        fills = [bar_fill(k) for k in kl] if kl else []
        r = volume_ratio(quotes, fills, window=ANOMALY_WINDOW, min_fill=MIN_BAR_FILL)
        out[label] = round(r, 2) if r is not None else 0.0

    return out

BOTTOM_WINDOW = 60
def _from_bottom(lows: list[float], price: float) -> tuple[float, int]:
    """Рост от минимума окна и его давность в днях.

    Окно короткое сознательно: 60 дней отвечают на вопрос «сколько
    уже отъехали от локального дна», а не «где было дно цикла».
    Для второго есть ath_drop, и величины дополняют друг друга —
    −80% от ATH при +150% от дна и −80% при +5% описывают разные
    монеты, хотя первая цифра у них общая.
    """
    if not lows or price <= 0:
        return 0.0, 0
    tail = lows[-BOTTOM_WINDOW:]
    low = min(tail)
    if low <= 0:
        return 0.0, 0
    idx = len(tail) - 1 - tail.index(low)
    return (price / low - 1) * 100, idx

def collect_metrics(symbol: str, quote_volume_24h: float = 0.0) -> dict:
    """Все базовые метрики монеты.

    Возвращает словарь сырых чисел. Форматирование — отдельно,
    чтобы одни и те же данные шли и в отчёт, и в JSON снимка.
    """
    kl_1d = klines_1d(symbol)
    if not kl_1d or len(kl_1d) < MIN_HISTORY_DAYS:
        return {}

    closes_1d = series(kl_1d, K_CLOSE)
    volumes_1d = series(kl_1d, K_VOLUME)
    quote_1d = series(kl_1d, K_QUOTE_VOLUME)
    highs_1d = series(kl_1d, K_HIGH)
    lows_1d = series(kl_1d, K_LOW)

    price = closes_1d[-1]
    if price <= 0:
        return {}

    up_from_low, days_from_low = _from_bottom(lows_1d, price)
    kl_4h = klines_4h(symbol)
    closes_4h = series(kl_4h, K_CLOSE) if kl_4h else []
    highs_4h = series(kl_4h, K_HIGH) if kl_4h else []
    lows_4h = series(kl_4h, K_LOW) if kl_4h else []

    kl_1h = klines_1h(symbol)
    closes_1h = series(kl_1h, K_CLOSE, tail=48) if kl_1h else []
    volumes_1h = series(kl_1h, K_VOLUME, tail=48) if kl_1h else []

    vol_x_1h = vol_ratio(kl_1h)
    vol_x_4h = vol_ratio(kl_4h)
    vol_x_1d = vol_ratio(kl_1d)
    vol_ratio_5 = volume_ratios_5(kl_1h, kl_4h, kl_1d)
    # ── Изменения цены ──
    ch_24h = pct_change(closes_1d, 1)
    ch_7d = pct_change(closes_1d, 7)
    ch_30d = pct_change(closes_1d, 30)
    ch_3d = pct_change(closes_1d, 3)

    # Все три ряда уже загружены выше через канонические
    # загрузчики — попадают в ту же ячейку RunCache,
    # новых сетевых запросов ноль.
    vol_x_1h = vol_ratio(kl_1h)
    vol_x_4h = vol_ratio(kl_4h)
    vol_x_1d = vol_ratio(kl_1d)

    # ── ATH: недельная история покрывает всю жизнь контракта ──
    kl_1w = klines_1w(symbol)
    highs_1w = series(kl_1w, K_HIGH) if kl_1w else []
    ath = max(highs_1w) if highs_1w else 0.0
    ath = max(ath, max(highs_1d))
    ath_drop = drawdown_from_high(price, [ath])
    ath_source = "1w" if highs_1w else "1d"

    # ── Объёмы ──
    rvol_1h = rvol(volumes_1h, 24) if volumes_1h else 0.0
    obv_slope = obv_slope_pct(closes_1d, volumes_1d, 20)

    # ── Осцилляторы и волатильность ──
    srsi = stoch_rsi(closes_4h, 14) if closes_4h else None
    atr_p = atr_pct(highs_1d, lows_1d, closes_1d, 14)
    bb = bb_width_pct(closes_1d, 20, 2.0)
    bb_rank = bb_width_rank(closes_1d, 20, 120)

    vp_4h = vortex_phase(highs_4h, lows_4h, closes_4h, 14) if closes_4h else {}

    # ── Деривативы ──
    funding = get_funding_rate(symbol) * 100
    oi = get_open_interest(symbol)
    oi_usd = oi * price if oi > 0 else 0.0

    # ── Спот против фьючерса ──
    spot = get_spot_ticker(symbol)
    spot_vol = 0.0
    if spot:
        try:
            spot_vol = float(spot.get("quoteVolume", 0))
        except (TypeError, ValueError):
            spot_vol = 0.0

    fut_vol = quote_volume_24h
    if fut_vol <= 0 and quote_1d:
        fut_vol = quote_1d[-1]
    total_vol = spot_vol + fut_vol
    spot_ratio = spot_vol / total_vol if total_vol > 0 else 0.0

    ch_3d = pct_change(closes_1d, 3)

    return {
        "symbol": symbol,
        "price": price,
        "ch_24h": ch_24h,
        "ch_7d": ch_7d,
        "ch_3d": ch_3d,
        "vol_x_1h": vol_x_1h,
        "vol_x_4h": vol_x_4h,
        "vol_x_1d": vol_x_1d,
        "vol_ratio": vol_ratio_5,
        "ch_30d": ch_30d,
        "ath": ath,
        "ath_drop": ath_drop,
        "ath_source": ath_source,
        "rvol_1h": rvol_1h,
        "obv_slope": obv_slope,
        "srsi_4h": srsi,
        "atr_pct": atr_p,
        "bb_pct": bb,
        "bb_rank": bb_rank,
        "vortex_4h": vp_4h,
        "funding": funding,
        "oi": oi,
        "oi_usd": oi_usd,
        "spot_ratio": spot_ratio,
        "spot_vol": spot_vol,
        "fut_vol": fut_vol,
        "history_days": len(closes_1d),
        # Короткие ряды для спарклайнов, остаются в снимке
        "spark_1d": _thin(closes_1d),
        "spark_vol": _thin(quote_1d),
        # Полные ряды нужны детекторам и стратегии, в JSON не уходят
        "closes_1d": closes_1d,
        "volumes_1d": volumes_1d,
        "highs_1d": highs_1d,
        "lows_1d": lows_1d,
        "closes_4h": closes_4h,
        "closes_1h": closes_1h,
        "ch_3d": ch_3d,
        "up_from_low": up_from_low,
        "days_from_low": days_from_low,
    }


def build_metric_rows(m: dict) -> list[dict]:
    """Форматированные строки метрик для отображения."""
    def cls_by_sign(v: float | None) -> str:
        if v is None or v == 0:
            return ""
        return "up" if v > 0 else "down"

    return [
        {"key": "Цена", "val": fmt_price_short(m["price"]), "cls": ""},
        {"key": "24h", "val": fmt_pct(m["ch_24h"]), "cls": cls_by_sign(m["ch_24h"])},
        {"key": "7d", "val": fmt_pct(m["ch_7d"]), "cls": cls_by_sign(m["ch_7d"])},
        {"key": "30d", "val": fmt_pct(m["ch_30d"]), "cls": cls_by_sign(m["ch_30d"])},
        {"key": "От ATH", "val": fmt_pct(m["ath_drop"]), "cls": "down"},
        {"key": "RVOL 1H", "val": f"{m['rvol_1h']:.2f}×", "cls": ""},
        {"key": "OBV", "val": fmt_pct(m["obv_slope"]), "cls": cls_by_sign(m["obv_slope"])},
        {"key": "StochRSI 4H", "val": fmt_num(m["srsi_4h"], 1), "cls": ""},
        {"key": "ATR %", "val": fmt_num(m["atr_pct"], 2), "cls": ""},
        {"key": "BB width", "val": fmt_num(m["bb_pct"], 2), "cls": ""},
        {"key": "BB rank", "val": fmt_num(m["bb_rank"], 0), "cls": ""},
        {"key": "Funding", "val": f"{m['funding']:.4f}%", "cls": cls_by_sign(m["funding"])},
        {"key": "OI", "val": fmt_big(m["oi_usd"]), "cls": ""},
        {"key": "Spot ratio", "val": f"{m['spot_ratio']*100:.0f}%", "cls": ""},
    ]


def strip_series(m: dict) -> dict:
    """Убирает тяжёлые ряды, оставляя короткие для спарклайнов."""
    return {
        k: v for k, v in m.items()
        if not isinstance(v, list) or k in KEEP_SERIES
    }
