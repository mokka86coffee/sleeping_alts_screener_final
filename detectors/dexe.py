"""DEXE Post-Pump Detector.

Профиль паттерна:
  - плавный рост до пика: не меньше 10 дней, множитель от ×10
  - дамп: не дольше 30 часов, глубина от −90% от пика
  - возраст дампа: не больше 4 дней, иначе сетап уходит в TAIKO
  - консолидация 0–4 дня, отскок не обязателен
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from core.binance import (
    K_HIGH, K_LOW, K_CLOSE, K_QUOTE_VOLUME,
    klines_1h, series,
)

# ── Пороги ──
MIN_HISTORY_HOURS = 300     # минимум часовых свечей
MIN_GROWTH_DAYS = 10.0      # минимальная длительность роста до пика
MIN_GROWTH_MULT = 10.0      # минимальный множитель роста
MAX_DUMP_HOURS = 30         # максимальная длительность дампа
MIN_DUMP_DROP = -90.0       # минимальная глубина дампа, %
MAX_AGE_DAYS = 4            # свежесть сетапа от дна
MAX_GROWTH_DRAWDOWN = -50.0 # глубже — это два пампа, а не один тренд
GROWTH_WINDOW_HOURS = 700   # окно поиска начала ноги роста
PEAK_NOISE_BARS = 2         # хвост, исключаемый из поиска пика

CLIMAX_STRONG = 15.0
CLIMAX_MODERATE = 5.0
DETECT_SCORE = 55


@dataclass
class DexeSignal:
    detected: bool = False
    score: int = 0
    peak_price: float = 0.0
    peak_hours_ago: int = 0
    bottom_price: float = 0.0
    growth_days: float = 0.0
    growth_mult: float = 0.0
    dump_hours: float = 0.0
    dump_pct: float = 0.0
    bottom_hours_ago: float = 0.0
    volume_climax_ratio: float = 0.0
    climax_label: str = ""
    verdict: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _last_index_of(values: list[float], target: float) -> int:
    """Последнее вхождение значения.

    Если цена коснулась пика дважды, брать первое вхождение неверно:
    дамп искусственно удлиняется на весь промежуток между касаниями.
    """
    for i in range(len(values) - 1, -1, -1):
        if values[i] == target:
            return i
    return 0


def detect_dexe(symbol: str) -> DexeSignal:
    """Разбирает часовой график в поисках post-pump капитуляции."""
    kl = klines_1h(symbol)
    if not kl or len(kl) < MIN_HISTORY_HOURS:
        return DexeSignal()

    highs = series(kl, K_HIGH)
    lows = series(kl, K_LOW)
    closes = series(kl, K_CLOSE)
    vols = series(kl, K_QUOTE_VOLUME)

    n = len(closes)

    # ── 1. Пик за окно, последние часы исключены как шум ──
    search_end = n - PEAK_NOISE_BARS
    if search_end < 100:
        return DexeSignal()

    head = highs[:search_end]
    peak = max(head)
    if peak <= 0:
        return DexeSignal()

    peak_idx = _last_index_of(head, peak)
    peak_hours_ago = n - 1 - peak_idx

    # Пик не должен быть слишком старым, иначе это уже область TAIKO
    if peak_hours_ago > (MAX_AGE_DAYS + 2) * 24:
        return DexeSignal()

    # ── 2. Дно после пика ──
    post = lows[peak_idx:]
    if not post:
        return DexeSignal()

    bottom = min(post)
    if bottom <= 0:
        return DexeSignal()

    bottom_offset = post.index(bottom)      # часов от пика до дна
    bottom_idx = peak_idx + bottom_offset
    bottom_hours_ago = n - 1 - bottom_idx
    dump_hours = float(bottom_offset)

    # ── 3. Глубина дампа ──
    dump_pct = (bottom / peak - 1) * 100
    if dump_pct > MIN_DUMP_DROP:
        return DexeSignal()

    # ── 4. Скорость дампа ──
    if dump_hours <= 0 or dump_hours > MAX_DUMP_HOURS:
        return DexeSignal()

    # ── 5. Возраст сетапа: с момента дна прошло не больше MAX_AGE_DAYS ──
    if bottom_hours_ago > MAX_AGE_DAYS * 24:
        return DexeSignal()

    # ── 6. Плавный длительный рост до пика ──
    window_start = max(0, peak_idx - GROWTH_WINDOW_HOURS)
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

    # ── 7. Проверка плавности роста ──
    # На участке роста не должно быть отдельного обвала глубже 50%
    # с последующим восстановлением: это два пампа подряд, а не тренд.
    seg_highs = highs[growth_start_idx:peak_idx + 1]
    seg_lows = lows[growth_start_idx:peak_idx + 1]
    max_drawdown = 0.0
    running_max = seg_highs[0] if seg_highs else 0.0
    for j in range(len(seg_highs)):
        running_max = max(running_max, seg_highs[j])
        if running_max > 0:
            dd = (seg_lows[j] / running_max - 1) * 100
            max_drawdown = min(max_drawdown, dd)
    if max_drawdown < MAX_GROWTH_DRAWDOWN:
        return DexeSignal()

    # ── Volume Climax Ratio ──
    # Объём в окне вокруг дна против среднего до начала пампа
    lo = max(0, bottom_idx - 1)
    hi = min(len(vols), bottom_idx + 2)
    climax_vol = max(vols[lo:hi]) if hi > lo else 0.0

    pre_from = max(0, peak_idx - 20)
    pre_slice = vols[pre_from:peak_idx]
    avg_pre_vol = sum(pre_slice) / len(pre_slice) if pre_slice else 0.0

    volume_climax_ratio = climax_vol / avg_pre_vol if avg_pre_vol > 0 else 0.0

    if volume_climax_ratio >= CLIMAX_STRONG:
        climax_label = "сильный откуп, потенциал тренда"
    elif volume_climax_ratio >= CLIMAX_MODERATE:
        climax_label = "умеренный откуп, скальп"
    else:
        climax_label = "слабый откуп, риск мёртвого сетапа"

    # ── Скоринг ──
    score = 0
    # Глубина дампа: −90…−99% даёт 20..47
    score += int(min(30, max(0, (abs(dump_pct) - 90) * 3 + 20)))
    # Скорость дампа: чем быстрее, тем выше
    score += int(max(0, 25 - (dump_hours - 1) * 0.8))
    # Множитель роста: ×10 даёт 10, ×20 даёт 25, потолок 20
    score += int(min(20, (growth_mult - 10) * 1.5 + 10))
    # Длительность роста: 10 дней даёт 8, 15 дней даёт 15
    score += int(min(15, (growth_days - 10) * 1.5 + 8))
    # Свежесть: сразу после дна +10, через 96 часов 0
    score += int(max(0, 10 - bottom_hours_ago / 10))
    score = max(0, min(score, 100))

    detected = score >= DETECT_SCORE

    verdict = ""
    if detected:
        verdict = (
            f"DEXE Post-Pump: рост ×{growth_mult:.1f} за {growth_days:.0f} дней, "
            f"затем дамп {dump_pct:.0f}% за {dump_hours:.0f}ч, "
            f"дно {bottom_hours_ago:.0f}ч назад. "
            f"Volume Climax ×{volume_climax_ratio:.1f} — {climax_label}. "
            "Окно для входа на отскок открыто."
        )

    return DexeSignal(
        detected=detected,
        score=score,
        peak_price=peak,
        peak_hours_ago=peak_hours_ago,
        bottom_price=bottom,
        growth_days=growth_days,
        growth_mult=growth_mult,
        dump_hours=dump_hours,
        dump_pct=dump_pct,
        bottom_hours_ago=bottom_hours_ago,
        volume_climax_ratio=volume_climax_ratio,
        climax_label=climax_label,
        verdict=verdict,
    )
