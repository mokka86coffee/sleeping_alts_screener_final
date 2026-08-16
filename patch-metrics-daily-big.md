# Дневные крупные заявки

## файл: `analytics/metrics.py`

Применять ПОСЛЕ `patch-metrics-intraday.md`.

Выход по красному пузырю на пампе смотрит дневной масштаб, а
`_big_trades` в проекте живёт внутри dormant и наружу не выходит.
Модуль `intraday` шкалы не знает по построению — ему можно дать
дневные свечи, они здесь уже загружены.

Отдельный ключ, а не второй вызов `scan`: из всего набора величин на
дневках нужны только заявки, а вортекс и скорость на этом масштабе
уже считает семейство, и второй расчёт разошёлся бы с первым.

### было

```python
from analytics.intraday import scan as intraday_scan
```

### стало

```python
from analytics.intraday import big_trades as intraday_big
from analytics.intraday import scan as intraday_scan
```

### было

```python
    intraday = intraday_scan(kl_1h, "1h") if kl_1h else {}
```

### стало

```python
    intraday = intraday_scan(kl_1h, "1h") if kl_1h else {}

    # Крупные заявки на ДНЕВНОМ масштабе: по ним журнал закрывает
    # позицию, увидев продажу на пампе. Норма и хвост здесь те же
    # 168 и 48 баров, но это уже дни, а не часы, — то есть норма за
    # полгода и метки за полтора месяца. tail отдаётся наружу, чтобы
    # читатель знал, от какого хвоста отсчитаны позиции, и не
    # угадывал длину.
    daily_big = intraday_big(kl_1d) if kl_1d else {}
    if daily_big:
        daily_big["tail"] = 48
```

### было

```python
        "intraday": intraday,
```

### стало

```python
        "intraday": intraday,
        "daily_big": daily_big,
```
