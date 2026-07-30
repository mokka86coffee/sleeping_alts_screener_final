"""FLOW Order Flow Reversal Detector — 1D + 4H.

Четвёртая стратегия. Три существующих детектора смотрят на цену
и суммарный объём. Этот смотрит на характер потока: кто агрессор,
поглощается ли предложение, что делают плечи.

Ловит момент, когда после затяжного падения покупатель начинает
бить по рынку, а не подбирать лимитками. Работает независимо,
ничего не заимствует у остальных детекторов.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from core.binance import (
    K_OPEN, K_HIGH, K_LOW, K_CLOSE, K_QUOTE_VOLUME,
    get_funding_rate, get_oi_history,
    klines_1d, klines_4h, series,
)

# Индекс takerBuyQuoteVolume в свече Binance.
# В core.binance константа не объявлена, держим локально:
# модуль намеренно самодостаточен.
K_TAKER_BUY_QUOTE = 10

# ── История ──
MIN_HISTORY_DAYS = 45          # без базы поток не с чем сравнивать
BASE_WINDOW = 30               # окно нормировки
RECENT_WINDOW = 3              # что считается свежим

# ── Поток тейкеров ──
TAKER_SHIFT_MIN = 0.05         # сдвиг доли покупок, с которого поток сменился
TAKER_SHIFT_STRONG = 0.10
TAKER_DOMINANT = 0.58          # явное доминирование покупателя в свежих барах

# ── Кумулятивная дельта ──
CVD_DIV_WINDOW = 60
CVD_PRICE_TOLERANCE = 1.03     # цена «не выше» прошлого минимума с допуском
CVD_RISE_BARS = 10             # окно проверки подъёма дельты

# ── Поглощение ──
ABSORPTION_MULT = 2.0          # объём на единицу диапазона против базы
ABSORPTION_BARS = 7            # где ищем
ABSORPTION_MAX_RANGE = 0.7     # диапазон свечи не шире 70% от среднего

# ── Плечи ──
OI_CHANGE_MIN = 4.0            # значимое изменение открытого интереса, %
FUNDING_NEGATIVE = -0.00005    # ставка, при которой рынок платит лонгам

# ── Контекст ──
BTC_SYMBOL = "BTCUSDT"
BTC_WEAK_PCT = -3.0            # падение BTC за сутки, при котором глушим скор
BTC_DAMPEN = 0.75              # множитель к скору в этом случае

MIN_SCORE = 45


@dataclass
class FlowSignal:
    detected: bool = False
    score: int = 0

    # поток тейкеров
    taker_ratio_now: float = 0.0
    taker_ratio_recent: float = 0.0
    taker_ratio_base: float = 0.0
    taker_shift: float = 0.0
    taker_flipped: bool = False
    taker_4h_ratio: float = 0.0
    taker_4h_flipped: bool = False

    # кумулятивная дельта
    cvd_rising: bool = False
    cvd_divergence: bool = False
    cvd_note: str = ""

    # поглощение
    absorption: bool = False
    absorption_ratio: float = 0.0
    absorption_bar_ago: int = 0

    # плечи
    oi_change_pct: float = 0.0
    funding_rate: float = 0.0
    leverage_regime: str = ""      # accumulation | squeeze | distribution | capitulation
    leverage_bullish: bool = False
    leverage_note: str = ""

    # контекст
    price_change_pct: float = 0.0
    btc_change_pct: float = 0.0
    dampened: bool = False

    strength_label: str = ""
    verdict: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────
# Разбор потока
# ─────────────────────────────────────────────────────────────
def _taker_ratios(kl: list, tail: int) -> list[float]:
    """Доля агрессивных покупок в объёме каждой свечи.

    0.5 — равновесие, выше — покупатель бьёт по аскам,
    ниже — продавец льёт в биды.
    """
    out: list[float] = []
    for k in kl[-tail:]:
        try:
            total = float(k[K_QUOTE_VOLUME])
            buys = float(k[K_TAKER_BUY_QUOTE])
        except (TypeError, ValueError, IndexError):
            out.append(0.5)
            continue
        out.append(buys / total if total > 0 else 0.5)
    return out


def _cvd(kl: list, tail: int) -> list[float]:
    """Кумулятивная дельта тейкеров.

    Отличие от OBV: OBV приписывает свече весь объём по знаку закрытия,
    здесь берётся реальное соотношение агрессоров внутри свечи.
    """
    out: list[float] = []
    acc = 0.0
    for k in kl[-tail:]:
        try:
            total = float(k[K_QUOTE_VOLUME])
            buys = float(k[K_TAKER_BUY_QUOTE])
        except (TypeError, ValueError, IndexError):
            out.append(acc)
            continue
        acc += buys - (total - buys)
        out.append(acc)
    return out


def _swing_lows(seq: list[float], lookback: int = 3) -> list[int]:
    out: list[int] = []
    for i in range(lookback, len(seq) - lookback):
        left = seq[i - lookback:i]
        right = seq[i + 1:i + 1 + lookback]
        if all(seq[i] <= x for x in left) and all(seq[i] <= x for x in right):
            out.append(i)
    return out


def _mean(seq: list[float]) -> float:
    return sum(seq) / len(seq) if seq else 0.0


# ─────────────────────────────────────────────────────────────
# Компоненты
# ─────────────────────────────────────────────────────────────
def _detect_taker_flip(kl: list) -> tuple[float, float, float, float, bool]:
    """Сменился ли характер потока в пользу покупателя.

    Сравниваем свежие бары с собственной базой монеты, а не с 0.5:
    у каждой пары свой нормальный уровень агрессии.
    """
    ratios = _taker_ratios(kl, BASE_WINDOW + 1)
    if len(ratios) < RECENT_WINDOW + 5:
        return 0.0, 0.0, 0.0, 0.0, False

    now = ratios[-1]
    recent = _mean(ratios[-RECENT_WINDOW:])
    base = _mean(ratios[:-RECENT_WINDOW])
    shift = recent - base

    flipped = shift >= TAKER_SHIFT_MIN and recent >= TAKER_DOMINANT
    return now, recent, base, shift, flipped


def _detect_cvd_divergence(kl: list) -> tuple[bool, bool, str]:
    """Цена обновляет минимум, дельта — нет: агрессивные продажи иссякают."""
    closes = series(kl, K_CLOSE, tail=CVD_DIV_WINDOW)
    cvd = _cvd(kl, CVD_DIV_WINDOW)

    rising = False
    if len(cvd) >= CVD_RISE_BARS:
        rising = cvd[-1] > cvd[-CVD_RISE_BARS]

    if len(closes) < CVD_DIV_WINDOW or len(cvd) < CVD_DIV_WINDOW:
        return rising, False, ""

    p_idx = _swing_lows(closes, lookback=3)
    c_idx = _swing_lows(cvd, lookback=3)
    if len(p_idx) < 2 or len(c_idx) < 2:
        return rising, False, ""

    p1, p2 = closes[p_idx[-2]], closes[p_idx[-1]]
    c1, c2 = cvd[c_idx[-2]], cvd[c_idx[-1]]

    price_lower = p2 <= p1 * CVD_PRICE_TOLERANCE
    cvd_higher = c2 > c1

    if price_lower and cvd_higher:
        return rising, True, f"цена {p1:.6g}→{p2:.6g}, дельта разворачивается вверх"
    return rising, False, ""


def _detect_absorption(kl: list) -> tuple[bool, float, int]:
    """Много объёма при узком диапазоне: предложение принимают, цену держат."""
    highs = series(kl, K_HIGH, tail=BASE_WINDOW + ABSORPTION_BARS)
    lows = series(kl, K_LOW, tail=BASE_WINDOW + ABSORPTION_BARS)
    vols = series(kl, K_QUOTE_VOLUME, tail=BASE_WINDOW + ABSORPTION_BARS)
    closes = series(kl, K_CLOSE, tail=BASE_WINDOW + ABSORPTION_BARS)

    n = len(closes)
    if n < BASE_WINDOW:
        return False, 0.0, 0

    # База считается по барам до зоны поиска, чтобы искомый бар
    # не разбавлял собственный эталон
    base_end = n - ABSORPTION_BARS
    ranges = [
        (highs[i] - lows[i]) / closes[i]
        for i in range(base_end)
        if closes[i] > 0
    ]
    base_range = _mean(ranges)
    base_vol = _mean(vols[:base_end])
    if base_range <= 0 or base_vol <= 0:
        return False, 0.0, 0

    best_ratio = 0.0
    best_ago = 0
    found = False

    for i in range(base_end, n):
        if closes[i] <= 0:
            continue
        rng = (highs[i] - lows[i]) / closes[i]
        if rng <= 0:
            continue
        # Узкий бар — обязательное условие: широкий разгон это уже не поглощение
        if rng > base_range * ABSORPTION_MAX_RANGE:
            continue
        vol_x = vols[i] / base_vol
        ratio = vol_x / (rng / base_range)
        if ratio > best_ratio:
            best_ratio = ratio
            best_ago = n - 1 - i
        if ratio >= ABSORPTION_MULT * 2:
            found = True

    if best_ratio >= ABSORPTION_MULT:
        found = True
    return found, best_ratio, best_ago


def _detect_leverage(symbol: str, price_change_pct: float) -> tuple[float, float, str, bool, str]:
    """Режим плечей по связке цена × открытый интерес плюс знак фандинга.

    Четыре квадранта:
      цена ↑ OI ↑ — новые лонги, здоровый разгон
      цена ↑ OI ↓ — шортсквиз, топливо кончается быстро
      цена ↓ OI ↑ — набор шортов, давление продолжается
      цена ↓ OI ↓ — капитуляция плечей, часто дно
    """
    funding = get_funding_rate(symbol)

    hist = get_oi_history(symbol, period="1d", limit=30)
    oi_change = 0.0
    if hist and len(hist) >= 8:
        try:
            oi_now = float(hist[-1].get("sumOpenInterestValue", 0))
            oi_prev = float(hist[-8].get("sumOpenInterestValue", 0))
            if oi_prev > 0:
                oi_change = (oi_now / oi_prev - 1) * 100
        except (TypeError, ValueError):
            oi_change = 0.0

    price_up = price_change_pct > 0
    oi_up = oi_change >= OI_CHANGE_MIN
    oi_down = oi_change <= -OI_CHANGE_MIN

    if price_up and oi_up:
        regime, bullish = "accumulation", True
        note = f"новые лонги, OI {oi_change:+.0f}%"
    elif price_up and oi_down:
        regime, bullish = "squeeze", False
        note = f"шортсквиз, OI {oi_change:+.0f}% — топливо на исходе"
    elif not price_up and oi_up:
        regime, bullish = "distribution", False
        note = f"набор шортов, OI {oi_change:+.0f}%"
    elif not price_up and oi_down:
        regime, bullish = "capitulation", True
        note = f"плечи вымыло, OI {oi_change:+.0f}%"
    else:
        regime, bullish = "flat", False
        note = f"OI без движения ({oi_change:+.0f}%)"

    # Отрицательный фандинг при растущей цене: рынок платит лонгам,
    # шорты перегружены — сильное подтверждение разворота
    if funding <= FUNDING_NEGATIVE and price_up:
        bullish = True
        note += f", фандинг {funding * 100:.3f}% платят лонгам"

    return oi_change, funding, regime, bullish, note


def _btc_context() -> float:
    """Суточное изменение BTC. Разворот альта против падающего рынка — ловушка."""
    kl = klines_1d(BTC_SYMBOL)
    if not kl or len(kl) < 2:
        return 0.0
    opens = series(kl, K_OPEN, tail=1)
    closes = series(kl, K_CLOSE, tail=1)
    if not opens or opens[0] <= 0:
        return 0.0
    return (closes[0] / opens[0] - 1) * 100


# ─────────────────────────────────────────────────────────────
# Основной детектор
# ─────────────────────────────────────────────────────────────
def detect_flow(symbol: str) -> FlowSignal:
    """Разворот по потоку ордеров.

    Даже при недоборе порога возвращает объект с заполненными метриками
    потока — воронке нужно видеть, насколько монета не дотянула.
    """
    kl = klines_1d(symbol)
    if not kl or len(kl) < MIN_HISTORY_DAYS:
        return FlowSignal()

    opens = series(kl, K_OPEN, tail=2)
    closes = series(kl, K_CLOSE, tail=2)
    if not opens or opens[-1] <= 0:
        return FlowSignal()

    price_change_pct = (closes[-1] / opens[-1] - 1) * 100

    # ── Поток тейкеров на дневках ──
    t_now, t_recent, t_base, t_shift, t_flipped = _detect_taker_flip(kl)

    # ── Поток на 4h: смена характера видна на сутки раньше ──
    t4_ratio = 0.0
    t4_flipped = False
    kl4 = klines_4h(symbol)
    if kl4 and len(kl4) >= 60:
        r4 = _taker_ratios(kl4, 60)
        recent4 = _mean(r4[-6:])
        base4 = _mean(r4[:-6])
        t4_ratio = recent4
        t4_flipped = (recent4 - base4) >= TAKER_SHIFT_MIN and recent4 >= TAKER_DOMINANT

    # ── Кумулятивная дельта ──
    cvd_rising, cvd_div, cvd_note = _detect_cvd_divergence(kl)

    # ── Поглощение ──
    absorb, absorb_ratio, absorb_ago = _detect_absorption(kl)

    # ── Плечи ──
    oi_change, funding, regime, lev_bullish, lev_note = _detect_leverage(
        symbol, price_change_pct
    )

    # ── Ядро сигнала ──
    # Минимум одно из двух: поток сменился либо дельта расходится с ценой.
    # Поглощение и плечи сами по себе сигнал не рождают — только усиливают.
    has_core = t_flipped or cvd_div

    # ── Скоринг ──
    score = 0

    if t_flipped:
        score += 22
        if t_shift >= TAKER_SHIFT_STRONG:
            score += 8
    if t4_flipped:
        score += 10
    if cvd_div:
        score += 24
    if cvd_rising:
        score += 8
    if absorb:
        score += min(int(absorb_ratio * 5), 18)
    if lev_bullish:
        score += 14
    if regime == "squeeze":
        score -= 12          # рост без нового интереса долго не живёт
    if regime == "distribution":
        score -= 8
    if funding <= FUNDING_NEGATIVE:
        score += 6

    # ── Режим рынка ──
    btc_change = _btc_context()
    dampened = False
    if btc_change <= BTC_WEAK_PCT:
        score = int(score * BTC_DAMPEN)
        dampened = True

    score = max(0, min(score, 100))

    detected = has_core and score >= MIN_SCORE

    if score >= 75:
        strength = "экстремальный"
    elif score >= 60:
        strength = "сильный"
    elif score >= MIN_SCORE:
        strength = "умеренный"
    else:
        strength = ""

    # ── Вердикт ──
    verdict = ""
    if detected:
        parts = [f"FLOW Reversal ({strength})"]
        if t_flipped:
            parts.append(
                f"поток сменился: тейкер-покупки {t_base * 100:.0f}%→"
                f"{t_recent * 100:.0f}% объёма"
            )
        if t4_flipped:
            parts.append(f"на 4H подтверждено ({t4_ratio * 100:.0f}%)")
        if cvd_div:
            parts.append(f"дивергенция дельты: {cvd_note}")
        elif cvd_rising:
            parts.append("кумулятивная дельта растёт")
        if absorb:
            parts.append(
                f"поглощение ×{absorb_ratio:.1f}"
                + (f", {absorb_ago}д назад" if absorb_ago else ", сегодня")
            )
        parts.append(lev_note)
        if dampened:
            parts.append(f"скор снижен: BTC {btc_change:+.1f}% за сутки")
        verdict = ". ".join(parts) + "."

    return FlowSignal(
        detected=detected,
        score=score,
        taker_ratio_now=round(t_now, 4),
        taker_ratio_recent=round(t_recent, 4),
        taker_ratio_base=round(t_base, 4),
        taker_shift=round(t_shift, 4),
        taker_flipped=t_flipped,
        taker_4h_ratio=round(t4_ratio, 4),
        taker_4h_flipped=t4_flipped,
        cvd_rising=cvd_rising,
        cvd_divergence=cvd_div,
        cvd_note=cvd_note,
        absorption=absorb,
        absorption_ratio=round(absorb_ratio, 2),
        absorption_bar_ago=absorb_ago,
        oi_change_pct=round(oi_change, 2),
        funding_rate=funding,
        leverage_regime=regime,
        leverage_bullish=lev_bullish,
        leverage_note=lev_note,
        price_change_pct=round(price_change_pct, 2),
        btc_change_pct=round(btc_change, 2),
        dampened=dampened,
        strength_label=strength,
        verdict=verdict,
    )
