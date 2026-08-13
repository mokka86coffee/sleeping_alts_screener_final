# Патч · `detectors/flow.py`

Файл 572 строки, поэтому патчем. Три блока, все в разных местах.

---

## 1. Причины отказа на втором возврате

`rejects=rejects` доехал только до раннего выхода «нет результатов».
Второй возврат — тот, которым пользуются все сработавшие монеты, — его
не получил, и в срезе 13 августа 57 монет из 157 остались без причин.

### было

```python
        context=ctx_dict,
        failures=failures,
    )
```

### стало

```python
        context=ctx_dict,
        failures=failures,
        rejects=rejects,
    )
```

Якорь отличается от раннего выхода отступом: там поля на двенадцати
пробелах, здесь на восьми.

---

## 2. Поток: `collapsing`, `delta_slope`, `buy_share`

### было

```python
        "flow": {
            "slope": round(ctx.flow.slope, 4),
            "homogeneity": round(ctx.flow.homogeneity, 3),
            "net": round(ctx.flow.net, 2),
            "accumulating": ctx.flow.accumulating,
            "distributing": ctx.flow.distributing,
        },
```

### стало

```python
        "flow": {
            "slope": round(ctx.flow.slope, 4),
            "homogeneity": round(ctx.flow.homogeneity, 3),
            "net": round(ctx.flow.net, 2),
            "accumulating": ctx.flow.accumulating,
            "distributing": ctx.flow.distributing,
            # Наклон дельты и вывод из него.
            #
            # Обе величины вместе намеренно: collapsing — это
            # delta_slope, сравнённый с DELTA_COLLAPSE_SLOPE, и по
            # булеву не видно, монета далеко за порогом или стоит на
            # нём. Пока поля не было, разброс приходилось собирать из
            # текстов причин отказа — а они есть только у тех, кто
            # отказал, то есть выборка обрезана сверху.
            "delta_slope": round(ctx.flow.delta_slope, 5),
            "collapsing": ctx.flow.collapsing,
            "buy_share": round(ctx.flow.buy_share, 4),
        },
```

---

## 3. Падение: поля для признака «первый разгон»

### было

```python
        "drop": {
            "drop_pct": round(ctx.drop.drop_pct * 100, 1),
            "bars_since_bottom": ctx.drop.bars_since_bottom,
            "distrust_zones": ctx.drop.distrust_zones,
        },
```

### стало

```python
        "drop": {
            "drop_pct": round(ctx.drop.drop_pct * 100, 1),
            "bars_since_bottom": ctx.drop.bars_since_bottom,
            "distrust_zones": ctx.drop.distrust_zones,
            # growth_x и peak_age_days читает fuel, наружу не отдавал
            # никто. Окно DropContext — 240 дней против 14 у журнала
            # лидеров, и признак «первый разгон после ЭТОГО падения»
            # выводится отсюда. Формула не выбрана, разброс нужен
            # раньше выбора.
            "growth_x": round(ctx.drop.growth_x, 2),
            "peak_age_days": ctx.drop.peak_age_days,
            "deep": ctx.drop.deep,
            "fresh": ctx.drop.fresh,
        },
```
