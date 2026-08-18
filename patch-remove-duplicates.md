# Удаление дублирующихся объявлений

Оба файла содержат один и тот же блок дважды. Тела копий совпадают
байт в байт, поэтому сейчас поведение верное: и в Python, и в
JavaScript второе объявление молча перекрывает первое, а раз они
одинаковы — разницы нет.

Опасность в другом. Правку внесут в верхнюю копию, работать будет
нижняя, и найти это тяжело: глазами блоки неотличимы. Удаляется
ВТОРАЯ копия, первая остаётся на месте.

Блоки «было» начинаются с хвоста ПЕРВОЙ копии — он и служит якорем.
Без него текст «было» после применения нашёлся бы снова, уже на
первой копии, и повторный прогон стёр бы и её.

Проверено на присланных файлах: якорь находится ровно один раз, после
применения не находится вовсе; `leaders.py` разбирается парсером и
объявляет каждую функцию по одному разу; `cardscene.py` разбирается и
как Python, и встроенный в него JavaScript проходит `node --check`.

## файл: `analytics/leaders.py`

Второй экземпляр `_touch_portfolio` и `portfolio_stats`, строки
520–648. Файл становится короче на 131 строку.

### было

```python
    if r_invested > 0:
        out["rules_pnl_pct"] = round((r_value / r_invested - 1.0) * 100.0, 1)
        out["rules_value"] = round(r_value, 0)
    return out


def _touch_portfolio(rec: dict, price: float, now: datetime,
                     run_no: int) -> None:
    """Добор, если монета вернулась выше входа после просадки.

    Вызывается ПОСЛЕ _touch_price: тот уже обновил change_pct и
    min_change_pct, и здесь читаются свежие величины.

    Условие проверяется на каждом прогоне, а срабатывает один раз —
    дальше поле add_price занято и путь закрыт. Повторные доборы
    превратили бы метрику в усреднение убытка, а она измеряет
    подтверждение разворота.

    Момент фиксируется ценой ТОГО прогона, где условие впервые
    выполнилось, а не ценой входа. Разница невелика — пересечение
    происходит около входа, — но подставлять вход значило бы
    записать догадку там, где есть замер.
    """
    if rec.get("add_price"):
        return
    if price <= 0:
        return

    try:
        dip = float(rec.get("min_change_pct") or 0.0)
        chg = float(rec.get("change_pct") or 0.0)
    except (TypeError, ValueError):
        return

    if dip <= -PORT_DIP_PCT and chg > 0:
        rec["add_price"] = price
        rec["add_run"] = int(run_no)
        rec["add_at"] = now.isoformat()


def portfolio_stats(store: dict) -> dict:
    """Во что превратился бы механический вход в каждую находку.

    Три величины, и вместе они отвечают на разные вопросы. Текущая
    стоимость — сколько стоит бездействие. Стоимость по максимумам —
    сколько стоила бы фиксация в лучшей точке каждой позиции, то есть
    потолок находок. Разрыв между ними и есть цена отсутствующего
    правила выхода: на 16 августа это +1% против +50%.

    Максимум по добору берётся тем же отношением цен, что и текущее
    значение: путь позиции между добором и максимумом в записи не
    хранится, и точнее посчитать нечем. Величина завышена ровно
    настолько, насколько максимум цены случился ДО добора; на
    подтверждении разворота это редкий случай.
    """
    invested = value = peak = 0.0
    r_invested = r_value = 0.0
    adds = skipped = exits = 0
    losers: list[dict] = []

    for symbol, rec in store.items():
        if symbol.startswith("_") or not isinstance(rec, dict):
            continue
        try:
            entry = float(rec.get("entry_price") or 0.0)
            price = float(rec.get("price") or 0.0)
            chg = float(rec.get("change_pct") or 0.0)
            mx = float(rec.get("max_change_pct") or 0.0)
        except (TypeError, ValueError):
            continue
        if entry <= 0 or price <= 0:
            continue

        if chg <= DEEP_LOSS_PCT:
            losers.append({
                "t": symbol[:-4] if symbol.endswith("USDT") else symbol,
                "chg": round(chg, 1),
                "case": str(rec.get("entry_case") or "").replace("flow_", ""),
                "at": str(rec.get("first_seen") or "")[:10],
                "entry": entry,
            })

        # ── Портфель по правилам ──
        # Пропущенные не участвуют вовсе, вышедшие зафиксированы по
        # цене выхода. Считается рядом с механическим, а не вместо:
        # без пары чисел неизвестно, помогают правила или мешают.
        if rec.get("skip"):
            skipped += 1
        else:
            r_invested += PORT_STAKE
            try:
                exit_at = float(rec.get("exit_price") or 0.0)
            except (TypeError, ValueError):
                exit_at = 0.0
            if exit_at > 0:
                exits += 1
                r_value += PORT_STAKE * (exit_at / entry)
            else:
                r_value += PORT_STAKE * (1.0 + chg / 100.0)

        invested += PORT_STAKE
        value += PORT_STAKE * (1.0 + chg / 100.0)
        peak += PORT_STAKE * (1.0 + mx / 100.0)

        try:
            add_at = float(rec.get("add_price") or 0.0)
        except (TypeError, ValueError):
            add_at = 0.0
        if add_at > 0:
            adds += 1
            invested += PORT_ADD
            value += PORT_ADD * (price / add_at)
            max_price = float(rec.get("max_price") or price)
            peak += PORT_ADD * (max(max_price, price) / add_at)

    if invested <= 0:
        return {}

    losers.sort(key=lambda d: d["chg"])

    out = {
        "invested": round(invested, 0),
        "value": round(value, 0),
        "pnl_pct": round((value / invested - 1.0) * 100.0, 1),
        "peak_pct": round((peak / invested - 1.0) * 100.0, 1),
        "adds": adds,
        "skipped": skipped,
        "exits": exits,
        "losers": losers[:6],
        "losers_all": len(losers),
    }
    if r_invested > 0:
        out["rules_pnl_pct"] = round((r_value / r_invested - 1.0) * 100.0, 1)
        out["rules_value"] = round(r_value, 0)
    return out


def _touch_price(rec: dict, price: float, now: datetime) -> None:
```

### стало

```python
    if r_invested > 0:
        out["rules_pnl_pct"] = round((r_value / r_invested - 1.0) * 100.0, 1)
        out["rules_value"] = round(r_value, 0)
    return out


def _touch_price(rec: dict, price: float, now: datetime) -> None:
```

## файл: `render/cardscene.py`

Второй экземпляр `hoursOf` и `fromLow` вместе с комментариями над
ними, строки 745–762. Файл становится короче на 24 строки.

### было

```javascript
й, ход ещё не начался. */
  function fromLow(c) {
    var s = (c.series || []).map(Number).filter(isFinite);
    if (s.length < 3) return null;
    var lo = 0;
    for (var i = 1; i < s.length; i++) if (s[i] < s[lo]) lo = i;
    return s.length - 1 - lo;
  }

  /* Часовой ряд бывает пустым, и это не редкость. Плоская линия из
     подставленных нулей выглядит как показание — «объём весь день
     ровный», — хотя означает «мы ничего не знаем». Порог в шесть
     точек взят тот же, что у панели на стене зала (h48HTML), чтобы
     карточка и панель молчали в одних и тех же случаях. */
  function hoursOf(c) {
    var s = (c.h48 || []).map(Number).filter(function (v) {
      return isFinite(v) && v > 0;
    });
    return s.length < 6 ? null : resample(s, HOURS_N);
  }

  /* Дни от дна. Считаем по сырому ряду цены, а не по выровненному:
     после resample шаг ряда уже не свой, а наш, и счёт съедет.
     Возвращаем число шагов от минимума до конца — при дневном ряде
     это и есть дни. Если минимум последний, ход ещё не начался. */
  function fromLow(c) {
    var s = (c.series || []).map(Number).filter(isFinite);
    if (s.length < 3) return null;
    var lo = 0;
    for (var i = 1; i < s.length; i++) if (s[i] < s[lo]) lo = i;
    return s.length - 1 - lo;
  }

  function adapt(c) {
```

### стало

```javascript
й, ход ещё не начался. */
  function fromLow(c) {
    var s = (c.series || []).map(Number).filter(isFinite);
    if (s.length < 3) return null;
    var lo = 0;
    for (var i = 1; i < s.length; i++) if (s[i] < s[lo]) lo = i;
    return s.length - 1 - lo;
  }

  function adapt(c) {
```
