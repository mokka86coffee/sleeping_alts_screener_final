"""
Sleeping Alts Screener v3 — для Python 3.10+
Автоматический сканер спящих криптоактивов по методологии.
Сохраняет отчёты в HTML, CSV, JSON, Markdown, TXT + отправка на email.
"""
from __future__ import annotations

import csv
import json
import logging
import smtplib
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
import schedule

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

CONFIG: dict[str, Any] = {
    # Email настройки
    "email_enabled": False,                         # True/False — включить рассылку
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "email_from": "your_email@gmail.com",           # ЗАПОЛНИ
    "email_password": "your_app_password",          # ЗАПОЛНИ (Google App Password)
    "email_to": "your_email@gmail.com",             # ЗАПОЛНИ
    "email_attach_files": True,

    # Расписание
    "schedule_time": "09:00",
    "run_on_start": True,                           # True = запустить сразу для теста

    # Пути и хранение
    "output_dir": "./reports",
    "keep_history_days": 90,

    # Форматы вывода
    "output_formats": {
        "html": True,
        "csv": True,
        "json": True,
        "markdown": True,
        "txt": True,
    },

    # Фильтры методологии
    "min_drop_from_ath_pct": 70,
    "max_drop_from_ath_pct": 99.9,
    "min_base_days": 21,
    "min_daily_volume_usd": 5_000_000,
    "min_open_interest_usd": 1_000_000,
    "funding_negative_threshold": -0.001,
    "top_results": 15,
    "include_watch_category": True,
    "min_score_threshold": 25,

    # Технические
    "request_delay": 0.15,
    "request_timeout": 15,
    "max_retries": 2,
    "log_file": "screener.log",
    "history_file": "screener_history.json",

    # Исключаемые монеты (крупные капы)
    "exclude_symbols": {
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
        "USDCUSDT", "DOGEUSDT", "ADAUSDT", "TRXUSDT", "LINKUSDT",
        "AVAXUSDT", "DOTUSDT", "MATICUSDT", "LTCUSDT", "BCHUSDT",
    },
}

# ============================================================
# ЛОГГЕР
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(CONFIG["log_file"], encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class SymbolMetrics:
    """Метрики по одному символу."""
    symbol: str
    price: float
    daily_volume_usd: float
    avg_volume_30d_usd: float
    drop_from_ath_pct: float
    days_since_ath: int
    days_in_base: int
    rvol_pct: float
    obv_divergence: float
    bb_width_pct: float
    bb_squeeze_score: float
    price_range_position: float
    funding_rate: float
    open_interest_usd: float
    oi_at_low: bool


@dataclass
class ScoreData:
    """Результат оценки сетапа."""
    score: int
    category: str
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class Candidate:
    """Полный кандидат: метрики + оценка."""
    metrics: SymbolMetrics
    score_data: ScoreData


# ============================================================
# HTTP ВСПОМОГАТЕЛЬНЫЕ
# ============================================================

def http_get(url: str, params: dict[str, Any] | None = None) -> Any:
    """GET с ретраями и таймаутом."""
    last_err: Exception | None = None
    for attempt in range(CONFIG["max_retries"] + 1):
        try:
            resp = requests.get(url, params=params, timeout=CONFIG["request_timeout"])
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_err = e
            if attempt < CONFIG["max_retries"]:
                time.sleep(0.5 * (attempt + 1))
    if last_err:
        raise last_err
    return None


# ============================================================
# API BINANCE (публичное, без ключей)
# ============================================================

class BinanceAPI:
    BASE = "https://fapi.binance.com"

    @staticmethod
    def get_all_perp_symbols() -> list[str]:
        try:
            data = http_get(f"{BinanceAPI.BASE}/fapi/v1/exchangeInfo")
            symbols = [
                s["symbol"] for s in data.get("symbols", [])
                if s.get("contractType") == "PERPETUAL"
                and s.get("quoteAsset") == "USDT"
                and s.get("status") == "TRADING"
            ]
            log.info(f"Binance: найдено {len(symbols)} perpetual символов")
            return symbols
        except Exception as e:
            log.error(f"Ошибка загрузки списка Binance: {e}")
            return []

    @staticmethod
    def get_klines(symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame | None:
        try:
            data = http_get(
                f"{BinanceAPI.BASE}/fapi/v1/klines",
                params={"symbol": symbol, "interval": interval, "limit": limit},
            )
            if not isinstance(data, list) or len(data) == 0:
                return None
            df = pd.DataFrame(data, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "trades", "taker_buy_base",
                "taker_buy_quote", "ignore",
            ])
            for col in ("open", "high", "low", "close", "volume", "quote_volume"):
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
            df = df.dropna(subset=["close", "volume"]).reset_index(drop=True)
            return df if len(df) > 0 else None
        except Exception as e:
            log.debug(f"klines {symbol}: {e}")
            return None

    @staticmethod
    def get_funding_rate(symbol: str) -> float | None:
        try:
            data = http_get(
                f"{BinanceAPI.BASE}/fapi/v1/premiumIndex",
                params={"symbol": symbol},
            )
            return float(data.get("lastFundingRate", 0))
        except Exception:
            return None

    @staticmethod
    def get_open_interest_usd(symbol: str) -> float | None:
        try:
            data_oi = http_get(
                f"{BinanceAPI.BASE}/fapi/v1/openInterest",
                params={"symbol": symbol},
            )
            oi_coins = float(data_oi.get("openInterest", 0))
            data_price = http_get(
                f"{BinanceAPI.BASE}/fapi/v1/ticker/price",
                params={"symbol": symbol},
            )
            price = float(data_price.get("price", 0))
            return oi_coins * price
        except Exception:
            return None

    @staticmethod
    def get_oi_history(symbol: str, period: str = "1d", limit: int = 30) -> pd.DataFrame | None:
        try:
            data = http_get(
                f"{BinanceAPI.BASE}/futures/data/openInterestHist",
                params={"symbol": symbol, "period": period, "limit": limit},
            )
            if not isinstance(data, list) or len(data) == 0:
                return None
            df = pd.DataFrame(data)
            df["sumOpenInterest"] = pd.to_numeric(df["sumOpenInterest"], errors="coerce")
            df["sumOpenInterestValue"] = pd.to_numeric(df["sumOpenInterestValue"], errors="coerce")
            df = df.dropna().reset_index(drop=True)
            return df if len(df) > 0 else None
        except Exception:
            return None


# ============================================================
# ИНДИКАТОРЫ / АНАЛИЗ
# ============================================================

def calc_obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff().fillna(0))
    return (direction * df["volume"]).cumsum()


def calc_drop_from_ath(df: pd.DataFrame) -> float:
    ath = df["high"].max()
    current = df["close"].iloc[-1]
    if ath <= 0:
        return 0.0
    return (current - ath) / ath * 100


def calc_days_since_ath(df: pd.DataFrame) -> int:
    ath_idx = int(df["high"].idxmax())
    return len(df) - ath_idx - 1


def calc_days_in_base(df: pd.DataFrame, threshold_pct: float = 15.0) -> int:
    lows = df["low"].values
    if len(lows) < 2:
        return 0
    recent_low = lows[-1]
    days = 0
    for i in range(len(lows) - 2, -1, -1):
        if lows[i] < recent_low * (1 - threshold_pct / 100):
            break
        if lows[i] < recent_low:
            recent_low = lows[i]
        days += 1
    return days


def calc_relative_volume(df: pd.DataFrame, lookback: int = 10) -> float:
    if len(df) < lookback + 1:
        return 100.0
    recent = df["quote_volume"].iloc[-1]
    avg = df["quote_volume"].iloc[-lookback - 1:-1].mean()
    if avg == 0 or pd.isna(avg):
        return 0.0
    return recent / avg * 100


def calc_obv_divergence(df: pd.DataFrame, lookback: int = 60) -> float:
    if len(df) < lookback:
        return 0.0
    obv = calc_obv(df)
    obv_start = obv.iloc[-lookback]
    obv_end = obv.iloc[-1]
    price_start = df["close"].iloc[-lookback]
    price_end = df["close"].iloc[-1]
    if obv_start == 0 or price_start == 0:
        return 0.0
    obv_change = (obv_end - obv_start) / abs(obv_start) * 100
    price_change = (price_end - price_start) / price_start * 100
    return float(obv_change - price_change)


def calc_bollinger_width(df: pd.DataFrame, period: int = 20) -> float:
    if len(df) < period:
        return 100.0
    close = df["close"].iloc[-period:]
    ma = close.mean()
    std = close.std()
    if ma == 0 or pd.isna(ma) or pd.isna(std):
        return 100.0
    return (4 * std) / ma * 100


def calc_bollinger_squeeze_percentile(df: pd.DataFrame, period: int = 20) -> float:
    """Возвращает percentile: какой % истории имел более широкие полосы, чем сейчас.
    Высокое значение (>85) = экстремальный squeeze."""
    if len(df) < period + 30:
        return 0.0
    current = calc_bollinger_width(df, period)
    history: list[float] = []
    for i in range(period, len(df), 5):
        sub = df.iloc[:i + 1]
        history.append(calc_bollinger_width(sub, period))
    if not history:
        return 0.0
    return sum(1 for x in history if x > current) / len(history) * 100


def calc_price_range_position(df: pd.DataFrame, lookback: int = 60) -> float:
    if len(df) < lookback:
        return 50.0
    highs = df["high"].iloc[-lookback:].max()
    lows = df["low"].iloc[-lookback:].min()
    current = df["close"].iloc[-1]
    if highs == lows:
        return 50.0
    return (current - lows) / (highs - lows) * 100


def analyze_symbol(symbol: str) -> SymbolMetrics | None:
    df = BinanceAPI.get_klines(symbol, "1d", 500)
    time.sleep(CONFIG["request_delay"])
    if df is None or len(df) < 60:
        return None

    funding = BinanceAPI.get_funding_rate(symbol)
    time.sleep(CONFIG["request_delay"])

    oi = BinanceAPI.get_open_interest_usd(symbol)
    time.sleep(CONFIG["request_delay"])

    oi_hist = BinanceAPI.get_oi_history(symbol)
    time.sleep(CONFIG["request_delay"])

    oi_at_low = False
    if oi_hist is not None and len(oi_hist) >= 10:
        current_oi = float(oi_hist["sumOpenInterestValue"].iloc[-1])
        min_oi = float(oi_hist["sumOpenInterestValue"].min())
        if min_oi > 0:
            oi_at_low = current_oi <= min_oi * 1.15

    return SymbolMetrics(
        symbol=symbol,
        price=float(df["close"].iloc[-1]),
        daily_volume_usd=float(df["quote_volume"].iloc[-1]),
        avg_volume_30d_usd=float(df["quote_volume"].iloc[-30:].mean()),
        drop_from_ath_pct=calc_drop_from_ath(df),
        days_since_ath=calc_days_since_ath(df),
        days_in_base=calc_days_in_base(df),
        rvol_pct=calc_relative_volume(df),
        obv_divergence=calc_obv_divergence(df),
        bb_width_pct=calc_bollinger_width(df),
        bb_squeeze_score=calc_bollinger_squeeze_percentile(df),
        price_range_position=calc_price_range_position(df),
        funding_rate=funding if funding is not None else 0.0,
        open_interest_usd=oi if oi is not None else 0.0,
        oi_at_low=oi_at_low,
    )


# ============================================================
# SCORING
# ============================================================

def score_setup(m: SymbolMetrics) -> ScoreData:
    score = 0
    reasons: list[str] = []
    warnings_list: list[str] = []

    # 1. Падение с ATH
    drop = abs(m.drop_from_ath_pct)
    if CONFIG["min_drop_from_ath_pct"] <= drop <= CONFIG["max_drop_from_ath_pct"]:
        score += 15
        reasons.append(f"Падение {drop:.0f}% от ATH")
    elif drop < CONFIG["min_drop_from_ath_pct"]:
        return ScoreData(score=0, category="SKIP", warnings=["Малое падение с ATH"])
    else:
        warnings_list.append(f"Экстремальное падение {drop:.0f}%")

    # 2. База
    if m.days_in_base >= CONFIG["min_base_days"]:
        score += 10
        reasons.append(f"База {m.days_in_base} дней")
    else:
        warnings_list.append(f"Короткая база ({m.days_in_base} дн.)")

    # 3. Ликвидность
    if m.avg_volume_30d_usd < CONFIG["min_daily_volume_usd"]:
        return ScoreData(score=0, category="SKIP", warnings=["Низкая ликвидность"])

    # 4. OBV дивергенция
    if m.obv_divergence > 20:
        score += 20
        reasons.append(f"Сильная бычья OBV-дивергенция (+{m.obv_divergence:.0f}%)")
    elif m.obv_divergence > 5:
        score += 10
        reasons.append(f"Умеренная OBV-дивергенция (+{m.obv_divergence:.0f}%)")
    elif m.obv_divergence < -15:
        warnings_list.append(f"Медвежья OBV-дивергенция ({m.obv_divergence:.0f}%)")

    # 5. Bollinger squeeze
    if m.bb_squeeze_score > 85:
        score += 15
        reasons.append(f"Экстремальный Bollinger squeeze ({m.bb_squeeze_score:.0f}%ile)")
    elif m.bb_squeeze_score > 70:
        score += 8
        reasons.append("Сильный Bollinger squeeze")

    # 6. Положение в диапазоне
    if m.price_range_position < 20:
        score += 10
        reasons.append("Цена на дне 60-дневного диапазона")
    elif m.price_range_position > 70:
        warnings_list.append("Цена в верхней части диапазона")

    # 7. Funding
    if m.funding_rate < CONFIG["funding_negative_threshold"]:
        score += 10
        reasons.append(f"Отрицательный funding ({m.funding_rate * 100:.3f}%)")

    # 8. OI на минимуме
    if m.oi_at_low:
        score += 10
        reasons.append("OI на историческом минимуме")

    # 9. RVOL
    if m.rvol_pct > 500:
        score += 10
        reasons.append(f"Экстремальный RVOL {m.rvol_pct:.0f}%")
    elif m.rvol_pct > 200:
        score += 5
        reasons.append(f"Повышенный RVOL {m.rvol_pct:.0f}%")

    # Категория
    match score:
        case s if s >= 60:
            category = "STRONG"
        case s if s >= 40:
            category = "GOOD"
        case s if s >= 25:
            category = "WATCH"
        case _:
            category = "SKIP"

    return ScoreData(score=score, category=category, reasons=reasons, warnings=warnings_list)


# ============================================================
# ФОРМАТИРОВЩИКИ
# ============================================================

def _emoji(cat: str) -> str:
    return {"STRONG": "🔥", "GOOD": "✅", "WATCH": "🟡"}.get(cat, "")


def format_html(candidates: list[Candidate], scan_time: str) -> str:
    parts: list[str] = []
    parts.append(
        '<!DOCTYPE html>\n<html><head><meta charset="utf-8">'
        '<title>Sleeping Alts Screener</title>\n<style>\n'
        'body { font-family: -apple-system, Segoe UI, sans-serif; color: #222; '
        'max-width: 1000px; margin: 20px auto; padding: 20px; background: #f5f5f7; }\n'
        'h2 { color: #1a1a1a; }\n'
        '.card { border-left: 4px solid; padding: 16px 20px; margin: 16px 0; '
        'background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }\n'
        '.strong { border-color: #16a34a; } .good { border-color: #ca8a04; } '
        '.watch { border-color: #6b7280; }\n'
        '.metric-row { margin: 6px 0; font-size: 14px; }\n'
        '.metric-row b { color: #1a1a1a; }\n'
        'ul { margin: 6px 0; padding-left: 24px; }\n'
        '.warning { color: #b45309; }\n'
        '.footer { color: #6b7280; font-size: 12px; margin-top: 32px; '
        'padding-top: 16px; border-top: 1px solid #e5e5e5; }\n'
        'a { color: #2563eb; text-decoration: none; } a:hover { text-decoration: underline; }\n'
        '</style></head><body>\n'
    )
    parts.append(f"<h2>🎯 Sleeping Alts Screener</h2>\n")
    parts.append(
        f"<p><b>Дата сканирования:</b> {scan_time}<br>"
        f"<b>Кандидатов найдено:</b> {len(candidates)}</p>\n"
    )

    for i, c in enumerate(candidates, 1):
        m = c.metrics
        s = c.score_data
        css = s.category.lower()
        emoji = _emoji(s.category)
        tv_link = f"https://www.tradingview.com/chart/?symbol=BINANCE:{m.symbol}.P"

        parts.append(f'<div class="card {css}">\n')
        parts.append(f"<h3>#{i}. {m.symbol} — {emoji} {s.category} (score: {s.score})</h3>\n")
        parts.append(
            f'<div class="metric-row"><b>Цена:</b> ${m.price:.6f} | '
            f"<b>Падение с ATH:</b> {m.drop_from_ath_pct:.1f}% | "
            f"<b>База:</b> {m.days_in_base} дн.</div>\n"
        )
        parts.append(
            f'<div class="metric-row"><b>Дневной объём:</b> ${m.daily_volume_usd:,.0f} | '
            f"<b>OI:</b> ${m.open_interest_usd:,.0f} | "
            f"<b>Funding:</b> {m.funding_rate * 100:.4f}%</div>\n"
        )
        parts.append(
            f'<div class="metric-row"><b>OBV-дивергенция:</b> {m.obv_divergence:+.1f}% | '
            f"<b>BB-squeeze:</b> {m.bb_squeeze_score:.0f}%ile | "
            f"<b>RVOL:</b> {m.rvol_pct:.0f}%</div>\n"
        )
        parts.append(
            f'<div class="metric-row">'
            f'<a href="{tv_link}" target="_blank">📊 Открыть на TradingView</a></div>\n'
        )
        if s.reasons:
            parts.append("<div><b>✅ Причины:</b><ul>")
            parts.extend(f"<li>{r}</li>" for r in s.reasons)
            parts.append("</ul></div>\n")
        if s.warnings:
            parts.append('<div class="warning"><b>⚠️ Предупреждения:</b><ul>')
            parts.extend(f"<li>{w}</li>" for w in s.warnings)
            parts.append("</ul></div>\n")
        parts.append("</div>\n")

    parts.append(
        '<div class="footer">Автоматический сканер по методологии торговли '
        "спящими микрокапами.<br>Каждого кандидата рекомендуется дополнительно "
        "проверить: пузыри Market Order, социалы, историю пампов.</div>\n"
        "</body></html>"
    )
    return "".join(parts)


def format_csv(candidates: list[Candidate], filepath: Path) -> None:
    rows: list[dict[str, Any]] = []
    for i, c in enumerate(candidates, 1):
        m = c.metrics
        s = c.score_data
        rows.append({
            "Rank": i,
            "Symbol": m.symbol,
            "Category": s.category,
            "Score": s.score,
            "Price": round(m.price, 8),
            "Drop_from_ATH_%": round(m.drop_from_ath_pct, 2),
            "Days_in_base": m.days_in_base,
            "Days_since_ATH": m.days_since_ath,
            "Daily_Volume_USD": round(m.daily_volume_usd, 0),
            "Avg_Volume_30d_USD": round(m.avg_volume_30d_usd, 0),
            "Open_Interest_USD": round(m.open_interest_usd, 0),
            "OI_at_low": m.oi_at_low,
            "Funding_Rate_%": round(m.funding_rate * 100, 4),
            "OBV_Divergence_%": round(m.obv_divergence, 2),
            "BB_Squeeze_Percentile": round(m.bb_squeeze_score, 1),
            "BB_Width_%": round(m.bb_width_pct, 2),
            "Price_Range_Position_%": round(m.price_range_position, 1),
            "RVOL_%": round(m.rvol_pct, 1),
            "Reasons": " | ".join(s.reasons),
            "Warnings": " | ".join(s.warnings),
        })
    if not rows:
        return
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def format_json(candidates: list[Candidate], scan_time: str, filepath: Path) -> None:
    output = {
        "scan_time": scan_time,
        "total_candidates": len(candidates),
        "candidates": [
            {"rank": i, **asdict(c.metrics), **asdict(c.score_data)}
            for i, c in enumerate(candidates, 1)
        ],
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)


def format_markdown(candidates: list[Candidate], scan_time: str) -> str:
    lines: list[str] = []
    lines.append("# 🎯 Sleeping Alts Screener\n")
    lines.append(f"**Дата:** {scan_time}  \n**Кандидатов:** {len(candidates)}\n")
    lines.append("---\n")
    lines.append("## Сводная таблица\n")
    lines.append("| # | Symbol | Cat | Score | Price | Drop | Base | OBV Div | BB Sq | Fund |")
    lines.append("|---|--------|-----|-------|-------|------|------|---------|-------|------|")

    for i, c in enumerate(candidates, 1):
        m = c.metrics
        s = c.score_data
        emoji = _emoji(s.category)
        lines.append(
            f"| {i} | **{m.symbol}** | {emoji}{s.category} | {s.score} | "
            f"${m.price:.6f} | {m.drop_from_ath_pct:.0f}% | {m.days_in_base}д | "
            f"{m.obv_divergence:+.0f}% | {m.bb_squeeze_score:.0f}% | "
            f"{m.funding_rate * 100:.3f}% |"
        )

    lines.append("\n---\n\n## Детальный анализ\n")

    for i, c in enumerate(candidates, 1):
        m = c.metrics
        s = c.score_data
        emoji = _emoji(s.category)
        tv_link = f"https://www.tradingview.com/chart/?symbol=BINANCE:{m.symbol}.P"

        lines.append(f"### {i}. {m.symbol} — {emoji} {s.category} (score: {s.score})\n")
        lines.append(f"- **Цена:** ${m.price:.6f}")
        lines.append(f"- **Падение с ATH:** {m.drop_from_ath_pct:.1f}% ({m.days_since_ath} дней назад)")
        lines.append(f"- **База:** {m.days_in_base} дней")
        lines.append(f"- **Дневной объём:** ${m.daily_volume_usd:,.0f}")
        oi_note = " *(на минимуме)*" if m.oi_at_low else ""
        lines.append(f"- **Open Interest:** ${m.open_interest_usd:,.0f}{oi_note}")
        lines.append(f"- **Funding rate:** {m.funding_rate * 100:.4f}%")
        lines.append(f"- **OBV-дивергенция:** {m.obv_divergence:+.1f}%")
        lines.append(f"- **Bollinger squeeze:** {m.bb_squeeze_score:.0f}%ile")
        lines.append(f"- **RVOL:** {m.rvol_pct:.0f}%")
        lines.append(f"- 📊 [Открыть на TradingView]({tv_link})\n")

        if s.reasons:
            lines.append("**✅ Сильные стороны:**")
            for r in s.reasons:
                lines.append(f"- {r}")
            lines.append("")
        if s.warnings:
            lines.append("**⚠️ Предупреждения:**")
            for w in s.warnings:
                lines.append(f"- {w}")
            lines.append("")
        lines.append("---\n")

    return "\n".join(lines)


def format_txt(candidates: list[Candidate], scan_time: str) -> str:
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append(f"  SLEEPING ALTS SCREENER — {scan_time}")
    lines.append(f"  Кандидатов: {len(candidates)}")
    lines.append("=" * 70)
    lines.append("")

    for i, c in enumerate(candidates, 1):
        m = c.metrics
        s = c.score_data
        emoji = _emoji(s.category)
        lines.append(f"[{i:2d}] {m.symbol:15s}  {emoji} {s.category:6s}  score: {s.score}")
        lines.append(
            f"     Price: ${m.price:.6f}  |  Drop: {m.drop_from_ath_pct:.1f}%  "
            f"|  Base: {m.days_in_base}d"
        )
        lines.append(
            f"     Vol: ${m.daily_volume_usd:>12,.0f}  |  OI: ${m.open_interest_usd:>12,.0f}  "
            f"|  Fund: {m.funding_rate * 100:+.4f}%"
        )
        lines.append(
            f"     OBV div: {m.obv_divergence:+.1f}%  |  BB sq: {m.bb_squeeze_score:.0f}%ile  "
            f"|  RVOL: {m.rvol_pct:.0f}%"
        )
        if s.reasons:
            lines.append(f"     [+] {' | '.join(s.reasons)}")
        if s.warnings:
            lines.append(f"     [!] {' | '.join(s.warnings)}")
        lines.append("")

    return "\n".join(lines)


# ============================================================
# СОХРАНЕНИЕ ОТЧЁТОВ
# ============================================================

def save_reports(candidates: list[Candidate], scan_time: str) -> dict[str, Path]:
    output_dir = Path(CONFIG["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    date_folder = output_dir / datetime.now().strftime("%Y-%m-%d")
    date_folder.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%H%M%S")
    base_name = f"scan_{timestamp}"

    files_created: dict[str, Path] = {}
    formats = CONFIG["output_formats"]

    try:
        if formats.get("html"):
            path = date_folder / f"{base_name}.html"
            path.write_text(format_html(candidates, scan_time), encoding="utf-8")
            files_created["html"] = path

        if formats.get("csv"):
            path = date_folder / f"{base_name}.csv"
            format_csv(candidates, path)
            files_created["csv"] = path

        if formats.get("json"):
            path = date_folder / f"{base_name}.json"
            format_json(candidates, scan_time, path)
            files_created["json"] = path

        if formats.get("markdown"):
            path = date_folder / f"{base_name}.md"
            path.write_text(format_markdown(candidates, scan_time), encoding="utf-8")
            files_created["markdown"] = path

        if formats.get("txt"):
            path = date_folder / f"{base_name}.txt"
            path.write_text(format_txt(candidates, scan_time), encoding="utf-8")
            files_created["txt"] = path

        # Latest.* — быстрый доступ
        for fmt, path in files_created.items():
            ext = "md" if fmt == "markdown" else fmt
            latest_path = output_dir / f"latest.{ext}"
            latest_path.write_bytes(path.read_bytes())

        for fmt, path in files_created.items():
            log.info(f"{fmt.upper()} сохранён: {path}")

    except Exception as e:
        log.error(f"Ошибка сохранения отчётов: {e}")

    return files_created


def cleanup_old_reports() -> None:
    try:
        output_dir = Path(CONFIG["output_dir"])
        if not output_dir.exists():
            return

        cutoff = datetime.now() - timedelta(days=CONFIG["keep_history_days"])
        for folder in output_dir.iterdir():
            if not folder.is_dir():
                continue
            try:
                folder_date = datetime.strptime(folder.name, "%Y-%m-%d")
            except ValueError:
                continue
            if folder_date < cutoff:
                for f in folder.iterdir():
                    f.unlink(missing_ok=True)
                folder.rmdir()
                log.info(f"Удалена старая папка: {folder.name}")
    except Exception as e:
        log.error(f"Ошибка очистки: {e}")


# ============================================================
# EMAIL
# ============================================================

def send_email(subject: str, html_body: str, attachments: list[Path] | None = None) -> bool:
    if not CONFIG["email_enabled"]:
        return False

    try:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = CONFIG["email_from"]
        msg["To"] = CONFIG["email_to"]

        msg_alt = MIMEMultipart("alternative")
        msg_alt.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(msg_alt)

        if attachments and CONFIG["email_attach_files"]:
            for filepath in attachments:
                if not filepath.exists():
                    continue
                part = MIMEBase("application", "octet-stream")
                part.set_payload(filepath.read_bytes())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{filepath.name}"',
                )
                msg.attach(part)

        with smtplib.SMTP(CONFIG["smtp_server"], CONFIG["smtp_port"]) as server:
            server.starttls()
            server.login(CONFIG["email_from"], CONFIG["email_password"])
            server.send_message(msg)

        log.info(f"Email отправлен на {CONFIG['email_to']}")
        return True
    except Exception as e:
        log.error(f"Ошибка email: {e}")
        return False


# ============================================================
# ИСТОРИЯ
# ============================================================

def save_history(candidates: list[Candidate]) -> None:
    try:
        output_dir = Path(CONFIG["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        history_path = output_dir / CONFIG["history_file"]

        history: list[dict[str, Any]] = []
        if history_path.exists():
            try:
                history = json.loads(history_path.read_text(encoding="utf-8"))
            except Exception:
                history = []

        entry = {
            "date": datetime.now().isoformat(),
            "candidates": [
                {
                    "symbol": c.metrics.symbol,
                    "score": c.score_data.score,
                    "category": c.score_data.category,
                    "price": c.metrics.price,
                }
                for c in candidates
            ],
        }
        history.append(entry)
        history = history[-CONFIG["keep_history_days"]:]
        history_path.write_text(
            json.dumps(history, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        log.error(f"Ошибка сохранения истории: {e}")


# ============================================================
# ГЛАВНЫЙ ЦИКЛ
# ============================================================

def run_scan() -> None:
    log.info("=" * 60)
    log.info("Начало сканирования")
    log.info("=" * 60)

    scan_start = datetime.now()
    scan_time = scan_start.strftime("%Y-%m-%d %H:%M:%S")

    symbols = BinanceAPI.get_all_perp_symbols()
    if not symbols:
        log.error("Не удалось получить список символов")
        return

    exclude = CONFIG["exclude_symbols"]
    symbols = [s for s in symbols if s not in exclude]

    candidates: list[Candidate] = []
    total = len(symbols)

    for i, symbol in enumerate(symbols, 1):
        if i % 20 == 0:
            log.info(f"Прогресс: {i}/{total}")

        try:
            metrics = analyze_symbol(symbol)
            if metrics is None:
                continue
            score_data = score_setup(metrics)

            min_score = (
                CONFIG["min_score_threshold"]
                if CONFIG["include_watch_category"] else 40
            )

            if score_data.category != "SKIP" and score_data.score >= min_score:
                candidates.append(Candidate(metrics=metrics, score_data=score_data))
        except Exception as e:
            log.debug(f"Ошибка анализа {symbol}: {e}")
            continue

    candidates.sort(key=lambda x: x.score_data.score, reverse=True)
    top = candidates[:CONFIG["top_results"]]

    scan_duration = (datetime.now() - scan_start).total_seconds()
    log.info(f"Сканирование заняло {scan_duration:.0f} сек")
    log.info(f"Найдено кандидатов: {len(candidates)}, отправляем TOP-{len(top)}")

    save_history(top)

    if not top:
        log.info("Нет кандидатов — файлы и email не создаются")
        return

    files = save_reports(top, scan_time)

    if CONFIG["email_enabled"]:
        html_content = format_html(top, scan_time)
        subject = f"🎯 Sleeping Alts — {len(top)} кандидатов ({datetime.now().strftime('%d.%m.%Y')})"

        attachments: list[Path] = []
        for key in ("csv", "json", "markdown"):
            if key in files:
                attachments.append(files[key])

        send_email(subject, html_content, attachments)

    cleanup_old_reports()
    log.info("Сканирование завершено")


def main() -> None:
    log.info("=" * 60)
    log.info("Sleeping Alts Screener v3 запущен")
    log.info(f"Расписание: ежедневно в {CONFIG['schedule_time']}")
    log.info(f"Папка отчётов: {CONFIG['output_dir']}")
    active_formats = [k for k, v in CONFIG["output_formats"].items() if v]
    log.info(f"Форматы: {', '.join(active_formats)}")
    log.info(f"Email: {'включён' if CONFIG['email_enabled'] else 'отключён'}")
    log.info("=" * 60)

    if CONFIG["run_on_start"]:
        log.info("Запуск немедленного сканирования (run_on_start=True)")
        run_scan()

    schedule.every().day.at(CONFIG["schedule_time"]).do(run_scan)
    log.info(f"Ожидание запланированного времени ({CONFIG['schedule_time']})...")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
