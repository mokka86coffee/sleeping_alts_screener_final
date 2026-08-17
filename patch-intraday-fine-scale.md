# Мелкая шкала: окна во времени и срез последних часов

## файл: `analytics/intraday.py`

Три правки. Первая — окна, заданные в барах, переводятся в бары по
шкале: на пятнадцатиминутке 168 баров это 42 часа, а не неделя, и
величина молча меняла смысл вместе со шкалой. Вторая — новая функция
`shakeout`: крупные заявки за последние часы вместе с тем, что в это
время делала цена. Третья — ступени лестницы подписываются от базовой
шкалы, иначе при базе 15 минут ступень ×2 подписывалась бы как «2h».

Применять вместе с целыми файлами `core/binance.py` и
`analytics/metrics.py` — без них `scan` останется на часовой шкале и
новые окна ничего не изменят.

### было

```python
# Сколько последних баров отдаём с позициями — столько же, сколько
# рисует карточка.
BIG_TAIL_BARS = 48
```

### стало

```python
# Сколько последних баров отдаём с позициями — столько же, сколько
# рисует карточка.
BIG_TAIL_BARS = 48

# Норма размера сделки во ВРЕМЕНИ, а не в барах.
#
# BIG_NORM_BARS задана числом баров и на часах означает неделю. На
# пятнадцатиминутках те же 168 баров это 42 часа, то есть норма молча
# меняет смысл вместе со шкалой, и «крупная заявка» считается от
# другой базы. Величины с разных шкал после этого несравнимы, хотя
# называются одинаково. Поэтому шкала переводится в бары здесь, а
# BIG_NORM_BARS остаётся значением по умолчанию для часового вызова.
BIG_NORM_HOURS = 168

# Окно «что было только что». Четыре часа — столько, сколько человек
# держит в голове между обновлениями сайта; сутки уже отвечает фон.
SHAKE_HOURS = 4
```

### было

```python
def big_trades(klines: list[list]) -> dict:
```

### стало

```python
def big_trades(klines: list[list], norm_bars: int = BIG_NORM_BARS,
               tail_bars: int = BIG_TAIL_BARS) -> dict:
```

### было

```python
    Позиции отдаются относительно ХВОСТА в BIG_TAIL_BARS баров — в
    том же виде, в каком их ждёт карточка, чтобы не пересчитывать
    индексы на стороне отрисовки.
    """
```

### стало

```python
    Позиции отдаются относительно ХВОСТА в tail_bars баров — в том же
    виде, в каком их ждёт карточка, чтобы не пересчитывать индексы на
    стороне отрисовки.

    norm_bars и tail_bars — параметры, а не константы, потому что оба
    выражают ВРЕМЯ, а не количество. Вызывающий, знающий шкалу,
    переводит часы в бары сам; значения по умолчанию описывают
    часовую шкалу, на которой модуль писался.
    """
```

### было

```python
    norm_src = [s for s in sizes[-BIG_NORM_BARS:] if s > 0]
    if len(norm_src) < 20:
        return {}
    norm = median(norm_src)
    if norm <= 0:
        return {}

    tail_from = max(0, len(sizes) - BIG_TAIL_BARS)
```

### стало

```python
    norm_src = [s for s in sizes[-norm_bars:] if s > 0]
    if len(norm_src) < 20:
        return {}
    norm = median(norm_src)
    if norm <= 0:
        return {}

    tail_from = max(0, len(sizes) - tail_bars)
```

### было

```python
        return {"count": 0, "max_x": round(max(sizes[-BIG_TAIL_BARS:] or [0]) / norm, 1)}
```

### стало

```python
        return {"count": 0, "max_x": round(max(sizes[-tail_bars:] or [0]) / norm, 1)}
```

### было

```python
def pressure(klines: list[list], window: int = PRESSURE_WINDOW) -> dict:
```

### стало

```python
def shakeout(klines: list[list], minutes: int = 60,
             hours: float = SHAKE_HOURS,
             norm_bars: int = BIG_NORM_BARS) -> dict:
    """Крупные заявки за последние часы и что в это время делала цена.

    Что это. Срез последнего окна по двум величинам сразу: крупные
    заявки со сторонами и поведение цены на тех же барах.

    Почему вместе, а не двумя числами. Крупные покупки на растущих
    барах — это догоняющие, они не говорят ничего. Те же покупки при
    цене, которая стоит или сползает, означают, что кто-то набирает,
    пока не двигают. Разница вся в цене, поэтому разносить эти две
    величины по разным местам панели нельзя: по отдельности каждая
    бессмысленна.

    Ход меряется в ATR, а не в процентах: «стоит» у монеты с ATR 12%
    и у монеты с ATR 1.5% — разные проценты и одно и то же число в
    ATR. Порога здесь нет намеренно, наружу отдаётся величина; где
    проходит «стоит», решает читатель.

    low_break отвечает на отдельный вопрос: удержали ли покупки низ
    окна. Сравнивается с таким же предыдущим окном — не с историей,
    потому что вопрос про сейчас.

    Окно задаётся в ЧАСАХ и переводится в бары по шкале: четыре часа
    это четыре бара на часовике и шестнадцать на пятнадцатиминутке.
    """
    if minutes <= 0 or hours <= 0:
        return {}
    bars = max(2, round(hours * 60 / minutes))
    if len(klines) < bars * 2 + 1:
        return {}

    big = big_trades(klines, norm_bars=norm_bars, tail_bars=bars)

    opens = _col(klines, K_OPEN)
    closes = _col(klines, K_CLOSE)
    lows = [l for l in _col(klines, K_LOW)[-bars:] if l > 0]
    prev_lows = [l for l in _col(klines, K_LOW)[-bars * 2:-bars] if l > 0]

    start = opens[-bars] if opens[-bars] > 0 else closes[-bars]
    last = closes[-1]
    move_pct = ((last / start) - 1) * 100 if start > 0 else 0.0

    trs = true_ranges(
        _col(klines, K_HIGH), _col(klines, K_LOW), closes)
    atr = sum(trs[-ATR_PERIOD:]) / ATR_PERIOD if len(trs) >= ATR_PERIOD else 0.0
    move_atr = abs(last - start) / atr if atr > 0 else None

    out = {
        "hours": hours,
        "bars": bars,
        "buys": int(big.get("buys") or 0),
        "sells": int(big.get("sells") or 0),
        "max_x": big.get("max_x") or 0,
        "move_pct": round(move_pct, 2),
    }
    if move_atr is not None:
        out["move_atr"] = round(move_atr, 2)
    if lows and prev_lows:
        out["low_break"] = min(lows) < min(prev_lows)
    return out


def pressure(klines: list[list], window: int = PRESSURE_WINDOW) -> dict:
```

### было

```python
def background(klines: list[list], window: int = 24) -> float | None:
```

### стало

```python
def background(klines: list[list], window: int = 24,
               norm_bars: int = BIG_NORM_BARS) -> float | None:
```

### было

```python
    if len(quotes) < BIG_NORM_BARS // 2:
        return None
    norm = median(quotes[-BIG_NORM_BARS:])
```

### стало

```python
    if len(quotes) < norm_bars // 2:
        return None
    norm = median(quotes[-norm_bars:])
```

### было

```python
def prominence(klines: list[list]) -> dict:
```

### стало

```python
def prominence(klines: list[list], norm_bars: int = BIG_NORM_BARS,
               tail_bars: int = BIG_TAIL_BARS) -> dict:
```

### было

```python
    norm_src = [s for s in sizes[-BIG_NORM_BARS:] if s > 0]
    if len(norm_src) < PROM_MIN_BARS:
```

### стало

```python
    norm_src = [s for s in sizes[-norm_bars:] if s > 0]
    if len(norm_src) < PROM_MIN_BARS:
```

### было

```python
    tail = [s for s in sizes[-BIG_TAIL_BARS:] if s > 0]
    if not tail:
        return {}
    max_x = max(tail) / norm
```

### стало

```python
    tail = [s for s in sizes[-tail_bars:] if s > 0]
    if not tail:
        return {}
    max_x = max(tail) / norm
```

### было

```python
        "trades_med": round(median([t for t in trades[-BIG_NORM_BARS:] if t > 0] or [0]), 1),
```

### стало

```python
        "trades_med": round(median([t for t in trades[-norm_bars:] if t > 0] or [0]), 1),
```

### было

```python
def ladder(klines: list[list], scales: tuple = LADDER_SCALES) -> dict:
```

### стало

```python
def _scale_label(minutes: int) -> str:
    """Подпись шкалы по числу минут в баре.

    Нужна лестнице: ступени задаются множителем к базовой шкале, а не
    в часах. При базе 15 минут ступень ×2 это получасовка, и подпись
    «2h» была бы прямой ложью в данных.
    """
    if minutes < 60:
        return f"{minutes}m"
    if minutes % 60 == 0:
        return f"{minutes // 60}h"
    return f"{minutes}m"


def ladder(klines: list[list], scales: tuple = LADDER_SCALES,
           base_minutes: int = 60) -> dict:
```

### было

```python
        steps.append({
            "scale": f"{n}h",
```

### стало

```python
        steps.append({
            "scale": _scale_label(n * base_minutes),
```

### было

```python
    out: dict = {"scale": scale, "bars": len(klines)}
    big = big_trades(klines)
    if big:
        out["big"] = big
    pres = pressure(klines)
```

### стало

```python
    # Окна, выраженные во ВРЕМЕНИ, переводятся в бары по шкале. Норма
    # размера сделки, «сутки фона» и диапазон заданы в часах и на
    # пятнадцатиминутке дали бы 42 часа, 6 часов и двое суток вместо
    # недели, суток и недели. Неразобранная подпись оставляет
    # значения по умолчанию — часовые, на которых модуль писался.
    minutes = _scale_minutes(scale)
    if minutes > 0:
        per_hour = 60 / minutes
        norm_bars = max(PROM_MIN_BARS, round(BIG_NORM_HOURS * per_hour))
        day_bars = max(2, round(24 * per_hour))
        range_bars = max(2, round(RANGE_BARS * per_hour))
    else:
        norm_bars, day_bars, range_bars = BIG_NORM_BARS, 24, RANGE_BARS

    out: dict = {"scale": scale, "bars": len(klines)}
    big = big_trades(klines, norm_bars=norm_bars)
    if big:
        out["big"] = big
    shake = shakeout(klines, minutes=minutes or 60, norm_bars=norm_bars)
    if shake:
        out["shake"] = shake
    pres = pressure(klines)
```

### было

```python
    pos = range_pos(klines)
    if pos is not None:
        out["range_pos"] = pos
    bg = background(klines)
    if bg is not None:
        out["bg"] = bg
    prom = prominence(klines)
```

### стало

```python
    pos = range_pos(klines, bars=range_bars)
    if pos is not None:
        out["range_pos"] = pos
    bg = background(klines, window=day_bars, norm_bars=norm_bars)
    if bg is not None:
        out["bg"] = bg
    prom = prominence(klines, norm_bars=norm_bars)
```

### было

```python
    lad = ladder(klines)
```

### стало

```python
    lad = ladder(klines, base_minutes=minutes or 60)
```
