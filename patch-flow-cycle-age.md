# Давность вершины — в пейлоад и в вето

## файл: `detectors/flow.py`

Дельта к `patch-flow-cycle-done.md`. Применять после него,
`patch-core-peak-age.md` и `patch-config-cycle-age.md`.

### было

```python
            "peak_up_x": round(ctx.drop.peak_up_x, 2),
            "now_up_x": round(ctx.drop.now_up_x, 2),
```

### стало

```python
            "peak_up_x": round(ctx.drop.peak_up_x, 2),
            "now_up_x": round(ctx.drop.now_up_x, 2),
            # Сколько дней назад была вершина. Без этого числа
            # кратность к правилу не пригодна: ход, отданный год
            # назад, движением не завершается, а сменяется новым.
            # Журнал считает выбытие по той же тройке и обязан
            # видеть ту же давность, а не выводить свою.
            "peak_up_age": ctx.drop.peak_up_age,
```

### было

```python
    peak_x = float(ctx.drop.peak_up_x or 0.0)
    now_x = float(ctx.drop.now_up_x or 0.0)
    if cycle_done(now_x, peak_x):
```

### стало

```python
    peak_x = float(ctx.drop.peak_up_x or 0.0)
    now_x = float(ctx.drop.now_up_x or 0.0)
    peak_age = ctx.drop.peak_up_age
    if cycle_done(now_x, peak_x, peak_age if peak_age >= 0 else None):
```

### было

```python
        if max(peak_x, now_x) >= CYCLE_COMPLETE_X:
            reason = f"цикл отработан: вершина ×{max(peak_x, now_x):.1f} от базы"
        else:
            given = (1.0 - now_x / peak_x) * 100.0 if peak_x > 0 else 0.0
            reason = (f"ход отдан: вершина ×{peak_x:.1f}, "
                      f"сейчас ×{now_x:.1f}, отдано {given:.0f}%")
```

### стало

```python
        if max(peak_x, now_x) >= CYCLE_COMPLETE_X:
            reason = (f"цикл отработан: вершина ×{max(peak_x, now_x):.1f} "
                      f"от базы, {peak_age} дн назад")
        else:
            given = (1.0 - now_x / peak_x) * 100.0 if peak_x > 0 else 0.0
            reason = (f"ход отдан: вершина ×{peak_x:.1f} ({peak_age} дн назад), "
                      f"сейчас ×{now_x:.1f}, отдано {given:.0f}%")
```
