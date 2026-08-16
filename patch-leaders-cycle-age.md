# Журнал: давность вершины, отказ от max_price, ручные записи не трогаем

## файл: `analytics/leaders.py`

Дельта к `patch-leaders-cycle-done.md`. Применять после него,
`patch-core-peak-age.md` и `patch-config-cycle-age.md`.

Три правки, и первые две связаны.

**Вершина больше не выводится из `max_price`.** У величины,
восстановленной из журнальной цены, нет и не может быть давности:
`max_price` помнит уровень, но не помнит, когда он был. А правило
теперь требует срок. Кроме того, поле пачкается: у PROM в записи
лежит 12.28 при входе 2.08 и `max_change_pct` 23% — числа
противоречат друг другу, за период записи монета ходила от 2 до 3.
Из этого мусора выводилась вершина ×13.7, и PROM выбывал по откату.
Вершина теперь только из пейлоада, где она посчитана по свечам, с
соблюдением порядка «сначала дно, потом максимум после него», и с
известным индексом.

**Давность хранится рядом с вершиной** и стареет между прогонами:
пик, записанный неделю назад, сегодня на неделю старше. Иначе запись
вечно считала бы вершину свежей.

**Ручные записи не выбывают.** Флаг `added_manually` ставится при
добавлении монеты руками и до сих пор не читался нигде: чистка
сносила её наравне с остальными. Монету добавляют руками именно
потому, что хотят за ней следить, — правило выбытия к ней
неприменимо. Срок бездействия на такие записи тоже не действует.

### было

```python
def _cycle_peak_x(c: Candidate) -> tuple[float, float]:
```

### стало

```python
def _cycle_peak_age(c: Candidate) -> float | None:
    """Давность вершины хода в днях из пейлоада FLOW.

    None означает «не знаем, когда»: у монеты без срабатывания
    семейства пейлоада нет, а −1 из ядра значит то же самое.
    Восстановить давность из истории записи нельзя — max_price
    помнит уровень, но не помнит дату, — поэтому запасного пути
    здесь нет и быть не может.
    """
    flow = getattr(c, "flow", None) or {}
    drop = (flow.get("context") or {}).get("drop") or {}
    try:
        age = float(drop.get("peak_up_age"))
    except (TypeError, ValueError):
        return None
    return age if age >= 0 else None


def _cycle_peak_x(c: Candidate) -> tuple[float, float]:
```

### было

```python
    peak = max(float(rec.get("max_up_x") or 0.0), float(peak_x or 0.0), now)

    price = float(rec.get("price") or 0.0)
    peak_price = float(rec.get("max_price") or 0.0)
    # _touch_price вызывается раньше в том же проходе, обе цены здесь
    # уже свежие. Ноль означает «не мерили» — остаёмся на том, что есть.
    if price > 0 and peak_price > price and now > 0:
        peak = max(peak, peak_price * now / price)

    rec["max_up_x"] = round(peak, 2)
    rec["trend_done"] = peak >= CYCLE_TREND_DONE_X
```

### стало

```python
    # Вершина только из пейлоада или из ранее записанной.
    #
    # Вывод из max_price убран намеренно. У такой величины нет
    # давности — цена помнит уровень, но не помнит дату, — а правило
    # завершения без срока не работает. Плюс поле пачкается: у PROM
    # там лежало 12.28 при входе 2.08, и вершина выходила ×13.7 на
    # монете, которая за всю жизнь записи ходила от 2 до 3.
    prev_peak = float(rec.get("max_up_x") or 0.0)
    peak = max(prev_peak, float(peak_x or 0.0), now)

    # Давность стареет вместе с записью: пик, записанный неделю
    # назад, сегодня на неделю старше. Свежая давность из пейлоада
    # принимается только вместе со своей вершиной — иначе к старому
    # пику приписался бы новый возраст.
    if peak_x and peak_x >= prev_peak and peak_age is not None:
        rec["peak_up_age"] = round(float(peak_age), 1)
    elif "peak_up_age" in rec and bars_passed > 0:
        rec["peak_up_age"] = round(float(rec["peak_up_age"]) + bars_passed, 1)

    rec["max_up_x"] = round(peak, 2)
    rec["trend_done"] = peak >= CYCLE_TREND_DONE_X
```

### было

```python
def _touch_cycle(rec: dict, up_x: float, peak_x: float = 0.0,
                 now_x: float = 0.0) -> None:
```

### стало

```python
def _touch_cycle(rec: dict, up_x: float, peak_x: float = 0.0,
                 now_x: float = 0.0, peak_age: float | None = None,
                 bars_passed: float = 0.0) -> None:
```

### было

```python
            peak_x, now_x = _cycle_peak_x(c)
            _touch_cycle(rec, _cycle_up_x(c), peak_x, now_x)
```

### стало

```python
            peak_x, now_x = _cycle_peak_x(c)
            # Сколько дней прошло с прошлого прогона — на столько же
            # постарела записанная вершина.
            passed = _days_since(rec.get("last_seen"), now)
            _touch_cycle(rec, _cycle_up_x(c), peak_x, now_x,
                         _cycle_peak_age(c), passed)
```

### было

```python
    kept: dict[str, dict] = {}
    for symbol, rec in store.items():
        now_x = float(rec.get("now_up_x") or rec.get("up_x") or 0.0)
        peak_x = float(rec.get("max_up_x") or 0.0)
        if cycle_done(now_x, peak_x):
```

### стало

```python
    kept: dict[str, dict] = {}
    for symbol, rec in store.items():
        # Добавленную руками монету не трогаем ни одним правилом.
        # Её добавили именно затем, чтобы следить, и решать за
        # человека, что наблюдение окончено, нечем.
        if rec.get("added_manually"):
            kept[symbol] = rec
            continue

        now_x = float(rec.get("now_up_x") or rec.get("up_x") or 0.0)
        peak_x = float(rec.get("max_up_x") or 0.0)
        peak_age = rec.get("peak_up_age")
        if cycle_done(now_x, peak_x, peak_age):
```

### было

```python
def _touch_price(rec: dict, price: float, now: datetime) -> None:
```

### стало

```python
def _days_since(stamp: str | None, now: datetime) -> float:
    """Сколько дней прошло с отметки. Ноль, если отметки нет.

    Ноль здесь безопасен: он означает «не старим», то есть вершина
    остаётся той же свежести. Ошибка в эту сторону монету сохраняет.
    """
    if not stamp:
        return 0.0
    try:
        when = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return 0.0
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (now - when).total_seconds() / 86400.0)


def _touch_price(rec: dict, price: float, now: datetime) -> None:
```
