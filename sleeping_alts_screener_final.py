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
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from taiko_detector import detect_taiko, TaikoSignal
from dexe_detector import detect_dexe, DexeSignal
from volume_surge_detector import detect_volume_surge
from squeeze_detector import detect_squeeze
from external_data import get_fundamentals, build_fundamental_take_live
from rr_dial import build_dial, fmt_price

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

STOCK_PERPS = {
    "TSLA", "MRVL", "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL",
    "COIN", "MSTR", "HOOD", "PLTR", "AMD", "INTC", "NFLX", "BABA",
    "SPY", "QQQ", "GLD", "SLV", "ON", "SNDK", "SKHYNIX", "SOXL",
    "MU", "TSM", "ASML", "AVGO", "ORCL", "SMCI", "ARM", "DELL",
    "IBM", "CRM", "UBER", "ABNB", "SHOP", "GME", "AMC", "BB",
    "NOK", "LCID", "RIVN", "NIO", "XPEV", "BRKB", "JPM", "V",
    "MA", "WMT", "COST", "DIS", "PYPL", "COINBASE", "CRCL", "FIGR",
    "BMNR", "SBET",
    # добавлено по результатам прогона
    "NBIS", "CRWV", "RKLB", "AAOI", "IREN", "SAMSUNG", "SKHY",
    "ZHIPU", "MVLL", "GLW", "EWY", "SNXX", "MINIMAX", "STRC",
    "GRAM", "TQQQ", "SQQQ", "SOXS", "SPCX", "LITE", "BILL",
}

# Товарные активы и сырьё — не крипта
COMMODITY_PERPS = {
    "XAU", "XAG", "XAUT", "PAXG", "XPT", "XPD", "NATGAS", "OIL", "WTI", "BRENT",
}

EXCLUDE_TOKENS = {
    "BTC", "ETH", "XRP", "FARTCOIN", "NEAR", "LTC", "ETC", "ADA", "BNB", "DOGE", "SOL"  # мажоры
}

EXCLUDE_TOKENS = STABLECOINS | EXCLUDE_TOKENS | STOCK_PERPS | COMMODITY_PERPS

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
def _get(url: str, params: dict | None = None, quiet_400: bool = False) -> Any:
    try:
        r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if r.status_code == 400 and quiet_400:
            return None
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
        quiet_400=True,
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
        sq_level = (sq or {}).get("risk_level", "none")
        if sq_level in ("high", "extreme"):
            parts.append(
                f"⚠ КОНФЛИКТ СИГНАЛОВ. TAIKO даёт разворот, но squeeze-риск {sq_level.upper()} "
                f"({(sq or {}).get('risk_score', 0)}) — часть роста на ликвидациях шортов. "
                f"Вход половинным объёмом от ${price:.4g} или ждать отката и повторного теста базы."
            )
        else:
            parts.append(
                f"🎯 TAIKO REVERSAL. Вход лесенкой от текущей ${price:.4g}, "
                f"стоп под минимум базы, тейки 1.3× / 2× / 3× от риска."
            )
        return " ".join(parts)

    if dexe_sig.detected:
        parts.append(
            f"🎰 DEXE POST-PUMP. Дамп {dexe_sig.dump_pct:.0f}% за {dexe_sig.dump_hours:.0f}ч, "
            f"дно {dexe_sig.bottom_hours_ago:.0f}ч назад. "
            f"Climax ×{dexe_sig.volume_climax_ratio:.1f} — {dexe_sig.climax_label}. "
            f"Вход от текущей ${price:.4g} частями, стоп под дно, "
            f"первая цель — 30–50% отката к пику ${dexe_sig.peak_price:.4g}."
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
    vs = detect_volume_surge(symbol)
    surge_block = None
    if vs.detected:
        surge_block = {
            "detected": True,
            "surge_ratio": vs.surge_ratio,
            "candle_type": ("зелёная" if vs.is_green else "красная") + f" {vs.day_change_pct:+.1f}%",
            "strength_label": vs.strength_label,
            "current_vol_usd": vs.current_vol_usd,
            "avg_vol_usd": vs.avg_vol_usd,
            "verdict": vs.verdict,
        }
        arrow = "▲" if vs.is_green else "▼"
        tags.append({
            "text": f"📊 VOL SURGE ×{vs.surge_ratio:.1f} {arrow}",
            "class": "tag-pattern surge",
        })
        score += 12 if vs.surge_ratio >= 10 else 8

    # ── Squeeze ──
    sq = detect_squeeze(symbol, m.get("closes_1d") or [], m.get("volumes_1d") or [])
    squeeze_block = None
    if sq and sq.get("detected"):
        squeeze_block = sq
        lvl = sq.get("risk_level", "high")
        tags.append({
            "text": f"⚠ SQUEEZE {lvl.upper()} · {sq.get('risk_score', 0)}",
            "class": "tag-pattern euphoria",
        })
        score += 12 if lvl == "extreme" else 8

    # ── TAIKO ──
    taiko_sig = detect_taiko(symbol)

    # ── DEXE ──
    dexe_sig = detect_dexe(symbol)
    dexe_block = None
    if dexe_sig.detected:
        dexe_block = {
            "detected": True,
            "score": dexe_sig.score,
            "peak_price": dexe_sig.peak_price,
            "dump_pct": dexe_sig.dump_pct,
            "dump_hours": dexe_sig.dump_hours,
            "growth_mult": dexe_sig.growth_mult,
            "growth_days": dexe_sig.growth_days,
            "bottom_hours_ago": dexe_sig.bottom_hours_ago,
            "volume_climax_ratio": dexe_sig.volume_climax_ratio,
            "climax_label": dexe_sig.climax_label,
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
        # внутренний скор 45..100 → вклад 15..35
        score += int(15 + (taiko_sig.score - 45) * 0.36)

    if dexe_sig.detected:
        tags.append({
            "text": f"◉ DEXE POST-PUMP · {dexe_sig.score}",
            "class": "tag-pattern dexe",
        })
        # внутренний скор 55..100 → вклад 15..35
        score += int(15 + (dexe_sig.score - 55) * 0.44)

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
    # Twitter HOT × Volume Surge × (спекулятивный сектор ИЛИ поведение цены)
    VIRAL_SECTOR_KEYWORDS = [
        # мемы
        "meme", "dog", "cat", "frog", "pepe", "inu", "shib", "wif",
        "bonk", "floki", "broccoli", "farto", "useless",
        # игры и метаверс
        "game", "gaming", "gamefi", "play-to-earn", "metaverse", "virtual",
        # AI — самый горячий нарратив
        "artificial intelligence", " ai ", "ai agent", "agent", "machine learning",
        "deai", "ai & big data", "depin",
        # экосистемы, где живёт спекуляция
        "solana meme", "bnb chain ecosystem", "base ecosystem", "pump.fun",
    ]
    cats_lower = " " + " ".join(c.lower() for c in all_categories) + " "
    in_speculative_sector = any(kw in cats_lower for kw in VIRAL_SECTOR_KEYWORDS)

    # Фолбэк: мемное имя в самом тикере (когда CoinGecko не дал категорий)
    MEME_TICKER_HINTS = [
        "PEPE", "SHIB", "DOGE", "FLOKI", "BONK", "WIF", "BROCCOLI",
        "FARTCOIN", "USELESS", "NEIRO", "GIGGLE", "TRUMP", "MELANIA",
        "MOG", "TURBO", "POPCAT", "MEW", "BOME", "PENGU", "SPX",
    ]
    if not in_speculative_sector:
        sym_upper = symbol.upper()
        if any(h in sym_upper for h in MEME_TICKER_HINTS):
            in_speculative_sector = True

    twitter_hot = (buzz or {}).get("level") == "hot"
    has_vol_surge = surge_block is not None and surge_block.get("detected")

    # Спекулятивное поведение: сурж на зелёной свече с большим ходом
    behaves_speculative = (
        has_vol_surge and vs.is_green and vs.day_change_pct >= 20
    )

    is_viral = twitter_hot and has_vol_surge and (
        in_speculative_sector or behaves_speculative
    )

    if is_viral:
        label = "🚀 VIRAL HYPE" if in_speculative_sector else "🚀 VIRAL PUMP"
        tags.insert(0, {
            "text": label,
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

    fund_take = build_fundamental_take_live(fund)
    if fund_take:
        analysis = (analysis + " " + fund_take).strip() if analysis else fund_take

    strategy = build_strategy(m, sq, taiko_sig, dexe_sig)

    # ── Ссылки на графики ──
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    links = [
        {"text": "TradingView", "url": f"https://www.tradingview.com/chart/?symbol=BINANCE:{symbol}.P"},
        {"text": "Binance",     "url": f"https://www.binance.com/en/futures/{symbol}"},
        {"text": "CoinGecko",   "url": f"https://www.coingecko.com/en/search?query={base}"},
        {"text": "Twitter",     "url": f"https://x.com/search?q=%24{base}&f=live"},
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
      --bg:#0a0a0c; --card:#0e0e12; --panel:#16161c; --panel2:#121217; --panel3:#0f0f14;
      --line:#22222a; --line2:#1a1a22;
      --am1:#FFD24A; --am2:#F0A800; --am3:#e0b850; --am4:#c9a24a; --am5:#a8863a; --am6:#8a6a2a;
      --txt:#e8e8f0; --txt2:#c8c8d4; --mut:#6b6b76; --mut2:#4e4e58; --mut3:#3f3f48; --ghost:#2e2e36;
      --up:#7fbf8f; --dn:#e39a9a;
      --mono:'SF Mono',SFMono-Regular,Consolas,'Liberation Mono',monospace;
      --serif:Georgia,'Times New Roman',serif;
    }
    *{box-sizing:border-box}
    body{background:var(--bg);color:var(--txt);margin:0;padding:26px 30px 60px;
      font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:13px;line-height:1.5;
      -webkit-font-smoothing:antialiased}
    a{text-decoration:none;color:inherit}
    summary{cursor:pointer;list-style:none}
    summary::-webkit-details-marker{display:none}

    /* ══════════ ШАПКА H1 ══════════ */
    .hd{display:flex;align-items:flex-start;gap:14px;margin-bottom:14px}
    .hd-bar{width:6px;height:26px;border-radius:3px;background:linear-gradient(160deg,var(--am1),var(--am2));flex:none;margin-top:2px}
    .hd-t{font-size:19px;font-weight:900;letter-spacing:2px;color:#fdfdff;margin:0}
    .hd-t span{color:var(--am1)}
    .hd-sub{display:flex;align-items:center;gap:10px;margin-top:5px}
    .hd-ts{font-family:var(--mono);font-size:9px;color:#5c5c66}
    .hd-stage{background:#22222a;border-radius:8px;padding:2px 9px;font-size:7px;font-weight:900;
      letter-spacing:1.5px;color:#8a8a96}
    .hd-r{margin-left:auto;text-align:right}
    .hd-n{font-family:var(--mono);font-size:20px;font-weight:900;color:var(--am1);line-height:1}
    .hd-nl{font-size:8px;letter-spacing:2px;color:var(--mut2);margin-top:4px}
    .hd-rule{height:1.5px;border:0;margin:0 0 12px;
      background:linear-gradient(90deg,rgba(255,184,0,.4),rgba(255,184,0,0))}

    .dash{display:grid;grid-template-columns:repeat(7,1fr);background:var(--panel2);
      border-radius:22px;padding:22px 0 20px}
    .dcell{padding:0 0 0 36px;position:relative}
    .dcell+.dcell::before{content:'';position:absolute;left:0;top:0;bottom:0;width:1px;background:#1e1e26}
    .dcell-l{font-size:8px;font-weight:900;letter-spacing:2px;color:var(--dc,var(--am1))}
    .dcell-v{font-family:var(--mono);font-size:24px;font-weight:900;color:var(--dc,var(--am1));margin:12px 0 4px;line-height:1}
    .dcell-d{font-family:var(--serif);font-style:italic;font-size:8px;color:var(--mut2)}
    .dc-1{--dc:var(--am1)} .dc-2{--dc:var(--am3)} .dc-3{--dc:var(--am4)}
    .dc-4{--dc:var(--am5)} .dc-5{--dc:var(--mut)}
    .dcell.empty{--dc:#3a3a44} .dcell.empty .dcell-d{color:#2a2a32}

    .lg{margin:12px 0 4px;background:#0d0d11;border:1px solid var(--line2);border-radius:17px}
    .lg summary{display:flex;align-items:center;gap:20px;height:34px;padding:0 14px}
    .lg-q{width:18px;height:18px;border-radius:50%;background:#22201a;color:var(--am4);
      font-size:9px;font-weight:900;display:flex;align-items:center;justify-content:center;flex:none}
    .lg-t{font-size:9px;font-weight:900;letter-spacing:2px;color:#8a8a96}
    .lg-d{font-family:var(--serif);font-style:italic;font-size:9px;color:#45454e}
    .lg-c{margin-left:auto;width:22px;height:22px;border-radius:50%;background:#1a1a22;
      display:flex;align-items:center;justify-content:center;transition:transform .18s}
    .lg-c::before{content:'';width:7px;height:7px;border-right:1.8px solid var(--am4);
      border-bottom:1.8px solid var(--am4);transform:translateY(-2px) rotate(45deg)}
    .lg[open] .lg-c{transform:rotate(180deg)}
    .lg[open] .lg-t{color:var(--txt2)}
    .lg-body{display:grid;grid-template-columns:1fr 1px 1fr;gap:0 34px;padding:4px 26px 20px}
    .lg-sep{background:var(--line2)}
    .lg-h{font-size:7px;font-weight:900;letter-spacing:2px;color:#3a3a44;margin:6px 0 12px}
    .lg-row{display:flex;gap:12px;padding:4px 0;font-size:8.5px;align-items:baseline}
    .lg-k{font-weight:900;letter-spacing:1.5px;width:76px;flex:none;color:var(--am4)}
    .lg-v{font-family:var(--serif);font-style:italic;color:var(--mut)}
    .lg-n{font-family:var(--mono);color:var(--am4);width:56px;flex:none}

    /* ══════════ ЗАГОЛОВКИ СЕКЦИЙ ══════════ */
    .sec{display:flex;align-items:center;gap:14px;margin:34px 0 12px}
    .sec-p{display:flex;align-items:center;gap:14px;border-radius:19px;padding:0 18px;height:38px}
    .sec-n{font-size:14px;font-weight:900;letter-spacing:2px}
    .sec-c{min-width:22px;height:22px;border-radius:11px;display:flex;align-items:center;
      justify-content:center;font-family:var(--mono);font-size:9px;font-weight:900;padding:0 6px}
    .sec-d{font-family:var(--serif);font-style:italic;font-size:10px;color:#7a6a44}
    .sec-l{flex:1;height:1.2px;background:linear-gradient(90deg,rgba(255,184,0,.4),rgba(255,184,0,0))}
    .t1 .sec-p{background:linear-gradient(160deg,var(--am1),var(--am2));box-shadow:0 4px 14px rgba(240,168,0,.32)}
    .t1 .sec-n{color:#1a1400} .t1 .sec-c{background:rgba(26,20,0,.2);color:#1a1400}
    .t2 .sec-p{background:#241f10;border:1px solid rgba(255,184,0,.5)}
    .t2 .sec-n{color:var(--am1)} .t2 .sec-c{background:#3a2f18;color:var(--am1)}
    .t3 .sec-p{background:#1a1710;border:1px solid rgba(138,106,42,.45)}
    .t3 .sec-n{color:var(--am4);font-size:13px} .t3 .sec-c{background:#2a2417;color:var(--am4)}
    .t3 .sec-d{color:#6b6050} .t3 .sec-l{background:linear-gradient(90deg,rgba(138,106,42,.4),rgba(138,106,42,0))}
    .t4 .sec-p{background:#131317;border:1px solid #2a2a34}
    .t4 .sec-n{color:#7a7a86;font-size:13px} .t4 .sec-c{background:#1e1e26;color:#7a7a86}
    .t4 .sec-d{color:var(--mut3)} .t4 .sec-l{background:linear-gradient(90deg,rgba(74,74,84,.45),rgba(74,74,84,0))}

    /* ══════════ ТАБЛИЦЫ-СЛАЙДЕРЫ ══════════ */
    .tbl{margin-bottom:8px}
    .tbl-h{display:grid;grid-template-columns:150px 1fr 308px 84px 66px;gap:12px;
      padding:0 22px 8px;font-size:7px;font-weight:900;letter-spacing:2px;color:#3a3a44}
    .tbl-h b:nth-child(4),.tbl-h b:nth-child(5){text-align:right;font-weight:900}
    .trow{display:grid;grid-template-columns:150px 1fr 308px 84px 66px;gap:12px;align-items:center;
      height:36px;padding:0 22px;border-radius:14px;background:var(--panel2)}
    .trow:nth-child(even){background:var(--panel3)}
    .trow:hover{background:#191920}
    .t-sym{font-size:11px;font-weight:800;color:#dcdce4;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .t-note{font-family:var(--serif);font-style:italic;font-size:8px;color:var(--mut3);
      white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .t-track{position:relative;height:5px;border-radius:2.5px;background:#1c1c24}
    .t-fill{height:5px;border-radius:2.5px;background:linear-gradient(90deg,var(--am2),var(--am1))}
    .t-dot{position:absolute;top:50%;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;
      background:var(--am1);box-shadow:0 0 0 2.5px rgba(255,184,0,.32)}
    .t-val{font-family:var(--mono);font-size:12px;font-weight:900;color:var(--am1);text-align:right}
    .t-ch{font-family:var(--mono);font-size:10px;text-align:right}
    .t-scale{display:grid;grid-template-columns:150px 1fr 308px 84px 66px;gap:12px;padding:8px 22px 0}
    .t-scale div:nth-child(3){display:flex;justify-content:space-between;
      font-family:var(--mono);font-size:7px;color:var(--ghost)}
    .up{color:var(--up)} .dn{color:var(--dn)}

    /* ══════════ КАРТОЧКИ ══════════ */
    .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));
      gap:20px;align-items:start;margin-bottom:8px}
    .card{position:relative;background:var(--card);border-radius:30px;padding:16px}
    .card.glow{background:linear-gradient(135deg,var(--g1),var(--g2) 50%,var(--g3));padding:1.2px;
      border-radius:30px;box-shadow:0 0 11px var(--gs1),0 0 24px var(--gs2)}
    .card.glow>.card-in{background:var(--card);border-radius:28.8px;padding:15px}
    .card-in{position:relative}
    .g-am{--g1:#FFB800;--g2:#e07a3a;--g3:#FFD24A;--gs1:rgba(255,184,0,.42);--gs2:rgba(240,168,0,.16)}
    .g-rd{--g1:#e05a5a;--g2:#c04a6a;--g3:#f08a8a;--gs1:rgba(224,90,90,.42);--gs2:rgba(208,85,85,.16)}

    .hdr{position:relative;height:118px;border-radius:22px;margin:0 0 14px;
      background:linear-gradient(160deg,var(--h1),var(--h2));box-shadow:0 5px 18px var(--hs)}
    .hdr.amber{--h1:#FFD24A;--h2:#F0A800;--hs:rgba(240,168,0,.3);--hf:#7a5c00;--hd:#1a1400;--hp:#6b5000}
    .hdr.red{--h1:#f0a0a0;--h2:#d06060;--hs:rgba(208,85,85,.3);--hf:#5c1a1a;--hd:#2a0d0d;--hp:#6b2a2a}
    .hdr::after{content:'';position:absolute;bottom:-22px;left:96px;width:44px;height:44px;
      border-radius:50%;background:var(--card)}
    .hdr-cl{position:absolute;inset:0;border-radius:22px;overflow:hidden}
    .hdr-gh{position:absolute;left:-4px;bottom:-16px;font-size:80px;font-weight:900;
      letter-spacing:-3px;color:var(--hd);opacity:.12;line-height:1;white-space:nowrap}
    .hdr-in{position:relative;padding:22px 24px 0}
    .hdr-rk{display:flex;align-items:center;gap:12px}
    .hdr-rk b{font-size:8px;font-weight:800;letter-spacing:3px;color:var(--hf)}
    .hdr-rk i{flex:1;max-width:80px;height:1px;background:var(--hf);opacity:.35}
    .hdr-sym{margin-top:16px;font-weight:900;color:#fffdf6;text-shadow:0 2px 3px rgba(58,42,0,.55);
      white-space:nowrap;overflow:hidden}
    .hdr-ph{font-family:var(--serif);font-style:italic;font-weight:500;font-size:27px;
      color:var(--hd);margin:-2px 0 0 10px;line-height:1.05}
    .hdr-pr{position:absolute;right:24px;bottom:14px;font-family:var(--mono);font-size:9px;
      font-weight:800;color:var(--hp)}

    .med{position:absolute;top:52px;right:38px;width:50px;height:50px;border-radius:50%;
      background:conic-gradient(from -90deg,var(--am1) calc(var(--p)*3.6deg),#24242c 0);
      box-shadow:0 5px 8px rgba(0,0,0,.92),0 0 10px rgba(255,184,0,.35)}
    .med.red{background:conic-gradient(from -90deg,#e39a9a calc(var(--p)*3.6deg),#24242c 0)}
    .med::before{content:'';position:absolute;inset:3.4px;border-radius:50%;background:#14141a}
    .med-i{position:relative;height:100%;display:flex;flex-direction:column;
      align-items:center;justify-content:center;gap:1px}
    .med-v{font-size:16px;font-weight:900;color:var(--am1);line-height:1}
    .med.red .med-v{color:var(--dn)}
    .med-l{font-size:5.5px;font-weight:800;letter-spacing:1.2px;color:var(--mut)}
    .med-link{position:absolute;top:76px;right:88px;width:30px;height:1.2px;
      background:var(--am2);opacity:.6}

    .chips{display:flex;flex-wrap:wrap;gap:6px;margin:26px 0 12px}
    .chip{height:18px;padding:0 11px;border-radius:9px;background:#1e1e26;color:#8a8a96;
      font-size:7px;font-weight:900;letter-spacing:1px;display:flex;align-items:center;text-transform:uppercase}
    .chip.risk{background:#2c1c1f;color:var(--dn)}
    .chip.more{background:transparent;border:1px dashed #2a2a34;color:var(--mut3)}

    .wrap{display:grid;grid-template-columns:120px 1fr;gap:8px;margin-bottom:12px}
    .rvol{grid-row:span 2;background:var(--panel);border-radius:22px;padding:14px 0;text-align:center;
      box-shadow:2px 4px 5px rgba(0,0,0,.8)}
    .rvol-i{width:34px;height:34px;margin:0 auto;border-radius:50%;background:rgba(255,184,0,.14);
      display:flex;align-items:center;justify-content:center;font-size:15px}
    .rvol-v{font-family:var(--mono);font-size:22px;font-weight:900;color:var(--am1);margin-top:12px}
    .rvol-l{font-size:7.5px;font-weight:700;letter-spacing:1.5px;color:#9a9080;margin-top:6px}
    .rvol-d{font-family:var(--serif);font-style:italic;font-size:8px;color:#6e6a60;margin-top:4px}
    .sigs{display:flex;flex-direction:column;gap:8px}
    .sig{display:flex;align-items:center;gap:12px;height:46px;padding:0 16px;border-radius:20px;
      background:var(--panel);box-shadow:2px 4px 5px rgba(0,0,0,.8)}
    .sig.half{height:30px;border-radius:15px;background:#141419;box-shadow:none}
    .sig-i{width:24px;height:24px;border-radius:50%;background:#2b2718;color:var(--am1);flex:none;
      font-size:9px;font-weight:900;display:flex;align-items:center;justify-content:center}
    .sig.rd .sig-i{background:#2c1c1f;color:var(--dn)}
    .sig.half .sig-i{width:18px;height:18px;background:#22201a;color:var(--am4);font-size:8px}
    .sig-t{font-size:9px;font-weight:900;letter-spacing:1.2px;color:#f2f2f6}
    .sig.half .sig-t{font-size:8px;color:#dcdce4}
    .sig-d{font-family:var(--serif);font-style:italic;font-size:8.5px;color:#82828e;margin-top:3px;
      white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .sig.half .sig-d{font-family:var(--mono);font-style:normal;font-size:7.5px;color:#5c5c66}
    .sig-row{display:grid;grid-template-columns:1fr 1fr;gap:8px}

    .perf{display:grid;grid-template-columns:repeat(4,1fr);height:48px;align-items:center;
      padding:0 24px;border-radius:20px;background:#0a0a0d;border:1px solid var(--line);margin-bottom:8px}
    .perf-k{font-size:7px;font-weight:700;letter-spacing:1.8px;color:#57575f}
    .perf-v{font-family:var(--mono);font-size:12px;font-weight:800;margin-top:5px}
    .tech{height:22px;line-height:20px;border-radius:11px;background:#0a0a0d;border:1px solid var(--line2);
      text-align:center;font-family:var(--mono);font-size:7.5px;color:var(--mut2);margin-bottom:16px;
      white-space:nowrap;overflow:hidden}

    .blk{position:relative;border-radius:20px;margin-bottom:8px;overflow:hidden}
    .blk-n{position:absolute;left:16px;top:50%;transform:translateY(-50%);
      font-size:38px;font-weight:900;line-height:1;pointer-events:none}
    .b1{background:#141418;min-height:52px;box-shadow:2px 4px 5px rgba(0,0,0,.8)}
    .b1 .blk-n{color:#26262e}
    .b1-in{padding:12px 16px 12px 82px}
    .b1-h{display:flex;align-items:center;gap:8px}
    .tw{width:22px;height:22px;border-radius:50%;background:#1d2a33;flex:none;
      display:flex;align-items:center;justify-content:center}
    .tw svg{width:11px;height:11px;fill:#8fc4e8}
    .b1-t{font-size:8px;font-weight:900;letter-spacing:2.5px;color:#c8c8d4}
    .b1-lv{height:13px;padding:0 8px;border-radius:6.5px;font-size:6.5px;font-weight:900;
      letter-spacing:1.2px;display:flex;align-items:center}
    .lv-hot{background:#3a2f18;color:var(--am1)} .lv-warm{background:#3a2f18;color:var(--am4)}
    .lv-cool{background:#22222a;color:#8a8a96} .lv-cold{background:#1a1a22;color:var(--mut2)}
    .b1-d{font-size:8.5px;color:#63636d;margin-top:6px;line-height:1.4}
    .b2{background:var(--panel);box-shadow:2px 4px 5px rgba(0,0,0,.8)}
    .b2 .blk-n{color:#332a12}
    .b2 summary{display:flex;align-items:center;min-height:52px;padding:10px 16px 10px 82px;gap:12px}
    .b2-t{font-size:8px;font-weight:900;letter-spacing:2.5px;color:var(--am1)}
    .b2-p{font-size:8.5px;color:#63636d;margin-top:6px;white-space:nowrap;overflow:hidden;
      text-overflow:ellipsis;max-width:250px}
    .b2-c{margin-left:auto;width:22px;height:22px;border-radius:50%;background:#22222a;flex:none;
      display:flex;align-items:center;justify-content:center;transition:transform .18s}
    .b2-c::before{content:'';width:7px;height:7px;border-right:1.8px solid var(--am1);
      border-bottom:1.8px solid var(--am1);transform:translateY(-2px) rotate(45deg)}
    .b2[open] .b2-c{transform:rotate(180deg)}
    .b2[open] .b2-p{white-space:normal;max-width:none}
    .b2-body{padding:0 20px 16px 82px;font-size:9.5px;line-height:1.65;color:#9a9aa4}
    .b2-body p{margin:0 0 8px}
    .b2-body p:last-child{margin:0}
    .b3{background:#f4f4f7;min-height:62px;box-shadow:2px 4px 5px rgba(0,0,0,.8)}
    .b3 .blk-n{color:#e2e2ea;font-size:44px}
    .b3-in{padding:14px 20px 14px 82px}
    .b3-t{font-size:8px;font-weight:900;letter-spacing:2.5px;color:#1a1a20}
    .b3-d{font-size:8.5px;color:#5a5a66;margin-top:6px;line-height:1.5}
    .b3-tv{position:absolute;right:20px;top:14px;font-size:7.5px;font-weight:900;color:#8a8a96}
    .empty-note{font-family:var(--serif);font-style:italic;font-size:10px;color:#3a3a44;padding:6px 22px}

    /* ══════════ ССЫЛКИ КАРТОЧКИ ══════════ */
    .lnks{display:flex;gap:8px;margin-top:12px}
    .lnk{flex:1;height:32px;border-radius:16px;background:#121217;border:1px solid var(--line2);
      display:flex;align-items:center;justify-content:center;gap:7px;
      font-size:8px;font-weight:900;letter-spacing:1.5px;color:#8a8a96;
      transition:background .15s,color .15s,border-color .15s}
    .lnk:hover{background:#1c1a14;border-color:rgba(255,184,0,.4);color:var(--am1)}
    .lnk i{font-style:normal;font-size:9px;opacity:.7}
    .lnk.pri{background:#1a1710;border-color:rgba(255,184,0,.32);color:var(--am4)}
    .lnk.pri:hover{background:#241f10;color:var(--am1)}
    .hdr-sym-a{display:block}
    .hdr-sym-a:hover .hdr-sym{opacity:.82}

    @media(max-width:1180px){
      .dash{grid-template-columns:repeat(4,1fr);row-gap:20px}
      .dcell:nth-child(5)::before{display:none}
      .tbl-h,.trow,.t-scale{grid-template-columns:130px 1fr 200px 70px 60px}
    }
    @media(max-width:820px){
      body{padding:18px 14px 40px}
      .dash{grid-template-columns:repeat(2,1fr)}
      .grid{grid-template-columns:1fr}
      .tbl-h b:nth-child(2),.trow>div:nth-child(2){display:none}
      .tbl-h,.trow,.t-scale{grid-template-columns:120px 1fr 66px 56px}
      .lg-body{grid-template-columns:1fr}.lg-sep{display:none}
    }
    """
# ═══════════════════════════════════════════════════════════════
#  ЧАСТЬ 3a/3 КОНЕЦ
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
#  sleeping_alts_screener_final.py — ЧАСТЬ 3b/3 НАЧАЛО
# ═══════════════════════════════════════════════════════════════

    # ─────────────────────────────────────────────
    # Хелперы извлечения данных
    # ─────────────────────────────────────────────
    def mval(metrics: list, key: str) -> str:
        for mm in (metrics or []):
            if mm.get("key") == key:
                return str(mm.get("val", ""))
        return "—"

    def mcls(metrics: list, key: str) -> str:
        for mm in (metrics or []):
            if mm.get("key") == key:
                return str(mm.get("cls", ""))
        return ""

    def mnum(metrics: list, key: str) -> float:
        raw = mval(metrics, key)
        buf = ""
        for ch in raw:
            if ch.isdigit() or ch in "+-.":
                buf += ch
            elif buf:
                break
        try:
            return float(buf)
        except Exception:
            return 0.0

    def tick_font(sym: str) -> tuple[str, str]:
        n = len(sym)
        if n <= 6:   return "23px", "4px"
        if n <= 8:   return "21px", "3px"
        if n <= 11:  return "17px", "2px"
        if n <= 13:  return "15px", "1.2px"
        return "12.5px", "0.8px"

    def pct_cls(v: float) -> str:
        return "up" if v > 0 else ("dn" if v < 0 else "")

    TW_SVG = ('<svg viewBox="0 0 24 24"><path d="M23 4.9c-.8.4-1.7.6-2.6.8 1-.6 1.7-1.5 2-2.6'
              '-.9.5-1.9.9-3 1.1a4.7 4.7 0 0 0-8 4.3C7.5 8.3 4 6.5 1.7 3.7a4.7 4.7 0 0 0 1.5 6.3'
              'c-.8 0-1.5-.2-2.1-.6 0 2.3 1.6 4.2 3.8 4.6-.4.1-.8.2-1.2.2-.3 0-.6 0-.9-.1'
              '.6 1.9 2.4 3.3 4.4 3.3A9.5 9.5 0 0 1 0 19.5a13.3 13.3 0 0 0 7.2 2.1'
              'c8.7 0 13.4-7.2 13.4-13.4v-.6c.9-.7 1.7-1.5 2.4-2.7z"/></svg>')

    # ─────────────────────────────────────────────
    # Шапка H1 «Панель приборов»
    # ─────────────────────────────────────────────
    def render_header(total: int) -> str:
        cells = [
            ("VIRAL",  len(viral),  "memegame",        "dc-1"),
            ("TAIKO",  len(taiko),  "HTF reversal",    "dc-1"),
            ("DEXE",   len(dexe),   "post-pump",       "dc-2"),
            ("STRONG", len(strong), "high-confluence", "dc-2"),
            ("GOOD",   len(good),   "tradable setups", "dc-3"),
            ("SCOUT",  len(scout),  "early stage",     "dc-4"),
            ("WATCH",  len(watch),  "monitor only",    "dc-5"),
        ]
        cl = ""
        for label, cnt, desc, tone in cells:
            empty = " empty" if cnt == 0 else ""
            cl += (f'<div class="dcell {tone}{empty}">'
                   f'<div class="dcell-l">{esc(label)}</div>'
                   f'<div class="dcell-v">{cnt}</div>'
                   f'<div class="dcell-d">{esc(desc)}</div></div>')

        cats = [
            ("VIRAL",  "meme/gamefi + Twitter HOT + всплеск объёма"),
            ("TAIKO",  "разворот на старшем таймфрейме подтверждён"),
            ("DEXE",   "отскок после дампа, post-pump капитуляция"),
            ("STRONG", "совпало несколько независимых условий"),
            ("GOOD",   "сетап пригоден к торговле, риск умеренный"),
            ("SCOUT",  "ранняя стадия, вход преждевременен"),
            ("WATCH",  "только наблюдение, действий нет"),
        ]
        thr = [
            ("RVOL 1H",     "≥ 1.8×",  "относительный объём часа"),
            ("VOL SURGE",   "≥ 3.0×",  "против среднего за 30 дней"),
            ("SQUEEZE",     "≥ 60",    "риск ликвидационного выброса"),
            ("ОБОРОТ 24H",  "≥ $5M",   "минимальная ликвидность"),
            ("ЛИМИТ",       f"{MAX_SYMBOLS}",  "монет в обработке"),
        ]
        lc = "".join(f'<div class="lg-row"><span class="lg-k">{esc(k)}</span>'
                     f'<span class="lg-v">{esc(v)}</span></div>' for k, v in cats)
        lt = "".join(f'<div class="lg-row"><span class="lg-k" style="width:96px">{esc(k)}</span>'
                     f'<span class="lg-n">{esc(v)}</span>'
                     f'<span class="lg-v">{esc(d)}</span></div>' for k, v, d in thr)

        return f"""
<div class="hd">
  <div class="hd-bar"></div>
  <div>
    <h1 class="hd-t">SLEEPING ALTS <span>SCREENER</span></h1>
    <div class="hd-sub">
      <span class="hd-ts">{esc(ts)}</span>
      <span class="hd-stage">STAGE 2</span>
    </div>
  </div>
  <div class="hd-r">
    <div class="hd-n">{total}</div>
    <div class="hd-nl">МОНЕТ В ВЫБОРКЕ</div>
  </div>
</div>
<hr class="hd-rule">
<div class="dash">{cl}</div>
<details class="lg">
  <summary>
    <span class="lg-q">?</span>
    <span class="lg-t">ЛЕГЕНДА И ПОРОГИ</span>
    <span class="lg-d">описание категорий, метрик и условий отбора</span>
    <span class="lg-c"></span>
  </summary>
  <div class="lg-body">
    <div><div class="lg-h">КАТЕГОРИИ</div>{lc}</div>
    <div class="lg-sep"></div>
    <div><div class="lg-h">УСЛОВИЯ ОТБОРА</div>{lt}</div>
  </div>
</details>
"""

    # ─────────────────────────────────────────────
    # Заголовок секции
    # ─────────────────────────────────────────────
    def render_sec(name: str, count: int, desc: str, tier: int) -> str:
        return f"""
<div class="sec t{tier}">
  <div class="sec-p">
    <span class="sec-n">{esc(name)}</span>
    <span class="sec-c">{count}</span>
  </div>
  <span class="sec-d">{esc(desc)}</span>
  <span class="sec-l"></span>
</div>"""

    # ─────────────────────────────────────────────
    # Таблица-слайдер (Z3)
    # ─────────────────────────────────────────────
    def render_slider_table(items: list, cfg: dict) -> str:
        if not items:
            return ""
        lo, hi = cfg["lo"], cfg["hi"]
        rows_html = ""
        for c in items:
            sym = c.get("symbol", "")
            raw = cfg["value"](c)
            frac = (raw - lo) / (hi - lo) if hi > lo else 0
            frac = max(0.0, min(1.0, frac))
            pos = round(frac * 100, 2)
            ch_v = mval(c.get("metrics"), "24h")
            ch_c = "up" if mcls(c.get("metrics"), "24h") == "up" else "dn"
            tv = f"https://www.tradingview.com/chart/?symbol=BINANCE:{sym}.P"
            rows_html += f"""
<a class="trow" href="{tv}" target="_blank" rel="noopener">
  <div class="t-sym">{esc(sym)}</div>
  <div class="t-note">{esc(cfg["note"](c))}</div>
  <div class="t-track">
    <div class="t-fill" style="width:{pos}%"></div>
    <div class="t-dot" style="left:{pos}%"></div>
  </div>
  <div class="t-val">{esc(cfg["label"](c))}</div>
  <div class="t-ch {ch_c}">{esc(ch_v)}</div>
</a>"""
        return f"""
<div class="tbl">
  <div class="tbl-h">
    <b>СИМВОЛ</b><b>{esc(cfg["col2"])}</b><b>{esc(cfg["col3"])}</b>
    <b>{esc(cfg["col4"])}</b><b>24H</b>
  </div>
  {rows_html}
  <div class="t-scale">
    <div></div><div></div>
    <div><span>{esc(cfg["lo_lbl"])}</span><span>{esc(cfg["hi_lbl"])}</span></div>
    <div></div><div></div>
  </div>
</div>"""

    # ─────────────────────────────────────────────
    # Карточка монеты
    # ─────────────────────────────────────────────
    def render_card(c: dict) -> str:
        sym    = c.get("symbol", "")
        rank   = (c.get("rank", "") or "").lstrip("#")
        score  = min(int(c.get("score", 0) or 0), 100)
        tags   = c.get("tags") or []
        phase  = c.get("phase") or {}
        met    = c.get("metrics") or []
        buzz   = c.get("buzz") or {}
        sq     = c.get("squeeze") or {}
        surge  = c.get("surge") or {}

        ch24   = mnum(met, "24h")
        price  = mval(met, "Цена")
        ph_lbl = str(phase.get("label", "—")).lower()
        risky  = (sq.get("risk_level") in ("high", "extreme")) or phase.get("num", 0) <= 1
        tone   = "red" if (risky and ch24 <= 0) else "amber"

        has_sig = bool(c.get("is_viral")) or any(
            t.get("class", "").startswith("tag-pattern") for t in tags)
        glow = ("g-rd" if tone == "red" else "g-am") if has_sig else ""

        fs, ls = tick_font(sym)
        ghost  = mval(met, "24h")

        # ── чипы категорий ──
        cats = [t for t in tags if "tag-cat" in t.get("class", "")]
        chips = ""
        for t in cats[:4]:
            chips += f'<span class="chip">{esc(t.get("text",""))}</span>'
        if risky:
            chips += '<span class="chip risk">HIGH RISK</span>'
        extra = len(cats) - 4
        if extra > 0:
            chips += f'<span class="chip more">+{extra}</span>'

        # ── сигналы ──
        ICON = {"taiko": "✓", "dexe": "◉", "surge": "📊", "viral": "🚀", "euphoria": "!"}
        wide, half = [], []
        for t in tags:
            cl = t.get("class", "")
            if not cl.startswith("tag-pattern"):
                continue
            kind = cl.replace("tag-pattern", "").strip() or "surge"
            txt  = t.get("text", "")
            head = txt.split("·")[0].strip()
            head = "".join(ch for ch in head if ch.isascii()).strip() or head
            note = ""
            if kind == "taiko":
                note = "разворот подтверждён на старшем ТФ"
            elif kind == "dexe":
                d = c.get("dexe") or {}
                note = f"дамп {d.get('dump_pct',0):.0f}% · дно {d.get('bottom_hours_ago',0):.0f}ч назад"
            elif kind == "surge":
                note = f"{_big(surge.get('current_vol_usd'))} против {_big(surge.get('avg_vol_usd'))}"
            elif kind == "euphoria":
                note = "сжатие волатильности, риск выброса"
            elif kind == "viral":
                note = "Twitter HOT + всплеск объёма"
            rd = " rd" if kind == "euphoria" else ""
            wide.append(f'<div class="sig{rd}"><span class="sig-i">{ICON.get(kind,"◉")}</span>'
                        f'<div style="min-width:0"><div class="sig-t">{esc(txt)}</div>'
                        f'<div class="sig-d">{esc(note)}</div></div></div>')

        fund = mval(met, "Funding")
        half.append(f'<div class="sig half"><span class="sig-i">≈</span><div style="min-width:0">'
                    f'<div class="sig-t">FUNDING</div><div class="sig-d">{esc(fund)}</div></div></div>')
        half.append(f'<div class="sig half"><span class="sig-i">↑</span><div style="min-width:0">'
                    f'<div class="sig-t">OPEN INTEREST</div>'
                    f'<div class="sig-d">{esc(mval(met,"OI"))}</div></div></div>')

        sigs = "".join(wide[:2])
        if len(wide) > 2:
            sigs += "".join(wide[2:])
        sigs += '<div class="sig-row">' + "".join(half) + "</div>"

        # ── перформанс ──
        perf = ""
        for k, lbl in (("7d", "7D"), ("30d", "30D"), ("От ATH", "ATH"), ("OBV", "OBV")):
            v = mval(met, k)
            cl = "up" if mcls(met, k) == "up" else "dn"
            perf += (f'<div><div class="perf-k">{lbl}</div>'
                     f'<div class="perf-v {cl}">{esc(v)}</div></div>')

        tech = " · ".join([
            f'SRSI {mval(met,"StochRSI 4H")}',
            f'ATR {mval(met,"ATR %")}',
            f'BB {mval(met,"BB width")}',
            f'SPOT {mval(met,"Spot ratio")}',
            f'VI+ {phase.get("vi_plus","—")}/{phase.get("vi_minus","—")}',
        ])

        # ── блок 01 twitter ──
        lv = str(buzz.get("level", "cold"))
        b1 = f"""
<div class="blk b1"><div class="blk-n">01</div><div class="b1-in">
  <div class="b1-h"><span class="tw">{TW_SVG}</span>
    <span class="b1-t">TWITTER BUZZ</span>
    <span class="b1-lv lv-{esc(lv)}">{esc(buzz.get("level_text","—"))}</span></div>
  <div class="b1-d">{esc(buzz.get("text",""))}</div>
</div></div>"""

        # ── блок 02 анализ ──
        analysis = (c.get("analysis") or "").strip()
        sq_v = (sq.get("verdict") or "").strip()
        paras = [p for p in (analysis, sq_v) if p]
        b2 = ""
        if paras:
            preview = paras[0]
            if len(preview) > 64:
                preview = preview[:61].rstrip() + "…"
            body = "".join(f"<p>{esc(p)}</p>" for p in paras)
            b2 = f"""
<details class="blk b2"><div class="blk-n">02</div>
  <summary>
    <div style="min-width:0">
      <div class="b2-t">АНАЛИЗ · {len(paras)} БЛОК{"А" if len(paras)>1 else ""}</div>
      <div class="b2-p">{esc(preview)}</div>
    </div>
    <span class="b2-c"></span>
  </summary>
  <div class="b2-body">{body}</div>
</details>"""

        # ── 03 · Стратегия ──
        st = c.get("strategy") or {}
        strat_text = esc(st.get("text") or c.get("strategy_text") or "")
        size_hint = st.get("size_hint") or ""
        tv_url = c.get("tv_url") or ""

        dial = build_dial(
            entry=float(st.get("entry") or c.get("price") or 0),
            stop=float(st.get("stop") or 0),
            target=float(st.get("target1") or 0),
        )
    
        if dial.ok:
            dial_html = f"""
        <div class="rr-dial rr-{dial.grade}">
          <svg viewBox="0 0 100 100" aria-hidden="true">
            <circle class="rr-trk" cx="50" cy="50" r="42"/>
            <circle class="rr-arc" cx="50" cy="50" r="42"
                    stroke-dasharray="{dial.dash} {dial.circumference}"/>
          </svg>
          <div class="rr-val">{dial.rr_text}</div>
          <div class="rr-cap">R : R</div>
        </div>
        <div class="rr-nums">
          <div class="rr-c"><span class="rr-l">ВХОД</span>
            <span class="rr-p rr-e">{fmt_price(dial.entry)}</span></div>
          <div class="rr-c"><span class="rr-l">СТОП</span>
            <span class="rr-p rr-s">{fmt_price(dial.stop)}</span>
            <span class="rr-d">{dial.stop_pct:+.1f}%</span></div>
          <div class="rr-c"><span class="rr-l">ЦЕЛЬ 1</span>
            <span class="rr-p rr-t">{fmt_price(dial.target)}</span>
            <span class="rr-d">{dial.target_pct:+.1f}%</span></div>
        </div>"""
            b3_body = f'<div class="b3-grid">{dial_html}</div>'
        else:
            b3_body = ""

        size_chip = (f'<span class="b3-chip">{esc(size_hint)}</span>'
                     if size_hint else "")
        tv_link = (f'<a class="b3-tv" href="{esc(tv_url)}" target="_blank" '
                   f'rel="noopener">TV ↗</a>' if tv_url else "")

        b3 = f"""
    <div class="blk b3">
      <div class="blk-n">03</div>
      <div class="b3-in">
        <div class="b3-hd">
          <span class="b3-t">СТРАТЕГИЯ</span>{size_chip}{tv_link}
        </div>
        {b3_body}
        <div class="b3-d">{strat_text}</div>
      </div>
    </div>"""

        # ── ссылки ──
        ICON_L = {"tradingview": "📈", "binance": "🅱", "coingecko": "🦎", "twitter": "𝕏"}
        links = c.get("links") or []
        lnk_html = ""
        for i, l in enumerate(links):
            txt = str(l.get("text", ""))
            ico = ICON_L.get(txt.lower().replace(" ", ""), "↗")
            pri = " pri" if i == 0 else ""
            lnk_html += (f'<a class="lnk{pri}" href="{esc(l.get("url",""))}" '
                         f'target="_blank" rel="noopener">'
                         f'<i>{ico}</i>{esc(txt.upper())} ↗</a>')
        links_block = f'<div class="lnks">{lnk_html}</div>' if lnk_html else ""

        inner = f"""
<div class="card-in">
  <div class="hdr {tone}">
    <div class="hdr-cl"><div class="hdr-gh">{esc(ghost)}</div></div>
    <div class="hdr-in">
      <div class="hdr-rk"><b>RANK {esc(rank)}</b><i></i></div>
      <a class="hdr-sym-a" href="{tv}" target="_blank" rel="noopener">
          <div class="hdr-sym" style="font-size:{fs};letter-spacing:{ls}">{esc(sym)}</div>
      <a>
      <div class="hdr-ph">{esc(ph_lbl)}</div>
    </div>
    <div class="hdr-pr">{esc(price)}</div>
  </div>
  <div class="med-link"></div>
  <div class="med {"red" if tone=="red" else ""}" style="--p:{score}">
    <div class="med-i"><div class="med-v">{score}</div><div class="med-l">SCORE</div></div>
  </div>
  <div class="chips">{chips}</div>
  <div class="wrap">
    <div class="rvol">
      <div class="rvol-i">📊</div>
      <div class="rvol-v">{esc(mval(met,"RVOL 1H"))}</div>
      <div class="rvol-l">RVOL 1H</div>
      <div class="rvol-d">{"выше нормы" if mnum(met,"RVOL 1H") >= 1.5 else "в норме"}</div>
    </div>
    <div class="sigs">{sigs}</div>
  </div>
  <div class="perf">{perf}</div>
  <div class="tech">{esc(tech)}</div>
  {b1}{b2}{b3}
  {links_block}
</div>"""

        if glow:
            return f'<div class="card glow {glow}">{inner}</div>'
        return f'<div class="card">{inner}</div>'

    # ─────────────────────────────────────────────
    # Секции-таблицы
    # ─────────────────────────────────────────────
    def render_volume_surge_section(cands: list) -> str:
        items = [c for c in cands if (c.get("surge") or {}).get("detected")]
        if not items:
            return ""
        items.sort(key=lambda c: -(c.get("surge") or {}).get("surge_ratio", 0))
        cfg = {
            "lo": 3.0, "hi": 30.0,
            "lo_lbl": "×3", "hi_lbl": "×30",
            "col2": "ОБЪЁМ 24H / СРЕДНИЙ", "col3": "ПОЛОЖЕНИЕ НА ШКАЛЕ", "col4": "SURGE",
            "value": lambda c: (c.get("surge") or {}).get("surge_ratio", 0),
            "label": lambda c: f'×{(c.get("surge") or {}).get("surge_ratio", 0):.1f}',
            "note":  lambda c: (f'{_big((c.get("surge") or {}).get("current_vol_usd"))}'
                                f' / ср. {_big((c.get("surge") or {}).get("avg_vol_usd"))}'
                                f' · {(c.get("surge") or {}).get("candle_type","")}'),
        }
        return (render_sec("АНОМАЛЬНЫЕ ОБЪЁМЫ", len(items),
                           "дневной объём ≥3× среднего за 30 дней", 2)
                + render_slider_table(items, cfg))

    def render_twitter_hot_section(cands: list) -> str:
        items = [c for c in cands if (c.get("buzz") or {}).get("level") == "hot"]
        if not items:
            return ""
        items.sort(key=lambda c: -mnum(c.get("metrics"), "RVOL 1H"))

        def _setup(c):
            for t in (c.get("tags") or []):
                x = t.get("text", "")
                if "VIRAL" in x:            return "viral hype"
                if "TAIKO CONFIRMED" in x:  return "пробой базы подтверждён"
                if "TAIKO" in x:            return "разворот на старшем ТФ"
                if "DEXE" in x:             return "отскок после дампа"
                if "SQUEEZE" in x:          return "сжатие, риск выброса"
                if "VOL SURGE" in x:        return "всплеск дневного объёма"
            return "накопление без явного сетапа"

        cfg = {
            "lo": 3.0, "hi": 12.0,
            "lo_lbl": "×3", "hi_lbl": "×12",
            "col2": "ХАРАКТЕР ДВИЖЕНИЯ", "col3": "ИНТЕНСИВНОСТЬ RVOL", "col4": "RVOL 1H",
            "value": lambda c: mnum(c.get("metrics"), "RVOL 1H"),
            "label": lambda c: mval(c.get("metrics"), "RVOL 1H"),
            "note":  _setup,
        }
        return (render_sec("TWITTER HOT", len(items),
                           "резкий всплеск объёма и накопления", 2)
                + render_slider_table(items, cfg))

    # ─────────────────────────────────────────────
    # Секции-сетки
    # ─────────────────────────────────────────────
    def render_bucket(name: str, items: list, desc: str, tier: int) -> str:
        if not items:
            return ""
        srt = sorted(items, key=lambda x: -x.get("score", 0))
        cards = "\n".join(render_card(r) for r in srt)
        return render_sec(name, len(items), desc, tier) + f'<div class="grid">{cards}</div>'

    header_html = render_header(len(rows))
    body = "".join([
        render_bucket("VIRAL", viral, "meme/gamefi hype · размер позиции ¼, горизонт 1–3 дня", 1),
        render_twitter_hot_section(rows),
        render_volume_surge_section(rows),
        render_bucket("TAIKO",  taiko,  "подтверждённые развороты на старшем ТФ", 2),
        render_bucket("DEXE",   dexe,   "отскок после дампа, post-pump", 2),
        render_bucket("STRONG", strong, "совпало несколько независимых условий", 3),
        render_bucket("GOOD",   good,   "сетап пригоден к торговле", 3),
        render_bucket("SCOUT",  scout,  "ранняя стадия, вход преждевременен", 4),
        render_bucket("WATCH",  watch,  "только наблюдение, действий нет", 4),
    ])

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sleeping Alts Screener</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800;900&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>
{header_html}
{body}
</body>
</html>
"""

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
        if not base.isascii():
            continue
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
    errors: list[tuple[str, str]] = []
    for i, (sym, _) in enumerate(candidates_syms, 1):
        try:
            print(f"  [{i}/{len(candidates_syms)}] {sym}...", end=" ", flush=True)
            c = build_candidate(sym, i)
            if c:
                results.append(c)
                print(f"score={c.score} bucket={c.bucket}")
            else:
                print("skip")
                time.sleep(0.25)
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")
            errors.append((sym, f"{type(e).__name__}: {e}"))
            traceback.print_exc()

    # Сортируем по score
    results.sort(key=lambda x: -x.score)

    if errors:
        print(f"\n⚠ Ошибок: {len(errors)} из {len(candidates_syms)}")
        for sym, err in errors[:10]:
            print(f"   {sym}: {err}")

    print(f"→ Генерирую HTML отчёт → {REPORT_HTML}")
    html_str = build_html(results)
    REPORT_HTML.write_text(html_str, encoding="utf-8")
    print(f"✓ Готово! Открой {REPORT_HTML}")

if __name__ == "__main__":
    main()

# ═══════════════════════════════════════════════════════════════
#  ЧАСТЬ 3b/3 КОНЕЦ · ФАЙЛ ЗАВЕРШЁН
# ═══════════════════════════════════════════════════════════════
