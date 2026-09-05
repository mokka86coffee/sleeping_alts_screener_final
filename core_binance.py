"""Доступ к публичному API Binance: тикеры, свечи, funding, OI, спот.

Ключевая идея модуля — канонические запросы свечей. Все потребители
(метрики и детекторы) обязаны ходить через klines_1d, klines_4h и так далее,
а не запрашивать произвольные лимиты. Тогда кэш попадает в одну ячейку
и монета грузится один раз вместо четырёх.
"""

# Семейство FLOW строит ВСЕ свои масштабы (2D, 3D, 5D, 10D) агрегацией
# из klines_1d — отдельных запросов на старшие таймфреймы не делает.
# Поэтому LIMIT_1D = 500 задаёт потолок глубины анализа: 500 дней даёт
# 50 баров десятидневки, чего хватает на EVENT_NORM_WINDOW = 30.
# Уменьшать нельзя, не пересчитав MIN_BARS_BASE в flow_config.

from __future__ import annotations

import time

from core_config import BINANCE_FAPI, BINANCE_SPOT
from core_http import RunCache, get_json

# Кэш свечей на время прогона
KLINES_CACHE = RunCache()

# ── Канонические параметры загрузки ──
# Вес запроса растёт ступенчато, поэтому брать 500 свечей почти так же
# дёшево, как 100. Берём с запасом и режем на месте.
LIMIT_1D = 500
LIMIT_4H = 200
LIMIT_1H = 1000

# Пятнадцатиминутки. Тысяча свечей это 10.4 суток — норма размера
# сделки за неделю (672 бара) умещается целиком, и остаётся запас на
# монету, у которой часть баров пустая.
#
# Берётся НЕ для всей выборки: вес запроса 5, и двести монет за
# прогон это лишняя тысяча веса без пользы. Загружается только для
# монет журнала — см. metrics.collect_metrics.
LIMIT_15M = 1000
LIMIT_1W = 200
LIMIT_HTF = 200   # для 2d, 3d, 5d, 2w


def _klines_weight(limit: int) -> int:
    """Вес запроса свечей зависит от запрошенного количества."""
    if limit <= 100:
        return 1
    if limit <= 500:
        return 2
    if limit <= 1000:
        return 5
    return 10


def get_futures_tickers() -> list[dict]:
    """24-часовая статистика по всем фьючерсным парам."""
    data = get_json(f"{BINANCE_FAPI}/fapi/v1/ticker/24hr", weight=40)
    return data or []


def get_klines(symbol: str, interval: str, limit: int = 500) -> list[list]:
    """Свечи фьючерсов с кэшем на время прогона."""
    key = (symbol, "kl", interval, limit)

    def _fetch():
        data = get_json(
            f"{BINANCE_FAPI}/fapi/v1/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
            weight=_klines_weight(limit),
        )
        return closed_only(data or [])

    return KLINES_CACHE.get_or_call(key, _fetch)


def closed_only(klines: list[list]) -> list[list]:
    """ТОЛЬКО ЗАКРЫТЫЕ СВЕЧИ (05.09). Binance всегда кладёт последней текущую,
    незакрытую свечу — с частичным объёмом и промежуточным закрытием; анализ,
    лог ликвидности и плечо по типу считали её как целую. Закрытость — по
    времени, не по позиции: свеча закрыта, если её closeTime (индекс 6, мс)
    уже наступил. Незакрытых в ответе может быть только одна, но проверяем все."""
    now_ms = int(time.time() * 1000)
    out = []
    for k in klines:
        try:
            if int(k[K_CLOSE_TIME]) <= now_ms:
                out.append(k)
        except (TypeError, ValueError, IndexError):
            out.append(k)
    return out


# ── Канонические загрузчики ──
def klines_1d(symbol: str) -> list[list]:
    return get_klines(symbol, "1d", LIMIT_1D)


def klines_4h(symbol: str) -> list[list]:
    return get_klines(symbol, "4h", LIMIT_4H)


def klines_1h(symbol: str) -> list[list]:
    return get_klines(symbol, "1h", LIMIT_1H)


def klines_15m(symbol: str) -> list[list]:
    """Пятнадцатиминутки. Мельче часа агрегацией не спуститься.

    Часовые складываются в двухчасовые и шестичасовые, но не делятся:
    внутри бара порядок сделок потерян. Поэтому мелкая шкала — это
    отдельный запрос, и он оправдан только там, где мы действительно
    смотрим: заявка, заметная на пятнадцати минутах, в часовом баре
    тонет вместе со своей стороной.
    """
    return get_klines(symbol, "15m", LIMIT_15M)


def klines_1w(symbol: str) -> list[list]:
    return get_klines(symbol, "1w", LIMIT_1W)


def klines_htf(symbol: str, interval: str) -> list[list]:
    """Старшие таймфреймы для лестницы Vortex: 2d, 3d, 5d, 1w, 2w."""
    if interval == "1w":
        return klines_1w(symbol)
    return get_klines(symbol, interval, LIMIT_HTF)


def get_spot_klines(symbol: str, interval: str = "1d", limit: int = 30) -> list[list]:
    """Свечи спота. Пустой список, если пары на споте нет."""
    key = (symbol, "spotkl", interval, limit)

    def _fetch():
        data = get_json(
            f"{BINANCE_SPOT}/api/v3/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
            quiet_400=True,
            weight=_klines_weight(limit),
        )
        return data or []

    return KLINES_CACHE.get_or_call(key, _fetch)


def drop_symbol_cache(symbol: str) -> None:
    """Освобождает память после того, как монета обработана."""
    KLINES_CACHE.drop_prefix(symbol)


def get_funding_rate(symbol: str) -> float:
    """Последняя ставка финансирования, доля (не проценты)."""
    data = get_json(
        f"{BINANCE_FAPI}/fapi/v1/premiumIndex",
        {"symbol": symbol},
        weight=1,
    )
    if not data:
        return 0.0
    try:
        return float(data.get("lastFundingRate", 0))
    except (TypeError, ValueError):
        return 0.0


def get_funding_history(symbol: str, limit: int = 100) -> list[dict]:
    """История ставок финансирования. Три записи в сутки."""
    key = (symbol, "funding", limit)

    def _fetch():
        data = get_json(
            f"{BINANCE_FAPI}/fapi/v1/fundingRate",
            {"symbol": symbol, "limit": limit},
            weight=1,
        )
        return data or []

    return KLINES_CACHE.get_or_call(key, _fetch)


def get_open_interest(symbol: str) -> float:
    """Текущий открытый интерес в базовой монете."""
    data = get_json(
        f"{BINANCE_FAPI}/fapi/v1/openInterest",
        {"symbol": symbol},
        weight=1,
    )
    if not data:
        return 0.0
    try:
        return float(data.get("openInterest", 0))
    except (TypeError, ValueError):
        return 0.0


def get_oi_history(symbol: str, period: str = "1d", limit: int = 30) -> list[dict]:
    """История открытого интереса. Доступна только за последние 30 дней."""
    key = (symbol, "oihist", period, limit)

    def _fetch():
        data = get_json(
            f"{BINANCE_FAPI}/futures/data/openInterestHist",
            {"symbol": symbol, "period": period, "limit": limit},
            weight=1,
        )
        return data or []

    return KLINES_CACHE.get_or_call(key, _fetch)


def get_spot_ticker(symbol: str) -> dict | None:
    """24-часовая статистика спота. None, если пары на споте нет."""
    key = (symbol, "spotticker")

    def _fetch():
        return get_json(
            f"{BINANCE_SPOT}/api/v3/ticker/24hr",
            {"symbol": symbol},
            quiet_400=True,
            weight=2,
        ) or {}

    result = KLINES_CACHE.get_or_call(key, _fetch)
    return result or None


def get_order_book_depth(symbol: str, limit: int = 100) -> dict | None:
    """Стакан заявок. Нужен для оценки реальной ликвидности входа."""
    weight = 2 if limit <= 100 else 5
    return get_json(
        f"{BINANCE_FAPI}/fapi/v1/depth",
        {"symbol": symbol, "limit": limit},
        weight=weight,
    )


# ─────────────────────────────────────────────────────────────
# Фон рынка: биткоин
# ─────────────────────────────────────────────────────────────
# BTC не попадает в выборку — он в MAJOR_TOKENS, и это правильно:
# искать в нём спящий альт бессмысленно. Но фоном он нужен всем
# остальным, поэтому отдельный загрузчик.
#
# Своих запросов практически не стоит: klines_1d канонический и
# кэшируется RunCache, так что повторные вызовы внутри прогона
# бесплатны, а первый весит 2.
def get_btc_context() -> dict:
    """Изменение биткоина за сутки и неделю плюс короткий ряд.

    Пустой словарь, если данных нет: отсутствующий фон должен
    выглядеть отсутствующим, а не нулевым изменением.
    """
    kl = klines_1d("BTCUSDT")
    if not kl or len(kl) < 8:
        return {}

    closes = series(kl, K_CLOSE)
    if not closes or closes[-1] <= 0:
        return {}

    last = closes[-1]

    def _back(bars: int) -> float | None:
        if len(closes) <= bars:
            return None
        prev = closes[-1 - bars]
        return ((last / prev) - 1) * 100 if prev > 0 else None

    out = {
        "price": last,
        "ch_24h": _back(1),
        "ch_7d": _back(7),
        # Короткий ряд для спарклайна в сводке. 24 точки — столько же,
        # сколько у монет в KEEP_SERIES, чтобы отрисовка была общей.
        "spark": [round(c, 8) for c in closes[-24:]],
    }

    # Н-9 тех.долга: сжатие волатильности как фон рынка. Та же
    # формула, что уже работает на альтах (bb_width_rank), применённая
    # к BTC на том же ряду — ни нового запроса, ни нового источника.
    #
    # ОБЯЗАТЕЛЬНАЯ ОГОВОРКА: величина про сжатие, а НЕ про направление.
    # Fundstrat говорит о медианном движении на 30% за 60 дней БЕЗ
    # знака — сжатие разряжается в любую сторону, та же логика, что
    # у flow_spring. Читатель экрана обязан увидеть факт «в нижних N%
    # сжатия за год», а не прогноз «значит будет рост».
    #
    # None — истории меньше periода+10 (bb_width_rank сам это решает):
    # «не измерено», а не середина шкалы.
    from analytics_indicators import bb_width_rank
    rank = bb_width_rank(closes, 20, 120)
    if rank is not None:
        out["vol_rank"] = round(rank, 1)

    # Н-1 тех.долга: тейкерский перекос по биткоину — тот же вопрос,
    # что PUMP ON/OFF, но по потоку, а не по цене. Поля 9 и 10 свечей
    # (K_TAKER_BUY_BASE, K_TAKER_BUY_QUOTE) проект уже парсит для
    # дельты FLOW; здесь тот же приём на том же ряду BTC.
    #
    # Окно — семь дней, порядок величины «на этой неделе». Не
    # откалибровано: число по порядку величины, первый прогон покажет
    # разброс.
    #
    # None — окно короче семи дней либо продаж в нём не было вовсе
    # (sell <= 0): отсутствие перекоса должно выглядеть отсутствием,
    # а не единицей или нулём.
    BTC_TAKER_SKEW_DAYS = 7
    if len(kl) >= BTC_TAKER_SKEW_DAYS:
        tail = kl[-BTC_TAKER_SKEW_DAYS:]
        try:
            buy = sum(float(k[K_TAKER_BUY_QUOTE]) for k in tail)
            turn = sum(float(k[K_QUOTE_VOLUME]) for k in tail)
        except (TypeError, ValueError, IndexError):
            buy = turn = 0.0
        sell = turn - buy
        if sell > 0:
            out["taker_skew"] = round(buy / sell, 3)

    return out


# ─────────────────────────────────────────────────────────────
# Доминация BTC · единственный вызов не к Binance в этом модуле
# ─────────────────────────────────────────────────────────────
# Доля капитализации BTC от всего крипторынка — агрегат по всем
# биржам и монетам сразу, у Binance такой величины взять неоткуда.
# CoinGecko /global — обычный публичный источник, без ключа.
#
# get_json() host-agnostic: заголовок X-MBX-USED-WEIGHT-1M читается,
# только если он есть в ответе — для не-Binance хоста его нет, и
# лимитер просто не трогается. Вес формально уходит из бюджета
# Binance, но при weight=1 и одном вызове за прогон (кэш RunCache)
# это не заметно.
COINGECKO_GLOBAL = "https://api.coingecko.com/api/v3/global"


def get_btc_dominance() -> float | None:
    """Доля BTC от капитализации всего крипторынка, в процентах.

    None — если источник не ответил или ответ не разобрать: пробел на
    экране обязан выглядеть пробелом, а не нулём и не старой
    константой, случайно похожей на настоящее число.
    """
    def _fetch():
        return get_json(COINGECKO_GLOBAL, weight=1) or {}

    data = KLINES_CACHE.get_or_call(("_global", "coingecko"), _fetch)
    try:
        return float(data["data"]["market_cap_percentage"]["btc"])
    except (KeyError, TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────
# Разбор свечей
# ─────────────────────────────────────────────────────────────
# Индексы полей в ответе Binance
K_OPEN_TIME = 0
K_OPEN = 1
K_HIGH = 2
K_LOW = 3
K_CLOSE = 4
K_VOLUME = 5          # объём в базовой монете
K_CLOSE_TIME = 6
K_QUOTE_VOLUME = 7    # объём в USDT
K_TRADES = 8            # число сделок
K_TAKER_BUY_BASE = 9    # покупки тейкером, базовая монета
K_TAKER_BUY_QUOTE = 10  # покупки тейкером, USDT — база дельты в FLOW


def series(klines: list[list], index: int, tail: int | None = None) -> list[float]:
    """Извлекает колонку из массива свечей, при желании только хвост."""
    src = klines[-tail:] if tail else klines
    out: list[float] = []
    for k in src:
        try:
            out.append(float(k[index]))
        except (TypeError, ValueError, IndexError):
            out.append(0.0)
    return out


def ohlcv(klines: list[list], tail: int | None = None) -> dict[str, list[float]]:
    """Все ряды разом — экономит повторные проходы по массиву."""
    src = klines[-tail:] if tail else klines
    o: list[float] = []
    h: list[float] = []
    l: list[float] = []
    c: list[float] = []
    v: list[float] = []
    q: list[float] = []
    for k in src:
        try:
            o.append(float(k[K_OPEN]))
            h.append(float(k[K_HIGH]))
            l.append(float(k[K_LOW]))
            c.append(float(k[K_CLOSE]))
            v.append(float(k[K_VOLUME]))
            q.append(float(k[K_QUOTE_VOLUME]))
        except (TypeError, ValueError, IndexError):
            continue
    return {"open": o, "high": h, "low": l, "close": c, "volume": v, "quote": q}
