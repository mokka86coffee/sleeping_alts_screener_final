# Портфель в сводку журнала и в хвост брифа

## файл: `render/orbit.py`

Применять ПОСЛЕ `patch-leaders-portfolio.md`.

Величина посчитана в журнале, но наружу не выходит. Сводка журнала —
единственное место в отчёте, где говорится о самом скринере, а не о
монетах; портфелю там и место.

### было

```python
    recs = {k: v for k, v in j.items()
            if not k.startswith("_") and isinstance(v, dict)}
    if not recs:
        return {}
```

### стало

```python
    recs = {k: v for k, v in j.items()
            if not k.startswith("_") and isinstance(v, dict)}
    if not recs:
        return {}

    # Условный портфель считается в журнале, здесь только берётся:
    # правило вложения живёт рядом с записями, а не в отрисовке.
    from analytics.leaders import portfolio_stats
    port = portfolio_stats(j)
```

### было

```python
        "best": {"t": _lbl(best_sym),
                 "chg": round(float(best.get("change_pct") or 0.0), 1)},
```

### стало

```python
        "port": port,
        "best": {"t": _lbl(best_sym),
                 "chg": round(float(best.get("change_pct") or 0.0), 1)},
```

## файл: `render/brief.py`

Хвост брифа — единственная строка отчёта про сам скринер. Портфель
дописывается туда же, рядом с лучшим и худшим ходом.

Показываются два числа, а не одно. Текущее отвечает «сколько стоит
бездействие», по максимумам — «сколько стоила бы фиксация в лучшей
точке каждой позиции». Разрыв между ними и есть цена отсутствующего
правила выхода, и ради него всё и заводилось: одно число без второго
выглядело бы приговором скринеру, тогда как находки как раз есть.

### было

```python
      J.n
        ? { p: 'Журнал: ' + J.n + ' ' +
              plural(J.n, 'монета', 'монеты', 'монет') +
```

### стало

```python
      (J.port && J.port.invested)
        ? { p: 'По тысяче в каждую: ' + fmtMoney(J.port.value) + ' из ' +
              fmtMoney(J.port.invested) + ', ' + signed(J.port.pnl_pct) +
              '. По максимумам вышло бы ' + signed(J.port.peak_pct) + '.',
            h: 'По тысяче в каждую: <b>' + fmtMoney(J.port.value) +
              '</b> из ' + fmtMoney(J.port.invested) + ', <b class="' +
              (J.port.pnl_pct >= 0 ? 'up' : 'dn') + '">' +
              signed(J.port.pnl_pct) + '</b>. По максимумам вышло бы ' +
              '<b class="up">' + signed(J.port.peak_pct) + '</b>' +
              (J.port.adds ? ' · доборов ' + J.port.adds : '') + '.' }
        : null,

      J.n
        ? { p: 'Журнал: ' + J.n + ' ' +
              plural(J.n, 'монета', 'монеты', 'монет') +
```

### было

```python
    /* Причина ожидания у каждой монеты своя. Прежняя подпись
```

### стало

```python
    /* Деньги короткой формой: тысячи с буквой, иначе строка
       разъезжается на пяти цифрах. */
    function fmtMoney(v) {
      var n = +v || 0;
      return n >= 10000 ? '$' + (n / 1000).toFixed(1) + 'K' :
             '$' + Math.round(n);
    }
    function signed(v) {
      var n = +v || 0;
      return (n >= 0 ? '+' : '') + n.toFixed(1) + '%';
    }

    /* Причина ожидания у каждой монеты своя. Прежняя подпись
```
