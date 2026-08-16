# Портфель — первой строкой, а не в хвосте

## файл: `render/brief.py`

Дельта к `patch-portfolio-display.md`. Применять после него.

Строка портфеля встала в хвост, вместе с итогом журнала. Место
неверное: хвост читают последним и часто не читают вовсе, а вопрос
«чего стоят находки» — первый, с которым открывают отчёт. Описание
рынка и лидеры отвечают на «что происходит»; сколько это принесло,
должно стоять до них.

Строка переносится в начало, перед фоном рынка. Итог журнала —
сколько монет, кто лучший и худший — остаётся в хвосте: это справка
о составе, а не о результате.

### было

```python
    var lines = bg.concat(wknd.p ? [wknd] : []).concat([
```

### стало

```python
    /* Портфель идёт ПЕРЕД описанием рынка. Отчёт открывают, чтобы
       узнать, чего стоят находки; режим рынка и лидеры отвечают на
       другой вопрос и могут подождать одну строку. */
    var portLine = (J.port && J.port.invested)
      ? [{ p: 'По тысяче в каждую: ' + fmtMoney(J.port.value) + ' из ' +
             fmtMoney(J.port.invested) + ', ' + signed(J.port.pnl_pct) +
             '. По максимумам вышло бы ' + signed(J.port.peak_pct) + '.',
           h: 'По тысяче в каждую: <b>' + fmtMoney(J.port.value) +
             '</b> из ' + fmtMoney(J.port.invested) + ', <b class="' +
             (J.port.pnl_pct >= 0 ? 'up' : 'dn') + '">' +
             signed(J.port.pnl_pct) + '</b>' +
             (J.port.rules_pnl_pct !== undefined
               ? ', по правилам <b class="' +
                 (J.port.rules_pnl_pct >= 0 ? 'up' : 'dn') + '">' +
                 signed(J.port.rules_pnl_pct) + '</b>' : '') +
             '. По максимумам вышло бы <b class="up">' +
             signed(J.port.peak_pct) + '</b>.' }]
      : [];

    /* Монеты в глубокой просадке — сразу следом. Их разбирают руками,
       и список должен попасться на глаза раньше, чем начнётся
       описание рынка. */
    var lossLine = (J.port && (J.port.losers || []).length)
      ? [{ p: 'Разобрать: ' + J.port.losers.map(function (d) {
             return d.t + ' ' + signed(d.chg) + ' (' + (d.case || '?') +
               ', ' + (d.at || '').slice(5) + ')'; }).join(', ') + '.',
           h: 'Разобрать: ' + J.port.losers.map(function (d) {
             return '<span class="t">' + d.t + '</span> <b class="dn">' +
               signed(d.chg) + '</b> <span class="mut">' + (d.case || '?') +
               ', ' + (d.at || '').slice(5) + '</span>'; }).join(', ') + '.' }]
      : [];

    var lines = portLine.concat(lossLine).concat(bg)
      .concat(wknd.p ? [wknd] : []).concat([
```

### было

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
```

### стало

```python
      J.n
```
