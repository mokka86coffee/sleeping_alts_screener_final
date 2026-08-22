"""Сбор метрик по монете: сырые числа плюс форматированные значения."""

from __future__ import annotations
import time
from datetime import datetime, timedelta, timezone

from analytics_indicators import (
    atr_pct, bb_width_pct, bb_width_rank, drawdown_from_high,
    obv_slope_pct, pct_change, rvol, stoch_rsi, vortex_phase,
    median, volume_ratio,
)
from analytics_intraday import big_trades as intraday_big
from analytics_unlocks import for_symbol as unlocks_for
from analytics_intraday import scan as intraday_scan
from core_binance import (
    K_CLOSE, K_HIGH, K_LOW, K_QUOTE_VOLUME, K_VOLUME, K_CLOSE_TIME, K_OPEN_TIME,
    get_funding_rate, get_oi_history, get_open_interest, get_spot_ticker,
    klines_1d, klines_1h, klines_15m, klines_4h, klines_1w, series,
)
from core_config import (
    MIN_HISTORY_DAYS, VOL_MEDIAN_WINDOW, MIN_BAR_FILL, ANOMALY_WINDOW,
    FROZEN_MAX_CHANGE_PCT, FROZEN_TAIL_MIN, FROZEN_TAIL_PCT,
)
from core_models import Candidate

# Короткие ряды, которые остаются в снимке для отрисовки спарклайнов
KEEP_SERIES = ("spark_1d", "spark_vol")
SPARK_POINTS = 24


# ── Мелкая шкала: только для монет журнала ──────────────────
# Что это. Множество символов, за которыми следит журнал лидеров,
# и время правки файла, по которому оно обновляется.
#
# Почему так. Пятнадцатиминутки стоят пять веса на монету; на всей
# выборке это лишняя тысяча за прогон и риск упереться в лимит биржи
# ради монет, на которые никто не смотрит. Журнал — ровно тот
# список, который открывают, и он же невелик.
#
# Читается с диска, не по сети. Ключ — время правки, потому что
# планировщик крутит прогоны в одном процессе: закешированное
# навсегда множество устарело бы на первом же обновлении журнала.
_JOURNAL = {"mtime": None, "symbols": frozenset()}


def _journal_symbols() -> frozenset:
    """Символы журнала лидеров. Сети не трогает, ошибки гасит.

    Импорт leaders отложен внутрь функции намеренно: leaders тянет
    detectors_flow_config, а тот исполняет пакет detectors, который
    сам ходит в analytics_ На уровне модуля это замкнуло бы импорт;
    внутри вызова — нет.

    Любая ошибка означает «журнала нет», и монета просто останется
    без мелкой шкалы. Терять из-за этого всю метрику не за что.
    """
    try:
        from core_config import LEADERS_PATH
        mtime = LEADERS_PATH.stat().st_mtime
    except OSError:
        return frozenset()

    if _JOURNAL["mtime"] != mtime:
        try:
            from analytics_leaders import tracked_symbols
            _JOURNAL["symbols"] = frozenset(tracked_symbols())
            _JOURNAL["mtime"] = mtime
        except Exception:                              # noqa: BLE001
            return _JOURNAL["symbols"]
    return _JOURNAL["symbols"]


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


def fmt_cap(v: float | None) -> str:
    """Капитализация для плотных мест: «$11M», а не «$11.00M».

    Существует рядом с fmt_big() намеренно, а не по недосмотру. Обе
    считают одно и то же, но округляют по-разному, и обе величины уже
    показаны пользователю: fmt_big кормит таблицы метрик, где два
    знака после запятой различают соседние строки, fmt_cap — плашки и
    подписи графиков, где длина строки ограничена вёрсткой. Тихо
    свести их к одной значит незаметно изменить то, что видно на
    экране, — если сводить, то осознанно и отдельной задачей.

    Раньше жила в render_flow_report.py как _cap и импортировалась
    оттуда в орбиту и дашборд: рендер зависел от рендера. Сама по
    себе это не отрисовка, а форматирование числа, поэтому место ей
    здесь.
    """
    v = float(v or 0.0)
    if v <= 0:
        return "—"
    if v >= 1e9:
        return f"${v / 1e9:.1f}B"
    if v >= 1e6:
        return f"${v / 1e6:.0f}M"
    return f"${v / 1e3:.0f}K"


def card_data(c: Candidate) -> dict:
    """Числа карточки из raw кандидата.

    Все ключи скалярные: strip_series оставляет их в снимке, и они
    доживают до рендера после drop_symbol_cache — свечей монеты в
    памяти к этому моменту уже нет.

    mcap_usd, а не market_cap: поле CoinFundamentals называется
    именно так. Промах по имени здесь молчалив — .get вернул бы
    ноль, и колонка показывала бы прочерк при живых данных.

    Раньше жила в render_flow_report.py как _data. Ни одного тега и
    ни одного esc() внутри: это выборка и приведение полей, а не
    отрисовка, — поэтому карточка потока, орбита и любой следующий
    экран берут её отсюда, а не друг у друга.
    """
    r = c.raw or {}
    return {
        "v1h": r.get("vol_x_1h"),
        "v4h": r.get("vol_x_4h"),
        "v1d": r.get("vol_x_1d"),
        "p1d": float(r.get("ch_24h") or 0),
        "p3d": float(r.get("ch_3d") or 0),
        "p7d": float(r.get("ch_7d") or 0),
        "fund": float(r.get("funding") or 0),
        "cap": float(r.get("mcap_usd") or 0),
        "ath": float(r.get("ath_drop") or 0),
        # spark_1d — дневные закрытия, уже в KEEP_SERIES
        "series": list(r.get("spark_1d") or [])[-14:],
        "up": float(r.get("up_from_low") or 0),
        "up_days": int(r.get("days_from_low") or 0),
    }


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

    К-7 тех.долга (чтение момента, 19 августа): монете короче
    BOTTOM_WINDOW дней окно не сокращается — оно просто мельче своей
    заявленной длины, и «минимум» тогда почти всегда листинговый
    бар с аномальным разбросом на открытии торгов, а не дно цикла.
    У AKE так получалось +4940% от «дна». Ниже полного окна величина
    честно не измеряется: 0.0/0 здесь означает «рано мерить», а не
    «роста нет».
    """
    if len(lows) < BOTTOM_WINDOW or price <= 0:
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
    # Ч-6 тех.долга: без этой точки четырёхдневный ход не ловился
    # нигде — ch_3d режет его хвост, ch_7d размазывает в окно вдвое
    # длиннее самого события.
    ch_4d = pct_change(closes_1d, 4)

    # Пересчёт этих трёх стоял здесь второй раз подряд. Сети он не
    # стоил — ряды из кэша, — но медиана по пятистам барам гонялась
    # дважды на монету, и читателю приходилось гадать, какая из двух
    # пар значений уедет дальше.

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
    # К-7 тех.долга: тот же корень, что у up_from_low выше — при
    # MIN_HISTORY_DAYS=30 листинговый бар (аномальный разброс на
    # открытии торгов) ещё может сидеть внутри 14-барного окна ATR.
    # У BEAT так выходило 374%, у TUT 143%. Порог вдвое шире периода
    # ATR — заведомо выводит листинговый бар за пределы окна; число
    # не откалибровано, взято по порядку величины.
    ATR_FRESH_LISTING_MIN_DAYS = 14 * 2
    atr_p = (atr_pct(highs_1d, lows_1d, closes_1d, 14)
             if len(closes_1d) >= ATR_FRESH_LISTING_MIN_DAYS else None)
    bb = bb_width_pct(closes_1d, 20, 2.0)
    bb_rank = bb_width_rank(closes_1d, 20, 120)

    vp_4h = vortex_phase(highs_4h, lows_4h, closes_4h, 14) if closes_4h else {}

    # ── Интрадей: что происходит прямо сейчас ──
    # Отдельная шкала и отдельный горизонт — сутки-двое против недель
    # у остального в этом словаре. Считается по тем же часовым
    # свечам, что загружены выше, дополнительной сети ноль.
    #
    # Получасовки сюда пока не приходят: их нет в кэше, а запрос на
    # всю выборку стоит веса. Модуль шкалы не знает и примет любую —
    # добавление второй шкалы см. techdebt-intraday.md, пункт П-3.
    # Часовой ряд открытого интереса. Нужен интрадей-слою, чтобы
    # различать набор и выход: у дельты и цены этого различия нет.
    # Вес запроса 1, кэш общий с остальными вызовами прогона.
    #
    # Загружается здесь, а не в блоке деривативов ниже: тот идёт
    # ПОСЛЕ этой строки, и переменная оказывалась использованной до
    # присваивания. Синтаксис при этом валиден и модуль импортируется,
    # так что видно такое только запуском.
    #
    # Отказ загрузчика гасится: ряд OI — обогащение, а не условие.
    # Без него интрадей-слой не выставит вердикт, и это штатный
    # случай; ронять из-за него всю монету не за что.
    try:
        oi_hourly = [
            float(r.get("sumOpenInterest") or 0.0)
            for r in (get_oi_history(symbol, period="1h", limit=200) or [])
            if isinstance(r, dict)
        ]
    except Exception:                                 # noqa: BLE001
        oi_hourly = []

    # Часовые свечи плюс часовой ряд OI. Лестница шкал (2ч, 3ч, 6ч,
    # 12ч) складывается внутри из этих же часовых агрегацией — сети
    # на неё не нужно.
    intraday = intraday_scan(kl_1h, "1h", oi_hourly) if kl_1h else {}

    # Крупные заявки на ДНЕВНОМ масштабе: по ним журнал закрывает
    # позицию, увидев продажу на пампе. Норма и хвост здесь те же
    # 168 и 48 баров, но это уже дни, а не часы, — то есть норма за
    # полгода и метки за полтора месяца. tail отдаётся наружу, чтобы
    # читатель знал, от какого хвоста отсчитаны позиции, и не
    # угадывал длину.
    # Мелкая шкала. Крупная заявка, заметная на пятнадцати минутах, в
    # часовом баре тонет: сторона берётся по доле тейкер-покупок ВСЕГО
    # бара, и покупка внутри продавцового часа уходит в нейтраль. Для
    # монет журнала это ровно тот случай, ради которого слой и нужен —
    # откуп на проливе внутри идущего движения.
    #
    # Ряд OI сюда не передаётся: часовой ряд на мелкой шкале
    # растянулся бы по четыре бара на точку и дал бы вердикт, которого
    # не мерили. Связка с OI остаётся часовой.
    intraday_fine: dict = {}
    if symbol in _journal_symbols():
        kl_15m = klines_15m(symbol)
        if kl_15m:
            intraday_fine = intraday_scan(kl_15m, "15m")

    # Разлоки. Ручные данные, сети не трогают; пустой словарь означает
    # «монету не заполняли», а не «разлоков нет» — отрисовка обязана
    # показать пробел. Оборот нужен, чтобы перевести объём разлока в дни
    # торгов: рынок переваривает предложение объёмом, а не капитализацией.
    unlocks = unlocks_for(symbol, quote_volume_24h)

    daily_big = intraday_big(kl_1d) if kl_1d else {}
    if daily_big:
        daily_big["tail"] = 48

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
        "ch_4d": ch_4d,
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
        # Движение плеча — analytics_momentum.oi_cycle() через
        # context.oi_hist, единая формула на проект (см. Ч-1).
        # Отдельного поля здесь больше нет: было мёртвым дублем.
        "spot_ratio": spot_ratio,
        "spot_vol": spot_vol,
        "fut_vol": fut_vol,
        "history_days": len(closes_1d),
        "intraday": intraday,
        "intraday_fine": intraday_fine,
        "unlocks": unlocks,
        "daily_big": daily_big,
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


# ═════════════════════════════════════════════════════════════
# Фон рынка и ряды для графиков · перенесено из render_orbit.py
#
# Почему переехало. Эти величины считались внутри орбиты, хотя не
# имеют отношения к тому, как рисуются звёзды: это метрики по всей
# выборке (хвост распределения суточных изменений, кратности объёма,
# ряды цены и объёма для графиков). Орбита была не владельцем
# расчёта, а первым его потребителем.
#
# Почему это стало важно именно сейчас. Сводка (render_brief.py)
# брала те же числа из window.ORB — глобальной переменной, которую
# выставлял скрипт орбиты В ТОМ ЖЕ документе. При переезде экранов в
# отдельные iframe этот канал исчезает вовсе: у каждого документа
# своё window. Данные больше не передаются между экранами — каждый
# экран вызывает эти функции сам при сборке своего файла.
# ═════════════════════════════════════════════════════════════


# Ступени взрывного объёма. Одного порога мало: ×50 и ×200 — события
# разного веса, а одним цветом они сливаются в «жёлтое». Три ступени
# дают шкалу, читаемую без чисел.
#
# Жили в render_common.py как общая константа двух рендеров. Это
# пороги, а не оформление: по нижней ступени звезда помечается
# «горячей» ещё в данных, до всякой отрисовки, — а собирает эти данные
# аналитика, которой рендер недоступен.
LEAD_X1 = 50.0
LEAD_X2 = 100.0
LEAD_X3 = 150.0


def max_vol_ratio(rec: dict) -> float:
    """Максимальная кратность объёма по всем окнам записи журнала.

    Максимум, а не среднее: усреднение по пяти окнам топит аномалию,
    живущую в одном из них. У 1000RATS дневка даёт ×31 при 2h ×0.34 —
    по среднему монета невидима, хотя событие произошло.

    Жила в render_common.py, куда её положил Ч-8. Внутри нет ни тега,
    ни esc() — это метрика над записью, и после разделения слоёв она
    понадобилась аналитике, которой импортировать рендер нельзя.
    """
    vr = rec.get("vol_ratio") or {}
    values = []
    for v in vr.values():
        try:
            values.append(float(v))
        except (TypeError, ValueError):
            continue
    return max(values, default=0.0)


def base_symbol(symbol: str) -> str:
    """Тикер без котируемой валюты: ONGUSDT → ONG.

    Без esc(): экранирование — забота рендера, и слой аналитики о
    HTML знать не должен. Тот, кто вставляет результат в разметку,
    экранирует его у себя.
    """
    return symbol[:-4] if symbol.endswith("USDT") else symbol


# Торговая неделя привязана к Москве, а не к часовому поясу читателя:
# окно ликвидности задаёт биржа и её основной поток, а не то, откуда
# смотрят на отчёт. UTC+3 фиксированный, перевода часов нет.
#
# Пока рынок один, и это просто константа. Место ей всё равно здесь,
# а не в рендере: если позже понадобится время открытия других рынков
# (Нью-Йорк и остальные), это то же семейство вычислений — с
# параметром рынка вместо жёстко зашитой Москвы.
MSK = timezone(timedelta(hours=3))


def weekend_state(now: datetime | None = None) -> str:
    """Положение относительно выходных: 'soon', 'now' или пустая строка.

    Пятница — «выходные близко»: ликвидность начинает уходить уже к
    вечеру. Суббота и воскресенье — сами выходные.

    Единственная реализация на проект. Вторая жила в brief.py на JS и
    считала то же самое по своему часовому поясу.
    """
    moment = now or datetime.now(MSK)
    day = moment.astimezone(MSK).weekday()   # 0 пн … 6 вс
    if day == 4:
        return "soon"
    if day in (5, 6):
        return "now"
    return ""


def market_breadth(candidates: list[Candidate]) -> dict:
    """Хвост распределения суточных изменений по всей выборке.

    Отвечает на вопрос «есть ли вообще куда ехать», на который доля
    зелёных не отвечает: рынок бывает зелёным на 60% при росте в
    пределах двух процентов, и это ровно замирание.

    Два числа, а не одно. Максимум говорит, был ли сегодня хоть один
    сильный ход; счётчик — единичный это выброс или движение рынка.
    Замиранием считаем, когда провалены оба: одна улетевшая монета
    при мёртвом остальном рынке движением не является.

    Монета без ch_24h считается нулём, а не выбрасывается из выборки:
    так было в орбите (там это давал _num с нулём по умолчанию), и
    менять это заодно с переездом нельзя — пропуск данных и нулевое
    изменение по-разному сдвигают максимум на рынке, где почти всё
    красное.
    """
    changes = []
    for c in candidates:
        try:
            changes.append(float((c.raw or {}).get("ch_24h") or 0.0))
        except (TypeError, ValueError):
            changes.append(0.0)

    if not changes:
        return {"frozen": False, "maxChange": None, "tail": 0}

    top = max(changes)
    tail = sum(1 for x in changes if x >= FROZEN_TAIL_PCT)

    return {
        "frozen": top < FROZEN_MAX_CHANGE_PCT and tail < FROZEN_TAIL_MIN,
        "maxChange": round(top, 1),
        "tail": tail,
        "tailPct": FROZEN_TAIL_PCT,
    }


# ─────────────────────────────────────────────────────────────
# Р-5. Относительная мера: отделить монету от прилива
# ─────────────────────────────────────────────────────────────
# 21 августа BLESS дала +18% при +20% по биткоину — то есть шла
# вровень с приливом и собственной силы не показывала. В дни, когда
# едет вся выборка, абсолютный рост не отличает фигуру от течения.
#
# Знаменателем берётся МЕДИАНА ВЫБОРКИ, а не биткоин: наша вселенная
# — спящие альты, и «обогнал биткоин» отвечает на другой вопрос (это
# Р-19, доля обошедших). Медиана устойчива к выбросам: один TRUMP
# +92% не должен поднимать планку остальным двумстам.
#
# Окна в имени ключа (Р-10): d1/d7/d30 — разные величины, а не
# уточнения друг друга. Единица опережения — ПУНКТЫ, не проценты:
# разность двух процентов процентом не является.

def sample_medians(candidates: list) -> dict:
    """Медианный ход выборки по окнам. Пусто там, где нет данных."""
    out: dict = {}
    for key, raw_key in (("d1", "ch_24h"), ("d7", "ch_7d"),
                         ("d30", "ch_30d")):
        vals = []
        for c in candidates:
            v = (getattr(c, "raw", None) or {}).get(raw_key)
            if v is None:
                continue
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                continue
        if vals:
            out[key] = round(median(vals), 1)
    return out


def relative_moves(raw: dict | None, medians: dict) -> dict:
    """Опережение выборки в пунктах по каждому окну.

    Нет хода монеты или нет медианы за это окно — ключа нет. Ноль
    здесь означал бы «шла вровень», а это утверждение, которого мы не
    делали: у монеты вне выборки хода просто нет.
    """
    raw = raw or {}
    out: dict = {}
    for key, raw_key in (("d1", "ch_24h"), ("d7", "ch_7d"),
                         ("d30", "ch_30d")):
        med = medians.get(key)
        v = raw.get(raw_key)
        if med is None or v is None:
            continue
        try:
            out[key] = round(float(v) - med, 1)
        except (TypeError, ValueError):
            continue
    return out


def day_ratios(vals: list) -> list[float]:
    """Кратности дневного объёма к собственной медиане ряда.

    Считается ЗДЕСЬ, а не в JS. Объём в этом проекте уже мерился
    тремя разными способами под одним словом (бар к медиане нормы,
    час к среднему за сутки, максимум по пяти масштабам), и четвёртое
    место расчёта — в браузере, вне досягаемости пробы — сделало бы
    расхождение неотлаживаемым.

    Медиана, а не среднее: один аномальный день в ряду задирает
    среднее так, что все остальные дни становятся «ниже нормы».
    """
    clean = [float(v) for v in vals if v and float(v) > 0]
    if len(clean) < 4:
        return []
    med = median(clean)
    if med <= 0:
        return []
    return [
        round(float(v) / med, 2) if v and float(v) > 0 else 0.0
        for v in vals
    ]


def leader_chart(c: Candidate | None) -> dict:
    """Ряд цены лидера потока плюс уровни его фигуры.

    Уровень зоны идёт вместе с рядом не для украшения: без него
    график сообщает «монета росла» — ровно то, что уже сказано
    процентом в тексте. Фигура FLOW построена вокруг уровня, и
    только он делает график осмысленным.
    """
    if c is None:
        return {}
    s = [float(x) for x in (c.raw.get("spark_1d") or []) if x]
    if len(s) < 4:
        return {}

    f = c.flow or {}

    # Число уходит в JS дважды и в разных ролях: zone нужен как
    # величина (по нему считается шкала графика), stop и target —
    # только как подпись. Поэтому первое остаётся float, а вторые
    # форматируются здесь: у монеты за четыре цента полное float
    # представление это семнадцать знаков в строке.
    stop = float(f.get("stop_hint") or 0.0)
    target = float(f.get("target_hint") or 0.0)

    return {
        "series": s,
        "zone": float(f.get("zone_price") or 0.0),
        "stop": fmt_price_short(stop) if stop > 0 else "",
        "target": fmt_price_short(target) if target > 0 else "",
        "score": int(getattr(c, "score", 0) or 0),
        "case": ((f.get("case") or "").replace("flow_", "") or "—"),
        "horizonDays": int(f.get("horizon_days") or 0),
    }


def vol_chart(candidates: list[Candidate]) -> dict:
    """Монета с наибольшей кратностью объёма и её дневной ряд.

    Кратностью, а не оборотом в долларах: абсолютный оборот каждый
    день выводит одни и те же ликвидные имена, то есть является
    константой и новостью не бывает.

    Максимум берётся по ПЯТИ масштабам сразу — всплеск бывает
    двухчасовым и суточным, и спрашивать один масштаб значит
    пропускать половину случаев.
    """
    best, best_x = None, 0.0
    for c in candidates:
        for x in (c.raw.get("vol_ratio") or {}).values():
            try:
                x = float(x)
            except (TypeError, ValueError):
                continue
            if x > best_x:
                best_x, best = x, c

    if best is None or best_x <= 0:
        return {}

    d = card_data(best)
    return {
        "sym": base_symbol(best.symbol),
        "x": round(best_x),
        "cap": fmt_cap(d["cap"]),
        "ratios": day_ratios(best.raw.get("spark_vol") or []),
        "v1h": round(d.get("v1h") or 0, 1),
        "v4h": round(d.get("v4h") or 0, 1),
        "v1d": round(d.get("v1d") or 0, 1),
        "funding": round(float(best.raw.get("funding") or 0.0), 3),
    }
