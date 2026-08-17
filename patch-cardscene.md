# Карточка-пейзаж вместо раскрытой карточки зала

Зал не меняется: панели, ярусы, поворот, отражения остаются как есть.
Меняется только то, что происходит по клику — показ уходит в новый
модуль `render/cardscene.py`, а зал отдаёт ему список и номер монеты.

Перед запуском положить `cardscene.py` в `render/` — скрипт создаёт
только правки, не файлы. Дальше правятся `render/podium.py` (три блока)
и `render/dashboard.py` (два).

---

## 1 · список для листания — `render/podium.py`

Стрелки в раскрытой карточке листают по порядку, в котором монеты стоят
на стене. Значит, этот порядок надо где-то запомнить в момент сборки:
позже он не восстанавливается, сортировка внутри яруса своя у каждого
яруса.

### Было

```js
  /* ── Сборка ── */
  var PANS = [];
  var built = false;
```

### Стало

```js
  /* ── Сборка ── */
  var PANS = [];
  /* Порядок, в котором монеты стоят на стене: сверху вниз по ярусам,
     внутри яруса — по сортировке самого яруса. Стрелки в раскрытой
     карточке листают именно по нему, поэтому «следующая» означает
     «соседняя на стене», а не «следующая в журнале». */
  var ZLIST = [];
  var built = false;
```

---

## 2 · клик по панели — `render/podium.py`

### Было

```js
        d.addEventListener('click', function () { openZoom(c); });
```

### Стало

```js
        var zi = ZLIST.length;
        ZLIST.push(c);
        d.addEventListener('click', function () { openZoom(c, zi); });
```

---

## 3 · раскрытие карточки — `render/podium.py`

Числа для нижнего ящика по-прежнему форматирует зал: свой второй набор
тех же ячеек разошёлся бы с этим при первой правке. Модуль получает
готовую вёрстку и рисует картинку.

### Было

```js
  function openZoom(c) {
    var sc = stratOf(c), col = sc.c, up = Math.round(+c.up || 0);
```

### Стало

```js
  /* Фраза наблюдения для сцены: те же два наблюдения, что и в старой
     сводке, но без обёртки — в пейзаже у неё своё место и свой стиль. */
  function noteText(c) {
    var all = notes(c);
    var day = all.filter(function (n) { return n.span === 'day'; })[0];
    var wk = all.filter(function (n) { return n.span === 'weeks'; })[0];
    var parts = [];
    if (day) parts.push(day.full);
    if (wk) parts.push(wk.full);
    return parts.join(' · ');
  }

  function openZoom(c, zi) {
    /* Карточка-пейзаж живёт в render/cardscene.py и берёт на себя весь
       показ. Если модуль не подключён, работает прежняя карточка ниже —
       это и есть способ сравнить обе, не откатывая правку. */
    if (window.OBCARD && ZLIST.length) {
      window.OBCARD.open(ZLIST, zi || 0,
        function (s) {
          return { note: noteText(s), body: blocksHTML(s, stratOf(s).c) };
        },
        function (t) {
          pod.classList.remove('on');
          if (typeof window.obShowStar === 'function') window.obShowStar(t);
        });
      return;
    }

    var sc = stratOf(c), col = sc.c, up = Math.round(+c.up || 0);
```

---

## 4 · подключение — `render/dashboard.py`

Два места: импорт рядом с остальными модулями `render/` и вызов сразу
после подиума. Порядок в разметке важен только для стилей — карточка
ищет свой корень в DOM в момент открытия, а правила должны быть на
странице раньше.

### Было

```python
from render.orbit import render_orbit
from render.brief import render_brief
from render.podium import render_podium
```

### Стало

```python
from render.orbit import render_orbit
from render.brief import render_brief
from render.podium import render_podium
from render.cardscene import render_cardscene
```

### Было

```python
{render_brief()}
{render_podium()}
{DASH_JS}"""
```

### Стало

```python
{render_brief()}
{render_podium()}
{render_cardscene()}
{DASH_JS}"""
```

## 5 · что удалить потом — не сейчас

Старое тело `openZoom` остаётся рабочим запасным путём. Когда новая
карточка устоится, удалить его и то, что используется только им:
`fan`, `bigGauge`, `segs`, `ticksDays`, `summaryHTML`. Функции `art` и
`h48HTML` не трогать — они рисуют панели на стене зала.
