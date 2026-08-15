# Слой «жизнь контракта» в DropContext — пик за окном перестаёт быть слепым

## файл: `detectors/flow_core.py`


HEMI-вопрос: при пике старше BOTTOM_LOOKBACK_DAYS окно даёт
growth_x ≈ 1, и «цикла не было» — при том что цикл был. Окно не
расширяется (оно общее для всех подкейсов, а growth_x читает fuel в
значении «свежая кратность»); жизнь контракта идёт отдельным слоем.

### было

```python
    # Во сколько раз цена выросла до пика от предшествующего
    # минимума. Нужна fuel: свежая кратность означает толпу,
    # застрявшую выше карты зон.
    growth_x: float = 1.0
    bars_since_bottom: int = 0
```

### стало

```python
    # Во сколько раз цена выросла до пика от предшествующего
    # минимума. Нужна fuel: свежая кратность означает толпу,
    # застрявшую выше карты зон.
    growth_x: float = 1.0
    bars_since_bottom: int = 0

    # ── Слой «жизнь контракта» ──
    # Кратность роста до пика ЖИЗНИ и падение от него к текущему дну.
    # Зачем отдельно: окно выше ограничено BOTTOM_LOOKBACK_DAYS, и у
    # монеты с листинговым пиком за окном growth_x ≈ 1 — «цикла не
    # было», хотя цикл был (HEMI). Расширять окно нельзя: оно общее
    # для всех подкейсов, а growth_x читает fuel в значении «СВЕЖАЯ
    # кратность = толпа застряла выше карты зон» — пик двухлетней
    # давности застрявшей толпы не означает. Жизнь — отдельный слой,
    # оконные величины он не трогает.
    # 0.0 означает «не мерили» (недельного ряда не было) и отличимо
    # от измеренной единицы.
    life_growth_x: float = 0.0
    life_drop_pct: float = 0.0
```

### было

```python
def build_drop(bars: Sequence[Bar]) -> DropContext:
    tail = bars[-BOTTOM_LOOKBACK_DAYS:] if len(bars) > BOTTOM_LOOKBACK_DAYS else bars
    if len(tail) < 5:
        return DropContext()
```

### стало

```python
def build_drop(bars: Sequence[Bar],
               life_peak: float = 0.0, life_low: float = 0.0) -> DropContext:
    """Контекст падения по окну плюс слой «жизнь контракта».

    life_peak / life_low приходят из недельного ряда (_life_span в
    flow.py) и заполняют life_growth_x / life_drop_pct. Нули —
    честное «жизни не видели»: слой остаётся пустым, оконные
    величины считаются как раньше.
    """
    tail = bars[-BOTTOM_LOOKBACK_DAYS:] if len(bars) > BOTTOM_LOOKBACK_DAYS else bars
    if len(tail) < 5:
        return DropContext()
```

### было

```python
    rallies, max_rally, hold = _count_rallies(tail[bottom_idx:])

    return DropContext(
        peak_price=peak,
        peak_idx=peak_idx,
        bottom_price=bottom,
        bottom_idx=bottom_idx,
        drop_pct=_clip(drop, 0.0, 1.0),
        bars_since_bottom=len(tail) - 1 - bottom_idx,
        _peak_age=len(tail) - 1 - peak_idx,
        growth_x=_clip(growth, 1.0, 1000.0),
        rallies=rallies,
        max_rally_pct=max_rally,
        hold_pct=hold,
    )
```

### стало

```python
    rallies, max_rally, hold = _count_rallies(tail[bottom_idx:])

    # Слой жизни. Падение меряется от пика жизни к ТЕКУЩЕМУ дну окна:
    # вопрос будущего гейта — «монета выросла и обвалилась», и дно у
    # него то же, у которого цена стоит сейчас.
    life_growth = (life_peak / life_low) if life_peak > 0 and life_low > 0 else 0.0
    life_drop = ((life_peak - bottom) / life_peak) if life_peak > 0 and bottom > 0 else 0.0

    return DropContext(
        peak_price=peak,
        peak_idx=peak_idx,
        bottom_price=bottom,
        bottom_idx=bottom_idx,
        drop_pct=_clip(drop, 0.0, 1.0),
        bars_since_bottom=len(tail) - 1 - bottom_idx,
        _peak_age=len(tail) - 1 - peak_idx,
        growth_x=_clip(growth, 1.0, 1000.0),
        rallies=rallies,
        max_rally_pct=max_rally,
        hold_pct=hold,
        life_growth_x=_clip(life_growth, 0.0, 1000.0),
        life_drop_pct=_clip(life_drop, 0.0, 1.0),
    )
```

### было

```python
def build_context(symbol: str, raw_bars: Sequence[Bar]) -> FlowContext | None:
```

### стало

```python
def build_context(symbol: str, raw_bars: Sequence[Bar],
                  life_peak: float = 0.0, life_low: float = 0.0) -> FlowContext | None:
```

### было

```python
    zones = build_zones(all_events, bars)
    drop = build_drop(bars)
```

### стало

```python
    zones = build_zones(all_events, bars)
    drop = build_drop(bars, life_peak=life_peak, life_low=life_low)
```
