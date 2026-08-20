"""Детектор manipulated squeeze — пампа на выжимании шортов.

Отличает здоровый тренд от выжимания на тонком стакане. Смотрит на связку
цена / открытый интерес / фандинг / соотношение спота и фьючерсов.

Публичный интерфейс:
  analyze_squeeze(symbol) -> SqueezeSignal    полный анализ
  get_squeeze_tag(sig)    -> dict | None      тег для карточки
  detect_squeeze(symbol)  -> dict | None      адаптер для пайплайна
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict

from analytics_indicators import rsi_series
from core_binance import (
    K_CLOSE, K_QUOTE_VOLUME,
    get_funding_history, get_oi_history, get_spot_klines,
    klines_1d, series,
)

log = logging.getLogger(__name__)

# ── Пороги ──
MIN_HISTORY_DAYS = 15
PARABOLIC_7D_PCT = 50.0     # рост за неделю для признания параболой
PARABOLIC_DAILY_PCT = 15.0  # максимальная дневная свеча внутри недели
AGGRESSIVE_7D_PCT = 30.0

OI_RATIO_ALERT = 1.5        # OI растёт в полтора раза быстрее цены
OI_GROWTH_ALERT = 50.0
OI_GROWTH_HIGH = 100.0

FUNDING_PEAK_EXTREME = 0.15
FUNDING_PEAK_HIGH = 0.08
FUNDING_NEGATIVE = -0.05

SPOT_RATIO_PUMP = 0.25      # спот почти не участвует
SPOT_RATIO_LAG = 0.50

RSI_EXTREME = 85.0
RSI_OVERBOUGHT = 75.0

# Фандинг начисляется трижды в сутки
FUNDING_PER_DAY = 3
FUNDING_WINDOW_7D = FUNDING_PER_DAY * 7
FUNDING_WINDOW_14D = FUNDING_PER_DAY * 14

LEVEL_EXTREME = 75
LEVEL_HIGH = 60
LEVEL_MEDIUM = 40
LEVEL_LOW = 20


@dataclass
class SqueezeSignal:
    symbol: str
    risk_score: int = 0             # 0..100
    risk_level: str = "none"        # none | low | medium | high | extreme
    is_squeeze: bool = False        # True при risk_score >= 60

    price_change_14d_pct: float = 0.0
    price_change_7d_pct: float = 0.0
    max_daily_pct: float = 0.0
    oi_change_14d_pct: float = 0.0
    oi_price_ratio: float = 0.0
    funding_now: float = 0.0
    funding_avg_7d: float = 0.0
    funding_peak_14d: float = 0.0
    spot_futures_ratio: float = 0.0
    rsi_14: float = 50.0
    parabolic: bool = False

    reasons: list[str] = field(default_factory=list)
    verdict: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def analyze_squeeze(symbol: str) -> SqueezeSignal:
    """Оценка риска manipulated squeeze по фьючерсному тикеру."""
    sig = SqueezeSignal(symbol=symbol)

    # ── 1. Дневные свечи фьючерса ──
    kl = klines_1d(symbol)
    if not kl or len(kl) < MIN_HISTORY_DAYS:
        sig.verdict = "недостаточно данных для анализа"
        return sig

    # Достаточно последних 30 дней
    closes = series(kl, K_CLOSE, tail=30)
    vols_futures = series(kl, K_QUOTE_VOLUME, tail=30)

    price_now = closes[-1]
    price_14d_ago = closes[-15] if len(closes) >= 15 else closes[0]
    price_7d_ago = closes[-8] if len(closes) >= 8 else closes[0]

    sig.price_change_14d_pct = (
        (price_now / price_14d_ago - 1) * 100 if price_14d_ago > 0 else 0.0
    )
    sig.price_change_7d_pct = (
        (price_now / price_7d_ago - 1) * 100 if price_7d_ago > 0 else 0.0
    )

    rsis = rsi_series(closes, 14)
    sig.rsi_14 = rsis[-1] if rsis else 50.0

    # Парабола: сильная неделя и хотя бы одна очень крупная свеча внутри
    max_daily = 0.0
    for i in range(max(1, len(closes) - 7), len(closes)):
        if closes[i - 1] > 0:
            daily = (closes[i] / closes[i - 1] - 1) * 100
            max_daily = max(max_daily, daily)
    sig.max_daily_pct = max_daily
    sig.parabolic = (
        sig.price_change_7d_pct > PARABOLIC_7D_PCT
        and max_daily > PARABOLIC_DAILY_PCT
    )

    # ── 2. История открытого интереса ──
    oi = get_oi_history(symbol, "1d", 30)
    if oi and len(oi) >= 14:
        oi_vals: list[float] = []
        for x in oi:
            try:
                oi_vals.append(float(x.get("sumOpenInterestValue", 0)))
            except (TypeError, ValueError):
                oi_vals.append(0.0)
        if oi_vals:
            oi_now = oi_vals[-1]
            oi_14d_ago = oi_vals[-15] if len(oi_vals) >= 15 else oi_vals[0]
            if oi_14d_ago > 0:
                sig.oi_change_14d_pct = (oi_now / oi_14d_ago - 1) * 100
                if abs(sig.price_change_14d_pct) > 1:
                    sig.oi_price_ratio = (
                        sig.oi_change_14d_pct / sig.price_change_14d_pct
                    )

    # ── 3. История фандинга ──
    fr = get_funding_history(symbol, 100)
    if fr:
        rates: list[float] = []
        for x in fr:
            try:
                rates.append(float(x.get("fundingRate", 0)) * 100)
            except (TypeError, ValueError):
                continue
        if rates:
            sig.funding_now = rates[-1]
            recent = rates[-FUNDING_WINDOW_7D:]
            sig.funding_avg_7d = sum(recent) / len(recent)
            peak_window = rates[-FUNDING_WINDOW_14D:]
            sig.funding_peak_14d = max(peak_window)

    # ── 4. Спот против фьючерсов ──
    spot_kl = get_spot_klines(symbol, "1d", 7)
    if spot_kl and len(spot_kl) >= 3:
        spot_vol_7d = sum(series(spot_kl, K_QUOTE_VOLUME))
        fut_vol_7d = sum(vols_futures[-7:]) if len(vols_futures) >= 7 else sum(vols_futures)
        if fut_vol_7d > 0:
            sig.spot_futures_ratio = spot_vol_7d / fut_vol_7d

    # ── 5. Скоринг ──
    score = 0
    reasons: list[str] = []

    if sig.parabolic:
        score += 25
        reasons.append(
            f"параболический рост +{sig.price_change_7d_pct:.0f}% за 7д, "
            f"максимальная свеча +{max_daily:.0f}%"
        )
    elif sig.price_change_7d_pct > AGGRESSIVE_7D_PCT:
        score += 12
        reasons.append(f"агрессивный рост +{sig.price_change_7d_pct:.0f}% за 7д")

    if sig.oi_price_ratio > OI_RATIO_ALERT and sig.oi_change_14d_pct > OI_GROWTH_ALERT:
        score += 25
        reasons.append(
            f"OI растёт быстрее цены: OI +{sig.oi_change_14d_pct:.0f}% "
            f"против цены +{sig.price_change_14d_pct:.0f}%"
        )
    elif sig.oi_change_14d_pct > OI_GROWTH_HIGH:
        score += 15
        reasons.append(f"OI +{sig.oi_change_14d_pct:.0f}% за 14д, толпа набилась в перпы")

    if sig.funding_peak_14d > FUNDING_PEAK_EXTREME:
        score += 25
        apr = sig.funding_peak_14d * FUNDING_PER_DAY * 365
        reasons.append(f"пиковый фандинг {sig.funding_peak_14d:.3f}%, около {apr:.0f}% годовых")
    elif sig.funding_peak_14d > FUNDING_PEAK_HIGH:
        score += 15
        reasons.append(f"высокий фандинг {sig.funding_peak_14d:.3f}%")
    elif sig.funding_now < FUNDING_NEGATIVE:
        score += 10
        reasons.append(f"фандинг ушёл в минус {sig.funding_now:.3f}%, шорты капитулировали")

    if 0 < sig.spot_futures_ratio < SPOT_RATIO_PUMP:
        score += 15
        reasons.append(f"памп идёт в перпах, спот к фьючерсу {sig.spot_futures_ratio:.2f}")
    elif 0 < sig.spot_futures_ratio < SPOT_RATIO_LAG:
        score += 7
        reasons.append(f"спот отстаёт от фьючерсов, {sig.spot_futures_ratio:.2f}")

    if sig.rsi_14 > RSI_EXTREME:
        score += 10
        reasons.append(f"RSI дневной {sig.rsi_14:.0f}, экстремальный перегрев")
    elif sig.rsi_14 > RSI_OVERBOUGHT:
        score += 5
        reasons.append(f"RSI дневной {sig.rsi_14:.0f}, перекупленность")

    sig.risk_score = min(score, 100)

    if sig.risk_score >= LEVEL_EXTREME:
        sig.risk_level = "extreme"
    elif sig.risk_score >= LEVEL_HIGH:
        sig.risk_level = "high"
    elif sig.risk_score >= LEVEL_MEDIUM:
        sig.risk_level = "medium"
    elif sig.risk_score >= LEVEL_LOW:
        sig.risk_level = "low"
    else:
        sig.risk_level = "none"

    sig.is_squeeze = sig.risk_score >= LEVEL_HIGH
    sig.reasons = reasons
    sig.verdict = _build_verdict(sig)
    return sig


def _build_verdict(sig: SqueezeSignal) -> str:
    if sig.risk_level == "extreme":
        return (
            "EXTREME SQUEEZE RISK — классический manipulated памп. "
            "После разворота возможен откат 60–80%. Лонг не открывать, "
            "шорт только после подтверждённого разворота."
        )
    if sig.risk_level == "high":
        return (
            "HIGH SQUEEZE RISK — признаки выжимания шортов. Тренд может "
            "продолжиться, но соотношение риска к прибыли плохое. "
            "Если в позиции — фиксировать лесенкой, стопы жёсткие."
        )
    if sig.risk_level == "medium":
        return (
            "Умеренный squeeze-риск: часть роста обеспечена ликвидациями "
            "шортов, а не органическим спросом. Следить за фандингом и OI."
        )
    if sig.risk_level == "low":
        return "Небольшой перегрев на перпах, пока в рамках здорового тренда."
    return "Признаков squeeze нет, движение выглядит органическим."


def get_squeeze_tag(sig: SqueezeSignal) -> dict | None:
    """Тег для карточки монеты либо None."""
    if sig.risk_level == "none":
        return None
    label_map = {
        "low": ("SQUEEZE LOW", "tag-squeeze-low"),
        "medium": ("SQUEEZE MED", "tag-squeeze-med"),
        "high": ("SQUEEZE HIGH", "tag-squeeze-high"),
        "extreme": ("SQUEEZE EXT", "tag-squeeze-ext"),
    }
    text, cls = label_map[sig.risk_level]
    return {"text": text, "class": cls}


def detect_squeeze(
    symbol: str,
    closes: list[float] | None = None,
    vols: list[float] | None = None,
) -> dict | None:
    """Адаптер для пайплайна.

    Аргументы closes и vols принимаются для обратной совместимости,
    но не используются: анализу нужны OI, фандинг и спот, которые всё
    равно тянутся отдельно. Данные свечей берутся из общего кэша,
    повторного сетевого запроса не происходит.
    """
    try:
        sig = analyze_squeeze(symbol)
    except Exception as e:
        log.debug(f"detect_squeeze({symbol}) не сработал: {e}")
        return None

    if not sig or sig.risk_level == "none":
        return None

    return {
        "detected": sig.is_squeeze,          # True только при high или extreme
        "risk_level": sig.risk_level,
        "risk_score": sig.risk_score,
        "verdict": sig.verdict,
        "reasons": sig.reasons or [],
        "parabolic": sig.parabolic,
        "funding_peak_14d": sig.funding_peak_14d,
        "funding_now": sig.funding_now,
        "oi_change_14d_pct": sig.oi_change_14d_pct,
        "spot_futures_ratio": sig.spot_futures_ratio,
        "rsi_14": sig.rsi_14,
        "tag": get_squeeze_tag(sig),
    }
