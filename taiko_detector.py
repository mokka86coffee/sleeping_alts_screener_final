"""
TAIKO Reversal Detector — HTF.
Ищет паттерн разворота после длительного даунтренда:
  - Глубокое падение от исторического пика (≥60%)
  - Зрелая база у дна ИЛИ активный разворотный импульс
  - Подтверждение хотя бы одним сильным сигналом:
      * Vortex bullish crossover / divergence
      * OBV bullish divergence
      * Volume climax на разворотной свече
"""
from __future__ import annotations
from dataclasses import dataclass
import requests

BINANCE_FAPI = "https://fapi.binance.com"


@dataclass
class TaikoSignal:
    detected: bool = False
    score: int = 0
    # старые поля (для совместимости)
    downtrend_bars: int = 0
    drop_pct: float = 0.0
    capitulation_bar_ago: int = 0
    rsi_d: float = 50.0
    obv_turning_up: bool = False
    reversal_hint: bool = False
    verdict: str = ""
    vortex_divergence: bool = False
    vortex_note: str = ""
    # новые поля
    vortex_crossover: bool = False
    obv_divergence: bool = False
    volume_climax_bull: bool = False
    volume_climax_ratio: float = 0.0
    htf_drop_pct: float = 0.0
    days_in_downtrend: int = 0
    price_position_pct: float = 50.0    # где сейчас цена в диапазоне [low..high] окна, %


# ============================================================
# ==================== ДАННЫЕ ================================
# ============================================================

def _get_klines(symbol: str, interval: str = "1d", limit: int = 500) -> list[list] | None:
    try:
        r = requests.get(f"{BINANCE_FAPI}/fapi/v1/klines",
                         params={"symbol": symbol, "interval": interval, "limit": limit},
                         timeout=(8, 20))
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


# ============================================================
# ==================== ИНДИКАТОРЫ ============================
# ============================================================

def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    g = sum(gains[-period:]) / period
    l = sum(losses[-period:]) / period
    if l == 0:
        return 100.0
    return 100 - 100 / (1 + g / l)


def _obv(closes, vols):
    out = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]: out.append(out[-1] + vols[i])
        elif closes[i] < closes[i-1]: out.append(out[-1] - vols[i])
        else: out.append(out[-1])
    return out


def _vortex(highs, lows, closes, period: int = 14) -> tuple[list[float], list[float]]:
    n = len(closes)
    vi_plus = [0.0] * n
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
            abs(lows[i] - closes[i - 1]),
        ))
    for i in range(period, len(vm_plus) + 1):
        sum_tr = sum(tr[i - period:i])
        if sum_tr <= 0: continue
        vi_plus[i]  = sum(vm_plus[i - period:i]) / sum_tr
        vi_minus[i] = sum(vm_minus[i - period:i]) / sum_tr
    return vi_plus, vi_minus


def _find_swing_lows(series: list[float], lookback: int = 3) -> list[int]:
    out = []
    for i in range(lookback, len(series) - lookback):
        if series[i] <= 0: continue
        left = series[i - lookback:i]
        right = series[i + 1:i + 1 + lookback]
        if all(series[i] <= x for x in left) and all(series[i] <= x for x in right):
            out.append(i)
    return out


# ============================================================
# =============== ПРОВЕРКИ СИГНАЛОВ ==========================
# ============================================================

def _vortex_bullish_crossover(highs, lows, closes) -> bool:
    """Свежий crossover VI+ > VI- в последние 8 баров после долгого доминирования VI-."""
    vi_p, vi_m = _vortex(highs, lows, closes, 14)
    n = len(vi_p)
    if n < 30: return False
    # текущее состояние
    if vi_p[-1] <= vi_m[-1]: return False
    # crossover случился в последние 8 баров
    crossover_idx = None
    for i in range(n - 1, max(n - 9, 1), -1):
        if vi_p[i] > vi_m[i] and vi_p[i - 1] <= vi_m[i - 1]:
            crossover_idx = i
            break
    if crossover_idx is None: return False
    # до crossover VI- доминировало в 15 из 20 баров
    check_from = max(0, crossover_idx - 20)
    minus_dom = sum(1 for j in range(check_from, crossover_idx)
                    if vi_m[j] > vi_p[j])
    return minus_dom >= 15


def _vortex_divergence(highs, lows, closes) -> tuple[bool, str]:
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


def _obv_bullish_divergence(closes, vols, window: int = 80) -> bool:
    """Цена делает LL, OBV делает HL за окно."""
    if len(closes) < window: return False
    obv = _obv(closes, vols)
    seg_c = closes[-window:]
    seg_o = obv[-window:]
    price_lows_idx = _find_swing_lows(seg_c, lookback=3)
    obv_lows_idx = _find_swing_lows(seg_o, lookback=3)
    if len(price_lows_idx) < 2 or len(obv_lows_idx) < 2:
        return False
    pc1, pc2 = seg_c[price_lows_idx[-2]], seg_c[price_lows_idx[-1]]
    oc1, oc2 = seg_o[obv_lows_idx[-2]], seg_o[obv_lows_idx[-1]]
    # цена: LL (или flat), OBV: HL
    price_ll_or_flat = pc2 <= pc1 * 1.03
    obv_hl = oc2 > oc1
    return price_ll_or_flat and obv_hl


def _volume_climax_bullish(opens, closes, vols, avg_vol: float) -> tuple[bool, float]:
    """Есть ли в последних 5 барах зелёная свеча с аномальным объёмом (≥3× среднего)."""
    if avg_vol <= 0: return False, 0.0
    best_ratio = 0.0
    found = False
    for i in range(max(0, len(closes) - 5), len(closes)):
        if closes[i] <= opens[i]: continue    # только зелёные
        ratio = vols[i] / avg_vol
        if ratio > best_ratio:
            best_ratio = ratio
        if ratio >= 3.0:
            found = True
    return found, best_ratio


# ============================================================
# =============== ОСНОВНОЙ ДЕТЕКТОР ==========================
# ============================================================

def detect_taiko(symbol: str) -> TaikoSignal:
    # --- 1D данные (максимум 500 баров ≈ 1.4 года) ---
    kl = _get_klines(symbol, "1d", 500)
    if not kl or len(kl) < 90:                    # фильтр min history
        return TaikoSignal()

    opens  = [float(k[1]) for k in kl]
    highs  = [float(k[2]) for k in kl]
    lows   = [float(k[3]) for k in kl]
    closes = [float(k[4]) for k in kl]
    vols   = [float(k[7]) for k in kl]            # quote volume
    price  = closes[-1]

    # --- 2. Пик за всю доступную историю ---
    peak = max(highs)
    peak_idx = highs.index(peak)
    if peak <= 0: return TaikoSignal()
    drop_pct = (price / peak - 1) * 100

    # --- 3. Догружаем недельки для HTF-подтверждения глубины ---
    htf_drop_pct = drop_pct
    kl_w = _get_klines(symbol, "1w", 200)
    if kl_w and len(kl_w) >= 20:
        htf_highs = [float(k[2]) for k in kl_w]
        htf_peak = max(htf_highs)
        if htf_peak > 0:
            htf_drop_pct = (price / htf_peak - 1) * 100

    # для TAIKO нужен глубокий обвал в истории — минимум 60%
    effective_drop = min(drop_pct, htf_drop_pct)   # более отрицательный
    if effective_drop > -60:
        return TaikoSignal()

    # --- 4. Даунтренд: доля баров ниже 50% от пика за 180 дней ---
    window = min(180, len(closes))
    seg_h = highs[-window:]
    seg_l = lows[-window:]
    seg_c = closes[-window:]
    win_peak = max(seg_h)
    win_low  = min(seg_l)
    half = win_peak * 0.5
    days_in_downtrend = sum(1 for c in seg_c if c < half)

    # где сейчас цена в диапазоне окна
    if win_peak > win_low:
        price_position_pct = (price - win_low) / (win_peak - win_low) * 100
    else:
        price_position_pct = 50.0

    # для TAIKO: цена в нижней трети диапазона + существенная часть окна в даунтренде
    in_base = price_position_pct <= 35 and days_in_downtrend >= 30

    # --- 5. Старое поле downtrend_bars (для совместимости) ---
    downtrend_bars = 0
    for i in range(len(closes) - 1, 0, -1):
        w20 = closes[max(0, i-20):i]
        if not w20: break
        if closes[i] < sum(w20) / len(w20): downtrend_bars += 1
        else: break

    # --- 6. Капитуляционная свеча — окно 120 дней ---
    avg_vol_60 = sum(vols[-70:-10]) / 60 if len(vols) >= 70 else (sum(vols) / len(vols))
    capitulation_bar_ago = 0
    cap_found = False
    for i in range(len(closes) - 1, max(len(closes) - 120, 0), -1):
        body = (opens[i] - closes[i]) / opens[i] * 100 if opens[i] > 0 else 0
        vol_x = vols[i] / avg_vol_60 if avg_vol_60 > 0 else 0
        if body >= 6 and vol_x >= 1.8:
            capitulation_bar_ago = len(closes) - 1 - i
            cap_found = True
            break

    # --- 7. RSI: текущий + минимум за 60 дней ---
    rsi_d = _rsi(closes, 14)
    lookback_rsi = min(60, len(closes) - 15)
    rsi_min_recent = min(
        _rsi(closes[:i+1], 14)
        for i in range(len(closes) - lookback_rsi, len(closes))
    )
    deeply_oversold = rsi_min_recent < 32

    # --- 8. OBV разворот (короткое окно, для совместимости) ---
    obv_series = _obv(closes, vols)
    obv_tail = obv_series[-15:]
    obv_min_idx = obv_tail.index(min(obv_tail))
    obv_turning_up = obv_min_idx < len(obv_tail) - 3 and obv_tail[-1] > obv_tail[obv_min_idx]

    # --- 9. OBV bullish divergence (сильный сигнал, окно 80 дней) ---
    obv_div = _obv_bullish_divergence(closes, vols, window=80)

    # --- 10. Volume climax bullish (аномальный объём на зелёной свече в последних 5 барах) ---
    vc_bull, vc_ratio = _volume_climax_bullish(opens, closes, vols, avg_vol_60)

    # --- 11. Vortex: crossover или divergence (проверяем на 2D — плавнее) ---
    kl_2d = _get_klines(symbol, "2d", 200)
    if kl_2d and len(kl_2d) >= 40:
        h2 = [float(k[2]) for k in kl_2d]
        l2 = [float(k[3]) for k in kl_2d]
        c2 = [float(k[4]) for k in kl_2d]
        vortex_div, vortex_note = _vortex_divergence(h2, l2, c2)
        vortex_cross = _vortex_bullish_crossover(h2, l2, c2)
    else:
        vortex_div, vortex_note = _vortex_divergence(highs, lows, closes)
        vortex_cross = _vortex_bullish_crossover(highs, lows, closes)

    # --- 12. Разворотный импульс: зелёные свечи + подросший объём ---
    green_recent = sum(1 for i in range(-5, 0) if closes[i] > opens[i])
    recent_vol = sum(vols[-5:]) / 5
    vol_pickup = avg_vol_60 > 0 and recent_vol / avg_vol_60 >= 1.2
    reversal_hint = (green_recent >= 3 and vol_pickup) or obv_turning_up or vc_bull

    # --- 13. Скоринг ---
    score = 0
    # глубина падения: -60%..-95%+  → 0..25
    score += min(int((abs(effective_drop) - 60) * 0.6), 25) if effective_drop <= -60 else 0
    # зрелость базы (доля даунтренда в окне)
    score += min(int(days_in_downtrend / 6), 20)      # 30д→5, 120д→20
    # позиция цены — чем ниже, тем лучше
    score += max(0, int((35 - price_position_pct) * 0.6))  # 0%→+21, 35%→0

    if cap_found: score += 8
    if deeply_oversold: score += 8
    if obv_turning_up: score += 6

    # сильные сигналы разворота
    if vortex_cross: score += 20
    if vortex_div:   score += 18
    if obv_div:      score += 20
    if vc_bull:      score += 18
    if reversal_hint: score += 6

    score = max(0, min(score, 100))

    # --- 14. Условие срабатывания ---
    has_reversal_signal = vortex_cross or vortex_div or obv_div or vc_bull
    detected = (
        effective_drop <= -60
        and (in_base or has_reversal_signal)
        and has_reversal_signal
        and score >= 45
    )

    # --- 15. Вердикт ---
    verdict = ""
    if detected:
        parts = [f"TAIKO Reversal: падение {effective_drop:.0f}% от HTF-пика"]
        if in_base:
            parts.append(f"зрелая база ({days_in_downtrend} дней в даунтренде, "
                         f"цена в {price_position_pct:.0f}% диапазона)")
        if vortex_cross:
            parts.append("свежий Vortex bullish crossover")
        if vortex_div:
            parts.append(f"Vortex divergence ({vortex_note})")
        if obv_div:
            parts.append("OBV bullish divergence")
        if vc_bull:
            parts.append(f"Volume climax bullish (×{vc_ratio:.1f})")
        if cap_found:
            parts.append(f"капитуляция {capitulation_bar_ago}д назад")
        if deeply_oversold:
            parts.append(f"RSI-min {rsi_min_recent:.0f}")
        if reversal_hint and not vc_bull:
            parts.append("зелёные свечи с объёмом")
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
        vortex_crossover=vortex_cross,
        obv_divergence=obv_div,
        volume_climax_bull=vc_bull,
        volume_climax_ratio=vc_ratio,
        htf_drop_pct=htf_drop_pct,
        days_in_downtrend=days_in_downtrend,
        price_position_pct=price_position_pct,
    )
