"""Токены дизайна и утилиты форматирования для рендера.

Единственное место, где живут цвета, размеры и правила подачи чисел.
Модули отрисовки не содержат литеральных цветов.
"""

from __future__ import annotations

import html
from typing import Any

# ─────────────────────────────────────────────────────────────
# Палитра нового дашборда
# ─────────────────────────────────────────────────────────────
AMBER = "#F5A623"
AMBER_LIGHT = "#FFD98A"
AMBER_DEEP = "#B87A18"

BLUE = "#3E9BE0"
GOLD = "#E0C060"
GREEN = "#93ff00"
# SPARKLE = "#00d4d9"
RUST = "#C4703A"
STEEL = "#8FA0B0"

BG = "#08080b"
GLASS_EDGE = "#C8DCE8"

# Цвет акцента по коду сигнала
SIGNAL_TONE = {
    "viral": AMBER,
    "taiko": GREEN,
    "dexe": GOLD,
    "surge": AMBER,
    "squeeze": RUST,
    "neutral": STEEL,
}

# Тон severity вето
VETO_TONE = {
    "high": RUST,
    "mid": GOLD,
    "low": STEEL,
}

# Тон режима рынка
REGIME_TONE = {
    "risk-on": GREEN,
    "neutral": GOLD,
    "risk-off": RUST,
    "unknown": STEEL,
}


# ─────────────────────────────────────────────────────────────
# Экранирование
# ─────────────────────────────────────────────────────────────
def esc(x: Any) -> str:
    """Экранирование для вставки в HTML и SVG."""
    return html.escape(str(x), quote=True)


# ─────────────────────────────────────────────────────────────
# Форматирование чисел
# ─────────────────────────────────────────────────────────────
def pct(v: float | None, digits: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v:+.{digits}f}%"


def num(v: float | None, digits: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:.{digits}f}"


def big(v: float | None) -> str:
    if v is None:
        return "—"
    if v >= 1e9:
        return f"${v/1e9:.2f}B"
    if v >= 1e6:
        return f"${v/1e6:.2f}M"
    if v >= 1e3:
        return f"${v/1e3:.1f}K"
    return f"${v:.0f}"


def sign_class(v: float | None) -> str:
    """Класс окраски по знаку."""
    if v is None or v == 0:
        return ""
    return "up" if v > 0 else "dn"


def tone_by_value(v: float | None) -> str:
    """Цвет по знаку значения, для инлайновых стилей SVG."""
    if v is None or v == 0:
        return STEEL
    return GREEN if v > 0 else RUST


# ─────────────────────────────────────────────────────────────
# Типографика тикера
# ─────────────────────────────────────────────────────────────
def ticker_font(symbol: str) -> tuple[str, str]:
    """Размер и трекинг тикера, чтобы длинные имена не ломали шапку."""
    n = len(symbol)
    if n <= 6:
        return "23px", "4px"
    if n <= 8:
        return "21px", "3px"
    if n <= 11:
        return "17px", "2px"
    if n <= 13:
        return "15px", "1.2px"
    return "12.5px", "0.8px"


# ─────────────────────────────────────────────────────────────
# Работа с метриками кандидата
# ─────────────────────────────────────────────────────────────
def metric_val(metrics: list[dict], key: str) -> str:
    for m in (metrics or []):
        if m.get("key") == key:
            return str(m.get("val", "—"))
    return "—"


def metric_cls(metrics: list[dict], key: str) -> str:
    for m in (metrics or []):
        if m.get("key") == key:
            return str(m.get("cls", ""))
    return ""


def metric_num(metrics: list[dict], key: str) -> float:
    """Число из форматированной строки метрики."""
    raw = metric_val(metrics, key)
    buf = ""
    for ch in raw:
        if ch.isdigit() or ch in "+-.":
            buf += ch
        elif buf:
            break
    try:
        return float(buf)
    except ValueError:
        return 0.0


# ─────────────────────────────────────────────────────────────
# Геометрия дуг
# ─────────────────────────────────────────────────────────────
def arc_dash(fill: float, radius: float = 42.0) -> tuple[float, float]:
    """Длина закрашенной дуги и полная окружность.

    Отделено от расчёта R:R сознательно: радиус задаёт тема,
    а не математика сделки.
    """
    from math import pi
    circumference = 2 * pi * radius
    return round(circumference * max(0.0, min(fill, 1.0)), 2), round(circumference, 2)
