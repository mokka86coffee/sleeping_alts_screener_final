# ═══════════════════════════════════════════════════════════════
#  sleeping_alts_screener_final.py — ЧАСТЬ 1/3 НАЧАЛО
# ═══════════════════════════════════════════════════════════════
"""
SLEEPING ALTS SCREENER — институциональный скринер альткоинов
Stage 2: TAIKO + DEXE + Volume Surge + Twitter HOT + VIRAL HYPE
"""

from __future__ import annotations

import html
import math
import time
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from taiko_detector import detect_taiko, TaikoSignal
from dexe_detector import detect_dexe, DexeSignal
from volume_surge_detector import detect_volume_surge
from squeeze_detector import detect_squeeze
from external_data import get_fundamentals

# ─────────────────────────────────────────────────────────────
# Конфигурация
# ─────────────────────────────────────────────────────────────
BINANCE_FAPI = "https://fapi.binance.com"
BINANCE_SPOT = "https://api.binance.com"

REQUEST_TIMEOUT = (10, 30)
MAX_SYMBOLS = 200               # верхний предел монет для анализа
MIN_QUOTE_VOLUME_24H = 5_000_000  # $5M суточный оборот минимум

REPORT_HTML = Path("index.html")

STABLECOINS = {
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "USDP", "USDD",
    "UST", "PYUSD", "USDE", "USDS", "USDX",
}

EXCLUDE_TOKENS = {
    "BTC", "ETH",   # мажоры
}

# ─────────────────────────────────────────────────────────────
# Dataclass
# ─────────────────────────────────────────────────────────────
@dataclass
class Candidate:
    symbol: str
    bucket: str = "watch"
    rank: str = ""
    score: int = 0
    tags: list[dict] = field(default_factory=list)
    phase: dict = field(default_factory=dict)
    metrics: list[dict] = field(default_factory=list)
    dexe: dict | None = None
    analysis: str = ""
    buzz: dict | None = None
    strategy: str = ""
    squeeze: dict | None = None
    links: list[dict] = field(default_factory=list)
    surge: dict | None = None
    categories: list[str] = field(default_factory=list)
    is_viral: bool = False

# ─────────────────────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────────────────────
def _get(url: str, params: dict | None = None) -> Any:
    try:
        r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[HTTP ERROR] {url}: {e}")
        return None

def get_futures_tickers() -> list[dict]:
    data = _get(f"{BINANCE_FAPI}/fapi/v1/ticker/24hr")
    return data or []

def get_klines(symbol: str, interval: str, limit: int = 500) -> list[list]:
    data = _get(
        f"{BINANCE_FAPI}/fapi/v1/klines",
        {"symbol": symbol, "interval": interval, "limit": limit},
    )
    return data or []

def get_funding_rate(symbol: str) -> float:
    data = _get(
        f"{BINANCE_FAPI}/fapi/v1/premiumIndex",
        {"symbol": symbol},
    )
    try:
        return float(data.get("lastFundingRate", 0)) if data else 0.0
    except Exception:
        return 0.0

def get_open_interest(symbol: str) -> float:
    data = _get(
        f"{BINANCE_FAPI}/fapi/v1/openInterest",
        {"symbol": symbol},
    )
    try:
        return float(data.get("openInterest", 0)) if data else 0.0
    except Exception:
        return 0.0

def get_spot_ticker(symbol: str) -> dict | None:
    return _get(
        f"{BINANCE_SPOT}/api/v3/ticker/24hr",
        {"symbol": symbol},
    )

# ─────────────────────────────────────────────────────────────
# Индикаторы
# ─────────────────────────────────────────────────────────────
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

def stoch_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period * 2:
        return None
    rsis = []
    for i in range(period, len(closes)):
        gains = losses = 0.0
        for j in range(i - period + 1, i + 1):
            change = closes[j] - closes[j - 1]
            if change > 0:
                gains += change
            else:
                losses -= change
        rs = gains / losses if losses > 0 else 100
        rsi = 100 - (100 / (1 + rs))
        rsis.append(rsi)
    if len(rsis) < period:
        return None
    window = rsis[-period:]
    lo, hi = min(window), max(window)
    if hi == lo:
        return 50.0
    return (rsis[-1] - lo) / (hi - lo) * 100

def obv_series(closes: list[float], volumes: list[float]) -> list[float]:
    obv = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    return obv

def obv_slope_pct(closes: list[float], volumes: list[float], window: int = 20) -> float:
    obv = obv_series(closes, volumes)
    if len(obv) < window + 1:
        return 0.0
    old = obv[-window - 1]
    new = obv[-1]
    if old == 0:
        return 0.0
    return ((new - old) / abs(old)) * 100

def atr_pct(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return None
    atr = sum(trs[-period:]) / period
    return (atr / closes[-1]) * 100 if closes[-1] > 0 else None

def bb_squeeze_pct(closes: list[float], period: int = 20, mult: float = 2.0) -> float | None:
    if len(closes) < period:
        return None
    window = closes[-period:]
    m = sum(window) / period
    var = sum((x - m) ** 2 for x in window) / period
    sd = math.sqrt(var)
    upper = m + mult * sd
    lower = m - mult * sd
    width = upper - lower
    return (width / m) * 100 if m > 0 else None

def vortex_phase(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> dict:
    """Возвращает VI+, VI- и фазу тренда."""
    if len(closes) < period + 1:
        return {"vi_plus": 0, "vi_minus": 0, "phase": 0, "label": "no data"}
    vm_plus, vm_minus, trs = [], [], []
    for i in range(1, len(closes)):
        vm_plus.append(abs(highs[i] - lows[i - 1]))
        vm_minus.append(abs(lows[i] - highs[i - 1]))
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return {"vi_plus": 0, "vi_minus": 0, "phase": 0, "label": "no data"}
    sum_tr = sum(trs[-period:])
    sum_vm_plus = sum(vm_plus[-period:])
    sum_vm_minus = sum(vm_minus[-period:])
    vi_plus = sum_vm_plus / sum_tr if sum_tr > 0 else 0
    vi_minus = sum_vm_minus / sum_tr if sum_tr > 0 else 0
    diff = vi_plus - vi_minus
    if diff > 0.15:
        phase, label = 4, "TREND"
    elif diff > 0.05:
        phase, label = 3, "MOMENTUM"
    elif diff > -0.05:
        phase, label = 2, "BASE"
    else:
        phase, label = 1, "DECLINE"
    return {"vi_plus": round(vi_plus, 4), "vi_minus": round(vi_minus, 4),
            "phase": phase, "label": label}

# ─────────────────────────────────────────────────────────────
# Метрики для карточек
# ─────────────────────────────────────────────────────────────
def _pct(x: float | None, digits: int = 1) -> str:
    if x is None:
        return "—"
    sign = "+" if x > 0 else ""
    return f"{sign}{x:.{digits}f}%"

def _num(x: float | None, digits: int = 2) -> str:
    if x is None:
        return "—"
    return f"{x:.{digits}f}"

def _big(x: float | None) -> str:
    if x is None:
        return "—"
    if x >= 1e9:
        return f"${x/1e9:.2f}B"
    if x >= 1e6:
        return f"${x/1e6:.2f}M"
    if x >= 1e3:
        return f"${x/1e3:.1f}K"
    return f"${x:.0f}"

def collect_metrics(symbol: str) -> dict:
    """Собирает все базовые метрики для одной монеты."""
    kl_1d = get_klines(symbol, "1d", 200)
    kl_4h = get_klines(symbol, "4h", 200)
    kl_1h = get_klines(symbol, "1h", 200)

    if not kl_1d or len(kl_1d) < 30:
        return {}

    def _series(kl, idx):
        return [float(k[idx]) for k in kl]

    closes_1d = _series(kl_1d, 4)
    volumes_1d = _series(kl_1d, 5)
    highs_1d = _series(kl_1d, 2)
    lows_1d = _series(kl_1d, 3)

    closes_4h = _series(kl_4h, 4) if kl_4h else []
    volumes_4h = _series(kl_4h, 5) if kl_4h else []
    highs_4h = _series(kl_4h, 2) if kl_4h else []
    lows_4h = _series(kl_4h, 3) if kl_4h else []

    closes_1h = _series(kl_1h, 4) if kl_1h else []
    volumes_1h = _series(kl_1h, 5) if kl_1h else []

    price = closes_1d[-1]

    # изменения цены
    def _ch(series, back):
        if len(series) < back + 1:
            return None
        return ((series[-1] / series[-1 - back]) - 1) * 100

    ch_24h = _ch(closes_1d, 1)
    ch_7d  = _ch(closes_1d, 7)
    ch_30d = _ch(closes_1d, 30)

    # ATH
    ath = max(highs_1d)
    ath_drop = ((price / ath) - 1) * 100 if ath > 0 else 0

    # RVOL
    rvol_1h = 0.0
    if volumes_1h and len(volumes_1h) >= 24:
        avg_24 = sum(volumes_1h[-24:]) / 24
        last_vol = volumes_1h[-1]
        if avg_24 > 0:
            rvol_1h = last_vol / avg_24

    # OBV slope
    obv_slope = obv_slope_pct(closes_1d, volumes_1d, 20)

    # StochRSI 4H
    srsi = stoch_rsi(closes_4h, 14) if closes_4h else None

    # ATR %
    atr_p = atr_pct(highs_1d, lows_1d, closes_1d, 14)

    # BB squeeze
    bb = bb_squeeze_pct(closes_1d, 20, 2.0)

    # Vortex phase (4H)
    vp_4h = vortex_phase(highs_4h, lows_4h, closes_4h, 14) if closes_4h else {}

    # Funding & OI
    funding = get_funding_rate(symbol) * 100  # в %
    oi = get_open_interest(symbol)
    oi_usd = oi * price if oi > 0 else 0

    # Spot ratio
    spot = get_spot_ticker(symbol)
    spot_vol = float(spot.get("quoteVolume", 0)) if spot else 0
    fut_vol_24h = sum(volumes_1d[-1:]) * price if volumes_1d else 0
    spot_ratio = spot_vol / (spot_vol + fut_vol_24h) if (spot_vol + fut_vol_24h) > 0 else 0

    return {
        "symbol": symbol,
        "price": price,
        "ch_24h": ch_24h,
        "ch_7d": ch_7d,
        "ch_30d": ch_30d,
        "ath": ath,
        "ath_drop": ath_drop,
        "rvol_1h": rvol_1h,
        "obv_slope": obv_slope,
        "srsi_4h": srsi,
        "atr_pct": atr_p,
        "bb_pct": bb,
        "vortex_4h": vp_4h,
        "funding": funding,
        "oi": oi,
        "oi_usd": oi_usd,
        "spot_ratio": spot_ratio,
        "closes_1d": closes_1d,
        "volumes_1d": volumes_1d,
        "highs_1d": highs_1d,
        "lows_1d": lows_1d,
        "closes_4h": closes_4h,
        "closes_1h": closes_1h,
    }

# ═══════════════════════════════════════════════════════════════
#  ЧАСТЬ 1/3 КОНЕЦ
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
#  sleeping_alts_screener_final.py — ЧАСТЬ 2/3 НАЧАЛО
# ═══════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────
# Стратегия входа
# ─────────────────────────────────────────────────────────────
def build_strategy(m: dict, sq: dict | None, taiko_sig: TaikoSignal, dexe_sig: DexeSignal) -> str:
    """Возвращает короткую human-readable стратегию входа."""
    parts = []
    price = m["price"]

    if taiko_sig.detected:
        parts.append(
            f"🎯 TAIKO REVERSAL. Вход лесенкой от текущей ${price:.4g}, "
            f"стоп под минимум базы, тейки 1.3× / 2× / 3× от риска."
        )
        return " ".join(parts)

    if dexe_sig.detected:
        parts.append(
            f"🎰 DEXE POST-PUMP. Ждём отбоя от EMA200 (~${dexe_sig.ema200:.4g}). "
            f"Стоп под EMA, цель — возврат в диапазон до пампа."
        )
        return " ".join(parts)

    if sq and sq.get("detected"):
        parts.append(
            f"⚠ SQUEEZE MANIPULATED. Наблюдение, входы против движения рискованны."
        )
        return " ".join(parts)

    # Общая логика по фазе Vortex
    vp = m.get("vortex_4h", {})
    label = vp.get("label", "")
    if label == "TREND":
        parts.append(f"📈 TREND. Работать по тренду, коррекции откупать от EMA21.")
    elif label == "MOMENTUM":
        parts.append(f"⚡ MOMENTUM. Ищем подтверждение объёмом, вход по пробою.")
    elif label == "BASE":
        parts.append(f"📊 BASE. Диапазон, торговля от границ до пробоя.")
    elif label == "DECLINE":
        parts.append(f"📉 DECLINE. Лонги рискованны, ждать разворотной формации.")
    else:
        parts.append("Наблюдение.")

    return " ".join(parts)

# ─────────────────────────────────────────────────────────────
# Сборка кандидата
# ─────────────────────────────────────────────────────────────
def build_candidate(symbol: str, rank_idx: int) -> Candidate | None:
    m = collect_metrics(symbol)
    if not m:
        return None

    tags: list[dict] = []
    score = 0

    # ── Фаза Vortex ──
    vp = m.get("vortex_4h", {})
    phase = {
        "num": vp.get("phase", 0),
        "label": vp.get("label", "—"),
        "vi_plus": vp.get("vi_plus", 0),
        "vi_minus": vp.get("vi_minus", 0),
    }

    # ── Метрики карточки ──
    metrics = [
        {"key": "Цена",    "val": f"${m['price']:.4g}", "cls": ""},
        {"key": "24h",     "val": _pct(m["ch_24h"]),
         "cls": "up" if (m["ch_24h"] or 0) > 0 else "down" if (m["ch_24h"] or 0) < 0 else ""},
        {"key": "7d",      "val": _pct(m["ch_7d"]),
         "cls": "up" if (m["ch_7d"] or 0) > 0 else "down" if (m["ch_7d"] or 0) < 0 else ""},
        {"key": "30d",     "val": _pct(m["ch_30d"]),
         "cls": "up" if (m["ch_30d"] or 0) > 0 else "down" if (m["ch_30d"] or 0) < 0 else ""},
        {"key": "От ATH",  "val": _pct(m["ath_drop"]), "cls": "down"},
        {"key": "RVOL 1H", "val": f"{m['rvol_1h']:.2f}×", "cls": ""},
        {"key": "OBV",     "val": _pct(m["obv_slope"]),
         "cls": "up" if m["obv_slope"] > 0 else "down"},
        {"key": "StochRSI 4H", "val": _num(m["srsi_4h"], 1),
         "cls": ""},
        {"key": "ATR %",   "val": _num(m["atr_pct"], 2), "cls": ""},
        {"key": "BB width","val": _num(m["bb_pct"], 2), "cls": ""},
        {"key": "Funding", "val": f"{m['funding']:.4f}%",
         "cls": "up" if m["funding"] > 0 else "down"},
        {"key": "OI",      "val": _big(m["oi_usd"]), "cls": ""},
        {"key": "Spot ratio", "val": f"{m['spot_ratio']*100:.0f}%", "cls": ""},
    ]

    # ── Volume Surge ──
    vs = detect_volume_surge(symbol, m.get("volumes_1d") or [], m.get("closes_1d") or [])
    surge_block = None
    if vs.detected:
        surge_block = {
            "detected": True,
            "surge_ratio": vs.surge_ratio,
            "candle_type": vs.candle_type,
            "verdict": vs.verdict,
        }
        tags.append({
            "text": f"📊 VOL SURGE ×{vs.surge_ratio:.1f}",
            "class": "tag-pattern surge",
        })
        score += 12

    # ── Squeeze ──
    sq = detect_squeeze(symbol, m.get("closes_1d") or [], m.get("volumes_1d") or [])
    squeeze_block = None
    if sq and sq.get("detected"):
        squeeze_block = sq
        tags.append({
            "text": f"⚠ EUPHORIA SQUEEZE",
            "class": "tag-pattern euphoria",
        })
        score += 8

    # ── TAIKO ──
    taiko_sig = detect_taiko(symbol)

    # ── DEXE ──
    dexe_sig = detect_dexe(symbol)
    dexe_block = None
    if dexe_sig.detected:
        dexe_block = {
            "detected": True,
            "score": dexe_sig.score,
            "ema200": dexe_sig.ema200,
            "verdict": dexe_sig.verdict,
        }

    # ── Взаимоисключение TAIKO / DEXE ──
    if taiko_sig.detected and dexe_sig.detected:
        if taiko_sig.score >= dexe_sig.score:
            dexe_sig = DexeSignal()
            dexe_block = None
        else:
            taiko_sig = TaikoSignal()

    # ── Теги TAIKO / DEXE ──
    if taiko_sig.detected:
        if getattr(taiko_sig, "confirmed_breakout", False):
            tags.append({
                "text": f"✅ TAIKO CONFIRMED · {taiko_sig.score}",
                "class": "tag-pattern taiko",
            })
        else:
            tags.append({
                "text": f"◉ TAIKO REVERSAL · {taiko_sig.score}",
                "class": "tag-pattern taiko",
            })
        score += taiko_sig.score

    if dexe_sig.detected:
        tags.append({
            "text": f"◉ DEXE POST-PUMP · {dexe_sig.score}",
            "class": "tag-pattern dexe",
        })
        score += dexe_sig.score

    # ── Общий скор по фазе ──
    if vp.get("phase") == 4:
        score += 15
    elif vp.get("phase") == 3:
        score += 10
    elif vp.get("phase") == 2:
        score += 4

    if m["obv_slope"] > 50:
        score += 6
    if m["rvol_1h"] >= 3:
        score += 6

    # ── Классификация bucket ──
    if score >= 55:
        bucket = "strong"
    elif score >= 35:
        bucket = "good"
    elif score >= 20:
        bucket = "scout"
    else:
        bucket = "watch"

    # TAIKO / DEXE — всегда минимум scout
    if (taiko_sig.detected or dexe_sig.detected) and bucket == "watch":
        bucket = "scout"

    # ── Фундаменталка ──
    fund = get_fundamentals(symbol)
    if fund.categories:
        tags.append({"text": fund.categories[0], "class": "tag-cat"})
    elif fund.defillama_category:
        tags.append({"text": fund.defillama_category, "class": "tag-cat"})

    # Все категории — для секторных фильтров
    all_categories = list(fund.categories or [])
    if fund.defillama_category and fund.defillama_category not in all_categories:
        all_categories.append(fund.defillama_category)

    # ── Twitter Buzz (с уровнем) ──
    buzz = None
    if m["rvol_1h"] >= 3 and m["obv_slope"] > 20:
        buzz = {
            "level": "hot",
            "level_class": "buzz-hot", "level_text": "HOT",
            "text": "Резкий всплеск объёма + активное накопление. Внимание рынка на паре.",
        }
    elif m["rvol_1h"] >= 1.8:
        buzz = {
            "level": "warm",
            "level_class": "buzz-warm", "level_text": "WARM",
            "text": "Объём выше среднего, растёт интерес.",
        }
    elif m["rvol_1h"] >= 1.2:
        buzz = {
            "level": "cool",
            "level_class": "buzz-cool", "level_text": "COOL",
            "text": "Умеренная активность.",
        }
    else:
        buzz = {
            "level": "cold",
            "level_class": "buzz-cold", "level_text": "COLD",
            "text": "Низкий уровень внимания.",
        }

    # ── VIRAL HYPE детектор ──
    # Twitter HOT × Volume Surge × meme/gamefi сектор
    VIRAL_SECTOR_KEYWORDS = [
        "meme", "dog", "cat", "frog", "pepe",
        "game", "gaming", "gamefi", "play-to-earn",
        "metaverse", "virtual",
    ]
    cats_lower = " ".join(c.lower() for c in all_categories)
    in_speculative_sector = any(kw in cats_lower for kw in VIRAL_SECTOR_KEYWORDS)

    twitter_hot = (buzz or {}).get("level") == "hot"
    has_vol_surge = surge_block is not None and surge_block.get("detected")

    is_viral = twitter_hot and has_vol_surge and in_speculative_sector

    if is_viral:
        tags.insert(0, {
            "text": "🚀 VIRAL HYPE",
            "class": "tag-pattern viral",
        })

    # ── Аналитика и стратегия ──
    analysis_parts = []
    if taiko_sig.detected:
        analysis_parts.append(taiko_sig.verdict)
    if dexe_sig.detected:
        analysis_parts.append(dexe_sig.verdict)
    if vs.detected:
        analysis_parts.append(vs.verdict)
    analysis = " ".join(analysis_parts) if analysis_parts else ""

    strategy = build_strategy(m, sq, taiko_sig, dexe_sig)

    # ── Ссылки на графики ──
    links = [
        {"text": "TradingView", "url": f"https://www.tradingview.com/chart/?symbol=BINANCE:{symbol}.P"},
        {"text": "Binance",     "url": f"https://www.binance.com/en/futures/{symbol}"},
    ]

    return Candidate(
        symbol=symbol,
        bucket=bucket,
        rank=f"#{rank_idx:03d}",
        score=score,
        tags=tags,
        phase=phase,
        metrics=metrics,
        dexe=dexe_block,
        analysis=analysis,
        buzz=buzz,
        strategy=strategy,
        squeeze=squeeze_block,
        links=links,
        surge=surge_block,
        categories=all_categories,
        is_viral=is_viral,
    )

# ═══════════════════════════════════════════════════════════════
#  ЧАСТЬ 2/3 КОНЕЦ
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
#  sleeping_alts_screener_final.py — ЧАСТЬ 3a/3 НАЧАЛО
# ═══════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────
# HTML утилиты
# ─────────────────────────────────────────────────────────────
def esc(x: Any) -> str:
    return html.escape(str(x), quote=True)

# ─────────────────────────────────────────────────────────────
# Построение HTML отчёта
# ─────────────────────────────────────────────────────────────
def build_html(candidates: list[Candidate]) -> str:
    rows = [c.__dict__ for c in candidates]

    # ── Разбивка по bucket ──
    strong = [r for r in rows if r["bucket"] == "strong"]
    good   = [r for r in rows if r["bucket"] == "good"]
    scout  = [r for r in rows if r["bucket"] == "scout"]
    watch  = [r for r in rows if r["bucket"] == "watch"]

    taiko = [r for r in rows if any("TAIKO" in t.get("text", "") for t in r.get("tags") or [])]
    dexe  = [r for r in rows if any("DEXE"  in t.get("text", "") for t in r.get("tags") or [])]
    viral = [r for r in rows if r.get("is_viral")]

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    css = """
    :root{
      --bg:#0a0e1a; --panel:#111827; --panel2:#1f2937; --border:#374151;
      --text:#e8ecf5; --muted:#9ca3af; --accent:#22d3ee;
      --up:#10B981; --down:#EF4444;
    }
    *{box-sizing:border-box}
    body{background:var(--bg);color:var(--text);font-family:'Inter',-apple-system,sans-serif;
         margin:0;padding:16px;font-size:13px;line-height:1.5}
    a{color:var(--accent);text-decoration:none}
    h1{font-size:20px;letter-spacing:2px;margin:0 0 4px;font-weight:900}
    .subtitle{color:var(--muted);font-size:11px;letter-spacing:1.5px;margin-bottom:16px}

    /* === СТАТИСТИКА (плашки) === */
    .stats{display:grid;grid-template-columns:repeat(7,1fr);gap:8px;margin-bottom:20px}
    .stat{position:relative;background:linear-gradient(135deg,var(--panel) 0%,var(--panel2) 100%);
          border:1px solid var(--border);border-radius:6px;padding:10px 12px;cursor:pointer;
          transition:all 0.2s;border-left:3px solid var(--stat-color,#6b7280)}
    .stat:hover{border-color:var(--stat-color,#6b7280);transform:translateY(-1px)}
    .stat-label{color:var(--muted);font-size:10px;letter-spacing:1.5px;font-weight:700;text-transform:uppercase}
    .stat-value{color:var(--stat-color,var(--text));font-size:20px;font-weight:900;margin:2px 0}
    .stat-desc{color:var(--muted);font-size:10px;letter-spacing:.5px}
    .stat-tt{position:absolute;top:calc(100% + 4px);left:0;min-width:280px;max-width:400px;
             background:#0a0e1a;border:1px solid var(--stat-color,var(--border));border-radius:6px;
             padding:8px;font-size:11px;z-index:10000;opacity:0;pointer-events:none;
             transition:opacity 0.15s;max-height:400px;overflow-y:auto;
             box-shadow:0 8px 24px rgba(0,0,0,0.5)}
    .stat-tt::before{content:"";position:absolute;top:-4px;left:0;right:0;height:4px}
    .stat:hover .stat-tt{opacity:1;pointer-events:auto;transition-delay:0s}
    .stat-tt:hover{opacity:1;pointer-events:auto}
    .stats .stat:nth-child(n+6) .stat-tt{left:auto;right:0}
    .stat-tt-row{display:flex;justify-content:space-between;padding:4px 6px;border-bottom:1px solid var(--border)}
    .stat-tt-row:last-child{border-bottom:none}
    .stat-tt-row:hover{background:var(--panel2)}
    .stat-tt-sym{color:var(--text);font-weight:800}
    .stat-tt-score{color:var(--stat-color,var(--accent));font-weight:800}

    /* цвета плашек */
    .stat-viral{--stat-color:#f472b6;background:linear-gradient(135deg,var(--panel) 0%,rgba(244,114,182,0.08) 100%)}
    .stat-taiko{--stat-color:#22d3ee}
    .stat-dexe{--stat-color:#f472b6}
    .stat-strong{--stat-color:#10B981}
    .stat-good{--stat-color:#22d3ee}
    .stat-scout{--stat-color:#fbbf24}
    .stat-watch{--stat-color:#6b7280}

    /* === СЕКЦИИ === */
    .section-title{color:var(--section-color,var(--accent));font-size:14px;letter-spacing:2.5px;
                   text-transform:uppercase;font-weight:800;margin:24px 0 10px;
                   border-bottom:1px solid var(--border);padding-bottom:6px}
    .section-count{color:var(--muted);font-size:12px;margin-left:8px;letter-spacing:1px}
    .section-viral{--section-color:#f472b6}
    .section-taiko{--section-color:#22d3ee}
    .section-dexe{--section-color:#f472b6}
    .section-strong{--section-color:#10B981}
    .section-good{--section-color:#22d3ee}
    .section-scout{--section-color:#fbbf24}
    .section-watch{--section-color:#6b7280}

    /* === КАРТОЧКИ === */
    .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px;margin-bottom:20px}
    .card{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:12px;
          transition:all 0.2s}
    .card:hover{border-color:var(--accent);transform:translateY(-2px);box-shadow:0 4px 16px rgba(34,211,238,0.15)}
    .card-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
    .card-sym{font-size:16px;font-weight:900;letter-spacing:1px}
    .card-rank{color:var(--muted);font-size:11px;font-weight:700}
    .card-score{background:var(--panel2);color:var(--accent);padding:2px 8px;border-radius:4px;
                font-size:11px;font-weight:800;letter-spacing:.5px}

    .tags{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px}
    .tag{display:inline-block;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:700;
         letter-spacing:.5px;text-transform:uppercase}
    .tag-cat{background:rgba(107,114,128,0.2);color:#9ca3af;border:1px solid var(--border)}
    .tag-pattern{background:rgba(34,211,238,0.15);color:var(--accent);border:1px solid rgba(34,211,238,0.4)}
    .tag-pattern.taiko{background:rgba(34,211,238,0.15);color:#22d3ee;border:1px solid rgba(34,211,238,0.5)}
    .tag-pattern.dexe{background:rgba(244,114,182,0.15);color:#f472b6;border:1px solid rgba(244,114,182,0.5)}
    .tag-pattern.surge{background:rgba(245,158,11,0.15);color:#F59E0B;border:1px solid rgba(245,158,11,0.5)}
    .tag-pattern.euphoria{background:rgba(244,114,182,0.15);color:#f472b6;border:1px solid rgba(244,114,182,0.4)}
    .tag-pattern.viral{background:linear-gradient(90deg,rgba(244,114,182,0.18),rgba(167,139,250,0.18));
                       color:#f9a8d4;border:1px solid rgba(244,114,182,0.5);animation:pulse 2.4s infinite;
                       font-weight:900}
    @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.75}}

    .phase{display:flex;align-items:center;gap:6px;margin-bottom:8px;font-size:11px}
    .phase-badge{padding:2px 6px;border-radius:3px;font-weight:800;letter-spacing:.5px}
    .phase-4{background:rgba(16,185,129,0.15);color:#10B981}
    .phase-3{background:rgba(34,211,238,0.15);color:#22d3ee}
    .phase-2{background:rgba(251,191,36,0.15);color:#fbbf24}
    .phase-1{background:rgba(239,68,68,0.15);color:#EF4444}
    .phase-0{background:rgba(107,114,128,0.2);color:#6b7280}

    .metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:4px 12px;margin-bottom:8px;
             font-size:11px}
    .metric{display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px dashed var(--border)}
    .metric-key{color:var(--muted)}
    .metric-val{font-weight:700}
    .metric-val.up{color:var(--up)}
    .metric-val.down{color:var(--down)}

    .buzz{margin:8px 0;padding:6px 8px;border-radius:4px;font-size:11px;line-height:1.4}
    .buzz-hot{background:rgba(244,114,182,0.1);border-left:2px solid #f472b6}
    .buzz-warm{background:rgba(245,158,11,0.08);border-left:2px solid #F59E0B}
    .buzz-cool{background:rgba(34,211,238,0.08);border-left:2px solid #22d3ee}
    .buzz-cold{background:rgba(107,114,128,0.08);border-left:2px solid #6b7280}
    .buzz-level{font-weight:800;letter-spacing:1px;margin-right:6px}

    .analysis{background:rgba(34,211,238,0.05);border-left:2px solid var(--accent);
              padding:6px 8px;font-size:11px;line-height:1.4;margin:8px 0;color:#d1d5db}
    .strategy{background:rgba(16,185,129,0.05);border-left:2px solid var(--up);
              padding:6px 8px;font-size:11px;line-height:1.4;margin:8px 0;color:#d1d5db}
    .squeeze{background:rgba(244,114,182,0.05);border-left:2px solid #f472b6;
             padding:6px 8px;font-size:11px;line-height:1.4;margin:8px 0;color:#d1d5db}

    .links{display:flex;gap:8px;margin-top:8px;padding-top:8px;border-top:1px solid var(--border)}
    .link{color:var(--accent);font-size:11px;font-weight:700;letter-spacing:.5px}
    """

    # ── Render функции ──
    def render_stat_tile(label: str, count: int, desc: str, cls: str, items: list) -> str:
        tt_rows = ""
        for it in sorted(items, key=lambda x: -x.get("score", 0))[:20]:
            sym = it.get("symbol", "")
            sc = it.get("score", 0)
            tv = f"https://www.tradingview.com/chart/?symbol=BINANCE:{sym}.P"
            tt_rows += (
                f'<div class="stat-tt-row">'
                f'<a href="{tv}" target="_blank" rel="noopener" class="stat-tt-sym">{esc(sym)}</a>'
                f'<span class="stat-tt-score">{esc(sc)}</span>'
                f'</div>'
            )
        if not tt_rows:
            tt_rows = '<div class="stat-tt-row"><span class="stat-tt-sym" style="color:#6b7280">пусто</span></div>'

        return f"""
        <div class="stat {cls}">
          <div class="stat-label">{esc(label)}</div>
          <div class="stat-value">{count}</div>
          <div class="stat-desc">{esc(desc)}</div>
          <div class="stat-tt">{tt_rows}</div>
        </div>
        """

    def render_card(c: dict) -> str:
        sym = c.get("symbol", "")
        rank = c.get("rank", "")
        score = c.get("score", 0)
        tags = c.get("tags", []) or []
        phase = c.get("phase", {}) or {}
        metrics = c.get("metrics", []) or []
        buzz = c.get("buzz") or {}
        analysis = c.get("analysis", "") or ""
        strategy = c.get("strategy", "") or ""
        squeeze = c.get("squeeze") or {}
        links = c.get("links", []) or []

        tags_html = "".join(
            f'<span class="tag {esc(t.get("class",""))}">{esc(t.get("text",""))}</span>'
            for t in tags
        )

        phase_num = phase.get("num", 0)
        phase_html = f"""
        <div class="phase">
          <span class="phase-badge phase-{phase_num}">{esc(phase.get("label","—"))}</span>
          <span style="color:var(--muted)">VI+ {esc(phase.get("vi_plus","—"))} · VI- {esc(phase.get("vi_minus","—"))}</span>
        </div>
        """

        metrics_html = "".join(
            f'<div class="metric"><span class="metric-key">{esc(mm.get("key",""))}</span>'
            f'<span class="metric-val {esc(mm.get("cls",""))}">{esc(mm.get("val",""))}</span></div>'
            for mm in metrics
        )

        buzz_html = ""
        if buzz:
            buzz_html = f"""
            <div class="buzz {esc(buzz.get("level_class",""))}">
              <span class="buzz-level">{esc(buzz.get("level_text",""))}</span>{esc(buzz.get("text",""))}
            </div>
            """

        analysis_html = f'<div class="analysis">{esc(analysis)}</div>' if analysis else ""
        strategy_html = f'<div class="strategy">{esc(strategy)}</div>' if strategy else ""
        squeeze_html = ""
        if squeeze and squeeze.get("verdict"):
            squeeze_html = f'<div class="squeeze">{esc(squeeze.get("verdict",""))}</div>'

        links_html = "".join(
            f'<a class="link" href="{esc(l.get("url",""))}" target="_blank" rel="noopener">{esc(l.get("text",""))} ↗</a>'
            for l in links
        )

        return f"""
        <div class="card">
          <div class="card-head">
            <div>
              <span class="card-sym">{esc(sym)}</span>
              <span class="card-rank" style="margin-left:6px">{esc(rank)}</span>
            </div>
            <div class="card-score">SCORE {esc(score)}</div>
          </div>
          <div class="tags">{tags_html}</div>
          {phase_html}
          <div class="metrics">{metrics_html}</div>
          {buzz_html}
          {analysis_html}
          {strategy_html}
          {squeeze_html}
          <div class="links">{links_html}</div>
        </div>
        """

# ═══════════════════════════════════════════════════════════════
#  ЧАСТЬ 3a/3 КОНЕЦ
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
#  sleeping_alts_screener_final.py — ЧАСТЬ 3b/3 НАЧАЛО
# ═══════════════════════════════════════════════════════════════

    def render_volume_surge_section(candidates: list) -> str:
        """Таблица монет с аномальным объёмом на дневке."""
        surge_items = [c for c in candidates if (c.get("surge") or {}).get("detected")]
        if not surge_items:
            return ""

        surge_items.sort(
            key=lambda c: (c.get("surge") or {}).get("surge_ratio", 0),
            reverse=True,
        )

        html_str = """
        <div style="margin:24px 0;">
          <h2 style="color:#F59E0B;font-size:14px;letter-spacing:2.5px;text-transform:uppercase;
                     font-weight:800;margin-bottom:10px;">
            📊 Аномальные объёмы (дневка)
          </h2>
          <p style="color:#9ca3af;font-size:12px;margin-bottom:12px;">
            Дневной объём в 3+ раза выше среднего за 20 дней. Ранний сигнал перелома интереса.
          </p>
          <table style="width:100%;border-collapse:collapse;font-size:13px;background:#111827;">
            <thead>
              <tr style="background:#1f2937;color:#d1d5db;">
                <th style="padding:8px 10px;text-align:left;">СИМВОЛ</th>
                <th style="padding:8px 10px;text-align:right;">SURGE</th>
                <th style="padding:8px 10px;text-align:right;">24H</th>
                <th style="padding:8px 10px;text-align:left;">СВЕЧА</th>
                <th style="padding:8px 10px;text-align:left;">ВЕРДИКТ</th>
                <th style="padding:8px 10px;text-align:center;">TV</th>
              </tr>
            </thead>
            <tbody>
        """

        def _find_metric(metrics_list, key):
            for mm in (metrics_list or []):
                if mm.get("key") == key:
                    return mm.get("val", ""), mm.get("cls", "")
            return "", ""

        for c in surge_items:
            sym = c.get("symbol", "")
            surge = c.get("surge") or {}
            ratio = surge.get("surge_ratio", 0)
            candle = surge.get("candle_type", "—")
            verdict = surge.get("verdict", "")
            ch24_val, ch24_cls = _find_metric(c.get("metrics"), "24h")
            ch24_color = "#10B981" if ch24_cls == "up" else ("#EF4444" if ch24_cls == "down" else "#e8ecf5")
            tv = f"https://www.tradingview.com/chart/?symbol=BINANCE:{sym}.P"

            html_str += f"""
              <tr style="border-bottom:1px solid #374151;">
                <td style="padding:8px 10px;font-weight:800;color:#e8ecf5;">{esc(sym)}</td>
                <td style="padding:8px 10px;text-align:right;color:#F59E0B;font-weight:800;">×{ratio:.1f}</td>
                <td style="padding:8px 10px;text-align:right;color:{ch24_color};font-weight:700;">{esc(ch24_val)}</td>
                <td style="padding:8px 10px;color:#d1d5db;">{esc(candle)}</td>
                <td style="padding:8px 10px;color:#9ca3af;font-size:11px;">{esc(verdict)}</td>
                <td style="padding:8px 10px;text-align:center;">
                  <a href="{tv}" target="_blank" rel="noopener" style="color:#22d3ee;font-weight:700;">TV↗</a>
                </td>
              </tr>
            """
        html_str += "</tbody></table></div>"
        return html_str

    def render_twitter_hot_section(candidates: list) -> str:
        """Таблица монет с Twitter Buzz = HOT."""
        hot_items = [c for c in candidates if (c.get("buzz") or {}).get("level") == "hot"]
        if not hot_items:
            return ""

        hot_items.sort(key=lambda c: -c.get("score", 0))

        html_str = """
        <div style="margin:24px 0;">
          <h2 style="color:#a78bfa;font-size:14px;letter-spacing:2.5px;text-transform:uppercase;
                     font-weight:800;margin-bottom:10px;">
            🔥 Twitter Buzz — HOT
          </h2>
          <p style="color:#9ca3af;font-size:12px;margin-bottom:12px;">
            Монеты с резким всплеском объёма и активным накоплением — часто совпадает с волной упоминаний в X/Twitter.
          </p>
          <table style="width:100%;border-collapse:collapse;font-size:13px;background:#111827;">
            <thead>
              <tr style="background:#1f2937;color:#d1d5db;">
                <th style="padding:8px 10px;text-align:left;">СИМВОЛ</th>
                <th style="padding:8px 10px;text-align:right;">SCORE</th>
                <th style="padding:8px 10px;text-align:right;">24H</th>
                <th style="padding:8px 10px;text-align:right;">RVOL 1H</th>
                <th style="padding:8px 10px;text-align:right;">OBV</th>
                <th style="padding:8px 10px;text-align:left;">СЕТАП</th>
                <th style="padding:8px 10px;text-align:center;">TV</th>
              </tr>
            </thead>
            <tbody>
        """

        def _find_metric(metrics_list, key):
            for mm in (metrics_list or []):
                if mm.get("key") == key:
                    return mm.get("val", ""), mm.get("cls", "")
            return "", ""

        def _setup_label(cand):
            for t in (cand.get("tags") or []):
                text = t.get("text", "")
                if "VIRAL HYPE" in text:       return ("🚀 VIRAL",      "#f472b6")
                if "TAIKO CONFIRMED" in text:  return ("✅ TAIKO CONF", "#22d3ee")
                if "TAIKO REVERSAL" in text:   return ("◉ TAIKO",       "#22d3ee")
                if "DEXE POST-PUMP" in text:   return ("🎰 DEXE",       "#f472b6")
                if "VOL SURGE" in text:        return ("📊 SURGE",      "#F59E0B")
                if "EUPHORIA" in text:         return ("⚠ EUPHORIA",   "#f472b6")
            return ("—", "#6b7280")

        for c in hot_items:
            sym = c.get("symbol", "")
            score = c.get("score", 0)
            ch24_val, ch24_cls = _find_metric(c.get("metrics"), "24h")
            rvol_val, _        = _find_metric(c.get("metrics"), "RVOL 1H")
            obv_val, obv_cls   = _find_metric(c.get("metrics"), "OBV")
            ch24_color = "#10B981" if ch24_cls == "up" else ("#EF4444" if ch24_cls == "down" else "#e8ecf5")
            obv_color  = "#10B981" if obv_cls  == "up" else ("#EF4444" if obv_cls  == "down" else "#e8ecf5")
            setup_text, setup_color = _setup_label(c)
            tv = f"https://www.tradingview.com/chart/?symbol=BINANCE:{sym}.P"

            html_str += f"""
              <tr style="border-bottom:1px solid #374151;">
                <td style="padding:8px 10px;font-weight:800;color:#e8ecf5;">{esc(sym)}</td>
                <td style="padding:8px 10px;text-align:right;color:#a78bfa;font-weight:800;">{esc(score)}</td>
                <td style="padding:8px 10px;text-align:right;color:{ch24_color};font-weight:700;">{esc(ch24_val)}</td>
                <td style="padding:8px 10px;text-align:right;color:#22d3ee;font-weight:700;">{esc(rvol_val)}</td>
                <td style="padding:8px 10px;text-align:right;color:{obv_color};font-weight:700;">{esc(obv_val)}</td>
                <td style="padding:8px 10px;color:{setup_color};font-weight:800;font-size:11px;">{esc(setup_text)}</td>
                <td style="padding:8px 10px;text-align:center;">
                  <a href="{tv}" target="_blank" rel="noopener" style="color:#22d3ee;font-weight:700;">TV↗</a>
                </td>
              </tr>
            """
        html_str += "</tbody></table></div>"
        return html_str

    def render_viral_hype_section(candidates: list) -> str:
        """VIRAL HYPE — Twitter HOT × Vol Surge × meme/gamefi."""
        viral_items = [c for c in candidates if c.get("is_viral")]
        if not viral_items:
            return ""

        viral_items.sort(
            key=lambda c: (c.get("surge") or {}).get("surge_ratio", 0),
            reverse=True,
        )

        cards = "\n".join(render_card(r) for r in viral_items)
        return f"""
        <div class="section-title section-viral">
          🚀 VIRAL HYPE · MEME / GAMEFI
          <span class="section-count">[{len(viral_items):02d}]</span>
        </div>
        <div style="background:rgba(244,114,182,0.06);border-left:2px solid #f472b6;
                    padding:10px 14px;margin-bottom:14px;font-size:12px;color:#d1d5db;
                    line-height:1.5;">
          Пересечение трёх сигналов: <b style="color:#a78bfa;">Twitter HOT</b> +
          <b style="color:#F59E0B;">Volume Surge ×3+</b> +
          спекулятивный сектор <b style="color:#f472b6;">(meme / gamefi)</b>.
          Самые «горячие» монеты рынка прямо сейчас — но и самые рискованные.
          <br><span style="color:#f87171;font-weight:700;">
          ⚠ Размер позиции 1/4 от стандартного, стоп жёсткий, горизонт 1–3 дня.</span>
        </div>
        <div class="grid">{cards}</div>
        """

    # ── Легенда ──
    legend_html = """
    <div style="background:var(--panel);border:1px solid var(--border);border-radius:6px;
                padding:10px 14px;margin:16px 0;font-size:12px;color:#9ca3af;line-height:1.7;">
      <b style="color:#e8ecf5">Легенда:</b>
      <span style="color:#f472b6">🚀 VIRAL</span> — meme/gamefi + Twitter HOT + Vol Surge ·
      <span style="color:#22d3ee">◉ TAIKO</span> — HTF reversal setup ·
      <span style="color:#f472b6">◉ DEXE</span> — post-pump return to EMA200 ·
      <span style="color:#F59E0B">📊 VOL SURGE</span> — дневной объём ×3+ ·
      <span style="color:#a78bfa">🔥 HOT</span> — Twitter buzz.
    </div>
    """

    # ── Сборка секций ──
    volume_surge_html = render_volume_surge_section(rows)
    twitter_hot_html  = render_twitter_hot_section(rows)
    viral_html        = render_viral_hype_section(rows)

    viral_stat_html  = render_stat_tile("🚀 VIRAL", len(viral),  "meme/gamefi hype", "stat-viral",  viral)
    taiko_stat_html  = render_stat_tile("◉ TAIKO",  len(taiko),  "HTF reversal",     "stat-taiko",  taiko)
    dexe_stat_html   = render_stat_tile("◉ DEXE",   len(dexe),   "post-pump",        "stat-dexe",   dexe)
    strong_stat_html = render_stat_tile("Strong",   len(strong), "high-confluence",  "stat-strong", strong)
    good_stat_html   = render_stat_tile("Good",     len(good),   "tradable setups",  "stat-good",   good)
    scout_stat_html  = render_stat_tile("Scout",    len(scout),  "early stage",      "stat-scout",  scout)
    watch_stat_html  = render_stat_tile("Watch",    len(watch),  "monitor only",     "stat-watch",  watch)

    stats_html = (viral_stat_html + taiko_stat_html + dexe_stat_html +
                  strong_stat_html + good_stat_html + scout_stat_html + watch_stat_html)

    def render_bucket_section(name: str, items: list, css_class: str) -> str:
        if not items:
            return ""
        items_sorted = sorted(items, key=lambda x: -x.get("score", 0))
        cards = "\n".join(render_card(r) for r in items_sorted)
        return f"""
        <div class="section-title section-{css_class}">
          {esc(name)}
          <span class="section-count">[{len(items):02d}]</span>
        </div>
        <div class="grid">{cards}</div>
        """

    taiko_html  = render_bucket_section("◉ TAIKO REVERSAL SETUPS", taiko, "taiko")
    dexe_html   = render_bucket_section("◉ DEXE POST-PUMP SETUPS", dexe, "dexe")
    strong_html = render_bucket_section("STRONG · high-confluence", strong, "strong")
    good_html   = render_bucket_section("GOOD · tradable setups",   good,   "good")
    scout_html  = render_bucket_section("SCOUT · early stage",      scout,  "scout")
    watch_html  = render_bucket_section("WATCH · monitor only",     watch,  "watch")

    # ── Финальный HTML ──
    html_str = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sleeping Alts Screener</title>
  <style>{css}</style>
</head>
<body>
  <h1>SLEEPING ALTS SCREENER</h1>
  <div class="subtitle">Stage 2 · {esc(ts)} · {len(rows)} монет</div>

  <div class="stats">{stats_html}</div>

  {legend_html}
  {viral_html}
  {volume_surge_html}
  {twitter_hot_html}
  {taiko_html}
  {dexe_html}
  {strong_html}
  {good_html}
  {scout_html}
  {watch_html}

</body>
</html>
"""
    return html_str

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    print("→ Загружаю тикеры Binance Futures...")
    tickers = get_futures_tickers()
    if not tickers:
        print("✗ Не удалось получить тикеры")
        return

    # Фильтруем USDT-perp и по объёму
    candidates_syms = []
    for t in tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        base = sym[:-4]
        if base in STABLECOINS or base in EXCLUDE_TOKENS:
            continue
        try:
            qvol = float(t.get("quoteVolume", 0))
        except Exception:
            qvol = 0
        if qvol < MIN_QUOTE_VOLUME_24H:
            continue
        candidates_syms.append((sym, qvol))

    # Сортируем по обороту (топ ликвидных)
    candidates_syms.sort(key=lambda x: -x[1])
    candidates_syms = candidates_syms[:MAX_SYMBOLS]

    print(f"→ Обрабатываю {len(candidates_syms)} монет...")

    results: list[Candidate] = []
    for i, (sym, _) in enumerate(candidates_syms, 1):
        try:
            print(f"  [{i}/{len(candidates_syms)}] {sym}...", end=" ", flush=True)
            c = build_candidate(sym, i)
            if c:
                results.append(c)
                print(f"score={c.score} bucket={c.bucket}")
            else:
                print("skip")
        except Exception as e:
            print(f"ERROR: {e}")

    # Сортируем по score
    results.sort(key=lambda x: -x.score)

    print(f"→ Генерирую HTML отчёт → {REPORT_HTML}")
    html_str = build_html(results)
    REPORT_HTML.write_text(html_str, encoding="utf-8")

    print(f"✓ Готово! Открой {REPORT_HTML}")

if __name__ == "__main__":
    main()

# ═══════════════════════════════════════════════════════════════
#  ЧАСТЬ 3b/3 КОНЕЦ · ФАЙЛ ЗАВЕРШЁН
# ═══════════════════════════════════════════════════════════════
