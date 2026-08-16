# Плотность попаданий по дням

## файл: `analytics/leaders.py`

Применять ПОСЛЕ `patch-leaders-cycle-age.md`.

`hits` считает лидерство за всю жизнь записи, и «десять попаданий за
десять дней» неотличимо от «десять за сегодня». Первое — стабильность,
второе — монета горит прямо сейчас. HEMI и ACU попадали в топ не
меньше восьми раз за сутки при часовых прогонах, и это нигде не
оставляло следа.

Считается по СРАБАТЫВАНИЮ семейства, а не по лидерству. Лидер один на
прогон; восемь попаданий у двух монет одновременно бывают только при
широком условии — том же, что продлевает жизнь записи.

Карта, а не счётчик: семь суток вместо одного числа отвечают ещё и на
«растёт ли плотность день ко дню», а это интереснее самого значения.

### было

```python
            if bool((getattr(c, "flow", None) or {}).get("detected")) \
                    or _is_anomalous(ratios):
                rec["last_hit"] = now.isoformat()
```

### стало

```python
            if bool((getattr(c, "flow", None) or {}).get("detected")) \
                    or _is_anomalous(ratios):
                rec["last_hit"] = now.isoformat()
                _touch_density(rec, now)
```

### было

```python
def _days_since(stamp: str | None, now: datetime) -> float:
```

### стало

```python
# Сколько суток держим в карте плотности. Семи хватает, чтобы
# увидеть разгон, и мало, чтобы карта не росла в записи бесконечно.
DENSITY_DAYS = 7


def _touch_density(rec: dict, now: datetime) -> None:
    """Отмечает попадание в карте по дням и подрезает хвост.

    Ключ — календарная дата в UTC, а не «сутки назад»: при часовых
    прогонах скользящее окно давало бы разное число в зависимости от
    момента замера, и сравнивать дни между собой стало бы нельзя.

    Подрезка на каждом попадании, а не отдельной уборкой: карта
    маленькая, а забытая уборка означала бы запись, растущую весь
    срок жизни монеты.
    """
    day = now.date().isoformat()
    src = rec.get("hits_by_day")
    if not isinstance(src, dict):
        src = {}

    try:
        src[day] = int(src.get(day) or 0) + 1
    except (TypeError, ValueError):
        src[day] = 1

    cutoff = (now.date() - timedelta(days=DENSITY_DAYS - 1)).isoformat()
    rec["hits_by_day"] = {
        k: v for k, v in src.items() if isinstance(k, str) and k >= cutoff
    }


def _days_since(stamp: str | None, now: datetime) -> float:
```
