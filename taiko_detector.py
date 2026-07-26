"""
TAIKO Reversal Detector — HTF (1D).
Ищет паттерн: долгое падение → капитуляция (volume spike вниз) →
глубокая перепроданность → первые признаки разворота.
"""
from __future__ import annotations
from dataclasses import dataclass
import requests

BINANCE_FAPI = "https://fapi.binance.com"


@dataclass
class TaikoSignal:
    detected: bool = False
    score: int = 0                    # 0..100
    downtrend_bars: int = 0           # длина падения в днях
    drop_pct: float = 0.0             # глубина падения от максимума окна
    capitulation_bar_ago: int = 0     # дней назад была свеча капитуляции
    rsi_d: float = 50.0
    obv_turning_up: bool = False
    reversal_hint: bool = False
    verdict: str = ""


def _get_klines(symbol: str, interval: str = "1d", limit: int = 200) -> list[list] | None:
    try:
        r = requests.get(f"{BINANCE_FAPI}/fapi/v1/klines",
                         params={"symbol": symbol, "interval": interval, "limit": limit},
                         timeout=(8, 20))
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    g = sum(gains[-period:]) / period
    l = sum(losses[-period:]) / period
    if l == 0: return 100.0
    return 100 - 100 / (1 + g / l)


def _obv(closes, vols):
    out = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]: out.append(out[-1] + vols[i])
        elif closes[i] < closes[i-1]: out.append(out[-1] - vols[i])
        else: out.append(out[-1])
    return out


def detect_taiko(symbol: str) -> TaikoSignal:
    kl = _get_klines(symbol, "1d", 200)
    if not kl or len(kl) < 60:
        return TaikoSignal()

    opens   = [float(k[1]) for k in kl]
    highs   = [float(k[2]) for k in kl]
    lows    = [float(k[3]) for k in kl]
    closes  = [float(k[4]) for k in kl]
    vols    = [float(k[7]) for k in kl]

    price = closes[-1]

    # 1. Ищем максимум последних 90 дней
    window = 90 if len(closes) >= 90 else len(closes) - 1
    hi_window = highs[-window:]
    peak = max(hi_window)
    peak_idx_rel = hi_window.index(peak)
    peak_bars_ago = window - peak_idx_rel - 1

    if peak <= 0: return TaikoSignal()
    drop_pct = (price / peak - 1) * 100   # отрицательное

    # TAIKO — падение серьёзное, но не такое экстремальное как DEXE
    if drop_pct > -30:
        return TaikoSignal()

    # 2. Длина даунтренда: сколько дней подряд закрытие ниже EMA (упрощённо: ниже средней за 20)
    downtrend_bars = 0
    for i in range(len(closes) - 1, 0, -1):
        window20 = closes[max(0, i-20):i]
        if not window20: break
        ma = sum(window20) / len(window20)
        if closes[i] < ma:
            downtrend_bars += 1
        else:
            break

    if downtrend_bars < 10:
        return TaikoSignal()

    # 3. Капитуляционная свеча — большая красная с volume-spike за последние 30 дней
    avg_vol_60 = sum(vols[-70:-10]) / 60 if len(vols) >= 70 else (sum(vols) / len(vols))
    capitulation_bar_ago = 0
    cap_found = False
    for i in range(len(closes) - 1, max(len(closes) - 30, 0), -1):
        body = (opens[i] - closes[i]) / opens[i] * 100 if opens[i] > 0 else 0
        vol_x = vols[i] / avg_vol_60 if avg_vol_60 > 0 else 0
        # красная свеча -7%+ на объёме x2+
        if body >= 6 and vol_x >= 1.8:
            capitulation_bar_ago = len(closes) - 1 - i
            cap_found = True
            break

    # 4. RSI на дневках — глубокая перепроданность (либо была недавно)
    rsi_d = _rsi(closes, 14)
    rsi_min_recent = min(_rsi(closes[:i+1], 14) for i in range(len(closes) - 10, len(closes)))
    deeply_oversold = rsi_min_recent < 32

    # 5. OBV разворачивается вверх
    obv_series = _obv(closes, vols)
    obv_tail = obv_series[-15:]
    obv_min_idx = obv_tail.index(min(obv_tail))
    obv_turning_up = obv_min_idx < len(obv_tail) - 3 and obv_tail[-1] > obv_tail[obv_min_idx]

    # 6. Признаки разворота: зелёные свечи + объём последних 5 дней
    green_recent = sum(1 for i in range(-5, 0) if closes[i] > opens[i])
    recent_vol = sum(vols[-5:]) / 5
    vol_pickup = avg_vol_60 > 0 and recent_vol / avg_vol_60 >= 1.2

    reversal_hint = (green_recent >= 3 and vol_pickup) or obv_turning_up

    # 7. Скоринг
    score = 0
    score += min(int(abs(drop_pct) - 30) // 2, 20)      # глубина падения (до +20)
    score += min(downtrend_bars, 20)                     # длительность даунтренда (до +20)
    if cap_found: score += 15                            # капитуляционная свеча
    if deeply_oversold: score += 15                      # был RSI < 32
    if obv_turning_up: score += 15                       # OBV развернулся
    if reversal_hint: score += 15                        # свежий разворот
    score = max(0, min(score, 100))

    detected = score >= 50 and (cap_found or deeply_oversold) and downtrend_bars >= 12

    verdict = ""
    if detected:
        parts = [f"Паттерн TAIKO Reversal: даунтренд {downtrend_bars} дней",
                 f"падение {drop_pct:.0f}% от пика"]
        if cap_found:
            parts.append(f"капитуляционная свеча {capitulation_bar_ago} дней назад")
        if deeply_oversold:
            parts.append(f"RSI был в глубокой перепроданности ({rsi_min_recent:.0f})")
        if obv_turning_up:
            parts.append("OBV разворачивается вверх")
        if reversal_hint:
            parts.append("первые зелёные свечи на объёме")
        verdict = ". ".join(parts) + "."

    return TaikoSignal(
        detected=detected,
        score=score,
        downtrend_bars=downtrend_bars,
        drop_pct=drop_pct,
        capitulation_bar_ago=capitulation_bar_ago,
        rsi_d=rsi_d,
        obv_turning_up=obv_turning_up,
        reversal_hint=reversal_hint,
        verdict=verdict,
    )
