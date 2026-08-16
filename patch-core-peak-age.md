# Давность вершины хода

## файл: `detectors/flow_core.py`

Дельта к `patch-core-peak-up-x.md`. Применять после него.

Вершина без давности к правилу завершения не пригодна: ход, отданный
год назад, — это не отработанное движение, а начало нового. Монета
успела построить базу заново, и старый пик к ней отношения не имеет.

Индекс максимума уже находится внутри того же прохода, остаётся его
не выбросить.

### было

```python
    lows_w = [(i, b.low) for i, b in enumerate(tail) if b.low > 0]
    if lows_w:
        low_i, low_w = min(lows_w, key=lambda p: p[1])
        highs_after = [b.high for b in tail[low_i:] if b.high > 0]
        peak_after = max(highs_after) if highs_after else 0.0
        last_close = tail[-1].close
        peak_up = peak_after / low_w if low_w > 0 and peak_after > 0 else 0.0
        now_up = last_close / low_w if low_w > 0 and last_close > 0 else 0.0
    else:
        peak_up = now_up = 0.0
```

### стало

```python
    lows_w = [(i, b.low) for i, b in enumerate(tail) if b.low > 0]
    peak_age = -1
    if lows_w:
        low_i, low_w = min(lows_w, key=lambda p: p[1])
        highs_after = [(i, b.high) for i, b in enumerate(tail[low_i:], low_i)
                       if b.high > 0]
        if highs_after:
            peak_i, peak_after = max(highs_after, key=lambda p: p[1])
            # Баров от вершины до правого края. База дневная, значит
            # это дни.
            peak_age = len(tail) - 1 - peak_i
        else:
            peak_after = 0.0
        last_close = tail[-1].close
        peak_up = peak_after / low_w if low_w > 0 and peak_after > 0 else 0.0
        now_up = last_close / low_w if low_w > 0 and last_close > 0 else 0.0
    else:
        peak_up = now_up = 0.0
```

### было

```python
        peak_up_x=_clip(peak_up, 0.0, 10000.0),
        now_up_x=_clip(now_up, 0.0, 10000.0),
```

### стало

```python
        peak_up_x=_clip(peak_up, 0.0, 10000.0),
        now_up_x=_clip(now_up, 0.0, 10000.0),
        peak_up_age=peak_age,
```

### было

```python
    peak_up_x: float = 0.0
    now_up_x: float = 0.0
```

### стало

```python
    peak_up_x: float = 0.0
    now_up_x: float = 0.0

    # Сколько баров назад была та вершина. База дневная — это дни.
    #
    # Без давности вершина к правилу завершения не пригодна: ход,
    # отданный год назад, движением не завершается, а сменяется
    # новым — монета за это время построила базу заново. По пробе
    # 16 августа пик окна старше шестидесяти дней у 45 монет из 61,
    # медиана 104 дня: без отсечки по сроку правило судило бы рынок
    # по позапрошлому циклу.
    #
    # −1 означает «не мерили» и отличимо от нуля: ноль — это вершина
    # сегодня, законное значение.
    peak_up_age: int = -1
```
