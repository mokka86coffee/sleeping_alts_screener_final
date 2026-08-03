"""Норма объёма. Единственная реализация на проект.

Существует потому, что реализаций было две. metrics.vol_ratio и
flow_core.build_flow_stats считали одно и то же над одной ячейкой
кэша и расходились на два порядка: EUL показывала ×107 в колонке
отчёта и «тихо» в семействе — в одной карточке, в один момент.

Три правила. Нарушение любого даёт расхождение:
  · незакрытый бар достраивается по доле набранного времени;
  · норма строится ТОЛЬКО по закрытым барам;
  · нормы нет — возвращается None, а не отношение к пустоте.

Третье правило появилось после BANK и AKE с rel_volume порядка 110.
Величина читается как «объём вырос в сто раз», а означает «нормы
нет»: у свежего листинга окно нормы попадало в первые дни торгов,
где оборот на порядки ниже установившегося.
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

    quotes и fills — параллельные ряды. Последний элемент считается
    текущим баром и в норму не входит: включённый в собственную
    норму бар занижает свою же аномальность.

    min_norm — сколько закрытых баров обязано набраться. По умолчанию
    половина окна. Требовать полное окно значит терять свежие
    листинги, требовать один бар значит строить норму на шуме.
    """
    n = min(len(quotes), len(fills))
    if n < 2:
        return None

    cur_q = quotes[n - 1]
    cur_fill = fills[n - 1]
    if cur_q <= 0 or cur_fill <= 0 or cur_fill < min_fill:
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


def window_ratio(
    quotes: list[float],
    fills: list[float],
    window: int,
    norm_span: int,
) -> float:
    """Медиана окна к медиане более длинной нормы.

    Отдельная функция, а не параметр к volume_ratio, и это по смыслу.
    volume_ratio отвечает на вопрос «аномален ли текущий бар»,
    window_ratio — «шумный ли фон». Первое про событие, второе про
    режим; churn требует шумного фона, spring тихого, и расходятся
    они именно по второй величине.

    Нейтральная единица при отсутствии нормы — не признак и не
    аномалия, а честное «не знаю».
    """
    n = min(len(quotes), len(fills))
    if n < window * 2:
        return 1.0

    tail_q = [
        quotes[i] / max(fills[i], 1e-9)
        for i in range(n - window, n)
        if quotes[i] > 0
    ]
    if not tail_q:
        return 1.0

    lo = max(0, n - window - norm_span)
    norm = [
        quotes[i]
        for i in range(lo, n - window)
        if fills[i] >= 1.0 and quotes[i] > 0
    ]
    if len(norm) < window:
        return 1.0

    med_norm = median(norm)
    if med_norm <= 0:
        return 1.0

    return median(tail_q) / med_norm
