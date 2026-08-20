"""TAIKO Reversal Detector — старший таймфрейм.

Ищет разворот после длительного даунтренда:
  - глубокое падение от исторического пика, от 60%
  - зрелая база у дна либо активный разворотный импульс
  - подтверждение хотя бы одним сильным сигналом:
      Vortex crossover, дивергенция или затухание продаж,
      бычья дивергенция OBV, объёмная кульминация
  - CONFIRMED BREAKOUT: база плюс свежий пробой MA20 с объёмом
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from analytics_indicators import obv_series, rsi_series
from core_binance import (
    K_OPEN, K_HIGH, K_LOW, K_CLOSE, K_QUOTE_VOLUME,
    klines_1d, klines_1w, klines_htf, series,
)

# ── Пороги ──
MIN_HISTORY_BARS = 35
SHORT_HISTORY_BARS = 90
MIN_DROP_PCT = -60.0
MIN_DROP_SHORT = -70.0
MIN_SCORE = 45
MIN_SCORE_SHORT = 38
BASE_SCORE_DISCOUNT = 7     # скидка к порогу, если база вызрела

BASE_POSITION_PCT = 40.0    # цена в нижних 40% диапазона
MIN_DOWNTREND_DAYS = 30
MIN_DOWNTREND_DAYS_SHORT = 15

RSI_OVERSOLD = 32.0
CAPITULATION_BODY_PCT = 6.0
CAPITULATION_VOL_MULT = 1.8
CLIMAX_VOL_MULT = 3.0

BREAKOUT_PRICE_MULT = 1.03
BREAKOUT_VOL_MULT = 1.5

# Binance Futures поддерживает из старших только 3d, 1w и 1M.
# Интервалы 2d, 5d, 2w биржа не отдаёт — раньше они молча падали с 400.
VORTEX_TF_LADDER = ["3d", "1w", "1M"]
VORTEX_MIN_PEAKS = 3
VORTEX_MAX_PEAKS = 10
VORTEX_MIN_PROMINENCE = 0.15


@dataclass
class TaikoSignal:
    detected: bool = False
    score: int = 0

    # базовые характеристики
    downtrend_bars: int = 0
    drop_pct: float = 0.0
    htf_drop_pct: float = 0.0
    days_in_downtrend: int = 0
    price_position_pct: float = 50.0
    short_history: bool = False

    # триггеры разворота
    capitulation_bar_ago: int = 0
    rsi_d: float = 50.0
    rsi_min_recent: float = 50.0
    obv_turning_up: bool = False
    obv_divergence: bool = False
    reversal_hint: bool = False
    volume_climax_bull: bool = False
    volume_climax_ratio: float = 0.0

    # Vortex
    vortex_crossover: bool = False
    vortex_divergence: bool = False
    vortex_note: str = ""
    vortex_selling_exhaustion: bool = False
    vortex_exhaustion_note: str = ""
    vortex_tf_used: str = ""
    vortex_peaks_count: int = 0

    confirmed_breakout: bool = False
    verdict: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────
# Вспомогательные расчёты
# ─────────────────────────────────────────────────────────────
def _vortex(highs, lows, closes, period: int = 14) -> tuple[list[float], list[float]]:
    """Ряды VI+ и VI-, выровненные по длине входных данных."""
    n = len(closes)
    vi_plus = [0.0] * n
    vi_minus = [0.0] * n
    if n < period + 2:
        return vi_plus, vi_minus

    vm_plus: list[float] = []
    vm_minus: list[float] = []
    tr: list[float] = []
    for i in range(1, n):
        vm_plus.append(abs(highs[i] - lows[i - 1]))
        vm_minus.append(abs(lows[i] - highs[i - 1]))
        tr.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))

    for i in range(period, len(vm_plus) + 1):
        sum_tr = sum(tr[i - period:i])
        if sum_tr <= 0:
            continue
        vi_plus[i] = sum(vm_plus[i - period:i]) / sum_tr
        vi_minus[i] = sum(vm_minus[i - period:i]) / sum_tr

    return vi_plus, vi_minus


def _find_swing_lows(seq: list[float], lookback: int = 3) -> list[int]:
    out: list[int] = []
    for i in range(lookback, len(seq) - lookback):
        if seq[i] <= 0:
            continue
        left = seq[i - lookback:i]
        right = seq[i + 1:i + 1 + lookback]
        if all(seq[i] <= x for x in left) and all(seq[i] <= x for x in right):
            out.append(i)
    return out


def _find_swing_highs(seq: list[float], lookback: int = 3) -> list[int]:
    out: list[int] = []
    for i in range(lookback, len(seq) - lookback):
        if seq[i] <= 0:
            continue
        left = seq[i - lookback:i]
        right = seq[i + 1:i + 1 + lookback]
        if all(seq[i] >= x for x in left) and all(seq[i] >= x for x in right):
            out.append(i)
    return out


# ─────────────────────────────────────────────────────────────
# Проверки сигналов
# ─────────────────────────────────────────────────────────────
def _vortex_bullish_crossover(highs, lows, closes) -> bool:
    """Свежее пересечение VI+ над VI- после долгого доминирования VI-."""
    vi_p, vi_m = _vortex(highs, lows, closes, 14)
    n = len(vi_p)
    if n < 30 or vi_p[-1] <= vi_m[-1]:
        return False

    crossover_idx = None
    for i in range(n - 1, max(n - 9, 1), -1):
        if vi_p[i] > vi_m[i] and vi_p[i - 1] <= vi_m[i - 1]:
            crossover_idx = i
            break
    if crossover_idx is None:
        return False

    check_from = max(0, crossover_idx - 20)
    minus_dom = sum(1 for j in range(check_from, crossover_idx) if vi_m[j] > vi_p[j])
    return minus_dom >= 15


def _vortex_divergence(highs, lows, closes) -> tuple[bool, str]:
    """VI+ поднимает минимумы, VI- опускает — сила переходит к покупателям."""
    vi_p, vi_m = _vortex(highs, lows, closes, 14)
    tail_start = max(0, len(closes) - 60)
    p_tail = vi_p[tail_start:]
    m_tail = vi_m[tail_start:]

    p_lows_idx = _find_swing_lows(p_tail, lookback=3)
    m_lows_idx = _find_swing_lows(m_tail, lookback=3)
    if len(p_lows_idx) < 2 or len(m_lows_idx) < 2:
        return False, ""

    p1, p2 = p_tail[p_lows_idx[-2]], p_tail[p_lows_idx[-1]]
    m1, m2 = m_tail[m_lows_idx[-2]], m_tail[m_lows_idx[-1]]

    if p2 > p1 * 1.02 and m2 < m1 * 0.98:
        return True, f"VI+ {p1:.2f}→{p2:.2f}, VI- {m1:.2f}→{m2:.2f}"
    return False, ""


def _vortex_selling_exhaustion(highs, lows, closes) -> tuple[bool, str]:
    """Пики VI- становятся ниже: каждая волна продаж слабее предыдущей."""
    vi_p, vi_m = _vortex(highs, lows, closes, 14)
    tail_start = max(0, len(closes) - 60)
    p_tail = vi_p[tail_start:]
    m_tail = vi_m[tail_start:]

    m_highs_idx = _find_swing_highs(m_tail, lookback=3)
    if len(m_highs_idx) < 2:
        return False, ""

    peaks = [m_tail[i] for i in m_highs_idx[-3:]]
    descending = all(peaks[k] > peaks[k + 1] * 1.02 for k in range(len(peaks) - 1))
    if not descending:
        return False, ""

    p_last = p_tail[-1]
    p_prev_avg = sum(p_tail[-10:-1]) / 9 if len(p_tail) >= 10 else p_last
    if p_last >= p_prev_avg * 0.95:
        peaks_str = "→".join(f"{p:.2f}" for p in peaks)
        return True, f"пики продаж затухают ({peaks_str})"
    return False, ""


def _vortex_tf_quality(highs, lows, closes) -> tuple[int, float]:
    """Читаемость таймфрейма: сколько выраженных пиков VI- и насколько они рельефны."""
    vi_p, vi_m = _vortex(highs, lows, closes, 14)
    tail_start = max(0, len(closes) - 60)
    m_tail = vi_m[tail_start:]
    if len(m_tail) < 20:
        return 0, 0.0

    peaks_idx = _find_swing_highs(m_tail, lookback=3)
    if len(peaks_idx) < 2:
        return len(peaks_idx), 0.0

    avg_val = sum(m_tail) / len(m_tail)
    if avg_val <= 0:
        return len(peaks_idx), 0.0

    prominences = [(m_tail[i] - avg_val) / avg_val for i in peaks_idx]
    return len(peaks_idx), sum(prominences) / len(prominences)


def _analyze_vortex_multi_tf(symbol: str) -> dict:
    """Идёт по лестнице таймфреймов и берёт первый читаемый."""
    result = {
        "tf_used": "",
        "peaks_count": 0,
        "crossover": False,
        "divergence": False,
        "divergence_note": "",
        "exhaustion": False,
        "exhaustion_note": "",
    }

    for tf in VORTEX_TF_LADDER:
        kl = klines_htf(symbol, tf)
        if not kl or len(kl) < 40:
            continue

        h = series(kl, K_HIGH)
        l = series(kl, K_LOW)
        c = series(kl, K_CLOSE)

        peaks_count, prominence = _vortex_tf_quality(h, l, c)
        readable = (
            VORTEX_MIN_PEAKS <= peaks_count <= VORTEX_MAX_PEAKS
            and prominence >= VORTEX_MIN_PROMINENCE
        )
        if not readable:
            continue

        cross = _vortex_bullish_crossover(h, l, c)
        div, div_note = _vortex_divergence(h, l, c)
        exh, exh_note = _vortex_selling_exhaustion(h, l, c)

        result.update({
            "tf_used": tf,
            "peaks_count": peaks_count,
            "crossover": cross,
            "divergence": div,
            "divergence_note": div_note,
            "exhaustion": exh,
            "exhaustion_note": exh_note,
        })
        return result

    return result


def _obv_bullish_divergence(closes, vols, window: int = 80) -> bool:
    """Цена обновляет минимум, OBV — нет: продавцы выдыхаются."""
    if len(closes) < window:
        return False

    obv = obv_series(closes, vols)
    seg_c = closes[-window:]
    seg_o = obv[-window:]

    price_lows_idx = _find_swing_lows(seg_c, lookback=3)
    obv_lows_idx = _find_swing_lows(seg_o, lookback=3)
    if len(price_lows_idx) < 2 or len(obv_lows_idx) < 2:
        return False

    pc1, pc2 = seg_c[price_lows_idx[-2]], seg_c[price_lows_idx[-1]]
    oc1, oc2 = seg_o[obv_lows_idx[-2]], seg_o[obv_lows_idx[-1]]

    price_lower_or_flat = pc2 <= pc1 * 1.03
    obv_higher = oc2 > oc1
    return price_lower_or_flat and obv_higher


def _volume_climax_bullish(opens, closes, vols, avg_vol: float) -> tuple[bool, float]:
    """Зелёная свеча на кратно повышенном объёме за последние 5 баров."""
    if avg_vol <= 0:
        return False, 0.0

    best_ratio = 0.0
    found = False
    for i in range(max(0, len(closes) - 5), len(closes)):
        if closes[i] <= opens[i]:
            continue
        ratio = vols[i] / avg_vol
        best_ratio = max(best_ratio, ratio)
        if ratio >= CLIMAX_VOL_MULT:
            found = True
    return found, best_ratio


# ─────────────────────────────────────────────────────────────
# Основной детектор
# ─────────────────────────────────────────────────────────────
def detect_taiko(symbol: str) -> TaikoSignal:
    """Разворотный паттерн на старшем таймфрейме."""
    kl = klines_1d(symbol)
    if not kl or len(kl) < MIN_HISTORY_BARS:
        return TaikoSignal()

    short_history = len(kl) < SHORT_HISTORY_BARS

    opens = series(kl, K_OPEN)
    highs = series(kl, K_HIGH)
    lows = series(kl, K_LOW)
    closes = series(kl, K_CLOSE)
    vols = series(kl, K_QUOTE_VOLUME)

    price = closes[-1]
    peak = max(highs)
    if peak <= 0 or price <= 0:
        return TaikoSignal()

    drop_pct = (price / peak - 1) * 100

    # ── Недельная история для истинной глубины падения ──
    htf_drop_pct = drop_pct
    kl_w = klines_1w(symbol)
    if kl_w and len(kl_w) >= 20:
        htf_highs = series(kl_w, K_HIGH)
        htf_peak = max(htf_highs) if htf_highs else 0.0
        if htf_peak > 0:
            htf_drop_pct = (price / htf_peak - 1) * 100

    effective_drop = min(drop_pct, htf_drop_pct)
    if effective_drop > MIN_DROP_PCT:
        return TaikoSignal()

    # ── Характеристика даунтренда ──
    window = min(180, len(closes))
    seg_h = highs[-window:]
    seg_l = lows[-window:]
    seg_c = closes[-window:]

    win_peak = max(seg_h)
    win_low = min(seg_l)
    half = win_peak * 0.5
    days_in_downtrend = sum(1 for c in seg_c if c < half)

    if win_peak > win_low:
        price_position_pct = (price - win_low) / (win_peak - win_low) * 100
    else:
        price_position_pct = 50.0

    min_downtrend_days = MIN_DOWNTREND_DAYS_SHORT if short_history else MIN_DOWNTREND_DAYS
    in_base = (
        price_position_pct <= BASE_POSITION_PCT
        and days_in_downtrend >= min_downtrend_days
    )

    # ── Длина непрерывного даунтренда под MA20 ──
    downtrend_bars = 0
    for i in range(len(closes) - 1, 0, -1):
        w20 = closes[max(0, i - 20):i]
        if not w20:
            break
        if closes[i] < sum(w20) / len(w20):
            downtrend_bars += 1
        else:
            break

    # ── Капитуляция ──
    if len(vols) >= 70:
        avg_vol_60 = sum(vols[-70:-10]) / 60
    else:
        avg_vol_60 = sum(vols) / len(vols) if vols else 0.0

    capitulation_bar_ago = 0
    cap_found = False
    for i in range(len(closes) - 1, max(len(closes) - 120, 0), -1):
        body = (opens[i] - closes[i]) / opens[i] * 100 if opens[i] > 0 else 0.0
        vol_x = vols[i] / avg_vol_60 if avg_vol_60 > 0 else 0.0
        if body >= CAPITULATION_BODY_PCT and vol_x >= CAPITULATION_VOL_MULT:
            capitulation_bar_ago = len(closes) - 1 - i
            cap_found = True
            break

    # ── RSI: один проход вместо повторного пересчёта на каждом баре ──
    rsis = rsi_series(closes, 14)
    rsi_d = rsis[-1] if rsis else 50.0
    lookback_rsi = min(60, len(rsis))
    rsi_min_recent = min(rsis[-lookback_rsi:]) if lookback_rsi > 0 else 50.0
    deeply_oversold = rsi_min_recent < RSI_OVERSOLD

    # ── OBV: короткий разворот и дивергенция ──
    obv = obv_series(closes, vols)
    obv_tail = obv[-15:]
    obv_turning_up = False
    if obv_tail:
        obv_min_idx = obv_tail.index(min(obv_tail))
        obv_turning_up = (
            obv_min_idx < len(obv_tail) - 3
            and obv_tail[-1] > obv_tail[obv_min_idx]
        )
    obv_div = _obv_bullish_divergence(closes, vols, window=80)

    # ── Объёмная кульминация ──
    vc_bull, vc_ratio = _volume_climax_bullish(opens, closes, vols, avg_vol_60)

    # ── Vortex по лестнице таймфреймов ──
    v = _analyze_vortex_multi_tf(symbol)
    vortex_cross = v["crossover"]
    vortex_div = v["divergence"]
    vortex_note = v["divergence_note"]
    vortex_exh = v["exhaustion"]
    vortex_exh_note = v["exhaustion_note"]
    vortex_tf_used = v["tf_used"]
    vortex_peaks = v["peaks_count"]

    # ── Разворотный импульс ──
    green_recent = sum(1 for i in range(-5, 0) if closes[i] > opens[i])
    recent_vol = sum(vols[-5:]) / 5 if len(vols) >= 5 else 0.0
    vol_pickup = avg_vol_60 > 0 and recent_vol / avg_vol_60 >= 1.2
    reversal_hint = (green_recent >= 3 and vol_pickup) or obv_turning_up or vc_bull

    # ── Скоринг ──
    score = 0
    if effective_drop <= MIN_DROP_PCT:
        score += min(int((abs(effective_drop) - 60) * 0.6), 25)
    score += min(int(days_in_downtrend / 6), 20)
    score += max(0, int((35 - price_position_pct) * 0.6))

    if cap_found:
        score += 8
    if deeply_oversold:
        score += 8
    if obv_turning_up:
        score += 6
    if vortex_cross:
        score += 20
    if vortex_div:
        score += 18
    if vortex_exh:
        score += 14
    if obv_div:
        score += 20
    if vc_bull:
        score += 18
    if reversal_hint:
        score += 6

    if vortex_tf_used in ("1w", "1M"):
        score += 5
    elif vortex_tf_used == "3d":
        score += 3

    # ── Подтверждённый пробой ──
    confirmed_breakout = False
    if len(closes) >= 25 and len(vols) >= 25:
        ma20_prev = sum(closes[-25:-5]) / 20
        recent_high = max(closes[-3:])
        avg_vol_20 = sum(vols[-25:-5]) / 20
        recent_vol_max = max(vols[-3:])
        price_broke_out = ma20_prev > 0 and recent_high > ma20_prev * BREAKOUT_PRICE_MULT
        volume_confirmed = avg_vol_20 > 0 and recent_vol_max > avg_vol_20 * BREAKOUT_VOL_MULT
        if price_broke_out and volume_confirmed:
            confirmed_breakout = True
            score += 10

    score = max(0, min(score, 100))

    # ── Условие срабатывания ──
    has_reversal_signal = (
        vortex_cross or vortex_div or vortex_exh or obv_div or vc_bull
    )
    min_score = MIN_SCORE_SHORT if short_history else MIN_SCORE
    min_drop = MIN_DROP_SHORT if short_history else MIN_DROP_PCT

    # Зрелая база снижает планку: паттерн вызрел, остаётся дождаться триггера
    effective_min_score = min_score - BASE_SCORE_DISCOUNT if in_base else min_score

    detected = (
        effective_drop <= min_drop
        and has_reversal_signal
        and score >= effective_min_score
    )

    # ── Вердикт ──
    verdict = ""
    if detected:
        parts = [f"TAIKO Reversal: падение {effective_drop:.0f}% от пика старшего ТФ"]
        if confirmed_breakout:
            parts.insert(0, "CONFIRMED BREAKOUT")
        if in_base:
            parts.append(
                f"зрелая база, {days_in_downtrend} дней в даунтренде, "
                f"цена в нижних {price_position_pct:.0f}% диапазона"
            )
        tf_tag = f" [{vortex_tf_used.upper()}]" if vortex_tf_used else ""
        if vortex_cross:
            parts.append(f"свежий бычий crossover Vortex{tf_tag}")
        if vortex_div:
            parts.append(f"дивергенция Vortex{tf_tag}, {vortex_note}")
        if vortex_exh:
            parts.append(f"затухание продаж{tf_tag}, {vortex_exh_note}")
        if obv_div:
            parts.append("бычья дивергенция OBV")
        if vc_bull:
            parts.append(f"объёмная кульминация ×{vc_ratio:.1f}")
        if cap_found:
            parts.append(f"капитуляция {capitulation_bar_ago}д назад")
        if deeply_oversold:
            parts.append(f"минимум RSI {rsi_min_recent:.0f}")
        if reversal_hint and not vc_bull:
            parts.append("зелёные свечи с объёмом")
        verdict = ". ".join(parts) + "."

    return TaikoSignal(
        detected=detected,
        score=score,
        downtrend_bars=downtrend_bars,
        drop_pct=drop_pct,
        htf_drop_pct=htf_drop_pct,
        days_in_downtrend=days_in_downtrend,
        price_position_pct=price_position_pct,
        short_history=short_history,
        capitulation_bar_ago=capitulation_bar_ago,
        rsi_d=rsi_d,
        rsi_min_recent=rsi_min_recent,
        obv_turning_up=obv_turning_up,
        obv_divergence=obv_div,
        reversal_hint=reversal_hint,
        volume_climax_bull=vc_bull,
        volume_climax_ratio=vc_ratio,
        vortex_crossover=vortex_cross,
        vortex_divergence=vortex_div,
        vortex_note=vortex_note,
        vortex_selling_exhaustion=vortex_exh,
        vortex_exhaustion_note=vortex_exh_note,
        vortex_tf_used=vortex_tf_used,
        vortex_peaks_count=vortex_peaks,
        confirmed_breakout=confirmed_breakout,
        verdict=verdict,
    )
