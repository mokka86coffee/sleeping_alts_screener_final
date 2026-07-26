"""
DEXE Post-Pump Detector — HTF (1D).
Ищет паттерн: сильный памп → обвал 70%+ → консолидация у дна → признаки разворота.
"""
from __future__ import annotations
from dataclasses import dataclass
import requests

BINANCE_FAPI = "https://fapi.binance.com"


@dataclass
class DexeSignal:
    detected: bool = False
    score: int = 0
    peak_price: float = 0.0
    peak_bars_ago: int = 0
    drawdown_pct: float = 0.0
    pump_x: float = 0.0
    consolidation_bars: int = 0
    reversal_hint: bool = False
    verdict: str = ""


def _get_klines(symbol: str, interval: str = "1d", limit: int = 200):
    try:
        r = requests.get(f"{BINANCE_FAPI}/fapi/v1/klines",
                         params={"symbol": symbol, "interval": interval, "limit": limit},
                         timeout=(8, 20))
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def detect_dexe(symbol: str) -> DexeSignal:
    kl = _get_klines(symbol, "1d", 200)
    if not kl or len(kl) < 60:
        return DexeSignal()

    highs  = [float(k[2]) for k in kl]
    lows   = [float(k[3]) for k in kl]
    closes = [float(k[4]) for k in kl]
    vols   = [float(k[7]) for k in kl]
    price = closes[-1]

    # Ищем пик за окно (не последние 10 дней, чтобы был реальный откат)
    search = highs[:-10]
    if len(search) < 30:
        return DexeSignal()
    peak = max(search)
    peak_idx = search.index(peak)
    peak_bars_ago = len(highs) - 1 - peak_idx
    if peak <= 0:
        return DexeSignal()

    drawdown = (price / peak - 1) * 100
    if drawdown > -55:                    # упало меньше 55% — не DEXE
        return DexeSignal()

    # Был ли памп до пика (за 60 баров до)
    pre_start = max(0, peak_idx - 60)
    pre_low = min(lows[pre_start:peak_idx + 1]) if peak_idx > pre_start else peak
    pump_x = peak / pre_low if pre_low > 0 else 1
    if pump_x < 1.8:
        return DexeSignal()

    # Консолидация — последние 20 дней в узком диапазоне
    tail = closes[-20:]
    tail_min, tail_max = min(tail), max(tail)
    if tail_min <= 0:
        return DexeSignal()
    range_pct = (tail_max / tail_min - 1) * 100
    consolidation_bars = 20 if range_pct < 45 else (10 if range_pct < 80 else 0)

    # Признаки разворота
    avg_vol_20 = sum(vols[-25:-5]) / 20 if len(vols) >= 25 else 0
    recent_vol = sum(vols[-5:]) / 5
    vol_pickup = avg_vol_20 > 0 and recent_vol / avg_vol_20 >= 1.2
    green_recent = sum(1 for i in range(-3, 0) if closes[i] > closes[i - 1])
    local_low = min(lows[-15:])
    above_low = price > local_low * 1.05
    reversal_hint = vol_pickup and (green_recent >= 2 or above_low)

    # Скор
    score = 0
    score += min(int(abs(drawdown) - 55) // 3, 20)
    score += min(int(pump_x * 4), 25)
    score += consolidation_bars
    if reversal_hint: score += 25
    if peak_bars_ago > 25: score += 10
    score = max(0, min(score, 100))

    detected = score >= 45 and consolidation_bars > 0

    verdict = ""
    if detected:
        verdict = (f"DEXE Post-Pump: пик был {peak_bars_ago} дней назад "
                   f"(памп ×{pump_x:.1f}), падение {drawdown:.0f}%, "
                   f"консолидация {consolidation_bars} дней"
                   + (", признаки разворота (объём + зелёные свечи)." if reversal_hint else "."))

    return DexeSignal(
        detected=detected, score=score, peak_price=peak,
        peak_bars_ago=peak_bars_ago, drawdown_pct=drawdown, pump_x=pump_x,
        consolidation_bars=consolidation_bars, reversal_hint=reversal_hint,
        verdict=verdict,
    )
