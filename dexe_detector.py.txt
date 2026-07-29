"""
DEXE Post-Pump Detector.

Профиль:
  - Плавный рост до пика: ≥10 дней, множитель ≥×10
  - Дамп: ≤30 часов, глубина ≥−90% от пика
  - Возраст дампа: ≤4 дней (иначе уходит в TAIKO)
  - Консолидация 0–4 дня, отскок не обязателен
"""
from __future__ import annotations
from dataclasses import dataclass
import requests

BINANCE_FAPI = "https://fapi.binance.com"

# Пороги
MIN_GROWTH_DAYS   = 10       # мин. длительность роста до пика
MIN_GROWTH_MULT   = 10.0     # мин. множитель роста ×10
MAX_DUMP_HOURS    = 30       # мин. быстрота дампа
MIN_DUMP_DROP     = -90.0    # мин. глубина дампа, %
MAX_AGE_DAYS      = 4        # свежесть сетапа


@dataclass
class DexeSignal:
    detected: bool = False
    score: int = 0
    peak_price: float = 0.0
    peak_hours_ago: int = 0
    growth_days: float = 0.0
    growth_mult: float = 0.0
    dump_hours: float = 0.0
    dump_pct: float = 0.0
    bottom_hours_ago: float = 0.0
    volume_climax_ratio: float = 0.0
    climax_label: str = ""          # "сильный откуп" / "умеренный" / "слабый"
    verdict: str = ""


def _get_klines(symbol: str, interval: str, limit: int = 500):
    try:
        r = requests.get(f"{BINANCE_FAPI}/fapi/v1/klines",
                         params={"symbol": symbol, "interval": interval, "limit": limit},
                         timeout=(8, 20))
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def detect_dexe(symbol: str) -> DexeSignal:
    # 1H даёт разрешение по часам для дампа и возрасту сетапа
    kl = _get_klines(symbol, "1h", 500)   # ~20 дней истории
    if not kl or len(kl) < 300:
        return DexeSignal()

    highs  = [float(k[2]) for k in kl]
    lows   = [float(k[3]) for k in kl]
    closes = [float(k[4]) for k in kl]
    price  = closes[-1]
    n = len(closes)

    # === 1. Пик за окно (исключаем последние 2 часа шума) ===
    search_end = n - 2
    if search_end < 100:
        return DexeSignal()
    peak = max(highs[:search_end])
    peak_idx = highs[:search_end].index(peak)
    peak_hours_ago = (n - 1 - peak_idx)
    if peak <= 0:
        return DexeSignal()

    # Пик должен быть достаточно свежим (в окне 20 дней должен вообще быть виден дамп)
    # и не позже чем ~5 дней назад — иначе это уже точно TAIKO
    if peak_hours_ago > (MAX_AGE_DAYS + 2) * 24:
        return DexeSignal()

    # === 2. Дно после пика ===
    post = lows[peak_idx:]
    bottom = min(post)
    bottom_offset = post.index(bottom)          # часов от пика до дна
    bottom_idx = peak_idx + bottom_offset
    bottom_hours_ago = n - 1 - bottom_idx
    dump_hours = bottom_offset

    if bottom <= 0:
        return DexeSignal()

    # === 3. Глубина дампа ===
    dump_pct = (bottom / peak - 1) * 100
    if dump_pct > MIN_DUMP_DROP:                # например −85% > −90% → отсекаем
        return DexeSignal()

    # === 4. Скорость дампа ===
    if dump_hours == 0 or dump_hours > MAX_DUMP_HOURS:
        return DexeSignal()

    # === 5. Возраст сетапа: с момента ДНА прошло не больше 4 дней ===
    if bottom_hours_ago > MAX_AGE_DAYS * 24:
        return DexeSignal()

    # === 6. Плавный длительный рост ДО пика ===
    # Нога роста = от минимального лоя в окне (макс. 500ч) до пика
    window_start = max(0, peak_idx - 500)
    seg = lows[window_start:peak_idx + 1]
    if not seg:
        return DexeSignal()

    growth_low = min(seg)
    if growth_low <= 0:
        return DexeSignal()

    growth_start_idx = window_start + seg.index(growth_low)
    growth_mult = peak / growth_low
    growth_hours = peak_idx - growth_start_idx
    growth_days = growth_hours / 24.0

    if growth_days < MIN_GROWTH_DAYS:
        return DexeSignal()
    if growth_mult < MIN_GROWTH_MULT:
        return DexeSignal()

    # === 7. Проверка «плавности» роста ===
    # За период роста не должно быть отдельного мини-обвала >50% и восстановления —
    # это отсекает случаи двух пампов подряд вместо одного плавного тренда.
    # Простая эвристика: макс. просадка на участке роста относительно достигнутого локального пика ≤ 50%.
    seg_highs = highs[growth_start_idx:peak_idx + 1]
    seg_lows  = lows[growth_start_idx:peak_idx + 1]
    max_drawdown_on_growth = 0.0
    running_max = seg_highs[0]
    for j in range(len(seg_highs)):
        running_max = max(running_max, seg_highs[j])
        if running_max > 0:
            dd = (seg_lows[j] / running_max - 1) * 100
            if dd < max_drawdown_on_growth:
                max_drawdown_on_growth = dd
    if max_drawdown_on_growth < -50:
        return DexeSignal()

    # === Volume Climax Ratio ===
    # Объём в окне ±1 свечи от дна vs средний объём 20 свечей до пампа
    vols = [float(k[7]) for k in kl]  # quote volume (USD) — сопоставимо с TAIKO
    lo = max(0, bottom_idx - 1)
    hi = min(len(vols), bottom_idx + 2)
    climax_vol = max(vols[lo:hi]) if hi > lo else 0.0

    pre_from = max(0, peak_idx - 20)
    pre_slice = vols[pre_from:peak_idx]
    avg_pre_vol = (sum(pre_slice) / len(pre_slice)) if pre_slice else 0.0

    if avg_pre_vol > 0:
        volume_climax_ratio = climax_vol / avg_pre_vol
    else:
        volume_climax_ratio = 0.0

    if volume_climax_ratio >= 15:
        climax_label = "сильный откуп (потенциал тренда)"
    elif volume_climax_ratio >= 5:
        climax_label = "умеренный откуп (скальп)"
    else:
        climax_label = "слабый откуп (риск мёртвого сетапа)"

    # === Скоринг ===
    score = 0
    # Глубина дампа: −90…−99% → 20..30
    score += int(min(30, max(0, (abs(dump_pct) - 90) * 3 + 20)))
    # Скорость дампа: чем быстрее, тем лучше
    score += int(max(0, 25 - (dump_hours - 1) * 0.8))
    # Множитель роста: ×10..×20+
    score += int(min(20, (growth_mult - 10) * 1.5 + 10))
    # Длительность роста: 10..20+ дней
    score += int(min(15, (growth_days - 10) * 1.5 + 8))
    # Свежесть сетапа: 0ч → +10, 96ч → 0
    score += int(max(0, 10 - bottom_hours_ago / 10))
    score = max(0, min(score, 100))

    detected = score >= 55

    verdict = ""
    if detected:
        verdict = (
            f"DEXE Post-Pump: рост ×{growth_mult:.1f} за {growth_days:.0f} дней → "
            f"дамп {dump_pct:.0f}% за {dump_hours:.0f}ч, "
            f"дно {bottom_hours_ago:.0f}ч назад. "
            f"Volume Climax: ×{volume_climax_ratio:.1f} — {climax_label}. "
            "Окно для входа на отскок открыто."
        )

    return DexeSignal(
        detected=detected,
        score=score,
        peak_price=peak,
        peak_hours_ago=peak_hours_ago,
        growth_days=growth_days,
        growth_mult=growth_mult,
        dump_hours=dump_hours,
        dump_pct=dump_pct,
        bottom_hours_ago=bottom_hours_ago,
        volume_climax_ratio=volume_climax_ratio,
        climax_label=climax_label,
        verdict=verdict,
    )
