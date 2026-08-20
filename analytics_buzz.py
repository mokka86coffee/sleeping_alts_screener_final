"""Оценка внимания рынка и детектор вирусного разгона."""

from __future__ import annotations

from core_config import (
    MEME_TICKER_HINTS, OBV_ACCUMULATION,
    RVOL_COOL, RVOL_HOT, RVOL_WARM,
    SECTOR_MAP, VIRAL_SECTOR_KEYWORDS,
)

VIRAL_MOVE_PCT = 20.0   # ход дня, при котором сурж считается спекулятивным


def build_buzz(m: dict) -> dict:
    """Уровень внимания по объёму и характеру накопления.

    Пока это прокси через рыночные данные, а не реальные соцсети:
    резкий объём с накоплением почти всегда означает, что о монете говорят.
    """
    rvol_1h = m.get("rvol_1h") or 0.0
    obv_slope = m.get("obv_slope") or 0.0

    if rvol_1h >= RVOL_HOT and obv_slope > OBV_ACCUMULATION:
        return {
            "level": "hot",
            "level_class": "buzz-hot",
            "level_text": "HOT",
            "text": "Резкий всплеск объёма и активное накопление. Внимание рынка на паре.",
        }
    if rvol_1h >= RVOL_WARM:
        return {
            "level": "warm",
            "level_class": "buzz-warm",
            "level_text": "WARM",
            "text": "Объём выше среднего, интерес растёт.",
        }
    if rvol_1h >= RVOL_COOL:
        return {
            "level": "cool",
            "level_class": "buzz-cool",
            "level_text": "COOL",
            "text": "Умеренная активность.",
        }
    return {
        "level": "cold",
        "level_class": "buzz-cold",
        "level_text": "COLD",
        "text": "Низкий уровень внимания.",
    }


def in_speculative_sector(symbol: str, categories: list[str]) -> bool:
    """Относится ли монета к секторам, где живёт спекуляция."""
    haystack = " " + " ".join(c.lower() for c in categories) + " "
    if any(kw in haystack for kw in VIRAL_SECTOR_KEYWORDS):
        return True

    # Фолбэк: мемное имя в самом тикере, когда категорий нет
    sym_upper = symbol.upper()
    return any(hint in sym_upper for hint in MEME_TICKER_HINTS)


def detect_viral(buzz: dict, surge, symbol: str, categories: list[str]) -> tuple[bool, str]:
    """Вирусный разгон: внимание плюс объём плюс спекулятивный контекст.

    Возвращает пару (сработало, подпись).
    """
    twitter_hot = buzz.get("level") == "hot"
    has_surge = bool(surge and surge.detected)
    if not (twitter_hot and has_surge):
        return False, ""

    speculative = in_speculative_sector(symbol, categories)

    # Даже вне спекулятивного сектора большой ход на суржe читается так же
    behaves_speculative = (
        surge.is_green and surge.day_change_pct >= VIRAL_MOVE_PCT
    )

    if speculative:
        return True, "VIRAL HYPE"
    if behaves_speculative:
        return True, "VIRAL PUMP"
    return False, ""


def resolve_sector(categories: list[str]) -> str:
    """Сводит разнородные категории к одному крупному сектору."""
    if not categories:
        return "OTHER"
    haystack = " ".join(c.lower() for c in categories)
    for sector, keywords in SECTOR_MAP.items():
        if any(kw in haystack for kw in keywords):
            return sector
    return "OTHER"
