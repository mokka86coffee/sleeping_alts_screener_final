"""Журнал решений (Р-14). Записывать не только монеты, но и себя.

Скринер записывает, что показал рынок; этот файл записывает, что
человек РЕШИЛ и почему. Без него через месяц BLESS выглядит как
«вошли и просели», и восстановить ход мысли нечем. Это единственный
способ отличить «стратегия не работает» от «отошёл от стратегии» —
а без этого различения любой разбор результатов бессмыслен.

Путь ручной, тот же, что уже работает дважды (unlocks.json, ручные
поля): файл правится руками, читается при сборке, сети ноль.

Формат decisions.json — список записей, новые в конец:

    [
      {
        "date": "2026-08-22",
        "symbol": "BLESSUSDT",
        "action": "вход",            // вход / пропуск / добор / выход
        "size": 1000,                 // размер, для входа и добора
        "saw": "что увидел",
        "lacked": "чего не хватало",
        "waited": "чего ждал"
      }
    ]

ПРОПУСК — ТАКОЕ ЖЕ РЕШЕНИЕ, КАК ВХОД, и записывается так же: без
записей о пропусках Р-16 («пропущенные против взятых») не посчитать.
Поле size у пропуска пустое.

Никакой валидации сверх формы намеренно: журнал пишется для себя, и
барьер на входе убьёт привычку быстрее, чем кривое поле — пользу.
"""

from __future__ import annotations

import json
from pathlib import Path

from core_config import BASE_DIR

# Рядом с остальными накопительными файлами проекта.
DECISIONS_PATH = BASE_DIR / "output" / "decisions.json"

ACTIONS = ("вход", "пропуск", "добор", "выход")


def load_decisions(path: Path = DECISIONS_PATH) -> list[dict]:
    """Все записи журнала решений, как лежат. Отсутствие файла — не ошибка:
    журнал начинается с первой записи, а не с установки."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [r for r in data if isinstance(r, dict) and r.get("symbol")]


def decisions_for(symbol: str, path: Path = DECISIONS_PATH) -> list[dict]:
    """Записи по одной монете, в порядке файла (то есть времени)."""
    sym = str(symbol or "").upper()
    return [r for r in load_decisions(path)
            if str(r.get("symbol", "")).upper() == sym]


def decisions_summary(path: Path = DECISIONS_PATH) -> dict:
    """Счёт по действиям — для строки на экране и для Р-16.

    Возвращает {"total": N, "by": {"вход": n, "пропуск": m, ...},
    "symbols": {...}}. Пустой журнал — нули, а не отсутствие ключей:
    строка «решений: 0» на экране сама напоминает писать.
    """
    recs = load_decisions(path)
    by: dict[str, int] = {a: 0 for a in ACTIONS}
    symbols: set[str] = set()
    for r in recs:
        a = str(r.get("action", "")).strip()
        if a in by:
            by[a] += 1
        symbols.add(str(r.get("symbol", "")).upper())
    return {"total": len(recs), "by": by, "symbols": sorted(symbols)}
