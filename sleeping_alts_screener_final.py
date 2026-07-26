"""
sleeping_alts_screener_final.py
================================
Основной скрипт скринера "спящих" альткоинов Binance Futures.

Модули рядом:
  • external_data.py       — CoinGecko + DefiLlama
  • squeeze_detector.py    — детектор manipulated squeeze

Логика:
  1. Тянем список USDT-перпов с Binance Futures.
  2. Для каждой пары считаем метрики (RVOL, ATR, RSI, OBV, Vortex-фаза,
     spot/futures ratio, funding, OI).
  3. Обогащаем фундаменталкой (CoinGecko + DefiLlama).
  4. Детектим squeeze-risk.
  5. Классифицируем в бакеты: strong / good / scout / watch.
  6. Рендерим HTML (HEX GRID дизайн).
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from external_data import get_fundamentals, build_fundamental_take_live
from squeeze_detector import analyze_squeeze, get_squeeze_tag
from taiko_detector import detect_taiko

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("screener")

# ============================================================
# CONFIG
# ============================================================
BINANCE_FAPI = "https://fapi.binance.com"
BINANCE_SAPI = "https://api.binance.com"

OUT_DIR = Path("./out")
OUT_DIR.mkdir(parents=True, exist_ok=True)

REPORT_HTML = OUT_DIR / "screener_report.html"

MAX_WORKERS = 8
REQUEST_TIMEOUT = (8, 20)
HEADERS = {"User-Agent": "Mozilla/5.0 SleepingAlts/1.0"}

# Фильтры отбора
MIN_QUOTE_VOL_24H = 3_000_000       # USDT
MAX_PRICE_CHANGE_30D = 300          # если +300% за 30d — уже не "спящая"
MIN_RVOL_1H = 1.3
MIN_SCORE_TO_INCLUDE = 30

# Исключения (стейблы, wrapped, мемы вне интереса)
EXCLUDE_BASES = {
    # стейблы
    "USDC", "TUSD", "FDUSD", "BUSD", "DAI", "USDP", "USTC",
    # топ-капы (не "спящие")
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "TRX",
    "LTC", "BCH", "LINK", "AVAX", "DOT", "MATIC", "TON",
    "SHIB", "UNI", "ATOM", "XLM", "ETC", "FIL", "NEAR",
    "APT", "ARB", "OP", "SUI", "HBAR", "ICP", "AAVE",
}


# ============================================================
# DATACLASS
# ============================================================

@dataclass
class Candidate:
    symbol: str
    bucket: str = "watch"          # strong | good | scout | watch
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


# ============================================================
# HTTP
# ============================================================

def http_get(url: str, params: dict | None = None) -> Any:
    try:
        r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT, headers=HEADERS)
        if r.status_code == 200:
            return r.json()
        log.debug(f"HTTP {r.status_code}: {url}")
    except Exception as e:
        log.debug(f"HTTP fail {url}: {e}")
    return None


# ============================================================
# MARKET DATA
# ============================================================

def fetch_futures_symbols() -> list[str]:
    data = http_get(f"{BINANCE_FAPI}/fapi/v1/exchangeInfo")
    if not data:
        return []
    out = []
    for s in data.get("symbols", []):
        if s.get("status") != "TRADING":
            continue
        if s.get("contractType") != "PERPETUAL":
            continue
        if s.get("quoteAsset") != "USDT":
            continue
        base = s.get("baseAsset", "")
        if base in EXCLUDE_BASES:
            continue
        out.append(s["symbol"])
    return sorted(set(out))


def fetch_24h_stats() -> dict[str, dict]:
    data = http_get(f"{BINANCE_FAPI}/fapi/v1/ticker/24hr")
    if not isinstance(data, list):
        return {}
    return {x["symbol"]: x for x in data}


def fetch_klines(symbol: str, interval: str, limit: int = 200) -> list[list] | None:
    return http_get(
        f"{BINANCE_FAPI}/fapi/v1/klines",
        {"symbol": symbol, "interval": interval, "limit": limit},
    )


def fetch_funding(symbol: str) -> float:
    data = http_get(f"{BINANCE_FAPI}/fapi/v1/premiumIndex", {"symbol": symbol})
    if isinstance(data, dict):
        try:
            return float(data.get("lastFundingRate", 0)) * 100
        except Exception:
            return 0.0
    return 0.0


def fetch_oi(symbol: str) -> float:
    data = http_get(f"{BINANCE_FAPI}/fapi/v1/openInterest", {"symbol": symbol})
    if isinstance(data, dict):
        try:
            return float(data.get("openInterest", 0))
        except Exception:
            return 0.0
    return 0.0


def fetch_spot_klines(symbol: str, interval: str = "1d", limit: int = 7) -> list[list] | None:
    return http_get(
        f"{BINANCE_SAPI}/api/v3/klines",
        {"symbol": symbol, "interval": interval, "limit": limit},
    )


# ============================================================
# INDICATORS
# ============================================================

def rsi(closes: list[float], period: int = 14) -> float:
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


def atr_pct(highs, lows, closes, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    atr = sum(trs[-period:]) / period
    return (atr / closes[-1]) * 100 if closes[-1] > 0 else 0.0


def obv(closes, vols) -> list[float]:
    out = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            out.append(out[-1] + vols[i])
        elif closes[i] < closes[i - 1]:
            out.append(out[-1] - vols[i])
        else:
            out.append(out[-1])
    return out


def obv_slope(closes, vols, lookback: int = 20) -> float:
    o = obv(closes, vols)
    if len(o) < lookback:
        return 0.0
    tail = o[-lookback:]
    if tail[0] == 0:
        return 0.0
    return (tail[-1] - tail[0]) / abs(tail[0]) * 100


def rvol(vols: list[float], period: int = 20) -> float:
    if len(vols) < period + 1:
        return 1.0
    avg = sum(vols[-period - 1:-1]) / period
    if avg <= 0:
        return 1.0
    return vols[-1] / avg


def vortex_phase(closes: list[float], rsi_val: float, obv_slp: float) -> tuple[int, str]:
    """
    1 Accumulation | 2 Reversal | 3 Breakout | 4 Trend | 5 Euphoria
    Каждая фаза имеет ОДНО имя. Никаких пересечений.
    """
    if len(closes) < 20:
        return 3, "Breakout"

    c20 = closes[-20]
    change = (closes[-1] / c20 - 1) * 100 if c20 > 0 else 0

    # 5. Euphoria — параболический перегрев
    if rsi_val >= 82 and change > 25:
        return 5, "Euphoria"

    # 1. Accumulation — глубокая перепроданность, объёмы сухие
    if rsi_val < 35 and abs(obv_slp) < 5:
        return 1, "Accumulation"

    # 2. Reversal — разворот от низов
    if rsi_val < 45 and obv_slp > 0:
        return 2, "Reversal"

    # 4. Trend — устойчивое движение
    if rsi_val > 60 and change > 8:
        return 4, "Trend"

    # 3. Breakout — всё остальное (переход/пробой)
    return 3, "Breakout"


# ============================================================
# ANALYSIS PER SYMBOL
# ============================================================

def analyze_symbol(symbol: str, tick24: dict) -> dict | None:
    """Возвращает словарь метрик или None если данных недостаточно."""
    try:
        quote_vol = float(tick24.get("quoteVolume", 0))
    except Exception:
        quote_vol = 0
    if quote_vol < MIN_QUOTE_VOL_24H:
        return None

    try:
        price_change_24h = float(tick24.get("priceChangePercent", 0))
    except Exception:
        price_change_24h = 0

    # 4h klines (для RSI, ATR, OBV, Vortex)
    kl4 = fetch_klines(symbol, "4h", 120)
    if not kl4 or len(kl4) < 30:
        return None
    highs4 = [float(k[2]) for k in kl4]
    lows4  = [float(k[3]) for k in kl4]
    closes4 = [float(k[4]) for k in kl4]
    vols4 = [float(k[7]) for k in kl4]

    # 1h klines (для RVOL)
    kl1 = fetch_klines(symbol, "1h", 60)
    if not kl1 or len(kl1) < 25:
        return None
    vols1 = [float(k[7]) for k in kl1]

    # 1d klines (для 30d change)
    kld = fetch_klines(symbol, "1d", 40)
    if not kld or len(kld) < 30:
        return None
    closesd = [float(k[4]) for k in kld]
    price_change_30d = (closesd[-1] / closesd[-30] - 1) * 100 if closesd[-30] > 0 else 0

    # Отсекаем "уже улетевшие"
    if price_change_30d > MAX_PRICE_CHANGE_30D:
        return None

    rvol_1h = rvol(vols1, 20)
    if rvol_1h < MIN_RVOL_1H and price_change_24h < 5:
        return None

    rsi_4h = rsi(closes4, 14)
    atr_4h = atr_pct(highs4, lows4, closes4, 14)
    obv_slp = obv_slope(closes4, vols4, 20)
    phase_num, phase_name = vortex_phase(closes4, rsi_4h, obv_slp)

    funding = fetch_funding(symbol)

    # Spot / futures ratio
    spot_kl = fetch_spot_klines(symbol, "1d", 7)
    spot_ratio = 0.0
    if spot_kl and len(spot_kl) >= 3:
        try:
            spot_vol = sum(float(k[7]) for k in spot_kl)
            fut_kld_vol = sum(float(k[7]) for k in kld[-7:])
            if fut_kld_vol > 0:
                spot_ratio = spot_vol / fut_kld_vol
        except Exception:
            pass

    passes_normal = (price_change_30d <= MAX_PRICE_CHANGE_30D
                     and (rvol_1h >= MIN_RVOL_1H or price_change_24h >= 5))
    passes_htf_candidate = price_change_30d < -30  # TAIKO/DEXE кандидат
    if not (passes_normal or passes_htf_candidate):
        return None

    return {
        "symbol": symbol,
        "price": closes4[-1],
        "quote_vol_24h": quote_vol,
        "price_change_24h": price_change_24h,
        "price_change_30d": price_change_30d,
        "rvol_1h": rvol_1h,
        "rsi_4h": rsi_4h,
        "atr_4h": atr_4h,
        "obv_slope": obv_slp,
        "funding": funding,
        "spot_ratio": spot_ratio,
        "phase_num": phase_num,
        "phase_name": phase_name,
    }


# ============================================================
# SCORING
# ============================================================

def score_candidate(m: dict) -> int:
    score = 0

    # RVOL
    if m["rvol_1h"] >= 3.0:
        score += 20
    elif m["rvol_1h"] >= 2.0:
        score += 14
    elif m["rvol_1h"] >= 1.5:
        score += 8

    # OBV slope (накопление)
    if m["obv_slope"] > 30:
        score += 15
    elif m["obv_slope"] > 10:
        score += 8
    elif m["obv_slope"] < -20:
        score -= 8

    # RSI зона
    if 45 < m["rsi_4h"] <= 65:
        score += 10
    elif 65 < m["rsi_4h"] <= 75:
        score += 6
    elif m["rsi_4h"] > 85:
        score -= 10
    elif m["rsi_4h"] < 30:
        score += 5  # oversold bounce

    # ATR — волатильность нужна, но не сумасшедшая
    if 3 <= m["atr_4h"] <= 8:
        score += 8
    elif m["atr_4h"] > 15:
        score -= 5

    # Vortex phase
    phase_bonus = {1: 8, 2: 15, 3: 18, 4: 12, 5: -8}
    score += phase_bonus.get(m["phase_num"], 0)

    # Funding — экстремум это плохо
    if m["funding"] > 0.10:
        score -= 8
    elif m["funding"] < -0.05:
        score += 5  # шорты перегружены

    # Spot > 0.5 = здоровая база
    if m["spot_ratio"] >= 0.5:
        score += 8
    elif 0 < m["spot_ratio"] < 0.2:
        score -= 5

    # 24h умеренный рост — свежий импульс
    if 3 < m["price_change_24h"] < 20:
        score += 6
    elif m["price_change_24h"] > 40:
        score -= 5

    # 30d "спящая": не улетала
    if m["price_change_30d"] < 30:
        score += 6

    return max(0, min(score, 100))


def bucket_from_score(score: int, phase_num: int) -> str:
    if score >= 70:
        return "strong"
    if score >= 55:
        return "good"
    if score >= 40 or phase_num in (2, 1):
        return "scout"
    return "watch"


# ============================================================
# BUILD CANDIDATE
# ============================================================

def fmt_pct(v: float, decimals: int = 1) -> str:
    return f"{v:+.{decimals}f}%"


def fmt_usd_short(v: float) -> str:
    if v >= 1e9:
        return f"${v/1e9:.2f}B"
    if v >= 1e6:
        return f"${v/1e6:.1f}M"
    if v >= 1e3:
        return f"${v/1e3:.1f}K"
    return f"${v:.0f}"


def build_candidate(m: dict, rank_idx: int) -> Candidate:
    symbol = m["symbol"]
    score = score_candidate(m)
    bucket = bucket_from_score(score, m["phase_num"])

    tags: list[dict] = []

    # Фундаменталка
    fund = get_fundamentals(symbol)
    if fund.categories:
        tags.append({"text": fund.categories[0], "class": "tag-cat"})
    elif fund.defillama_category:
        tags.append({"text": fund.defillama_category, "class": "tag-cat"})

    # Squeeze detector
    sq = analyze_squeeze(symbol)
    taiko_sig = detect_taiko(symbol)

    # Форсим TAIKO-кандидатов в отчёт даже с низким скоромf
    if taiko_sig.detected:
        tags.append({"text": f"◉ TAIKO REVERSAL · {taiko_sig.score}", "class": "tag-pattern taiko"})
    elif (sq.risk_level in ("high", "extreme")
            and m["price_change_24h"] < 5 and m["rsi_4h"] < 55):
        tags.append({"text": "◉ DEXE POST-PUMP", "class": "tag-pattern dexe"})
    elif m["phase_num"] == 2:
        tags.append({"text": "REVERSAL", "class": "tag-pattern"})

    sq_tag = get_squeeze_tag(sq)
    if sq_tag:
        tags.append(sq_tag)

    # Паттерн-тэги (эвристика по фазе)
    # Паттерн-метки (для быстрого визуального сканирования отчёта)
    # TAIKO REVERSAL: капитуляция на HTF — RSI низкий, OBV разворачивается, цена глубоко упала
    if (m["phase_num"] == 2
            and m["rsi_4h"] < 42
            and m["obv_slope"] > 0
            and m["price_change_30d"] < -30):
        tags.append({"text": "◉ TAIKO REVERSAL", "class": "tag-pattern taiko"})

    # DEXE POST-PUMP: недавний памп + squeeze в истории + сейчас откат/консолидация
    elif (sq.risk_level in ("high", "extreme")
            and m["price_change_24h"] < 5
            and m["rsi_4h"] < 55):
        tags.append({"text": "◉ DEXE POST-PUMP", "class": "tag-pattern dexe"})

    # Обычные фазовые теги
    elif m["phase_num"] == 2:
        tags.append({"text": "REVERSAL", "class": "tag-pattern"})
    elif m["phase_num"] == 3:
        tags.append({"text": "BREAKOUT", "class": "tag-pattern"})
    elif m["phase_num"] == 4:
        tags.append({"text": "TREND", "class": "tag-pattern"})
    elif m["phase_num"] == 5:
        tags.append({"text": "⚠ EUPHORIA", "class": "tag-pattern dexe"})
    elif m["phase_num"] == 1:
        tags.append({"text": "ACCUMULATION", "class": "tag-pattern taiko"})

    # extreme squeeze понижаем в watch
    if sq.risk_level == "extreme" and bucket in ("strong", "good"):
        bucket = "watch"

    # Phase
    phase_class_map = {1: "phase-p1", 2: "phase-p2", 3: "phase-p3", 4: "phase-p4", 5: "phase-p5"}
    phase = {
        "class": phase_class_map.get(m["phase_num"], "phase-p3"),
        "icon": str(m["phase_num"]),
        "name": m["phase_name"],
        "tf": "4H",
    }

    # Metrics
    metrics = [
        {"key": "24h", "val": fmt_pct(m["price_change_24h"]),
         "cls": "up" if m["price_change_24h"] > 0 else "down"},
        {"key": "30d", "val": fmt_pct(m["price_change_30d"]),
         "cls": "up" if m["price_change_30d"] > 0 else "down"},
        {"key": "RVOL 1H", "val": f"{m['rvol_1h']:.2f}×",
         "cls": "hot" if m["rvol_1h"] >= 2 else ""},
        {"key": "RSI 4H", "val": f"{m['rsi_4h']:.0f}",
         "cls": "warn" if m["rsi_4h"] > 75 else ""},
        {"key": "ATR", "val": f"{m['atr_4h']:.1f}%", "cls": ""},
        {"key": "OBV", "val": fmt_pct(m["obv_slope"], 0),
         "cls": "up" if m["obv_slope"] > 0 else "down"},
        {"key": "FUNDING", "val": f"{m['funding']:+.3f}%",
         "cls": "warn" if abs(m["funding"]) > 0.08 else ""},
        {"key": "SPOT/FUT", "val": f"{m['spot_ratio']:.2f}",
         "cls": "" if m["spot_ratio"] > 0.4 else "warn"},
        {"key": "VOL 24H", "val": fmt_usd_short(m["quote_vol_24h"]), "cls": ""},
    ]

    # Ссылки
    base = symbol.replace("USDT", "")
    links = [
        {"text": "TV",   "url": f"https://www.tradingview.com/chart/?symbol=BINANCE:{symbol}.P"},
        {"text": "BIN",  "url": f"https://www.binance.com/en/futures/{symbol}"},
    ]
    if fund.coingecko_id:
        links.append({"text": "CG", "url": f"https://www.coingecko.com/en/coins/{fund.coingecko_id}"})
    if fund.defillama_slug:
        links.append({"text": "LLAMA", "url": f"https://defillama.com/protocol/{fund.defillama_slug}"})
    if fund.twitter_handle:
        links.append({"text": "X", "url": f"https://twitter.com/{fund.twitter_handle}"})
    if fund.homepage:
        links.append({"text": "WEB", "url": fund.homepage})

    # DEX/Onchain (из фундаменталки)
    dexe = None
    dexe_cells = []
    if fund.mcap_usd > 0:
        dexe_cells.append({"k": "MCAP", "v": fmt_usd_short(fund.mcap_usd), "cls": ""})
    if fund.mcap_rank:
        dexe_cells.append({"k": "RANK", "v": f"#{fund.mcap_rank}", "cls": ""})
    if fund.fdv_usd > 0 and fund.mcap_usd > 0:
        ratio = fund.fdv_usd / fund.mcap_usd
        cls = "rev-hot" if ratio >= 3 else ("down" if ratio >= 1.8 else "")
        dexe_cells.append({"k": "FDV/MC", "v": f"{ratio:.2f}×", "cls": cls})
    if fund.tvl_usd > 0:
        dexe_cells.append({"k": "TVL", "v": fmt_usd_short(fund.tvl_usd), "cls": ""})
    if fund.tvl_change_7d:
        cls = "up" if fund.tvl_change_7d > 0 else "down"
        dexe_cells.append({"k": "TVL 7D", "v": fmt_pct(fund.tvl_change_7d), "cls": cls})
    if fund.price_change_7d:
        cls = "up" if fund.price_change_7d > 0 else "down"
        dexe_cells.append({"k": "PRICE 7D", "v": fmt_pct(fund.price_change_7d), "cls": cls})
    if dexe_cells:
        dexe = {"cells": dexe_cells}

    # Fundamental Take
    analysis = ""
    if fund.has_data():
        try:
            analysis = build_fundamental_take_live(fund)
        except Exception as e:
            log.debug(f"fund take failed for {symbol}: {e}")

    # Twitter Buzz (эвристика от RVOL/OBV)
    buzz = None
    if m["rvol_1h"] >= 3 and m["obv_slope"] > 20:
        buzz = {
            "level_class": "buzz-hot",
            "level_text": "HOT",
            "text": "Резкий всплеск объёма + активное накопление. Внимание рынка на паре, часто идёт вместе с ростом упоминаний в X/Twitter.",
        }
    elif m["rvol_1h"] >= 1.8:
        buzz = {
            "level_class": "buzz-warm",
            "level_text": "WARM",
            "text": "Объём выше среднего, растёт интерес. Пара может быть на радаре трейдеров.",
        }
    elif m["rvol_1h"] >= 1.2:
        buzz = {
            "level_class": "buzz-cool",
            "level_text": "COOL",
            "text": "Умеренная активность. Пара в фоновом режиме, без явного хайпа.",
        }
    else:
        buzz = {
            "level_class": "buzz-cold",
            "level_text": "COLD",
            "text": "Низкий уровень внимания. Полностью «спящая» пара.",
        }

    # Squeeze block
    squeeze_block = None
    if sq.risk_level != "none":
        squeeze_block = {
            "level": sq.risk_level,
            "score": sq.risk_score,
            "reasons": sq.reasons,
            "verdict": sq.verdict,
            "funding_peak": sq.funding_peak_14d,
            "oi_change": sq.oi_change_14d_pct,
            "spot_fut": sq.spot_futures_ratio,
        }

    # Strategy
    strategy = build_strategy(m, sq, bucket)

    return Candidate(
        symbol=symbol,
        bucket=bucket,
        rank=f"#{rank_idx:03d}",
        score=score,
        tags=tags,
        phase=phase,
        metrics=metrics,
        dexe=dexe,
        analysis=analysis,
        buzz=buzz,
        strategy=strategy,
        squeeze=squeeze_block,
        links=links,
    )


def build_strategy(m: dict, sq, bucket: str) -> str:
    if sq.risk_level == "extreme":
        return ("Не входить в лонг сейчас. Если пара в позиции — фиксировать по факту разворота. "
                "Возможен откат 60–80% от топа. Шорт — только после подтверждённого пробоя вниз.")
    if bucket == "strong":
        return ("Приоритетный сетап. Заход лесенкой на ретестах поддержки, "
                f"стоп под ATR×1.5 (~{m['atr_4h']*1.5:.1f}%). Фикс частями на 1.5R / 3R / 5R.")
    if bucket == "good":
        return ("Валидный сетап. Ждать локального отката для входа, стоп под ближайший low. "
                "Не спешить — если пропустил вход, не догонять.")
    if bucket == "scout":
        return ("Ранняя стадия. Держать в watchlist, входить только после подтверждения "
                "объёмом и пробоя ключевого уровня.")
    return "Наблюдение. Пока нет достаточной силы для входа — ждать формирования сетапа."


# ============================================================
# HTML RENDER (HEX GRID)
# ============================================================

def build_html(rows, out_path=None) -> str:
    from datetime import datetime as _dt
    import html as _html

    def esc(s) -> str:
        return _html.escape(str(s) if s is not None else "")

    def to_dict(r):
        if isinstance(r, dict):
            return r
        if is_dataclass(r):
            return asdict(r)
        return {k: getattr(r, k) for k in dir(r)
                if not k.startswith("_") and not callable(getattr(r, k))}

    rows = [to_dict(r) for r in rows]

    def has_tag(r, needle: str) -> bool:
        for t in (r.get("tags") or []):
            if needle in (t.get("text") or ""):
                return True
        return False

    taiko = [r for r in rows if has_tag(r, "TAIKO REVERSAL")]
    dexe  = [r for r in rows if has_tag(r, "DEXE POST-PUMP")]

    # Исключаем TAIKO/DEXE из общих бакетов, чтобы не дублировать
    special_syms = {r.get("symbol") for r in taiko + dexe}
    rest = [r for r in rows if r.get("symbol") not in special_syms]

    strong = [r for r in rest if r.get("bucket") == "strong"]
    good   = [r for r in rest if r.get("bucket") == "good"]
    scout  = [r for r in rest if r.get("bucket") == "scout"]
    watch  = [r for r in rest if r.get("bucket") == "watch"]

    total = len(rows)
    ts = _dt.now().strftime("%Y-%m-%d %H:%M UTC")

    css = r"""
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg-0:#080b12;--bg-1:#0d1220;
  --panel:#111827;--panel-2:#1a2338;--panel-3:#232e48;
  --line:rgba(120,150,220,0.14);--line-hi:rgba(140,180,255,0.42);
  --ink:#e8ecf5;--ink-dim:#b8c2d6;--mute:#6b7688;--soft:#3d4560;
  --cyan:#22d3ee;--blue:#5a9dff;--violet:#a78bfa;--pink:#f472b6;
  --green:#34d399;--amber:#fbbf24;--coral:#f87171;
}
html,body{
  background:
    radial-gradient(1200px 700px at 15% -10%, rgba(90,157,255,0.06), transparent 60%),
    radial-gradient(900px 600px at 100% 100%, rgba(167,139,250,0.05), transparent 60%),
    linear-gradient(180deg, var(--bg-0) 0%, var(--bg-1) 100%);
  background-attachment:local;color:var(--ink);
  font-family:"JetBrains Mono","SF Mono","Menlo",ui-monospace,monospace;
  min-height:100vh;-webkit-font-smoothing:antialiased;
}
body::before{
  content:"";position:fixed;inset:0;
  background-image:
    linear-gradient(rgba(120,150,220,0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(120,150,220,0.04) 1px, transparent 1px);
  background-size:56px 56px;pointer-events:none;z-index:0;
}
.container{max-width:1520px;margin:0 auto;padding:32px 24px 80px;position:relative;z-index:1}
.hex{clip-path:polygon(18px 0,calc(100% - 18px) 0,100% 18px,100% calc(100% - 18px),calc(100% - 18px) 100%,18px 100%,0 calc(100% - 18px),0 18px)}
.hex-sm{clip-path:polygon(10px 0,calc(100% - 10px) 0,100% 10px,100% calc(100% - 10px),calc(100% - 10px) 100%,10px 100%,0 calc(100% - 10px),0 10px)}

@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
@keyframes scan{0%{transform:translateX(-100%)}100%{transform:translateX(200%)}}

.header{display:flex;justify-content:space-between;align-items:center;padding:26px 32px;margin-bottom:24px;gap:16px;flex-wrap:wrap;background:linear-gradient(135deg,var(--panel) 0%,var(--panel-2) 100%);position:relative}
.brand{display:flex;align-items:center;gap:14px}
.brand-icon{width:44px;height:44px;background:linear-gradient(135deg,var(--cyan),var(--blue));display:flex;align-items:center;justify-content:center;color:#0b0f18;font-size:20px;font-weight:900}
.brand-title{font-size:22px;font-weight:800;letter-spacing:-0.2px;color:var(--ink);font-family:"Inter",sans-serif}
.subtitle{color:var(--mute);font-size:10px;letter-spacing:2.5px;text-transform:uppercase;margin-top:4px;font-weight:700}
.header-right{text-align:right}
.status-badge{display:inline-flex;align-items:center;gap:8px;padding:6px 14px;background:rgba(52,211,153,0.10);border:1px solid rgba(52,211,153,0.4);font-size:10px;color:var(--green);letter-spacing:1.4px;font-weight:800;margin-bottom:6px;text-transform:uppercase}
.status-dot{width:6px;height:6px;background:var(--green);border-radius:50%;animation:pulse 1.6s infinite;box-shadow:0 0 6px var(--green)}
.timestamp{font-size:11px;color:var(--ink-dim);letter-spacing:1.2px;font-weight:600}
.timestamp span{color:var(--cyan);margin-left:6px;font-weight:800}

.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-bottom:22px}
.stat{padding:18px 22px 18px 26px;background:var(--panel);position:relative;transition:transform .2s,background .2s;border-left:2px solid var(--stat-color,var(--blue))}
.stat::before{content:"";position:absolute;top:0;right:0;width:24px;height:24px;background:linear-gradient(225deg,var(--stat-color,var(--blue)) 50%,transparent 50%);opacity:.6}
.stat:hover{transform:translateY(-2px);background:var(--panel-2)}
.stat-strong{--stat-color:var(--green)}.stat-good{--stat-color:var(--blue)}
.stat-scout{--stat-color:var(--amber)}.stat-watch{--stat-color:var(--mute)}
.stat-label{font-size:9px;color:var(--mute);letter-spacing:2px;text-transform:uppercase;margin-bottom:8px;font-weight:800}
.stat-value{font-size:30px;font-weight:800;color:var(--ink);line-height:1;letter-spacing:-1px;font-family:"Inter",sans-serif}
.stat-value.accent{color:var(--stat-color,var(--blue))}
.stat-sub{font-size:10px;color:var(--mute);margin-top:4px;font-weight:600;letter-spacing:.5px}
.stat-taiko{--stat-color:var(--cyan)}
.stat-dexe{--stat-color:var(--pink)}
.section-taiko{--section-color:var(--cyan)}
.section-dexe{--section-color:var(--pink)}

.filter-bar{display:flex;gap:8px;margin-bottom:22px;flex-wrap:wrap;padding:12px 18px;background:var(--panel);border-left:2px solid var(--cyan)}
.filter-label{font-size:9px;color:var(--mute);letter-spacing:2px;text-transform:uppercase;align-self:center;font-weight:800;margin-right:4px}
.pill{padding:4px 12px;background:var(--panel-2);font-size:10px;letter-spacing:1px;color:var(--ink-dim);display:inline-flex;align-items:center;gap:6px;font-weight:700;text-transform:uppercase;border:1px solid var(--line)}
.pill-dot{width:5px;height:5px;border-radius:50%}

.phase-legend{background:var(--panel);padding:18px 22px;margin-bottom:22px;border-left:2px solid var(--violet);position:relative}
.phase-legend-title{font-size:10px;color:var(--violet);letter-spacing:2.5px;text-transform:uppercase;font-weight:800;margin-bottom:14px}
.phase-legend-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;margin-bottom:14px}
.pl-item{display:flex;gap:12px;padding:10px 12px;background:var(--panel-2);border-left:2px solid var(--pl-color,var(--blue));align-items:flex-start}
.pl-1{--pl-color:var(--coral)}
.pl-2{--pl-color:var(--amber)}
.pl-3{--pl-color:var(--cyan)}
.pl-4{--pl-color:var(--green)}
.pl-5{--pl-color:var(--pink)}
.pl-num{width:26px;height:26px;flex-shrink:0;background:var(--pl-color);color:#0b0f18;font-size:12px;font-weight:900;display:flex;align-items:center;justify-content:center;font-family:"Inter",sans-serif}
.pl-body{flex:1;min-width:0}
.pl-name{font-size:11px;color:var(--pl-color);letter-spacing:1.4px;text-transform:uppercase;font-weight:800;margin-bottom:3px;font-family:"JetBrains Mono",monospace}
.pl-desc{font-size:11px;color:var(--ink-dim);line-height:1.45;font-family:"Inter",sans-serif}
.phase-legend-tags{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;padding-top:12px;border-top:1px solid var(--line);font-size:11px;color:var(--ink-dim);font-family:"Inter",sans-serif}
.pl-tag{font-size:9px;letter-spacing:1.2px;padding:3px 9px;font-weight:800;text-transform:uppercase;font-family:"JetBrains Mono",monospace}
.pl-tag-taiko{background:rgba(34,211,238,0.10);color:var(--cyan);border:1px solid rgba(34,211,238,0.4)}
.pl-tag-dexe{background:rgba(244,114,182,0.10);color:var(--pink);border:1px solid rgba(244,114,182,0.4)}
.pl-tag-desc{color:var(--mute);font-size:10.5px}

.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(410px,1fr));gap:16px;content-visibility:auto;contain-intrinsic-size:0 740px}
.card{position:relative;background:var(--panel);padding:22px 24px 20px;animation:fadeUp .35s backwards;transition:background .2s;contain:layout style paint;--card-color:var(--blue);overflow:hidden}
.card:hover{background:var(--panel-2)}
.card::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--card-color);clip-path:polygon(0 8px,100% 0,100% 100%,0 calc(100% - 8px))}
.card::after{content:"";position:absolute;top:0;right:0;width:36px;height:36px;background:linear-gradient(225deg,var(--card-color) 50%,transparent 50%);opacity:.22}
.card-strong{--card-color:var(--green)}.card-good{--card-color:var(--blue)}
.card-scout{--card-color:var(--amber)}.card-watch{--card-color:var(--mute)}

.card-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px;gap:12px;position:relative;z-index:1}
.rank-symbol{display:flex;align-items:center;gap:10px}
.rank{font-size:9px;color:var(--mute);padding:3px 9px;background:var(--panel-3);letter-spacing:1px;font-weight:800}
.symbol{font-size:20px;font-weight:800;color:var(--ink);font-family:"Inter",sans-serif}
.tag-row{display:flex;gap:5px;flex-wrap:wrap;margin-top:6px}
.tag{font-size:8px;letter-spacing:1.2px;padding:3px 8px;font-weight:800;text-transform:uppercase}
.tag-cat{background:color-mix(in srgb,var(--card-color) 15%,transparent);color:var(--card-color);border:1px solid color-mix(in srgb,var(--card-color) 40%,transparent)}
.tag-pattern{background:rgba(167,139,250,0.10);color:var(--violet);border:1px solid rgba(167,139,250,0.38)}
.tag-pattern.taiko{background:rgba(34,211,238,0.10);color:var(--cyan);border-color:rgba(34,211,238,0.4)}
.tag-pattern.dexe{background:rgba(244,114,182,0.10);color:var(--pink);border-color:rgba(244,114,182,0.4)}

.links-row{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:12px}
.link-chip{font-size:9px;letter-spacing:1.2px;padding:4px 10px;background:var(--panel-2);color:var(--ink-dim);border:1px solid var(--line);font-family:"JetBrains Mono",monospace;font-weight:800;text-transform:uppercase;transition:background .18s,color .18s,border-color .18s}
.link-chip:hover{background:var(--panel-3);color:var(--cyan);border-color:rgba(34,211,238,0.4)}

.tag-squeeze-low{background:rgba(34,211,238,0.10);color:var(--cyan);border:1px solid rgba(34,211,238,0.4)}
.tag-squeeze-med{background:rgba(251,191,36,0.12);color:var(--amber);border:1px solid rgba(251,191,36,0.4)}
.tag-squeeze-high{background:rgba(248,113,113,0.12);color:var(--coral);border:1px solid rgba(248,113,113,0.4)}
.tag-squeeze-ext{background:var(--coral);color:#0b0f18;border:1px solid var(--coral);animation:pulse 2s infinite}

.score-badge{min-width:64px;text-align:center;padding:8px 12px;background:color-mix(in srgb,var(--card-color) 10%,transparent);border:1px solid color-mix(in srgb,var(--card-color) 40%,transparent);position:relative}
.score-badge::before{content:"";position:absolute;top:-1px;right:-1px;width:8px;height:8px;background:var(--card-color);clip-path:polygon(100% 0,100% 100%,0 0)}
.score-badge-label{font-size:8px;color:var(--mute);letter-spacing:1.4px;text-transform:uppercase;font-weight:800}
.score-badge-value{font-size:24px;font-weight:800;color:var(--card-color);line-height:1;letter-spacing:-0.5px;font-family:"Inter",sans-serif;margin-top:2px}

.phase-indicator{display:flex;align-items:center;gap:10px;padding:9px 14px;margin-bottom:12px;background:var(--panel-2);border-left:2px solid var(--phase-color,var(--blue))}
.phase-icon{width:22px;height:22px;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:900;background:var(--phase-color,var(--blue));color:#0b0f18;font-family:"Inter",sans-serif}
.phase-p1{--phase-color:var(--coral)}.phase-p2{--phase-color:var(--amber)}
.phase-p3{--phase-color:var(--cyan)}.phase-p4{--phase-color:var(--green)}
.phase-p5{--phase-color:var(--pink)}
.phase-name{font-size:10px;color:var(--ink-dim);letter-spacing:1.5px;font-weight:800;flex:1;text-transform:uppercase}
.phase-tf{font-size:9px;color:var(--cyan);padding:3px 8px;background:rgba(34,211,238,0.10);border:1px solid rgba(34,211,238,0.35);letter-spacing:1px;font-weight:800}

.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;margin-bottom:12px;background:var(--line)}
.metric{padding:10px 12px;background:var(--panel);transition:background .18s}
.metric:hover{background:var(--panel-3)}
.metric-key{font-size:8px;color:var(--mute);letter-spacing:1.4px;text-transform:uppercase;margin-bottom:4px;font-weight:800}
.metric-val{font-size:14px;color:var(--ink);font-weight:800;letter-spacing:-0.2px;font-family:"Inter",sans-serif}
.metric-val.up{color:var(--green)}.metric-val.down{color:var(--coral)}
.metric-val.hot{color:var(--cyan)}.metric-val.warn{color:var(--amber)}

.dexe-block{padding:12px 14px;margin-bottom:12px;background:var(--panel-2);border-left:2px solid var(--pink)}
.dexe-title{font-size:9px;color:var(--pink);letter-spacing:1.6px;font-weight:800;margin-bottom:8px;text-transform:uppercase}
.dexe-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:5px 16px}
.dexe-cell{display:flex;justify-content:space-between;font-size:12px}
.dexe-k{color:var(--mute);text-transform:uppercase;font-size:9px;letter-spacing:1px;font-weight:700;align-self:center}
.dexe-v{color:var(--ink);font-weight:800;font-family:"Inter",sans-serif}
.dexe-v.up{color:var(--green)}.dexe-v.down{color:var(--coral)}
.dexe-v.rev-hot{color:var(--amber);animation:pulse 2s infinite}
.dexe-v.rev-none{color:var(--mute)}

.analysis-block{padding:13px 16px;margin-bottom:12px;background:var(--panel-2);border-left:2px solid var(--cyan);position:relative;overflow:hidden}
.analysis-block::before{content:"";position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--cyan),transparent);animation:scan 4s linear infinite;opacity:.5}
.analysis-title{font-size:9px;color:var(--cyan);letter-spacing:1.6px;font-weight:800;margin-bottom:6px;text-transform:uppercase}
.analysis-text{font-size:12.5px;line-height:1.65;color:var(--ink-dim);font-weight:500;font-family:"Inter",sans-serif}

.buzz-block{padding:11px 14px;margin-bottom:12px;background:var(--panel-2);border-left:2px solid var(--violet)}
.buzz-header{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.buzz-icon{font-size:14px;color:var(--violet);font-weight:900}
.buzz-title{font-size:9px;color:var(--mute);letter-spacing:1.5px;font-weight:800;flex:1;text-transform:uppercase}
.buzz-level{font-size:8px;letter-spacing:1.2px;font-weight:800;padding:3px 9px;text-transform:uppercase}
.buzz-level.buzz-hot{color:#0b0f18;background:var(--coral);animation:pulse 2s infinite}
.buzz-level.buzz-warm{color:var(--amber);background:rgba(251,191,36,0.14);border:1px solid rgba(251,191,36,0.4)}
.buzz-level.buzz-cool{color:var(--cyan);background:rgba(34,211,238,0.12);border:1px solid rgba(34,211,238,0.35)}
.buzz-level.buzz-cold{color:var(--mute);background:var(--panel-3);border:1px solid var(--line)}
.buzz-text{font-size:11.5px;color:var(--ink-dim);line-height:1.55;font-family:"Inter",sans-serif}

.squeeze-block{padding:11px 14px;margin-bottom:12px;background:var(--panel-2);border-left:2px solid var(--sq-color);position:relative}
.squeeze-block.sq-low{--sq-color:var(--cyan)}
.squeeze-block.sq-medium{--sq-color:var(--amber)}
.squeeze-block.sq-high{--sq-color:var(--coral)}
.squeeze-block.sq-extreme{--sq-color:var(--coral);background:rgba(248,113,113,0.06)}
.squeeze-header{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.squeeze-icon{font-size:13px;color:var(--sq-color);font-weight:900}
.squeeze-title{font-size:9px;color:var(--mute);letter-spacing:1.5px;font-weight:800;flex:1;text-transform:uppercase}
.squeeze-level{font-size:8px;letter-spacing:1.2px;font-weight:800;padding:3px 9px;text-transform:uppercase;color:var(--sq-color);background:color-mix(in srgb,var(--sq-color) 12%,transparent);border:1px solid color-mix(in srgb,var(--sq-color) 40%,transparent)}
.squeeze-level.sq-extreme{color:#0b0f18;background:var(--sq-color);animation:pulse 2s infinite}
.squeeze-reasons{list-style:none;margin:6px 0;padding:0}
.squeeze-reasons li{font-size:11px;color:var(--ink-dim);padding:3px 0 3px 14px;position:relative;line-height:1.4;font-family:"Inter",sans-serif}
.squeeze-reasons li::before{content:"▸";position:absolute;left:0;color:var(--sq-color);font-weight:900}
.squeeze-verdict{font-size:11.5px;color:var(--ink);line-height:1.5;margin-top:6px;padding-top:6px;border-top:1px solid var(--line);font-family:"Inter",sans-serif;font-weight:500}

.strategy-block{padding:11px 14px;margin-top:10px;background:var(--panel-3);border-left:2px solid var(--card-color);position:relative}
.strategy-title{font-size:9px;color:var(--card-color);letter-spacing:1.6px;font-weight:800;margin-bottom:5px;text-transform:uppercase}
.strategy-text{font-size:12px;color:var(--ink);line-height:1.55;font-family:"Inter",sans-serif;font-weight:500}

.section-title{font-size:12px;color:var(--mute);letter-spacing:3px;text-transform:uppercase;margin:26px 0 14px;font-weight:800;display:flex;align-items:center;gap:14px}
.section-title::before{content:"";width:20px;height:2px;background:var(--section-color,var(--cyan))}
.section-title::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--line),transparent)}
.section-strong{--section-color:var(--green)}.section-good{--section-color:var(--blue)}
.section-scout{--section-color:var(--amber)}.section-watch{--section-color:var(--mute)}
.section-count{color:var(--section-color,var(--cyan));font-family:"JetBrains Mono",monospace;font-weight:800}

a{color:var(--cyan);text-decoration:none}a:hover{color:var(--blue)}
"""

    def render_card(r: dict) -> str:
        bucket = r.get("bucket", "watch")
        symbol = esc(r.get("symbol", "—"))
        rank = esc(r.get("rank", ""))
        score = r.get("score", 0)
        tags = r.get("tags", []) or []
        phase = r.get("phase") or {}
        metrics = r.get("metrics", []) or []
        dexe = r.get("dexe") or {}
        analysis = r.get("analysis", "") or ""
        buzz = r.get("buzz") or {}
        strategy = r.get("strategy", "") or ""
        squeeze = r.get("squeeze")

        tags_html = "".join(
            f'<span class="tag {esc(t.get("class","tag-cat"))}">{esc(t.get("text",""))}</span>'
            for t in tags
        )

        links = r.get("links", []) or []
        links_html = ""
        if links:
            items = "".join(
                f'<a class="link-chip" href="{esc(l["url"])}" target="_blank" rel="noopener">{esc(l["text"])}</a>'
                for l in links
            )
            links_html = f'<div class="links-row">{items}</div>'

        phase_html = ""
        if phase:
            phase_html = f"""
            <div class="phase-indicator {esc(phase.get("class","phase-p3"))}">
              <div class="phase-icon">{esc(phase.get("icon","3"))}</div>
              <div class="phase-name">{esc(phase.get("name",""))}</div>
              <div class="phase-tf">{esc(phase.get("tf",""))}</div>
            </div>"""

        metrics_html = ""
        if metrics:
            cells = "".join(
                f'<div class="metric"><div class="metric-key">{esc(m.get("key",""))}</div>'
                f'<div class="metric-val {esc(m.get("cls",""))}">{esc(m.get("val",""))}</div></div>'
                for m in metrics
            )
            metrics_html = f'<div class="metrics">{cells}</div>'

        dexe_html = ""
        if dexe and dexe.get("cells"):
            cells = "".join(
                f'<div class="dexe-cell"><span class="dexe-k">{esc(c.get("k",""))}</span>'
                f'<span class="dexe-v {esc(c.get("cls",""))}">{esc(c.get("v",""))}</span></div>'
                for c in dexe["cells"]
            )
            dexe_html = f"""
            <div class="dexe-block">
              <div class="dexe-title">◈ DEX / Onchain</div>
              <div class="dexe-grid">{cells}</div>
            </div>"""

        analysis_html = ""
        if analysis:
            analysis_html = f"""
            <div class="analysis-block">
              <div class="analysis-title">◇ Fundamental Take</div>
              <div class="analysis-text">{esc(analysis)}</div>
            </div>"""

        buzz_html = ""
        if buzz:
            buzz_html = f"""
            <div class="buzz-block">
              <div class="buzz-header">
                <span class="buzz-icon">◉</span>
                <span class="buzz-title">Twitter Buzz</span>
                <span class="buzz-level {esc(buzz.get("level_class","buzz-cool"))}">{esc(buzz.get("level_text","COOL"))}</span>
              </div>
              <div class="buzz-text">{esc(buzz.get("text",""))}</div>
            </div>"""

        squeeze_html = ""
        if squeeze:
            lvl = squeeze.get("level", "low")
            lvl_cls = f"sq-{lvl}"
            reasons_html = "".join(f"<li>{esc(x)}</li>" for x in (squeeze.get("reasons") or [])[:4])
            squeeze_html = f"""
            <div class="squeeze-block {lvl_cls}">
              <div class="squeeze-header">
                <span class="squeeze-icon">⚠</span>
                <span class="squeeze-title">Squeeze Risk</span>
                <span class="squeeze-level {lvl_cls}">{esc(lvl.upper())} · {esc(squeeze.get("score",0))}/100</span>
              </div>
              <ul class="squeeze-reasons">{reasons_html}</ul>
              <div class="squeeze-verdict">{esc(squeeze.get("verdict",""))}</div>
            </div>"""

        strategy_html = ""
        if strategy:
            strategy_html = f"""
            <div class="strategy-block">
              <div class="strategy-title">▶ Strategy</div>
              <div class="strategy-text">{esc(strategy)}</div>
            </div>"""

        return f"""
        <div class="card card-{esc(bucket)}">
          <div class="card-top">
            <div>
              <div class="rank-symbol">
                <span class="rank">{rank}</span>
                <span class="symbol">{symbol}</span>
              </div>
              <div class="tag-row">{tags_html}</div>
            </div>
            <div class="score-badge">
              <div class="score-badge-label">Score</div>
              <div class="score-badge-value">{esc(score)}</div>
            </div>
          </div>
          {links_html}
          {phase_html}
          {metrics_html}
          {dexe_html}
          {analysis_html}
          {buzz_html}
          {squeeze_html}
          {strategy_html}
        </div>"""

    def render_section(title: str, cls: str, items: list[dict]) -> str:
        if not items:
            return ""
        cards = "\n".join(render_card(r) for r in items)
        return f"""
        <div class="section-title section-{cls}">
          {title} <span class="section-count">[{len(items):02d}]</span>
        </div>
        <div class="grid">{cards}</div>"""

    taiko_html  = render_section("◉ TAIKO REVERSAL SETUPS", "taiko",  taiko)
    dexe_html   = render_section("◉ DEXE POST-PUMP SETUPS", "dexe",   dexe)
    strong_html = render_section("STRONG SIGNALS",          "strong", strong)
    good_html   = render_section("GOOD SETUPS",             "good",   good)
    scout_html  = render_section("SCOUT / EARLY",           "scout",  scout)
    watch_html  = render_section("WATCHLIST",               "watch",  watch)

    legend_html = """
      <div class="phase-legend">
        <div class="phase-legend-title">Vortex Phases</div>
        <div class="phase-legend-grid">
          <div class="pl-item pl-1">
            <div class="pl-num">1</div>
            <div class="pl-body">
              <div class="pl-name">Accumulation</div>
              <div class="pl-desc">Плоское дно, умные деньги собирают. Скаутить, ждать подтверждения.</div>
            </div>
          </div>
          <div class="pl-item pl-2">
            <div class="pl-num">2</div>
            <div class="pl-body">
              <div class="pl-name">Reversal</div>
              <div class="pl-desc">Разворот от низов, OBV вверх. Ранний вход, часто = TAIKO-сетап.</div>
            </div>
          </div>
          <div class="pl-item pl-3">
            <div class="pl-num">3</div>
            <div class="pl-body">
              <div class="pl-name">Breakout ★</div>
              <div class="pl-desc">Пробой уровня на объёме. Основная зона входа.</div>
            </div>
          </div>
          <div class="pl-item pl-4">
            <div class="pl-num">4</div>
            <div class="pl-body">
              <div class="pl-name">Trend</div>
              <div class="pl-desc">Устойчивое движение. Держать, добирать на откатах.</div>
            </div>
          </div>
          <div class="pl-item pl-5">
            <div class="pl-num">5</div>
            <div class="pl-body">
              <div class="pl-name">Euphoria ⚠</div>
              <div class="pl-desc">Параболический топ, RSI 85+. Не входить, фиксировать.</div>
            </div>
          </div>
        </div>
        <div class="phase-legend-tags">
          <span class="pl-tag pl-tag-taiko">◉ TAIKO REVERSAL</span>
          <span class="pl-tag-desc">— капитуляция + разворот на HTF, глубокая перепроданность</span>
          <span class="pl-tag pl-tag-dexe">◉ DEXE POST-PUMP</span>
          <span class="pl-tag-desc">— консолидация после сдувшегося пампа, ранний ре-энтри</span>
        </div>
      </div>"""

    html_str = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Sleeping Alts Screener — HEX v3</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@500;600;700;800&family=JetBrains+Mono:wght@500;700;800&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>
<div class="container">
  <div class="header hex">
    <div class="brand">
      <div class="brand-icon hex-sm">◈</div>
      <div>
        <div class="brand-title">Sleeping Alts Screener</div>
        <div class="subtitle">HEX GRID · Multi-Layer Signal Engine</div>
      </div>
    </div>
    <div class="header-right">
      <div class="status-badge">
        <span class="status-dot"></span> LIVE · {total} pairs
      </div>
      <div class="timestamp">Updated <span>{esc(ts)}</span></div>
    </div>
  </div>

  <div class="stats">
    <div class="stat stat-taiko">
      <div class="stat-label">◉ TAIKO</div>
      <div class="stat-value accent">{len(taiko)}</div>
      <div class="stat-sub">HTF reversal</div>
    </div>
    <div class="stat stat-dexe">
      <div class="stat-label">◉ DEXE</div>
      <div class="stat-value accent">{len(dexe)}</div>
      <div class="stat-sub">post-pump</div>
    </div>
    <div class="stat stat-strong">
      <div class="stat-label">Strong</div>
      <div class="stat-value accent">{len(strong)}</div>
      <div class="stat-sub">high-confluence</div>
    </div>
    <div class="stat stat-good">
      <div class="stat-label">Good</div>
      <div class="stat-value accent">{len(good)}</div>
      <div class="stat-sub">tradable setups</div>
    </div>
    <div class="stat stat-scout">
      <div class="stat-label">Scout</div>
      <div class="stat-value accent">{len(scout)}</div>
      <div class="stat-sub">early stage</div>
    </div>
    <div class="stat stat-watch">
      <div class="stat-label">Watch</div>
      <div class="stat-value accent">{len(watch)}</div>
      <div class="stat-sub">monitor only</div>
    </div>
  </div>

  <div class="filter-bar">
    <span class="filter-label">Legend</span>
    <span class="pill"><span class="pill-dot" style="background:var(--green)"></span>Strong</span>
    <span class="pill"><span class="pill-dot" style="background:var(--blue)"></span>Good</span>
    <span class="pill"><span class="pill-dot" style="background:var(--amber)"></span>Scout</span>
    <span class="pill"><span class="pill-dot" style="background:var(--mute)"></span>Watch</span>
  </div>

  {legend_html}

  {taiko_html}
  {dexe_html}
  {strong_html}
  {good_html}
  {scout_html}
  {watch_html}
</div>
</body>
</html>"""

    if out_path is not None:
        try:
            Path(out_path).write_text(html_str, encoding="utf-8")
        except Exception as e:
            log.error(f"build_html: не удалось записать {out_path}: {e}")

    return html_str


# ============================================================
# PIPELINE
# ============================================================

def run_pipeline() -> dict:
    log.info("Загружаем список USDT-перпов Binance Futures...")
    symbols = fetch_futures_symbols()
    log.info(f"Найдено {len(symbols)} пар")

    log.info("Загружаем 24h stats...")
    tick24 = fetch_24h_stats()

    # Первичный скрин через 24h stats
    prelim = [s for s in symbols if s in tick24]
    log.info(f"К анализу: {len(prelim)} пар")

    results: list[dict] = []
    total = len(prelim)
    processed = 0

    def worker(sym: str):
        try:
            return analyze_symbol(sym, tick24[sym])
        except Exception as e:
            log.debug(f"analyze {sym} failed: {e}")
            return None

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(worker, s): s for s in prelim}
        for fut in as_completed(futures):
            processed += 1
            if processed % 25 == 0:
                log.info(f"Прогресс: {processed}/{total}")
            res = fut.result()
            if res:
                results.append(res)

    log.info(f"Первичная оценка {len(results)} монет...")

    # Скоринг + отсечка
    candidates: list[Candidate] = []
    scored = []
    for m in results:
        sc = score_candidate(m)
        if sc >= MIN_SCORE_TO_INCLUDE or m["price_change_30d"] < -40:
            scored.append((sc, m))
    scored.sort(key=lambda x: -x[0])

    log.info(f"Итого кандидатов: {len(scored)}")

    for idx, (_, m) in enumerate(scored, start=1):
        try:
            cand = build_candidate(m, idx)
            candidates.append(cand)
        except Exception as e:
            log.warning(f"build_candidate {m['symbol']} failed: {e}")

    # Сортировка внутри бакетов по score
    candidates.sort(key=lambda c: (
        {"strong": 0, "good": 1, "scout": 2, "watch": 3}[c.bucket],
        -c.score,
    ))

    log.info(f"Рендерим HTML → {REPORT_HTML}")
    build_html(candidates, REPORT_HTML)

    return {"html": REPORT_HTML, "count": len(candidates)}


# ============================================================
# ENTRYPOINT
# ============================================================

def main():
    t0 = time.time()
    try:
        out = run_pipeline()
        dt = time.time() - t0
        log.info(f"✔ Готово за {dt:.1f}s. Отчёт: {out['html']} ({out['count']} монет)")
    except KeyboardInterrupt:
        log.warning("Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        log.exception(f"Ошибка: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
