# Пробелы в оверлее: что заполнить руками

## файл: `render/podium.py`

Применять ПОСЛЕ `patch-podium-portline.md` и `patch-orbit-gaps.md`.

Две вещи. В верхней строке — сколько пробелов всего и какое поле
чаще всего пустое: если у всех монет не хватает одного и того же,
заполнять надо его, а не ходить по монетам. В крупной карточке —
список пробелов конкретной монеты, чтобы было видно, что дописывать в
`leaders.json` именно для неё.

Пробелы не подаются как ошибка. Это не сбой расчёта, а граница
данных: историю открытого интереса Binance отдаёт за тридцать дней,
карта зон строится за 240, а характер истории — суждение. Поэтому и
оформление нейтральное, и слово «заполнить», а не «нет данных».

### было

```python
.obz-sum{padding:12px 20px;font-size:13px;line-height:1.6;color:#E3E8EF;
```

### стало

```python
/* Пробелы. Нейтральный серый и рамка пунктиром: это не ошибка, а
   место под ручную работу. Красным было бы неправдой — расчёт
   исправен, данных нет у биржи. */
.obz-gaps{margin-top:14px;padding:9px 11px;border-radius:6px;
  border:1px dashed rgba(255,255,255,.13);font-size:11px;line-height:1.6;
  color:#8D97A6}
.obz-gaps b{color:#B9C2CE;font-weight:600}
.obz-gaps i{font-style:normal;color:#5A6270;letter-spacing:.24em;
  text-transform:uppercase;font-size:9px;display:block;margin-bottom:4px}

.obp-port .gaps{color:#6E7684}
.obp-port .gaps b{color:#9AA6B5}

.obz-sum{padding:12px 20px;font-size:13px;line-height:1.6;color:#E3E8EF;
```

### было

```python
    var L = p.losers || [];
```

### стало

```python
    // Пробелы в данных — рядом с деньгами, но отдельной частью: это
    // не результат, а работа, которую предстоит сделать руками.
    var g = j.gaps;
    if (g && g.gaps) {
      out += ' <span class="sep">·</span> <span class="gaps">заполнить <b>' +
        g.gaps + '</b>';
      if (g.worst && g.worst.n) {
        out += ', чаще всего <b>' + g.worst.label + '</b> (' +
          g.worst.n + ' из ' + g.coins + ')';
      }
      out += '</span>';
    }

    var L = p.losers || [];
```

### было

```python
    var out = '<div class="obz-blocks">';
```

### стало

```python
    /* Список пробелов конкретной монеты. Идёт последним: сначала то,
       что известно, потом то, что предстоит дописать. */
    var gaps = '';
    if (c.gaps && c.gaps.length) {
      gaps = '<div class="obz-gaps"><i>заполнить руками</i>' +
        c.gaps.map(function (t) { return '<b>' + t + '</b>'; }).join(' · ') +
        '</div>';
    }

    var out = '<div class="obz-blocks">';
```

### было

```python
    return out + '</div>';
  }

  function closeZoom() { zoom.classList.remove('on'); }
```

### стало

```python
    return out + gaps + '</div>';
  }

  function closeZoom() { zoom.classList.remove('on'); }
```
