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
    vortex_divergence: bool = False
    vortex_note: str = ""


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

def _vortex(highs, lows, closes, period: int = 14) -> tuple[list[float], list[float]]:
    """Возвращает (VI+, VI-) серии длины len(closes)."""
    n = len(closes)
    vi_plus  = [0.0] * n
    vi_minus = [0.0] * n
    if n < period + 2:
        return vi_plus, vi_minus

    vm_plus, vm_minus, tr = [], [], []
    for i in range(1, n):
        vm_plus.append(abs(highs[i] - lows[i - 1]))
        vm_minus.append(abs(lows[i] - highs[i - 1]))
        tr.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i]  - closes[i - 1]),
        ))

    for i in range(period, len(vm_plus) + 1):
        sum_tr = sum(tr[i - period:i])
        if sum_tr <= 0: continue
        vi_plus[i]  = sum(vm_plus[i - period:i])  / sum_tr
        vi_minus[i] = sum(vm_minus[i - period:i]) / sum_tr

    return vi_plus, vi_minus


def _find_swing_lows(series: list[float], lookback: int = 3) -> list[int]:
    """Индексы локальных минимумов (свинг-лоу) в серии."""
    out = []
    for i in range(lookback, len(series) - lookback):
        if series[i] <= 0: continue
        left  = series[i - lookback:i]
        right = series[i + 1:i + 1 + lookback]
        if all(series[i] <= x for x in left) and all(series[i] <= x for x in right):
            out.append(i)
    return out


def _check_vortex_divergence(highs, lows, closes) -> tuple[bool, str]:
    """
    Bullish Vortex Divergence:
    - VI- делает lower lows (продажи слабеют по силе, но растут по агрессии — считаем как lower lows у VI-)
    - VI+ делает higher lows (покупки становятся крепче)
    Смотрим последние 2 свинга у каждой линии за последние ~40 баров.
    """
    vi_p, vi_m = _vortex(highs, lows, closes, 14)
    tail_start = max(0, len(closes) - 45)
    p_tail = vi_p[tail_start:]
    m_tail = vi_m[tail_start:]

    p_lows_idx = _find_swing_lows(p_tail, lookback=3)
    m_lows_idx = _find_swing_lows(m_tail, lookback=3)

    if len(p_lows_idx) < 2 or len(m_lows_idx) < 2:
        return False, ""

    # Последние 2 свинга
    p1, p2 = p_tail[p_lows_idx[-2]], p_tail[p_lows_idx[-1]]
    m1, m2 = m_tail[m_lows_idx[-2]], m_tail[m_lows_idx[-1]]

    vi_plus_higher_lows  = p2 > p1 * 1.02   # VI+ выше на 2%+
    vi_minus_lower_lows  = m2 < m1 * 0.98   # VI- ниже на 2%+

    if vi_plus_higher_lows and vi_minus_lower_lows:
        return True, (f"VI+ higher lows ({p1:.2f}→{p2:.2f}), "
                      f"VI- lower lows ({m1:.2f}→{m2:.2f})")
    return False, ""


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

    # Проверяем на 2D (главный TF для этого паттерна — как на скрине)
    kl_2d = _get_klines(symbol, "2d", 200)
    if kl_2d and len(kl_2d) >= 40:
        h2 = [float(k[2]) for k in kl_2d]
        l2 = [float(k[3]) for k in kl_2d]
        c2 = [float(k[4]) for k in kl_2d]
        vortex_div, vortex_note = _check_vortex_divergence(h2, l2, c2)
    else:
        # fallback на 1D
        vortex_div, vortex_note = _check_vortex_divergence(highs, lows, closes)

    # 7. Скоринг
    score = 0
    score += min(int(abs(drop_pct) - 30) // 2, 20)      # глубина падения (до +20)
    score += min(downtrend_bars, 20)                     # длительность даунтренда (до +20)
    if cap_found: score += 15                            # капитуляционная свеча
    if deeply_oversold: score += 15                      # был RSI < 32
    if obv_turning_up: score += 15                       # OBV развернулся
    if vortex_div:     score += 25                       # ← сильный подтверждающий сигнал
    if reversal_hint: score += 15                        # свежий разворот
    score = max(0, min(score, 100))

    # Vortex divergence — очень сильный сигнал, снижаем требование к остальному
    detected = (score >= 50 and downtrend_bars >= 12
                and (cap_found or deeply_oversold or vortex_div))

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
        if vortex_div:
            parts.append(f"Vortex bullish divergence ({vortex_note})")
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
        vortex_divergence=vortex_div,
        vortex_note=vortex_note,
    )
