# Патч: брифинг показывает время ПРОГОНА, а не открытия страницы

Применять вместе с `patch-orbit-market-ts.md` (тот добавляет поле
`ts` в `_orbit_market()`, без него `M.ts`/`O.market.ts` будет пустым).

`M` (переменная `O.market`) в момент вызова этой строки ещё не
объявлена — она определяется ниже по функции. Читаю `O.market`
напрямую: `O` уже существует в начале `buildBrief()`.

Если анкор не совпадёт (в файле могут быть двойные пустые строки
между операторами — видел такое в присланной версии ранее), пришлите
точный кусок функции `buildBrief()` вокруг `obfDate`, и я подгоню.

## файл: `render_brief.py`

### было
```javascript
    /* Отчёт статический: важно не «сегодня», а когда был прогон —
       иначе легко читать вчерашние числа как свежие. */
    document.getElementById('obfDate').textContent = 'ПРОГОН · ' +
      new Date().toLocaleString('ru-RU', { day: 'numeric', month: 'long',
        hour: '2-digit', minute: '2-digit' }).toUpperCase();
```

### стало
```javascript
    /* Отчёт статический: важно не «сегодня», а когда был прогон —
       иначе легко читать вчерашние числа как свежие.
       Раньше здесь стоял new Date() — момент открытия страницы
       браузером, а не момент прогона: поля со временем прогона не
       было вовсе ни под каким именем (см. _orbit_market). Читаю
       O.market напрямую, а не через M: M объявляется ниже по
       функции, и на этой строке она ещё не существует. */
    var runTs = (O.market && O.market.ts) ? new Date(O.market.ts) : new Date();
    document.getElementById('obfDate').textContent = 'ПРОГОН · ' +
      runTs.toLocaleString('ru-RU', { day: 'numeric', month: 'long',
        hour: '2-digit', minute: '2-digit' }).toUpperCase();
```
