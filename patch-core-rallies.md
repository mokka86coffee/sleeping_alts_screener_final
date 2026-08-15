# Патч · ядро: разгоны от дна и признак первого

Пункт 2 порядка работ 22.7 — семантика «первого разгона». Три блока:
`flow_core.py` (замер), `flow_config.py` (порог), `flow.py` (в срез
контекста, туда же `descent`, который считается с 13 августа и наружу
не отдавался).

---

## Почему именно эта семантика

Три варианта обсуждались.

**По журналу** — «первый разгон» значит «монета впервые попала в
leaders.json». Отвергаю: окно журнала 14 дней, это свойство нашего
наблюдения, а не рынка. Монета, за которой мы не следили, окажется
«первой» по факту нашего невнимания.

**Булев признак «после дна роста ещё не было»** — ближе, но теряет
всё, кроме нуля. «Разгонов не было» и «был один, слабый» — разные
состояния, и второе стоит уметь отличать.

**Счёт разгонов** — выбран. `rallies` считает подъёмы от дна выше
порога, `max_rally_pct` даёт величину крупнейшего. Первый разгон это
`rallies == 0`, и то же число отвечает на вопрос из раздела 14: сколько
циклов монета уже отработала.

**Побочно это выносит в ядро правило, которое уже работает.**
`flow_dormant` требует, чтобы отскок был и вернулся, то есть по
построению исключает первый памп после долгого падения — самое
подтверждённое правило проекта (BICO, BMT, TUT, ACU). Сейчас оно живёт
внутри одного подкейса и как побочный эффект; после этого патча его
видят все.

---

# 1 · `detectors/flow_core.py` — поля и замер

### было

```python
    growth_x: float = 1.0
    bars_since_bottom: int = 0
```

### стало

```python
    growth_x: float = 1.0
    bars_since_bottom: int = 0

    # Сколько разгонов от дна монета уже отработала и какой был
    # крупнейшим.
    #
    # Разгон — подъём от дна выше RALLY_MIN_PCT с последующим
    # возвратом хотя бы наполовину. Требование возврата обязательно:
    # без него текущее незакрытое движение считалось бы отработанным
    # циклом, и признак «первый разгон» гас бы ровно тогда, когда он
    # нужен.
    rallies: int = 0
    max_rally_pct: float = 0.0
```

### было

```python
    @property
    def deep(self) -> bool:
        return self.drop_pct >= DROP_DISTRUST_PCT
```

### стало

```python
    @property
    def first_run(self) -> bool:
        """Текущее движение — первое после этого падения.

        Самое подтверждённое правило проекта: первый разгон после
        долгого падения — вынос, а не начало тренда (BICO, BMT, TUT,
        ACU). Правило до сих пор жило внутри flow_dormant побочным
        эффектом требования «отскок был и вернулся»; здесь оно
        становится величиной, которую видят все подкейсы.

        Ноль отработанных разгонов означает именно это: движения от
        дна ещё не было ни разу, значит идущее сейчас — первое.
        """
        return self.rallies == 0

    @property
    def deep(self) -> bool:
        return self.drop_pct >= DROP_DISTRUST_PCT
```

### было

```python
    # Минимум ДО пика — точка отсчёта роста. Без неё growth_x
    # мерил бы падение, а не подъём.
    before = tail[:peak_idx + 1]
    low_before = min((b.low for b in before if b.low > 0), default=0.0)
    growth = (peak / low_before) if low_before > 0 else 1.0

    return DropContext(
```

### стало

```python
    # Минимум ДО пика — точка отсчёта роста. Без неё growth_x
    # мерил бы падение, а не подъём.
    before = tail[:peak_idx + 1]
    low_before = min((b.low for b in before if b.low > 0), default=0.0)
    growth = (peak / low_before) if low_before > 0 else 1.0

    rallies, max_rally = _count_rallies(tail[bottom_idx:])

    return DropContext(
```

### было

```python
        growth_x=_clip(growth, 1.0, 1000.0),
    )
```

### стало

```python
        growth_x=_clip(growth, 1.0, 1000.0),
        rallies=rallies,
        max_rally_pct=max_rally,
    )


def _count_rallies(after: Sequence[Bar]) -> tuple[int, float]:
    """Сколько ОТРАБОТАННЫХ разгонов было после дна и какой крупнейший.

    Отработанный — поднялся выше RALLY_MIN_PCT от опоры и вернул
    хотя бы RALLY_RETRACE_MIN пройденного. Возврат в определении
    обязателен: без него текущее незакрытое движение засчиталось бы
    как цикл, и признак «первый разгон» гас бы ровно в тот момент,
    когда он нужен.

    Явный автомат из двух состояний, а не бегущие максимум с
    минимумом. Первая редакция считала одним проходом и на одном
    отскоке давала два разгона, на двух — девять: после засчитанного
    цикла максимум сохранялся, опора продолжала сползать, и из хвоста
    того же падения собирался фантомный следующий цикл.

    В поиске опора едет вниз за ценой — это ещё формирование дна.
    В разгоне опора зафиксирована, и считается отданная доля хода.
    """
    if len(after) < 4:
        return 0, 0.0

    lows = [b.low for b in after if b.low > 0]
    if not lows:
        return 0, 0.0

    base = lows[0]
    top = base
    in_rally = False
    count, best = 0, 0.0

    for b in after:
        if b.low <= 0 or b.high <= 0:
            continue
        if not in_rally:
            if b.low < base:
                base = b.low
            if base > 0 and (b.high - base) / base * 100.0 >= RALLY_MIN_PCT:
                in_rally = True
                top = b.high
            continue

        if b.high > top:
            top = b.high
        span = top - base
        if span <= 0:
            in_rally = False
            continue
        if (top - b.low) / span >= RALLY_RETRACE_MIN:
            count += 1
            best = max(best, span / base * 100.0)
            base = b.low
            top = base
            in_rally = False

    return count, best
```

---

# 2 · `detectors/flow_config.py` — пороги

### было

```python
DROP_FRESH_BARS = 15
```

### стало

```python
# ── Счёт разгонов от дна ──
# Подъём ниже RALLY_MIN_PCT — это шум базы, а не разгон. Значение
# взято по нижней границе наблюдённых отскоков (flow_dormant, замер
# 14 августа: 5.7…30%, медиана 15) и намеренно чуть ниже неё: здесь
# считается сам факт цикла, а не его качество.
RALLY_MIN_PCT = 12.0

# Какую долю пройденного надо отдать, чтобы разгон считался
# отработанным. Половина — не подобранное число, а граница смысла:
# вернуть меньше половины значит удержать большую часть хода, то есть
# движение продолжается и цикл не закрыт.
RALLY_RETRACE_MIN = 0.5

DROP_FRESH_BARS = 15
```

---

## Импорт констант · `detectors/flow_core.py`

### было

```python
    DROP_FRESH_BARS,
```

### стало

```python
    DROP_FRESH_BARS,
    RALLY_MIN_PCT,
    RALLY_RETRACE_MIN,
```

---

# 3 · `detectors/flow.py` — в срез контекста

`descent` считается в `FlowState` с 13 августа и наружу не отдавался
ни разу — разброса по рынку у него нет до сих пор.

### было

```python
            "growth_x": round(ctx.drop.growth_x, 2),
            "peak_age_days": ctx.drop.peak_age_days,
            "deep": ctx.drop.deep,
            "fresh": ctx.drop.fresh,
```

### стало

```python
            "growth_x": round(ctx.drop.growth_x, 2),
            "peak_age_days": ctx.drop.peak_age_days,
            "deep": ctx.drop.deep,
            "fresh": ctx.drop.fresh,
            # Отработанные разгоны от дна и признак первого. Правило
            # «первый разгон после долгого падения — вынос» до сих
            # пор нигде не было величиной.
            "rallies": ctx.drop.rallies,
            "max_rally_pct": round(ctx.drop.max_rally_pct, 1),
            "first_run": ctx.drop.first_run,
            # Характер спуска кумулятивной дельты: планомерный съезд
            # или обвал. Считается с 13 августа и наружу не выходил,
            # поэтому разброса по рынку у него нет.
            "descent": ctx.flow.descent,
```
