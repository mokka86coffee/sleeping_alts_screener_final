"""Гейт стейблкоинов (Р-20). Вышел ли капитал из обороны.

Резервуарный контур Р-1 — самый медленный из трёх, живёт месяцами и
единственный отвечает на вопрос альтсезона. Механизм назван прямо:
альтсезон не начнётся, пока доля стейблов не сжимается — деньгам,
которым предстоит поднять альты, сначала надо выйти из доллара.
Это единственная величина, которая ОБЪЯСНЯЕТ, почему журнал лежит,
а не констатирует.

Из наших свечей не выводится — первый пункт, где тест «ноль
запросов» провален осознанно. Цена принятия: ОДНО число раз в
неделю, руками, тем же путём, что unlocks.json и decisions.json.

Формат reservoir.json — список записей, новые в конец:

    [
      {"date": "2026-08-15", "stables_pct": 12.2, "btc_dom_pct": 60.84}
    ]

stables_pct — доля стейблкоинов в капитализации топ-20 (или другого
фиксированного среза — главное, ОДНОГО И ТОГО ЖЕ: смена среза ломает
сравнимость ряда, и тогда честнее начать новый файл).
btc_dom_pct — доминация биткоина, по желанию: она дублируется в
market["dom"] из сети, но здесь остаётся история.

Пересмотр по понедельникам, минута работы. Записи не правятся и не
удаляются — ряд и есть ценность.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from core_config import BASE_DIR

# КОРЕНЬ, не output/ — ручной файл, та же ошибка пути, что у
# календаря (см. заметку в analytics_calendar, найдено 23.08).
RESERVOIR_PATH = BASE_DIR / "reservoir.json"

# Старше этого запись считается протухшей: контур живёт месяцами, но
# показывать июньскую долю как «текущую» в сентябре — враньё тоном
# свежести. Протухшая запись печатается с возрастом, не прячется.
RESERVOIR_STALE_DAYS = 14


def load_reservoir(path: Path = RESERVOIR_PATH) -> list[dict]:
    """Все записи как лежат. Отсутствие файла — не ошибка: гейт
    начинается с первой записи."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [r for r in data
            if isinstance(r, dict) and r.get("stables_pct") is not None]


def reservoir_state(path: Path = RESERVOIR_PATH, today: date | None = None) -> dict:
    """Состояние резервуара для строки разрешения.

    Возвращает known/note в контракте составляющих market_permission
    плюс сами числа. warn всегда False: гейт не предупреждает — он
    объясняет. Закрытый резервуар не риск сегодняшнего входа, а
    причина, по которой журнал лежит месяцами; смешение этих двух
    смыслов в одном флаге и было бы ошибкой чтения.

    Ход считается к предыдущей записи: направление здесь важнее
    уровня — «12.2 и сжимается» и «12.2 и растёт» это разные рынки.
    """
    recs = load_reservoir(path)
    if not recs:
        return {"known": False, "warn": False,
                "note": "резервуар: файла нет (Р-20, одно число в неделю)"}

    last = recs[-1]
    share = float(last.get("stables_pct") or 0.0)
    prev = float(recs[-2].get("stables_pct") or 0.0) if len(recs) > 1 else None

    age_days = None
    try:
        d = datetime.strptime(str(last.get("date", "")), "%Y-%m-%d").date()
        age_days = ((today or date.today()) - d).days
    except ValueError:
        pass

    note = f"стейблы {share:.1f}% капы"
    if prev is not None:
        step = share - prev
        arrow = "сжимаются" if step < 0 else ("растут" if step > 0 else "стоят")
        note += f" · {arrow} ({step:+.1f} п.п.)"
    if last.get("btc_dom_pct") is not None:
        note += f" · btc.d {float(last['btc_dom_pct']):.1f}%"
    if age_days is not None and age_days > RESERVOIR_STALE_DAYS:
        note += f" · запись {age_days} дн назад"

    return {"known": True, "warn": False, "share": round(share, 1),
            "prev": (round(prev, 1) if prev is not None else None),
            "ageDays": age_days, "note": note}
