# Встряска на экране: звезда и наблюдение

Заменяет прежний `patch-render-shakeout.md` — тот писался под поля,
которых больше нет, применять его не нужно.

Применять ПОСЛЕ `patch-shakeout-continuous.md`: без него в пейлоаде
не будет ни `size_x`, ни `buy_pp`, и звезда останется без ключей.

Вес наблюдения складывается из двух безразмерных частей: во сколько
раз крупнейшая сделка окна перекрыла обычный для суток разброс и
насколько сместился поток. В прошлой редакции я поставил туда сырой
счёт заявок, и он оказался несравним с весами остальных наблюдений —
те меряются в «во сколько раз перекрыт порог».

Проверено: на числах BLESS фраза получает вес 3.73 и забирает дневной
горизонт; при том же перекосе, но растущей цене молчит; при перекосе
меньше процентного пункта молчит; без замера ключей у звезды нет
вовсе.

Оба якоря после применения не находятся — повторный прогон ничего не
испортит.

## файл: `render/orbit.py`

### было

```python
    spd = intra.get("speed") or {}
    if spd.get("v"):
        out["speedV"] = float(spd["v"])
        out["speedAtr"] = float(spd.get("atr_move") or 0.0)

    return out
```

### стало

```python
    spd = intra.get("speed") or {}
    if spd.get("v"):
        out["speedV"] = float(spd["v"])
        out["speedAtr"] = float(spd.get("atr_move") or 0.0)

    # Последние часы против суток. Мелкая шкала предпочтительнее
    # часовой: на пятнадцати минутах крупная сделка меньше тонет в
    # среднем размере бара. Пятнадцатиминутки грузятся только для
    # монет журнала, поэтому у остальных остаётся часовой ответ, и
    # шкала едет рядом с числами — без неё одинаковые фразы с разных
    # монет означали бы разное.
    fine = (raw or {}).get("intraday_fine") or {}
    src = fine if (fine.get("shake") or {}) else intra
    shake = src.get("shake") or {}
    if shake:
        out["shakeScale"] = str(src.get("scale") or "")
        out["shakeHours"] = float(shake.get("hours") or 0)
        out["shakeX"] = float(shake.get("size_x") or 0.0)
        out["shakeP90"] = float(shake.get("size_p90") or 0.0)
        out["shakeMove"] = float(shake.get("move_pct") or 0.0)
        # Остальное приходит не всегда: перекос требует оборота с
        # обеих сторон, ход в ATR — ненулевого ATR, пробой низа —
        # предыдущего такого же окна. Ноль тут соврал бы.
        if shake.get("buy_pp") is not None:
            out["shakePP"] = float(shake["buy_pp"])
        if shake.get("buy_share") is not None:
            out["shakeShare"] = float(shake["buy_share"])
        if shake.get("move_atr") is not None:
            out["shakeAtr"] = float(shake["move_atr"])
        if shake.get("low_break") is not None:
            out["shakeLow"] = bool(shake["low_break"])

    return out
```

## файл: `render/podium.py`

Наблюдение встаёт перед разворотом вортекса, в общую очередь `notes()`.

### было

```javascript
    if (c.vxDir === 'up' && c.vxAgo >= 0 && c.vxAgo <= 12) {
```

### стало

```javascript
    /* Последние часы против суток. Условие составное: поток
       сместился в одну сторону, а цена в эту сторону НЕ пошла.
       Покупки на растущих барах — догоняющие, говорить о них
       нечего; смысл появляется, когда покупают на сползании, а
       продают на стоящей цене.

       Вес складывается из двух безразмерных частей: во сколько раз
       крупнейшая сделка окна перекрыла обычный для суток разброс, и
       насколько сместился поток. Так он сравним с весами остальных
       наблюдений, которые тоже меряются в «во сколько раз перекрыт
       порог».

       Отсечка в один пункт отсеивает дрожание доли: перекос меньше
       процентного пункта — это шум округления, а не смена стороны. */
    var shPP = +c.shakePP || 0, shX = +c.shakeX || 0, shP = +c.shakeP90 || 0;
    var shW = (shP > 1 ? shX / shP : shX) + Math.abs(shPP) / 5;
    var shTail = ' <small>' + (c.shakeScale || '') + '</small>';
    var shMid = 'сделки ×' + xfmtRaw(shX) + ' к суточной норме' +
      (shP > 0 ? ' (обычно ×' + xfmtRaw(shP) + ')' : '') +
      ', цена ' + (+c.shakeMove).toFixed(1) + '%' +
      (c.shakeLow ? ', низ окна пробит' : '');

    if (shPP >= 1 && c.shakeMove <= 0) {
      add(shW, 'day',
        'откупали на сползании: +' + shPP.toFixed(1) + ' п.п.',
        'за ' + (c.shakeHours || 4) + ' ч поток сместился в покупку на <b>' +
        shPP.toFixed(1) + ' п.п.</b>, ' + shMid + shTail);
    } else if (shPP <= -1 && c.shakeMove >= 0) {
      add(shW, 'day',
        'продавали в рост: ' + shPP.toFixed(1) + ' п.п.',
        'за ' + (c.shakeHours || 4) + ' ч поток сместился в продажу на <b>' +
        Math.abs(shPP).toFixed(1) + ' п.п.</b>, ' + shMid + shTail);
    }

    if (c.vxDir === 'up' && c.vxAgo >= 0 && c.vxAgo <= 12) {
```
