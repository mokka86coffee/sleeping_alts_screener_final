# Патч · `run.py` — журнал не ломает `--limit`

Ставится поверх `patch-run-journal.md`. Четыре блока, все в `run.py`.

**Заменяет прежнюю версию этого файла целиком.** В той был потолок на
добавку и константа `JOURNAL_EXTRA_SHARE` в конфиге — ни то, ни другое
больше не нужно. Если прежняя версия уже применена, скажи, соберу
откат.

Причина: 120 монет добавки были корзиной аномалий, а она в выборку не
просится вовсе — `_orbit_stars` читает только `leaders.json`, звёздами
аномалии не становятся. Чинится в `tracked_symbols` (файл `leaders.py`
целиком), и после этого добавка возвращается к единицам монет, ради
которых всё и затевалось. Потолок над ней был бы вреден: усечение
выкинет из выборки ровно ту звезду, которую надо наблюдать.

Остаётся одна настоящая правка — `--limit`.

---

## 1. Флаг вместо угадывания

### было

```python
def select_symbols(limit: int = MAX_SYMBOLS) -> tuple[list[tuple[str, float]], dict]:
    """Отбирает USDT-перпы по обороту.

    Возвращает список пар (символ, оборот) и статистику отсева
    для первого узла воронки.
    """
```

### стало

```python
def select_symbols(
    limit: int = MAX_SYMBOLS,
    with_journal: bool = True,
) -> tuple[list[tuple[str, float]], dict]:
    """Отбирает USDT-перпы по обороту.

    Возвращает список пар (символ, оборот) и статистику отсева
    для первого узла воронки.

    with_journal управляет добавкой монет журнала сверх лимита.
    Отдельным флагом, а не сравнением limit с MAX_SYMBOLS внутри:
    сравнение угадывало бы намерение вызывающего, а решает его он.
    """
```

---

## 2. Добавка только на полном прогоне

### было

```python
    have = {s for s, _ in picked}
    extra = [
        (s, vol_seen.get(s, 0.0))
        for s in sorted(tracked_symbols())
        if s not in have and s.endswith("USDT")
    ]
    if extra:
        picked.extend(extra)
        log(f"  → отбор: +{len(extra)} из журнала сверх лимита")
```

### стало

```python
    have = {s for s, _ in picked}
    extra: list[tuple[str, float]] = []
    if with_journal:
        extra = [
            (s, vol_seen.get(s, 0.0))
            for s in sorted(tracked_symbols())
            if s not in have and s.endswith("USDT")
        ]
    if extra:
        picked.extend(extra)
        log(f"  → отбор: +{len(extra)} из журнала сверх лимита")
```

---

## 3. Отладочный прогон обходится без журнала

### было

```python
        symbols, select_stats = select_symbols(args.limit)
```

### стало

```python
        # Журнал добавляется только на полном прогоне. Явный --limit
        # в докстроке файла описан как «только N монет, для отладки»,
        # то есть означает «столько и ни одной больше» — добавка
        # сверх него превращала прогон на одной монете в сотню.
        symbols, select_stats = select_symbols(
            args.limit, with_journal=(args.limit >= MAX_SYMBOLS),
        )
```

---

## 4. Счётчик добавки в статистику

### было

```python
    stats["selected"] = len(picked)
    stats["from_journal"] = len(extra)

    return picked, stats
```

### стало

```python
    stats["selected"] = len(picked)
    # Сколько монет пришло из журнала сверх лимита. Отдельным числом:
    # в «отобрано N» они неотличимы от прошедших по обороту, и рост
    # выборки выглядел бы как оживление рынка.
    stats["from_journal"] = len(extra)

    return picked, stats
```
