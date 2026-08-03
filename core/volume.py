"""Норма объёма. Единственная реализация на проект.

Существует потому, что реализаций было две: metrics.vol_ratio и
flow_core.build_flow_stats считали одно и то же над одной ячейкой
кэша и расходились на два порядка — EUL показывала ×107 в колонке
и «тихо» в семействе одновременно.

Три правила, нарушение любого даёт расхождение:
  · незакрытый бар достраивается по доле набранного времени;
  · норма строится ТОЛЬКО по закрытым барам;
  · нормы нет — возвращается None, а не отношение к пустоте.
"""

from __future__ import annotations


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def volume_ratio(
    quotes: list[float],
    fills: list[float],
    window: int,
    min_fill: float,
    min_norm: int | None = None,
) -> float | None:
    """Объём последнего бара к медиане нормы, кратностью.

    quotes/fills — параллельные ряды одной длины. Последний элемент
    считается текущим баром и в норму не входит.

    min_norm — сколько закрытых баров обязано набраться. По умолчанию
    половина окна: требовать полное окно значит терять свежие
    листинги, требовать один бар значит строить норму на шуме.
    """
    n = min(len(quotes), len(fills))
    if n < 2:
        return None

    cur_q = quotes[n - 1]
    cur_fill = fills[n - 1]
    if cur_q <= 0 or cur_fill < min_fill or cur_fill <= 0:
        return None

    lo = max(0, n - 1 - window)
    norm = [
        quotes[i]
        for i in range(lo, n - 1)
        if fills[i] >= 1.0 and quotes[i] > 0
    ]

    need = min_norm if min_norm is not None else max(2, window // 2)
    if len(norm) < need:
        return None

    med = median(norm)
    if med <= 0:
        return None

    return (cur_q / cur_fill) / med
