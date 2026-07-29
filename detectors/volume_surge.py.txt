"""Volume Surge Detector — 1D.

Ищет монеты с аномальным всплеском дневного объёма относительно среднего.
Работает независимо от TAIKO и DEXE: всплеск может быть началом пампа,
дампа, разворота или реакцией на новость.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from datetime import datetime, timezone

from core.binance import K_QUOTE_VOLUME, K_OPEN, K_CLOSE, klines_1d, series

# ── Пороги ──
MIN_HISTORY_DAYS = 40       # минимум истории для расчёта среднего
AVG_WINDOW_DAYS = 30        # окно усреднения
MIN_SURGE_RATIO = 3.0       # минимальный множитель для попадания в отчёт
STRONG_SURGE_RATIO = 10.0   # порог сильного всплеска
EXTREME_SURGE_RATIO = 20.0  # порог экстремального
BIG_MOVE_PCT = 15.0         # ход цены, дающий бонус к скору

# Ниже этой доли суток нормировка не применяется: в первые часы
# случайная крупная сделка даёт бессмысленно раздутый темп
MIN_DAY_FRACTION = 0.15


@dataclass
class VolumeSurgeSignal:
    detected: bool = False
    score: int = 0
    surge_ratio: float = 0.0        # во сколько раз объём выше среднего
    current_vol_usd: float = 0.0    # объём текущей дневной свечи в USD
    projected_vol_usd: float = 0.0  # ??
    avg_vol_usd: float = 0.0        # средний дневной объём в USD
    day_change_pct: float = 0.0     # изменение цены за текущий день
    is_green: bool = False          # текущая свеча зелёная
    strength_label: str = ""        # экстремальный | сильный | умеренный
    verdict: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _fmt_usd(v: float) -> str:
    if v >= 1e9:
        return f"{v/1e9:.2f}B"
    if v >= 1e6:
        return f"{v/1e6:.2f}M"
    if v >= 1e3:
        return f"{v/1e3:.1f}K"
    return f"{v:.0f}"

def _day_fraction() -> float:
    """Какая доля текущих UTC-суток уже прошла."""
    now = datetime.now(timezone.utc)
    seconds = now.hour * 3600 + now.minute * 60 + now.second
    return max(seconds / 86400, 1e-6)


def detect_volume_surge(symbol: str) -> VolumeSurgeSignal:
    """Всплеск дневного объёма против среднего за 30 дней.

    Даже при недоборе порога возвращает объект с заполненным surge_ratio —
    это нужно воронке отбора, чтобы показать, насколько монета не дотянула.
    """
    kl = klines_1d(symbol)
    if not kl or len(kl) < MIN_HISTORY_DAYS:
        return VolumeSurgeSignal()

    # Берём только нужный хвост: среднее плюс текущая свеча
    tail = AVG_WINDOW_DAYS + 1
    vols_usd = series(kl, K_QUOTE_VOLUME, tail=tail)
    opens = series(kl, K_OPEN, tail=tail)
    closes = series(kl, K_CLOSE, tail=tail)

    if len(vols_usd) < 2:
        return VolumeSurgeSignal()

    raw_vol = vols_usd[-1]

    # Текущая дневная свеча ещё не закрыта: сравнивать её сырой объём
    # со средним за полные сутки некорректно — утром любой всплеск
    # выглядит слабым. Приводим к ожидаемому объёму на конец дня.
    fraction = _day_fraction()
    if fraction >= MIN_DAY_FRACTION:
        current_vol = raw_vol / fraction
        projected = True
    else:
        current_vol = raw_vol
        projected = False

    # Среднее за окно ДО текущей свечи, сама она исключена
    avg_slice = vols_usd[:-1]
    if not avg_slice:
        return VolumeSurgeSignal()

    avg_vol = sum(avg_slice) / len(avg_slice)
    if avg_vol <= 0:
        return VolumeSurgeSignal()

    surge_ratio = current_vol / avg_vol

    if surge_ratio < MIN_SURGE_RATIO:
        return VolumeSurgeSignal(
            surge_ratio=surge_ratio,
            current_vol_usd=raw_vol,
            projected_vol_usd=current_vol if projected else 0.0,
            avg_vol_usd=avg_vol,
        )

    # Направление и сила движения на текущей свече
    day_change_pct = 0.0
    if opens and opens[-1] > 0:
        day_change_pct = ((closes[-1] / opens[-1]) - 1) * 100
    is_green = closes[-1] > opens[-1] if opens else False

    if surge_ratio >= EXTREME_SURGE_RATIO:
        strength_label = "экстремальный"
    elif surge_ratio >= STRONG_SURGE_RATIO:
        strength_label = "сильный"
    else:
        strength_label = "умеренный"

    # Скоринг: база по множителю, бонус за амплитуду хода
    # ×3 → 40, ×10 → 61, ×20 → 91, ×50+ → 100
    score = int(min(40 + (surge_ratio - MIN_SURGE_RATIO) * 3, 100))
    if abs(day_change_pct) >= BIG_MOVE_PCT:
        score = min(score + 5, 100)
    score = max(0, min(score, 100))

    direction_word = "зелёная" if is_green else "красная"
    verdict = (
        f"Volume Surge ×{surge_ratio:.1f} ({strength_label}): "
        f"текущий дневной объём ${_fmt_usd(current_vol)} "
        f"против среднего ${_fmt_usd(avg_vol)} за {AVG_WINDOW_DAYS} дней. "
        f"Свеча {direction_word} {day_change_pct:+.1f}%. "
        "Аномальная активность: крупный игрок, новость или начало движения."
    )

    return VolumeSurgeSignal(
        detected=True,
        score=score,
        surge_ratio=surge_ratio,
        current_vol_usd=raw_vol,
        projected_vol_usd=current_vol if projected else 0.0,
        avg_vol_usd=avg_vol,
        day_change_pct=day_change_pct,
        is_green=is_green,
        strength_label=strength_label,
        verdict=verdict,
    )
