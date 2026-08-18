# Встряска: в звезду и на панель зала

## файл: `render/orbit.py`

Применять ПОСЛЕ `patch-intraday-fine-scale.md` и целых файлов
`core/binance.py`, `analytics/metrics.py` — без них `shake` в пейлоаде
не появится и звезда просто не получит новых ключей.

Мелкая шкала предпочитается часовой, потому что сторона у `big_trades`
берётся по доле тейкер-покупок всего бара: крупная покупка внутри
продавцового часа уходит в нейтраль. Пятнадцатиминутки грузятся только
для монет журнала, у остальных остаётся часовой ответ, и шкала едет
рядом с числами.

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

    # Что было за последние часы. Мелкая шкала предпочтительнее
    # часовой: сторона у big_trades берётся по доле тейкер-покупок
    # ВСЕГО бара, и крупная покупка внутри продавцового часа уходит в
    # нейтраль — именно тот случай, ради которого слой и заведён.
    # Пятнадцатиминутки грузятся только для монет журнала, поэтому у
    # остальных остаётся часовой ответ, и шкала едет рядом с числами:
    # без неё «две покупки» с разных монет означали бы разное.
    fine = (raw or {}).get("intraday_fine") or {}
    src = fine if (fine.get("shake") or {}) else intra
    shake = src.get("shake") or {}
    if shake:
        out["shakeScale"] = str(src.get("scale") or "")
        out["shakeHours"] = float(shake.get("hours") or 0)
        out["shakeBuys"] = int(shake.get("buys") or 0)
        out["shakeSells"] = int(shake.get("sells") or 0)
        out["shakeMax"] = float(shake.get("max_x") or 0.0)
        out["shakeMove"] = float(shake.get("move_pct") or 0.0)
        # Ход в ATR и пробой низа приходят не всегда: у монеты с
        # нулевым ATR первого нет, у короткого ряда нет второго.
        # Ноль здесь соврал бы — «цена стояла» вместо «не мерили».
        if shake.get("move_atr") is not None:
            out["shakeAtr"] = float(shake["move_atr"])
        if shake.get("low_break") is not None:
            out["shakeLow"] = bool(shake["low_break"])

    return out
```

## файл: `render/podium.py`

Фраза встаёт в `notes()` рядом с остальными наблюдениями и
ранжируется тем же весом — во сколько раз перекрыт собственный порог.
Гейта по месту в диапазоне у неё нет намеренно: он молчал бы ровно в
середине хода, то есть там, где встряска и случается.

### было

```javascript
    if (c.vxDir === 'up' && c.vxAgo >= 0 && c.vxAgo <= 12) {
```

### стало

```javascript
    /* Что было за последние часы. Условие составное: крупные заявки
       ОДНОЙ стороны при цене, которая не пошла в её сторону. Покупки
       на растущих барах — догоняющие, и говорить о них нечего;
       смысл появляется, когда покупают на сползании, а продают на
       стоящей цене. Порога «стоит» здесь нет, есть знак хода: где
       именно проходит граница, мы ещё не мерили.

       Шкала печатается рядом с числами: пятнадцатиминутки берутся
       только для монет журнала, у остальных ответ часовой, и без
       подписи две одинаковые фразы означали бы разное. */
    if (c.shakeBuys > (c.shakeSells || 0) && c.shakeMove <= 0) {
      add(c.shakeBuys + (+c.shakeMax || 0) / 4, 'day',
        'откупали на сползании: ' + c.shakeBuys,
        'откупали на сползании, ' + (c.shakeHours || 4) + ' ч: <b>' +
        c.shakeBuys + '</b> заявок, крупнейшая ×' +
        xfmtRaw(c.shakeMax) + ' при цене ' + (+c.shakeMove).toFixed(1) +
        '% <small>' + (c.shakeScale || '') + '</small>');
    } else if (c.shakeSells > (c.shakeBuys || 0) && c.shakeMove >= 0) {
      add(c.shakeSells + (+c.shakeMax || 0) / 4, 'day',
        'продавали в рост: ' + c.shakeSells,
        'крупные продажи при растущей цене, ' + (c.shakeHours || 4) +
        ' ч: <b>' + c.shakeSells + '</b>, крупнейшая ×' +
        xfmtRaw(c.shakeMax) + ' <small>' + (c.shakeScale || '') +
        '</small>');
    }

    if (c.vxDir === 'up' && c.vxAgo >= 0 && c.vxAgo <= 12) {
```
