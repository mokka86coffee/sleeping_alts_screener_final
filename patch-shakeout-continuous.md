# Встряска: непрерывная величина вместо порога, норма — сутки

Прежняя редакция считала бар крупным при среднем размере сделки втрое
выше недельной нормы. На BLESS 18 августа это дало ноль при плотном
ряде пузырей на графике: максимум был ×1.6 на пятнадцатиминутке и
×1.3 на часе. Причина не в пороге — средний размер сделки по
определению не видит одиночную заявку, и опустить границу до полутора
нельзя, там начинается обычный разброс.

Поэтому наружу теперь идёт непрерывная величина вместе с собственным
разбросом окна, а норма считается по суткам без последнего окна, а не
по неделе: монета уже в журнале, вопрос «проснулась ли она» решён, и
сравнивать надо с тем, как шло сегодня.

Что отдаётся: `size_x` — крупнейшая сделка окна к суточной норме,
`size_p90` — обычный для этих суток разброс, `buy_pp` — на сколько
процентных пунктов сместилась доля покупок против суток, `buy_share`,
`move_pct`, `move_atr`, `low_break`.

Проверено на трёх сценариях: откуп на сползании даёт `size_x 1.61` при
`size_p90 1.21` и перекос +12 п.п.; тихое окно — `size_x 0.98` ниже
своего же разброса; короткий ряд — пустой словарь, а не нули.

## файл: `analytics/intraday.py`

### было

```python
# Окно «что было только что». Четыре часа — столько, сколько человек
# держит в голове между обновлениями сайта; сутки уже отвечает фон.
SHAKE_HOURS = 4

# Нейтральная полоса по стороне.
```

### стало

```python
# Окно «что было только что». Четыре часа — столько, сколько человек
# держит в голове между обновлениями сайта; сутки уже отвечает фон.
SHAKE_HOURS = 4

# Норма для этого окна — СУТКИ, а не неделя.
#
# Недельная норма отвечает на вопрос «эта монета вообще проснулась»,
# и он уже решён: в журнал попадают те, у кого семейство сработало.
# Дальше нужен другой вопрос — «что изменилось за последние часы
# против того, как шло весь день», и на него неделя отвечать не
# может: за семь дней в норму попадает и сам всплеск, ради которого
# монета в журнале, и он же эту норму задирает.
SHAKE_NORM_HOURS = 24

# Меньше этого числа ненулевых баров медиана суток уже не медиана.
SHAKE_MIN_NORM = 12

# Нейтральная полоса по стороне.
```

### было

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
```

### стало

```python
def shakeout(klines: list[list], minutes: int = 60,
             hours: float = SHAKE_HOURS,
             norm_hours: float = SHAKE_NORM_HOURS) -> dict:
    """Что происходило за последние часы против того, как шли сутки.

    Что это. Четыре величины по одному окну: насколько крупнее
    обычного шли сделки, на чью сторону сместился поток, куда ушла
    цена и удержался ли низ.

    Почему без порога «крупной заявки». Прежняя редакция считала бар
    крупным при среднем размере сделки втрое выше нормы и на BLESS
    18 августа дала ноль: максимум был 1.6 при плотном ряде пузырей
    на графике. Причина не в пороге, а в самой величине — средний
    размер сделки по определению не видит одиночку. Одна заявка на
    полсотни тысяч среди двух тысяч обычных поднимает среднее на
    проценты. Поэтому наружу отдаётся НЕПРЕРЫВНАЯ величина вместе с
    собственным разбросом окна (size_p90), а решение, много это или
    мало, принимает читатель. Выдуманная граница здесь означала бы
    молчание там, где событие есть.

    Почему норма суточная. Монета уже в журнале, тренд подтверждён —
    вопрос «проснулась ли она» решён неделей назад. Остался вопрос
    «что изменилось сегодня», и сравнивать его надо с сегодняшним же
    фоном.

    Ход меряется в ATR, а не в процентах: «стоит» у монеты с ATR 12%
    и у монеты с ATR 1.5% — разные проценты и одно число в ATR.

    low_break отвечает отдельно: удержали покупки низ окна или цена
    ушла ниже предыдущего такого же. Не история, а именно сейчас.

    Окна задаются в ЧАСАХ и переводятся в бары по шкале: четыре часа
    это четыре бара на часовике и шестнадцать на пятнадцатиминутке.
    """
    if minutes <= 0 or hours <= 0 or norm_hours <= 0:
        return {}
    bars = max(2, round(hours * 60 / minutes))
    norm_bars = max(bars * 2, round(norm_hours * 60 / minutes))
    if len(klines) < bars * 2 + 1:
        return {}

    quotes = _col(klines, K_QUOTE_VOLUME)
    trades = _col(klines, K_TRADES)
    buys = _col(klines, K_TAKER_BUY_QUOTE)
    closes = _col(klines, K_CLOSE)
    opens = _col(klines, K_OPEN)

    sizes = [
        (q / t) if t > 0 and q > 0 else 0.0
        for q, t in zip(quotes, trades)
    ]
    # Норма считается по суткам БЕЗ последнего окна. Иначе событие
    # входит в собственную норму и само себя гасит: шестнадцать баров
    # из девяноста шести тянут и медиану, и девяностый процентиль в
    # свою сторону, а сравнивать надо с тем, как шло ДО.
    norm_src = [s for s in sizes[-norm_bars:-bars] if s > 0]
    if len(norm_src) < SHAKE_MIN_NORM:
        return {}
    norm = median(norm_src)
    if norm <= 0:
        return {}

    ordered = sorted(norm_src)
    p90 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.9))] / norm

    tail_sizes = [s for s in sizes[-bars:] if s > 0]
    size_x = (max(tail_sizes) / norm) if tail_sizes else 0.0

    # Сторона окна целиком, а не по барам: на сползании отдельный бар
    # почти всегда продавцовый, и подсчёт «сколько баров куплено»
    # отвечал бы на вопрос о форме свечей, а не о потоке.
    def _share(lo: int, hi: int) -> float | None:
        q = sum(x for x in quotes[lo:hi] if x > 0)
        b = sum(x for x in buys[lo:hi] if x > 0)
        return (b / q) if q > 0 else None

    share_now = _share(len(quotes) - bars, len(quotes))
    share_day = _share(max(0, len(quotes) - norm_bars), len(quotes) - bars)

    start = opens[-bars] if opens[-bars] > 0 else closes[-bars]
    last = closes[-1]
    move_pct = ((last / start) - 1) * 100 if start > 0 else 0.0

    trs = true_ranges(_col(klines, K_HIGH), _col(klines, K_LOW), closes)
    atr = sum(trs[-ATR_PERIOD:]) / ATR_PERIOD if len(trs) >= ATR_PERIOD else 0.0

    lows = [l for l in _col(klines, K_LOW)[-bars:] if l > 0]
    prev_lows = [l for l in _col(klines, K_LOW)[-bars * 2:-bars] if l > 0]

    out = {
        "hours": hours,
        "bars": bars,
        "size_x": round(size_x, 2),
        "size_p90": round(p90, 2),
        "move_pct": round(move_pct, 2),
    }
    if share_now is not None:
        out["buy_share"] = round(share_now, 3)
    if share_now is not None and share_day is not None:
        out["buy_pp"] = round((share_now - share_day) * 100, 1)
    if atr > 0:
        out["move_atr"] = round(abs(last - start) / atr, 2)
    if lows and prev_lows:
        out["low_break"] = min(lows) < min(prev_lows)
    return out
```

### было

```python
    shake = shakeout(klines, minutes=minutes or 60, norm_bars=norm_bars)
```

### стало

```python
    shake = shakeout(klines, minutes=minutes or 60)
```

