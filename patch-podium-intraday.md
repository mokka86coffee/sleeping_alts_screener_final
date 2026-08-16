# Панель и карточка: уровень, метки заявок и блок «сегодня»

## файл: `render/podium.py`

Применять ПОСЛЕ `patch-podium-tier-by-up.md` и
`patch-orbit-stars-intraday.md`.

Раскладка из прототипа, как есть; дизайн доводим потом.

На панели добавляется минимум — места там нет: горизонталь уровня и
точки крупных заявок прямо на линии цены, объём разбит на два ряда,
внизу строка «сегодня».

В крупной карточке два блока с разными горизонтами. «За недели» —
форма цикла. «Сегодня» — часовая линия за двое суток с метками,
восемь величин, плотность попаданий по дням и выбор шкалы.

Величины, которых нет, не подменяются нулём: ключ просто
отсутствует, и подпись это различает. Ноль откупов и «не мерили» —
разные ответы.

### было

```python
.obp-hint{position:absolute;left:0;right:0;bottom:16px;text-align:center;
```

### стало

```python
/* ── Интрадей на панели и в карточке ── */
.obp-today{display:flex;justify-content:space-between;align-items:center;
  margin-top:6px;padding-top:5px;border-top:1px solid rgba(255,255,255,.07);
  font-size:9px;letter-spacing:.06em;color:#8D97A6}
.obp-today b{font-weight:600}
.obp-today b.up{color:#4FCF8A} .obp-today b.dn{color:#E8705A}

.obz-blocks{display:block}
.obz-blk{padding:14px 20px 16px;border-top:1px solid rgba(255,255,255,.08)}
.obz-blk-k{font-size:9px;letter-spacing:.4em;text-transform:uppercase;
  color:#5A6270}
.obz-blk-h{font-size:11px;color:#5A6270;margin:2px 0 10px}
.obz-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(104px,1fr));
  gap:12px 16px;margin-top:12px}
.obz-cell i{display:block;font-size:9px;letter-spacing:.28em;
  text-transform:uppercase;color:#5A6270;font-style:normal;margin-bottom:3px}
.obz-cell b{font-size:14px;font-weight:400;color:#E3E8EF}
.obz-cell b.up{color:#4FCF8A} .obz-cell b.dn{color:#E8705A}
.obz-cell b.am{color:#F0B85C}
.obz-h48{background:#0b0d12;border:1px solid rgba(255,255,255,.08);
  border-radius:6px;padding:5px}
.obz-days{display:flex;gap:3px;align-items:flex-end;height:26px;margin-top:5px}
.obz-days i{width:11px;background:#7FE3D4;opacity:.75;border-radius:1px}
.obz-days i.z{background:rgba(255,255,255,.09)}
.obz-chip{display:inline-block;font-size:10px;padding:3px 8px;margin:5px 5px 0 0;
  border:1px solid rgba(255,255,255,.08);border-radius:20px;color:#8D97A6}
.obz-chip.best{border-color:rgba(127,227,212,.5);color:#7FE3D4}

.obp-hint{position:absolute;left:0;right:0;bottom:16px;text-align:center;
```

### было

```python
  function frameHTML(c, col) {
    var up = Math.round(+c.up || 0);
```

### стало

```python
  /* ── Метки крупных заявок на линии ──
     Позиции в bigMarks отсчитаны от начала хвоста в 48 часов, тем же
     хвостом рисуется h48. Ряд и метки обязаны ехать вместе: если
     когда-нибудь длина хвоста изменится в одном месте, метки
     разъедутся молча.

     Белая точка — покупка, красная — продажа, нейтральные не
     рисуются вовсе: бар, где стороны погасили друг друга, ничего не
     сообщает, а точка на графике выглядит утверждением. */
  function markDots(marks, pts) {
    if (!marks || !marks.length || !pts.length) return '';
    var n = pts.length, out = '';
    for (var i = 0; i < marks.length; i++) {
      var m = marks[i];
      if (m.s !== 'buy' && m.s !== 'sell') continue;
      var idx = Math.round(m.i / 47 * (n - 1));
      if (idx < 0 || idx >= n) continue;
      var p = pts[idx];
      var r = Math.min(6, 2.2 + (+m.x || 0) * 0.35);
      out += '<circle cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) +
        '" r="' + r.toFixed(1) + '" fill="' +
        (m.s === 'buy' ? '#ffffff' : '#E8705A') + '" opacity=".9"/>';
    }
    return out;
  }

  /* Линия за 48 часов. Отдельно от art(): та рисует недели и знает
     про узел входа в журнал, здесь же вопрос другой — что было за
     двое суток. Общая функция обслуживала бы оба плохо. */
  function h48HTML(c, col, W, H) {
    var ser = (c.h48 || []).map(Number).filter(function (v) {
      return isFinite(v) && v > 0;
    });
    if (ser.length < 6) return '';
    var lo = Math.min.apply(null, ser), hi = Math.max.apply(null, ser);
    var rng = (hi - lo) || 1;
    var pts = ser.map(function (v, i) {
      return [i * W / (ser.length - 1), H - 8 - (v - lo) / rng * (H - 22)];
    });
    var d = smooth(pts);
    return '<div class="obz-h48"><svg viewBox="0 0 ' + W + ' ' + H +
      '" preserveAspectRatio="none" width="100%" height="' + H + '">' +
      '<path d="' + d + ' L' + W + ' ' + H + ' L0 ' + H + ' Z" fill="' +
        col + '" opacity=".12"/>' +
      '<path d="' + d + '" fill="none" stroke="' + col +
        '" stroke-width="1.5"/>' +
      markDots(c.bigMarks, pts) +
      '</svg></div>';
  }

  /* Строка «сегодня» на панели. Три коротких факта, каждый — ответ
     на отдельный вопрос: куда наклонён поток, откупали ли на
     проливе, жива ли монета в эти сутки. */
  function todayLine(c) {
    var bits = [];
    if (c.press !== undefined) {
      var up = +c.press >= 0;
      bits.push('<b class="' + (up ? 'up' : 'dn') + '">' +
        (up ? '↑' : '↓') + '</b>');
    }
    if (c.bigBuys) bits.push(c.bigBuys + ' откуп' +
      (c.bigBuys === 1 ? '' : c.bigBuys < 5 ? 'а' : 'ов'));
    var day = (c.byDay && c.byDay.length) ? c.byDay[c.byDay.length - 1] : null;
    var right = day !== null ? day + ' попад.' : '';
    if (!bits.length && !right) return '';
    return '<div class="obp-today"><span>сегодня ' + bits.join(' ') +
      '</span><span>' + right + '</span></div>';
  }

  function frameHTML(c, col) {
    var up = Math.round(+c.up || 0);
```

### было

```python
          '<span class="obp-row"><i>журнал</i>' + ticksDays(+c.days || 0) +
            '<b>' + (+c.days || 0) + 'д</b></span>' +
        '</span>' +
      '</div>' +
    '</div>';
  }
```

### стало

```python
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

### было

```python
      (c.verdict ? '<div class="obz-verdict">' + c.verdict + '</div>' : '') +
      '<div class="obz-goto" id="obpZgoto">показать на орбите</div>';
```

### стало

```python
      (c.verdict ? '<div class="obz-verdict">' + c.verdict + '</div>' : '') +
      blocksHTML(c, col) +
      '<div class="obz-goto" id="obpZgoto">показать на орбите</div>';
```

### было

```python
  function closeZoom() { zoom.classList.remove('on'); }
```

### стало

```python
  /* ── Два блока карточки ──
     Горизонты разные и намеренно разведены: «за недели» отвечает на
     вопрос цикла, «сегодня» — на вопрос ближайших суток. Одна
     таблица на оба заставляла бы сравнивать несравнимое. */
  function cell(k, v, cls) {
    if (v === null || v === undefined || v === '') return '';
    return '<span class="obz-cell"><i>' + k + '</i><b' +
      (cls ? ' class="' + cls + '"' : '') + '>' + v + '</b></span>';
  }

  function pct(v, digits) {
    if (v === undefined || v === null) return null;
    var n = +v;
    return (n >= 0 ? '+' : '') + n.toFixed(digits === undefined ? 0 : digits) + '%';
  }

  function blocksHTML(c, col) {
    var weeks =
      cell('от дна', pct(c.up), 'up') +
      cell('от пика жизни', c.lifeDrop ? '−' + Math.round(Math.abs(c.lifeDrop)) + '%' : null, 'dn') +
      cell('вершина хода', c.peakX ? '×' + c.peakX : null) +
      cell('отскоки', c.rallies ? (c.heldRallies || 0) + ' из ' + c.rallies : null) +
      cell('в лидерах', c.runsSeen ? (c.hitCount || 0) + ' из ' + c.runsSeen : null) +
      cell('в журнале', (+c.days || 0) + 'д · тишина ' + (+c.quiet || 0));

    var today =
      cell('объём сейчас', xfmt(volNow(c))) +
      cell('фон суток', c.volBg !== undefined ? xfmt(c.volBg) : null, 'am') +
      cell('перевес сторон', c.press !== undefined
        ? (+c.press >= 0 ? 'покупка ' : 'продажа ') +
          Math.abs(+c.press).toFixed(1) + ' п.п.' : null,
        (+c.press >= 0 ? 'up' : 'dn')) +
      cell('вортекс', c.vxDir
        ? (c.vxDir === 'up' ? 'вверх' : 'вниз') +
          (c.vxAgo >= 0 ? ' · ' + c.vxAgo + ' бар' : ' · держится')
        : null, c.vxDir === 'up' ? 'up' : 'dn') +
      cell('в диапазоне', c.rangePos !== undefined
        ? Math.round(c.rangePos) + '% снизу' : null) +
      cell('откупы за сутки', c.bigCount
        ? c.bigCount + ' · макс ×' + (c.bigMax || 0) : null) +
      cell('скорость хода', c.speedV ? c.speedV + ' ATR/бар' : null) +
      cell('заметность', c.q ? 'q ' + c.q + ' · ' + (c.qScale || '') : null);

    var days = '';
    if (c.byDay && c.byDay.length) {
      var mx = Math.max.apply(null, c.byDay) || 1;
      days = '<span class="obz-cell"><i>попадания по дням</i>' +
        '<span class="obz-days">' +
        c.byDay.map(function (n) {
          var h = Math.max(3, Math.round(n / mx * 26));
          return '<i class="' + (n ? '' : 'z') + '" style="height:' + h +
            'px"></i>';
        }).join('') + '</span></span>';
    }

    var out = '<div class="obz-blocks">';
    if (weeks) {
      out += '<div class="obz-blk"><div class="obz-blk-k">за недели</div>' +
        '<div class="obz-blk-h">форма цикла и место в нём</div>' +
        '<div class="obz-grid">' + weeks + '</div></div>';
    }
    if (today || days) {
      out += '<div class="obz-blk"><div class="obz-blk-k">сегодня</div>' +
        '<div class="obz-blk-h">горизонт сутки-двое · часовая шкала</div>' +
        h48HTML(c, col, 610, 84) +
        '<div class="obz-grid">' + today + days + '</div></div>';
    }
    return out + '</div>';
  }

  function closeZoom() { zoom.classList.remove('on'); }
```
