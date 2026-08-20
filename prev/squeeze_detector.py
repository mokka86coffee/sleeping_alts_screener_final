"""
squeeze_detector.py — детектор manipulated squeeze (DEXE-style памп).

Отличает "здоровый" тренд (KAITO, DIA) от "выжимания шортов на тонком стакане".
Работает на данных Binance Futures: klines + OI history + funding + premium index.

Публичный API:
  - analyze_squeeze(symbol) -> SqueezeSignal   (полный анализ, объект)
  - get_squeeze_tag(sig)    -> dict | None     (тег для карточки)
  - detect_squeeze(symbol, closes, vols) -> dict | None
        Адаптер под sleeping_alts_screener_final.py:
        возвращает {"detected": bool, "verdict": str, ...} или None.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import requests

log = logging.getLogger(__name__)

BINANCE_FAPI = "https://fapi.binance.com"
TIMEOUT = (8, 20)
HEADERS = {"User-Agent": "Mozilla/5.0 SleepingAlts/1.0"}


# ============================================================
# DATACLASS
# ============================================================
@dataclass
class SqueezeSignal:
    symbol: str
    risk_score: int = 0                 # 0-100
    risk_level: str = "none"            # none | low | medium | high | extreme
    is_squeeze: bool = False            # True если risk_score >= 60
    # Метрики
    price_change_14d_pct: float = 0.0
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


# ============================================================
# HTTP HELPERS
# ============================================================
def _get(url: str, params: dict | None = None) -> Any:
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT, headers=HEADERS)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.debug(f"squeeze GET {url} failed: {e}")
    return None


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_g = sum(gains[-period:]) / period
    avg_l = sum(losses[-period:]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100.0 - (100.0 / (1.0 + rs))


# ============================================================
# CORE
# ============================================================
def analyze_squeeze(symbol: str) -> SqueezeSignal:
    """
    Возвращает SqueezeSignal с оценкой риска manipulated squeeze.
    Символ — фьючерсный тикер Binance (напр. "DEXEUSDT").
    """
    sig = SqueezeSignal(symbol=symbol)

    # ─── 1. Klines 1d за 30 дней (futures) ───
    kl = _get(f"{BINANCE_FAPI}/fapi/v1/klines",
              {"symbol": symbol, "interval": "1d", "limit": 30})
    if not kl or len(kl) < 15:
        sig.verdict = "недостаточно данных для анализа"
        return sig

    closes = [float(k[4]) for k in kl]
    vols_futures = [float(k[7]) for k in kl]

    price_now = closes[-1]
    price_14d_ago = closes[-15] if len(closes) >= 15 else closes[0]
    price_7d_ago  = closes[-8]  if len(closes) >= 8  else closes[0]

    sig.price_change_14d_pct = (price_now / price_14d_ago - 1) * 100 if price_14d_ago > 0 else 0
    price_change_7d_pct = (price_now / price_7d_ago - 1) * 100 if price_7d_ago > 0 else 0

    sig.rsi_14 = _rsi(closes, 14)

    # Парабола: макс дневная свеча в последних 7 днях > 15% И суммарный рост > 50%
    max_daily = 0.0
    for i in range(max(1, len(closes) - 7), len(closes)):
        if closes[i - 1] > 0:
            daily = (closes[i] / closes[i - 1] - 1) * 100
            max_daily = max(max_daily, daily)
    sig.parabolic = (price_change_7d_pct > 50) and (max_daily > 15)

    # ─── 2. OI history 1d за 30 дней ───
    oi = _get(f"{BINANCE_FAPI}/futures/data/openInterestHist",
              {"symbol": symbol, "period": "1d", "limit": 30})
    if oi and len(oi) >= 14:
        oi_vals = [float(x.get("sumOpenInterestValue", 0)) for x in oi]
        oi_now = oi_vals[-1]
        oi_14d_ago = oi_vals[-15] if len(oi_vals) >= 15 else oi_vals[0]
        if oi_14d_ago > 0:
            sig.oi_change_14d_pct = (oi_now / oi_14d_ago - 1) * 100
            if abs(sig.price_change_14d_pct) > 1:
                sig.oi_price_ratio = sig.oi_change_14d_pct / sig.price_change_14d_pct

    # ─── 3. Funding rate history за 14 дней ───
    fr = _get(f"{BINANCE_FAPI}/fapi/v1/fundingRate",
              {"symbol": symbol, "limit": 100})
    if fr and len(fr) > 0:
        rates = [float(x.get("fundingRate", 0)) * 100 for x in fr]
        sig.funding_now = rates[-1]
        recent = rates[-21:] if len(rates) >= 21 else rates
        sig.funding_avg_7d = sum(recent) / len(recent)
        sig.funding_peak_14d = max(rates[-42:]) if len(rates) >= 42 else max(rates)

    # ─── 4. Spot vs Futures volume ───
    spot_kl = _get("https://api.binance.com/api/v3/klines",
                   {"symbol": symbol, "interval": "1d", "limit": 7})
    if spot_kl and len(spot_kl) >= 3:
        spot_vol_7d = sum(float(k[7]) for k in spot_kl)
        fut_vol_7d = sum(vols_futures[-7:]) if len(vols_futures) >= 7 else sum(vols_futures)
        if fut_vol_7d > 0:
            sig.spot_futures_ratio = spot_vol_7d / fut_vol_7d

    # ─── 5. SCORING ───
    score = 0
    reasons: list[str] = []

    if sig.parabolic:
        score += 25
        reasons.append(f"параболический рост (+{price_change_7d_pct:.0f}% за 7д, max свеча +{max_daily:.0f}%)")
    elif price_change_7d_pct > 30:
        score += 12
        reasons.append(f"агрессивный рост +{price_change_7d_pct:.0f}% за 7д")

    if sig.oi_price_ratio > 1.5 and sig.oi_change_14d_pct > 50:
        score += 25
        reasons.append(f"OI растёт быстрее цены (OI +{sig.oi_change_14d_pct:.0f}% vs цена +{sig.price_change_14d_pct:.0f}%)")
    elif sig.oi_change_14d_pct > 100:
        score += 15
        reasons.append(f"OI +{sig.oi_change_14d_pct:.0f}% за 14д — толпа лезет в перпы")

    if sig.funding_peak_14d > 0.15:
        score += 25
        reasons.append(f"пиковый funding {sig.funding_peak_14d:.3f}% (~{sig.funding_peak_14d*3*365:.0f}% APR)")
    elif sig.funding_peak_14d > 0.08:
        score += 15
        reasons.append(f"высокий funding {sig.funding_peak_14d:.3f}%")
    elif sig.funding_now < -0.05:
        score += 10
        reasons.append(f"funding развернулся в минус ({sig.funding_now:.3f}%) — шорты капитулировали")

    if 0 < sig.spot_futures_ratio < 0.25:
        score += 15
        reasons.append(f"памп в перпах (spot/fut = {sig.spot_futures_ratio:.2f})")
    elif 0 < sig.spot_futures_ratio < 0.5:
        score += 7
        reasons.append(f"спот отстаёт от фьючерсов (spot/fut = {sig.spot_futures_ratio:.2f})")

    if sig.rsi_14 > 85:
        score += 10
        reasons.append(f"RSI(14d) = {sig.rsi_14:.0f} — экстремальный перегрев")
    elif sig.rsi_14 > 75:
        score += 5
        reasons.append(f"RSI(14d) = {sig.rsi_14:.0f} — перекупленность")

    sig.risk_score = min(score, 100)
    if sig.risk_score >= 75:
        sig.risk_level = "extreme"
    elif sig.risk_score >= 60:
        sig.risk_level = "high"
    elif sig.risk_score >= 40:
        sig.risk_level = "medium"
    elif sig.risk_score >= 20:
        sig.risk_level = "low"
    else:
        sig.risk_level = "none"

    sig.is_squeeze = sig.risk_score >= 60
    sig.reasons = reasons
    sig.verdict = _build_verdict(sig)
    return sig


def _build_verdict(sig: SqueezeSignal) -> str:
    if sig.risk_level == "extreme":
        return ("⚠ EXTREME SQUEEZE RISK — классический manipulated памп. "
                "После разворота возможен откат 60-80%. "
                "Не входить в лонг, шортить только после подтверждённого разворота.")
    if sig.risk_level == "high":
        return ("⚠ HIGH SQUEEZE RISK — признаки выжимания шортов. "
                "Тренд может продолжиться, но risk/reward плохой. "
                "Если в позиции — фиксировать лесенкой, стопы жёсткие.")
    if sig.risk_level == "medium":
        return ("Умеренный squeeze-риск — часть роста обеспечена ликвидациями шортов, "
                "а не органическим спросом. Следить за funding и OI.")
    if sig.risk_level == "low":
        return "Небольшой перегрев на перпах, но пока в рамках здорового тренда."
    return "Признаков squeeze нет — движение выглядит органическим."


def get_squeeze_tag(sig: SqueezeSignal) -> dict | None:
    """Возвращает тег для отображения на карточке или None."""
    if sig.risk_level == "none":
        return None
    label_map = {
        "low":     ("SQUEEZE:LOW",     "tag-squeeze-low"),
        "medium":  ("SQUEEZE:MED",     "tag-squeeze-med"),
        "high":    ("⚠ SQUEEZE:HIGH",  "tag-squeeze-high"),
        "extreme": ("⚠ SQUEEZE:EXT",   "tag-squeeze-ext"),
    }
    text, cls = label_map[sig.risk_level]
    return {"text": text, "class": cls}


# ============================================================
# АДАПТЕР под sleeping_alts_screener_final.py
# ============================================================
def detect_squeeze(symbol: str,
                   closes: list[float] | None = None,
                   vols: list[float] | None = None) -> dict | None:
    """
    Совместимый интерфейс для главного скрипта.
    Аргументы closes/vols принимаются для совместимости, но не используются —
    внутри analyze_squeeze() данные тянутся заново по symbol (нужны OI, funding, spot).

    Возвращает dict с:
      - detected: bool  (True при risk_level >= high)
      - risk_level, risk_score
      - verdict, reasons
      - tag: {"text","class"} или None
    Или None при полном отсутствии данных.
    """
    try:
        sig = analyze_squeeze(symbol)
    except Exception as e:
        log.debug(f"detect_squeeze({symbol}) failed: {e}")
        return None

    if not sig or sig.risk_level == "none":
        return None

    return {
        "detected": sig.is_squeeze,          # True только при high/extreme
        "risk_level": sig.risk_level,
        "risk_score": sig.risk_score,
        "verdict": sig.verdict,
        "reasons": sig.reasons or [],
        "parabolic": sig.parabolic,
        "funding_peak_14d": sig.funding_peak_14d,
        "oi_change_14d_pct": sig.oi_change_14d_pct,
        "spot_futures_ratio": sig.spot_futures_ratio,
        "tag": get_squeeze_tag(sig),
    }
