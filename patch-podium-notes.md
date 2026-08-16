# Панель: числа убрать, наблюдение вывести словами

## файл: `render/podium.py`

Применять ПОСЛЕ `patch-podium-intraday.md`.

Блок чисел на панели убирается целиком: рост от дна, объём, фон и
срок в журнале дублируют то, что уже видно по звёздам на орбите, а
сам факт присутствия карточки означает, что монета в лидерах. Панель
занимала половину высоты пересказом известного.

Вместо него — одно наблюдение словами. Числа при этом не исчезают:
они остаются в крупной карточке, где по ним можно проверить, из чего
фраза собрана.

## Как выбирается фраза

Наблюдений много, места одно. Ранжируются они не фиксированным
приоритетом, а **необычностью величины**: каждое условие делится на
собственный порог срабатывания, и сравнивается «во сколько раз
перекрыт порог». При фиксированном приоритете верхняя фраза
загоралась бы у всех подряд и её перестали бы читать.

Три правила формулировки, и они не про вежливость:

Фраза описывает СЛУЧИВШЕЕСЯ, а не будущее. «×17 при мёртвом фоне»
остаётся верным независимо от того, куда пойдёт цена; «сейчас
поедет» через день выглядит враньём и обесценивает все остальные
подписи.

Величины нет — фразы нет. Никаких «данных недостаточно»: пустая
панель честнее заполненной пустотой.

Числа внутри фразы настоящие, не заменены на «сильно» и «слабо». Их
можно проверить глазами по блокам карточки — иначе подпись
непроверяема, а непроверяемой подписи веры нет.

### было

```python
.obp-today{display:flex;justify-content:space-between;align-items:center;
  margin-top:6px;padding-top:5px;border-top:1px solid rgba(255,255,255,.07);
  font-size:9px;letter-spacing:.06em;color:#8D97A6}
.obp-today b{font-weight:600}
.obp-today b.up{color:#4FCF8A} .obp-today b.dn{color:#E8705A}
```

### стало

```python
.obp-today{display:flex;justify-content:space-between;align-items:center;
  margin-top:6px;padding-top:5px;border-top:1px solid rgba(255,255,255,.07);
  font-size:9px;letter-spacing:.06em;color:#8D97A6}
.obp-today b{font-weight:600}
.obp-today b.up{color:#4FCF8A} .obp-today b.dn{color:#E8705A}

/* Наблюдение словами вместо блока чисел. Прижато к низу рамки:
   график остаётся главным, подпись читается под ним, а не спорит
   с ним за верх карточки. */
.obp-note{position:absolute;left:12px;right:12px;bottom:11px;
  font-size:10px;line-height:1.45;letter-spacing:.03em;color:#B9C2CE}
.obp-note b{font-weight:600;color:#E3E8EF}
.obp-note b.up{color:#4FCF8A} .obp-note b.dn{color:#E8705A}
.obp-note b.am{color:#F0B85C}
.obp-note-q{display:block;margin-top:3px;font-size:9px;letter-spacing:.16em;
  text-transform:uppercase;color:#5A6270}
```

### было

```python
  function frameHTML(c, col) {
    var up = Math.round(+c.up || 0);
    return '<div class="obp-frame">' +
      '<i class="obp-br tl"></i><i class="obp-br tr"></i>' +
      '<i class="obp-br bl"></i><i class="obp-br brr"></i>' +
      '<div class="obp-tick">' + c.t + '</div>' +
      '<div class="obp-state">' + (c.pattern || '—') + '</div>' +
      '<div class="obp-beam"></div>' +
      '<div class="obp-art">' + art(c, col, 210, 126) + '</div>' +
      '<div class="obp-nums">' +
        '<span class="obp-gau">' + gauge(up, col) +
          '<span class="obp-gau-v"><b>' + up + '%</b><i>от дна</i></span>' +
        '</span>' +
        '<span class="obp-rows">' +
          '<span class="obp-row"><i>объём</i>' +
            segs(volNow(c), +c.x || 0) +
            '<b>' + xfmt(volNow(c)) + '</b></span>' +
          '<span class="obp-row"><i>фон</i>' +
            segs(+c.volBg || 0, 4) +
            '<b>' + (c.volBg !== undefined ? xfmt(c.volBg) : '—') + '</b></span>' +
          '<span class="obp-row"><i>журнал</i>' + ticksDays(+c.days || 0) +
            '<b>' + (+c.days || 0) + 'д</b></span>' +
        '</span>' +
      '</div>' +
      todayLine(c) +
    '</div>';
  }
```

### стало

```python
  /* ── Наблюдения ──
     Каждое возвращает вес и две формы: короткую для панели и полную
     для карточки. Вес — во сколько раз перекрыт собственный порог
     срабатывания, поэтому наблюдения разной природы сравнимы между
     собой: всплеск объёма в три раза выше порога весит столько же,
     сколько втрое перекрытый порог по перекосу сторон.

     Горизонт помечен у каждого: в карточку идут два наблюдения, по
     одному с каждого, иначе обе строки окажутся про один и тот же
     всплеск. */
  function notes(c) {
    var out = [];
    function add(w, span, short, full) {
      if (w > 0) out.push({ w: w, span: span, short: short, full: full });
    }

    var vol = volNow(c), bg = c.volBg;

    if (vol >= 5 && bg !== undefined && bg < 1) {
      add(vol / 5, 'day',
        'всплеск первый час, ×' + xfmtRaw(vol),
        'всплеск первый час: <b class="am">×' + xfmtRaw(vol) +
        '</b> при фоне ×' + xfmtRaw(bg));
    } else if (bg !== undefined && bg >= 1.3) {
      add(bg / 1.3, 'day',
        'интерес держится сутки',
        'интерес держится сутки, фон <b class="am">×' + xfmtRaw(bg) + '</b>');
    } else if (vol < 0.5 && bg !== undefined && bg < 0.5) {
      add(0.5 / Math.max(vol, 0.05), 'day',
        'тихо в обоих измерениях',
        'тихо в обоих измерениях: ×' + xfmtRaw(vol) + ' при фоне ×' +
        xfmtRaw(bg));
    }

    if (c.press !== undefined && Math.abs(+c.press) >= 3) {
      var upside = +c.press >= 0;
      add(Math.abs(+c.press) / 3, 'day',
        upside ? 'покупатель усиливается' : 'продавец прибавил',
        (upside ? 'покупатель усиливается' : 'продавец прибавил') +
        ' на <b class="' + (upside ? 'up' : 'dn') + '">' +
        Math.abs(+c.press).toFixed(1) + ' п.п.</b> за последние часы');
    }

    if (c.bigBuys && c.rangePos !== undefined && c.rangePos <= 35) {
      add(c.bigBuys + (+c.bigMax || 0) / 4, 'day',
        'откупали у низа: ' + c.bigBuys,
        'откупали у низа: <b>' + c.bigBuys + '</b>, крупнейший ×' +
        (c.bigMax || 0));
    }
    if (c.bigSells && c.rangePos !== undefined && c.rangePos >= 65) {
      add(c.bigSells + (+c.bigMax || 0) / 4, 'day',
        'крупные продажи у верха',
        'крупные продажи у верха диапазона: <b>' + c.bigSells + '</b>');
    }

    if (c.vxDir === 'up' && c.vxAgo >= 0 && c.vxAgo <= 12) {
      add((13 - c.vxAgo) / 6, 'day',
        'развернулся ' + c.vxAgo + ' ч назад',
        'развернулся вверх <b class="up">' + c.vxAgo + ' часов назад</b>');
    }

    if (c.byDay && c.byDay.length >= 3) {
      var today = c.byDay[c.byDay.length - 1];
      var past = c.byDay.slice(0, -1).filter(function (n) { return n > 0; });
      if (today >= 2 && past.length) {
        var mid = past.slice().sort(function (a, b) { return a - b; })[
          Math.floor(past.length / 2)];
        if (mid > 0 && today > mid) {
          add(today / mid, 'day',
            'попадает чаще: ' + today,
            'попадает чаще обычного: сегодня <b>' + today +
            '</b> против ' + mid);
        }
      }
    }

    if ((+c.heldRallies || 0) >= 3) {
      add(c.heldRallies / 3, 'weeks',
        'дно выдержало ' + c.heldRallies,
        'дно выдержало <b>' + c.heldRallies + '</b> отскоков из ' +
        (c.rallies || c.heldRallies));
    }

    out.sort(function (a, b) { return b.w - a.w; });
    return out;
  }

  /* Кратность без знака умножения — фраза его ставит сама. */
  function xfmtRaw(v) {
    var n = +v || 0;
    return n >= 10 ? Math.round(n) : n.toFixed(1);
  }

  function frameHTML(c, col) {
    /* Блока чисел здесь больше нет намеренно. Рост от дна, объём,
       фон и срок в журнале пересказывали то, что видно по звёздам на
       орбите, а сам факт карточки означает, что монета в лидерах.
       Числа остались в крупной карточке — там по ним проверяется,
       из чего собрана подпись. */
    var n = notes(c)[0];
    return '<div class="obp-frame">' +
      '<i class="obp-br tl"></i><i class="obp-br tr"></i>' +
      '<i class="obp-br bl"></i><i class="obp-br brr"></i>' +
      '<div class="obp-tick">' + c.t + '</div>' +
      '<div class="obp-state">' + (c.pattern || '—') + '</div>' +
      '<div class="obp-beam"></div>' +
      '<div class="obp-art">' + art(c, col, 210, 126) + '</div>' +
      (n ? '<div class="obp-note">' + n.short + '</div>' : '') +
    '</div>';
  }
```

### было

```python
      (c.verdict ? '<div class="obz-verdict">' + c.verdict + '</div>' : '') +
      blocksHTML(c, col) +
```

### стало

```python
      (c.verdict ? '<div class="obz-verdict">' + c.verdict + '</div>' : '') +
      summaryHTML(c) +
      blocksHTML(c, col) +
```

### было

```python
  function blocksHTML(c, col) {
```

### стало

```python
  /* Сводка карточки: по одному наблюдению с каждого горизонта.
     Оба с одного означали бы две фразы про один и тот же всплеск,
     а вопрос у горизонтов разный. */
  function summaryHTML(c) {
    var all = notes(c);
    var day = all.filter(function (n) { return n.span === 'day'; })[0];
    var wk = all.filter(function (n) { return n.span === 'weeks'; })[0];
    var parts = [];
    if (day) parts.push(day.full);
    if (wk) parts.push(wk.full);
    if (!parts.length) return '';
    return '<div class="obz-sum">' + parts.join(' · ') + '</div>';
  }

  function blocksHTML(c, col) {
```

### было

```python
.obz-blocks{display:block}
```

### стало

```python
.obz-sum{padding:12px 20px;font-size:13px;line-height:1.6;color:#E3E8EF;
  background:rgba(127,227,212,.05);
  border-top:1px solid rgba(255,255,255,.08)}
.obz-sum b{font-weight:600;color:#7FE3D4}
.obz-sum b.up{color:#4FCF8A} .obz-sum b.dn{color:#E8705A}
.obz-sum b.am{color:#F0B85C}

.obz-blocks{display:block}
```
