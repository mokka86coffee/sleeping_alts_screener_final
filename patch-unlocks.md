# Разлоки: данные и строка в карточке

Первая величина проекта, которая смотрит ВПЕРЁД. Всё остальное —
импакт, отскоки, вершина, пузыри — описывает прошлое.

Ставится в три приёма: новый модуль `analytics/unlocks.py` вместе с
`analytics/unlocks.json` (оба файла отдельно, копировать как есть),
патч к `metrics.py`, патч к `orbit.py` и `cardscene.py`.

**Что решено и почему.** Размер разлока печатается в ДНЯХ ОБОРОТА, а не
в долларах и не в проценте капитализации: рынок переваривает предложение
объёмом торгов. У PORTAL ближайший транш — 0.11 дня оборота, шум; у
BLESS сентябрьский — 2.5 дня, событие. Отсутствие данных даёт отсутствие
строки, а не ноль: пробел обязан отличаться от «разлоков нет». Вердикта
нет, тон строки лишь выделяет случай, где транш весит больше суток
оборота или идёт инсайдерам.

**Якоря выбраны в местах, которых не касались патчи встряски и срока
журнала**, поэтому порядок применения значения не имеет.

Проверено: модуль отдаёт по PORTAL 3 дня, 0.11 дня оборота, инсайдерская
доля события 41.4%, флоат 63.2% и FDV ×1.58; на незаполненной монете —
пустой словарь и ни одного ключа в звезде; встроенный JavaScript
проходит `node --check`; вид строки прогнан на четырёх случаях.

## файл: `analytics/metrics.py`

### было

```python
from analytics.intraday import big_trades as intraday_big
```

### стало

```python
from analytics.intraday import big_trades as intraday_big
from analytics.unlocks import for_symbol as unlocks_for
```

### было

```python
    daily_big = intraday_big(kl_1d) if kl_1d else {}
```

### стало

```python
    # Разлоки. Ручные данные, сети не трогают; пустой словарь означает
    # «монету не заполняли», а не «разлоков нет» — отрисовка обязана
    # показать пробел. Оборот нужен, чтобы перевести объём разлока в дни
    # торгов: рынок переваривает предложение объёмом, а не капитализацией.
    unlocks = unlocks_for(symbol, quote_volume_24h)

    daily_big = intraday_big(kl_1d) if kl_1d else {}
```

### было

```python
        "intraday": intraday,
        "intraday_fine": intraday_fine,
```

### стало

```python
        "intraday": intraday,
        "intraday_fine": intraday_fine,
        "unlocks": unlocks,
```

## файл: `render/orbit.py`

### было

```python
def _star_intraday(raw: dict) -> dict:
```

### стало

```python
def _star_unlocks(raw: dict) -> dict:
    """Разлоки в звезду. Пусто — значит монету не заполняли.

    Ключей нет вовсе, а не нули: пробел на экране должен отличаться от
    «разлоков нет». Величины отдаются как есть, без вердикта — дни,
    доли и признак инсайдерского транша, а «опасно» решает человек.
    """
    u = (raw or {}).get("unlocks") or {}
    if not u:
        return {}

    out: dict = {}
    pairs = (
        ("unlockDays", "next_days"), ("unlockDate", "next_date"),
        ("unlockUsd", "next_usd"), ("unlockDaysVol", "next_days_vol"),
        ("unlockPct", "next_pct_float"), ("unlockAfter", "next_after_days"),
        ("unlockInsShare", "next_insider_share"),
        ("floatPct", "circ_pct"), ("fdvRatio", "fdv_ratio"),
        ("insNow", "insiders_now"), ("insGrow", "insiders_grow"),
    )
    for star_key, src_key in pairs:
        if u.get(src_key) is not None:
            out[star_key] = u[src_key]
    if u.get("next_insider") is not None:
        out["unlockIns"] = bool(u["next_insider"])
    if u.get("inferred"):
        out["unlockInferred"] = True
    if u.get("next_rounds"):
        out["unlockRounds"] = list(u["next_rounds"])
    return out


def _star_intraday(raw: dict) -> dict:
```

### было

```python
            **_star_intraday(raw),
```

### стало

```python
            **_star_intraday(raw),
            **_star_unlocks(raw),
```

## файл: `render/cardscene.py`

### было

```javascript
    if (c.speedV) foot.push(['скорость хода', c.speedV + ' ATR/бар', '']);
```

### стало

```javascript
    if (c.speedV) foot.push(['скорость хода', c.speedV + ' ATR/бар', '']);
    /* Разлок. Единственная величина на карточке, смотрящая ВПЕРЁД.
       Размер печатается в днях оборота, а не в долларах: рынок
       переваривает предложение объёмом торгов, и один и тот же процент
       капитализации на разной ликвидности значит разное.
       Тон горячий, когда транш весит больше суток оборота ИЛИ идёт
       инсайдерам — это не вердикт, а выделение того, что стоит
       посмотреть. Нет данных — строки нет вовсе: пробел обязан
       отличаться от «разлоков нет». */
    if (num(c.unlockDays) !== null) {
      var uv = num(c.unlockDaysVol);
      var ut = ((uv !== null && uv >= 1) || c.unlockIns) ? 'hot' : 'warm';
      foot.push(['разлок',
        c.unlockDays + ' дн' +
        (uv !== null ? ' · ' + uv + ' дн оборота' : '') +
        (c.unlockIns ? ' · инсайдеры' : '') +
        (c.unlockInferred ? ' · оценка' : ''), ut]);
    }
    if (num(c.floatPct) !== null) foot.push(['выпущено',
      Math.round(c.floatPct) + '%' +
      (num(c.fdvRatio) !== null ? ' · FDV ×' + xf(c.fdvRatio) : ''), '']);
```
