"""
Volume Surge Detector — 1D.
Ищет монеты с аномальным всплеском дневного объёма относительно среднего.
Работает независимо от TAIKO/DEXE — ловит любую нестандартную активность:
всплеск может быть началом пампа, дампа, разворота или новостным событием.
"""
from __future__ import annotations
from dataclasses import dataclass
import requests

BINANCE_FAPI = "https://fapi.binance.com"

# Пороги
MIN_HISTORY_DAYS   = 40      # минимум истории для расчёта среднего
AVG_WINDOW_DAYS    = 30      # окно усреднения (как D Avg на индикаторе)
MIN_SURGE_RATIO    = 3.0     # минимальный множитель для попадания в отчёт (×3)
STRONG_SURGE_RATIO = 10.0    # порог "сильного" всплеска (×10 = 1000% как на скрине)


@dataclass
class VolumeSurgeSignal:
    detected: bool = False
    score: int = 0
    surge_ratio: float = 0.0            # во сколько раз текущий объём выше среднего
    current_vol_usd: float = 0.0        # объём текущей дневной свечи в USD
    avg_vol_usd: float = 0.0            # средний дневной объём в USD
    day_change_pct: float = 0.0         # изменение цены за текущий день, %
    is_green: bool = False              # текущая свеча зелёная?
    strength_label: str = ""            # "экстремальный" / "сильный" / "умеренный"
    verdict: str = ""


def _get_klines(symbol: str, interval: str = "1d", limit: int = 60) -> list[list] | None:
    try:
        r = requests.get(f"{BINANCE_FAPI}/fapi/v1/klines",
                         params={"symbol": symbol, "interval": interval, "limit": limit},
                         timeout=(8, 20))
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def detect_volume_surge(symbol: str) -> VolumeSurgeSignal:
    kl = _get_klines(symbol, "1d", 60)
    if not kl or len(kl) < MIN_HISTORY_DAYS:
        return VolumeSurgeSignal()

    opens  = [float(k[1]) for k in kl]
    closes = [float(k[4]) for k in kl]
    # quote volume в USD (индекс 7) — именно это показывает индикатор
    vols_usd = [float(k[7]) for k in kl]

    current_vol = vols_usd[-1]
    # среднее за AVG_WINDOW_DAYS дней ДО текущей свечи (исключая её саму)
    avg_slice = vols_usd[-(AVG_WINDOW_DAYS + 1):-1]
    if not avg_slice:
        return VolumeSurgeSignal()
    avg_vol = sum(avg_slice) / len(avg_slice)

    if avg_vol <= 0:
        return VolumeSurgeSignal()

    surge_ratio = current_vol / avg_vol

    if surge_ratio < MIN_SURGE_RATIO:
        return VolumeSurgeSignal(surge_ratio=surge_ratio,
                                 current_vol_usd=current_vol,
                                 avg_vol_usd=avg_vol)

    # Направление и сила движения на текущей свече
    day_change_pct = ((closes[-1] / opens[-1]) - 1) * 100 if opens[-1] > 0 else 0.0
    is_green = closes[-1] > opens[-1]

    # Классификация силы
    if surge_ratio >= 20:
        strength_label = "экстремальный"
    elif surge_ratio >= STRONG_SURGE_RATIO:
        strength_label = "сильный"
    else:
        strength_label = "умеренный"

    # Скоринг: базовый по множителю + бонусы за направление и амплитуду
    # ×3 → 40, ×10 → 70, ×20 → 90, ×50+ → 100
    score = 0
    if surge_ratio >= 3:
        score = int(min(40 + (surge_ratio - 3) * 3, 100))
    # бонус за большое движение цены (аномальный объём + большой ход = событие)
    if abs(day_change_pct) >= 15:
        score = min(score + 5, 100)
    score = max(0, min(score, 100))

    direction_word = "зелёная" if is_green else "красная"
    verdict = (
        f"Volume Surge ×{surge_ratio:.1f} ({strength_label}): "
        f"текущий дневной объём ${_fmt_usd(current_vol)} "
        f"vs средний ${_fmt_usd(avg_vol)} за {AVG_WINDOW_DAYS} дней. "
        f"Свеча {direction_word} {day_change_pct:+.1f}%. "
        "Аномальная активность — крупный игрок / новость / начало движения."
    )

    return VolumeSurgeSignal(
        detected=True,
        score=score,
        surge_ratio=surge_ratio,
        current_vol_usd=current_vol,
        avg_vol_usd=avg_vol,
        day_change_pct=day_change_pct,
        is_green=is_green,
        strength_label=strength_label,
        verdict=verdict,
    )


def _fmt_usd(v: float) -> str:
    if v >= 1e9: return f"{v/1e9:.2f}B"
    if v >= 1e6: return f"{v/1e6:.2f}M"
    if v >= 1e3: return f"{v/1e3:.1f}K"
    return f"{v:.0f}"
