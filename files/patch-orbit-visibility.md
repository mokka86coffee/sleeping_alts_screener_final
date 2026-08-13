# Патч · `render/orbit.py` — видимость звёзд и легенда

Ставится поверх `patch-orbit-py.md`. Семь блоков.

**Главная причина, по которой звёзды тусклые, — не размер.**
Прозрачность считается из `rate(s)`, а `rate` читает `s.days`, которого
Python в звезду никогда не клал. Значит `rt === null` у всех без
исключения, `rateNorm` фиксируется на 0.5, и каждая звезда получает
`op = 0.43` — независимо ни от чего. Канал яркости мёртв с тех пор, как
его завели: ровно тот же класс, что `firstRun` и `streak`.

---

## 1. Имена подкейсов уходят в данные

Легенда называла fuel «топливо сверху», а чип карточки — «путь
свободен», потому что я завёл второй список имён в скрипте. Список
уже есть один — `CASE_RU` во `flow_report`, и `orbit.py` его
импортирует.

### было

```python
    blob = json.dumps({"nodes": nodes, "stars": stars, "market": market},
                      ensure_ascii=False).replace("<", "\\u003c")
```

### стало

```python
    # CASE_RU уходит в данные, а не дублируется в скрипте. Имя подкейса
    # уже названо один раз во flow_report и оттуда же попадает в чип
    # карточки; второй список в JS разошёлся с первым сразу — легенда
    # говорила «топливо сверху», карточка «путь свободен», и это про
    # одну и ту же монету на одном экране.
    blob = json.dumps({"nodes": nodes, "stars": stars, "market": market,
                       "names": CASE_RU},
                      ensure_ascii=False).replace("<", "\\u003c")
```

---

## 2. Возраст записи в звезде

`rate()` читает `s.days`, а Python его не отдаёт. Возраст уже посчитан
в `ages` строкой выше — не доезжал только до звезды.

### было

```python
            "x": round(ratio),
            "st": st,
```

### стало

```python
            "x": round(ratio),
            "st": st,
            # Возраст записи в журнале. Его читает rate() при расчёте
            # яркости, и без него ВСЕ звёзды получали одну и ту же
            # прозрачность 0.43: rate возвращал null, темп подменялся
            # серединой шкалы. Канал был мёртв с момента заведения.
            "days": (round(ages[sym]) if ages[sym] is not None else 0),
```

---

## 3. Таблица стратегий без имён

### было

```js
  var STRAT = {
    hidden:   { c: '#7FE3D4', n: 'скрытый набор',  stage: 0 },
    spring:   { c: '#6FC9E8', n: 'пружина',        stage: 0 },
    churn:    { c: '#F0B85C', n: 'поглощение',     stage: 1 },
    taker:    { c: '#FFD98A', n: 'агрессия',       stage: 1 },
    leverage: { c: '#E89AB0', n: 'перекос плеча',  stage: 1 },
    fuel:     { c: '#C4703A', n: 'топливо сверху', stage: 2 }
  };
```

### стало

```js
  /* Здесь только цвет и стадия. Имя приходит из CASE_RU через данные:
     оно уже названо в одном месте и попадает в чип карточки, а второй
     список рядом гарантированно разойдётся с первым. */
  var NAMES = DATA.names || {};
  var STRAT = {
    hidden:   { c: '#7FE3D4', stage: 0 },
    spring:   { c: '#6FC9E8', stage: 0 },
    churn:    { c: '#F0B85C', stage: 1 },
    taker:    { c: '#FFD98A', stage: 1 },
    leverage: { c: '#E89AB0', stage: 1 },
    fuel:     { c: '#C4703A', stage: 2 }
  };
  function stratName(k) { return NAMES[k] || k; }
```

---

## 4. Заглушка тоже без имени

### было

```js
  var STRAT_NONE = { c: '#8D97A6', n: 'фигура неизвестна', stage: -1 };
```

### стало

```js
  var STRAT_NONE = { c: '#8D97A6', stage: -1 };
```

---

## 5. Легенда: тикеры вместо счётчиков, сворачивание в полоску

Счётчик «сколько попало в стадию» ни на один вопрос не отвечает: число
и так видно по звёздам. Полезно обратное — какие именно монеты.

### было

```js
    var html = '<div class="ob-leg-h">стратегии</div>';
    STAGE.forEach(function (title, i) {
      var inStage = keys.filter(function (k) { return STRAT[k].stage === i; });
      if (!inStage.length) return;
      html += '<div class="ob-leg-g"><div class="ob-leg-s">' + title + '</div>';
      inStage.forEach(function (k) {
        var n = STARS.filter(function (s) { return s.st === k; }).length;
        html += '<div class="ob-leg-r">' +
          '<span class="ob-leg-d" style="background:' + STRAT[k].c +
          ';color:' + STRAT[k].c + '"></span>' +
          '<span class="ob-leg-n">' + STRAT[k].n + '</span>' +
          '<span class="ob-leg-x">' + n + '</span></div>';
      });
      html += '</div>';
    });
    host.innerHTML = html;
```

### стало

```js
    /* Шапка живёт всегда и в свёрнутом виде остаётся единственным,
       что видно: ряд цветных точек. Когда открыта карточка монеты,
       легенда мешает — но исчезать ей нельзя, иначе цвет звезды под
       карточкой становится нечитаемым. Поэтому сворачивается, а не
       прячется, и раскрывается наведением. */
    var dots = keys.map(function (k) {
      return '<i class="ob-leg-d" style="background:' + STRAT[k].c +
             ';color:' + STRAT[k].c + '"></i>';
    }).join('');
    var html = '<div class="ob-leg-h"><span>стратегии</span>' +
               '<span class="ob-leg-dots">' + dots + '</span></div>' +
               '<div class="ob-leg-body">';

    STAGE.forEach(function (title, i) {
      var inStage = keys.filter(function (k) { return STRAT[k].stage === i; });
      if (!inStage.length) return;
      html += '<div class="ob-leg-g"><div class="ob-leg-s">' + title + '</div>';
      inStage.forEach(function (k) {
        /* Тикеры, а не счётчик. Сколько монет в стадии — видно по
           самим звёздам; чего по ним не видно, так это КТО именно,
           потому что подписи мелкие и разбросаны по всему полю. */
        var syms = STARS.filter(function (s) { return s.st === k; })
                        .map(function (s) { return s.t; });
        html += '<div class="ob-leg-r">' +
          '<span class="ob-leg-d" style="background:' + STRAT[k].c +
          ';color:' + STRAT[k].c + '"></span>' +
          '<span class="ob-leg-n">' + stratName(k) + '</span></div>' +
          '<div class="ob-leg-c" style="color:' + STRAT[k].c + '">' +
          syms.join(' · ') + '</div>';
      });
      html += '</div>';
    });
    host.innerHTML = html + '</div>';
```

---

## 6. Размер и яркость звезды

### было

```js
      var r = (s.lead ? 4 : 2.4) + f * 2.1;
```

### стало

```js
      /* Было 2.4..4.5 у обычной звезды. При поле 1000×563 это точка в
         три пикселя с подписью в 5.7 — цвет на такой площади не
         различается вовсе, а именно цвет теперь несёт стратегию.
         Увеличено примерно вдвое; коллизии разводит starSpot, у
         которого порог расстояния поднят тем же патчем. */
      var r = (s.lead ? 6.2 : 4.2) + f * 3.4;
```

### было

```js
            var op = 0.18 + rateNorm * 0.5;
```

### стало

```js
            /* Нижняя граница поднята с 0.18 до 0.46. Прежняя ставилась
               в расчёте на живой темп, но rate() читал s.days, которого
               в звезде не было — величина всегда возвращала null, и
               ВСЕ звёзды садились на 0.43. Теперь days приходит, темп
               считается, и пол нужен другой: даже самая медленная
               звезда обязана читаться цветом. */
            var op = 0.46 + rateNorm * 0.42;
```

---

## 7. Наложение звёзд

Две причины. `PLACED` живёт между вызовами и не чистится, а запасная
раскладка по золотому углу вообще не проверяет соседей — именно она
кладёт звёзды друг на друга, когда перебор не нашёл места.

### было

```js
  function buildStars() {
    var host = document.getElementById('ob-stars');
```

### стало

```js
  function buildStars() {
    var host = document.getElementById('ob-stars');
    /* Список занятых мест чистится при каждой сборке. Без этого
       повторный рендер видел все прежние точки занятыми, перебор
       упирался в лимит и уходил в запасную раскладку — где проверки
       на соседей нет вовсе. */
    PLACED.length = 0;
```

### было

```js
      if (band > 0.18 && !inCard && !nearNode && !tooClose) {
```

### стало

```js
      /* Порог расстояния поднят с 78 до 96 вместе с размером звезды:
         прежний ставился под радиус 4.5, при 7.6 подписи снова
         наезжают. Считается в tooClose выше по функции. */
      if (band > 0.18 && !inCard && !nearNode && !tooClose) {
```

### было

```js
        if (Math.hypot(PLACED[m].x - x, PLACED[m].y - y) < 78) { tooClose = true; break; }
```

### стало

```js
        if (Math.hypot(PLACED[m].x - x, PLACED[m].y - y) < 96) { tooClose = true; break; }
```

### было

```js
    var ga = idx * 2.39996;
    var fr = 1.22 + (idx % 3) * 0.16;
    var fb = {
      x: Math.min(SKY.x1, Math.max(SKY.x0, CX + Math.cos(ga) * RX * fr)),
      y: Math.min(SKY.y1, Math.max(SKY.y0, CY + Math.sin(ga) * RY * 1.35 * fr))
    };
    PLACED.push(fb);
    return fb;
```

### стало

```js
    /* Запасная раскладка теперь тоже разводит соседей. Прежняя ставила
       точку по золотому углу и возвращала её как есть — а попадали
       сюда именно те звёзды, которым не нашлось места, то есть на
       плотном поле их несколько, и ложились они друг на друга.
       Спираль расширяется, пока не найдёт свободное место либо не
       упрётся в потолок попыток. */
    var fb = null;
    for (var t = 0; t < 40; t++) {
      var ga = (idx + t * 7) * 2.39996;
      var fr = 1.22 + ((idx + t) % 3) * 0.16 + t * 0.03;
      var cand = {
        x: Math.min(SKY.x1, Math.max(SKY.x0, CX + Math.cos(ga) * RX * fr)),
        y: Math.min(SKY.y1, Math.max(SKY.y0, CY + Math.sin(ga) * RY * 1.35 * fr))
      };
      var busy = false;
      for (var u = 0; u < PLACED.length; u++) {
        if (Math.hypot(PLACED[u].x - cand.x, PLACED[u].y - cand.y) < 84) {
          busy = true; break;
        }
      }
      if (!busy) { fb = cand; break; }
    }
    if (!fb) {
      var gz = idx * 2.39996;
      fb = {
        x: Math.min(SKY.x1, Math.max(SKY.x0, CX + Math.cos(gz) * RX * 1.3)),
        y: Math.min(SKY.y1, Math.max(SKY.y0, CY + Math.sin(gz) * RY * 1.35 * 1.3))
      };
    }
    PLACED.push(fb);
    return fb;
```

---

## 8. Цветная точка в чипе карточки

Карточка называет стратегию словом, звезда — цветом, и связать их
глазами нельзя. Точка того же цвета в чипе связывает.

### было

```js
        '<span class="ob-sc-chip">' + (s.pattern || '—') + '</span>' +
```

### стало

```js
        '<span class="ob-sc-chip"><i class="ob-sc-dot" style="background:' +
          stratOf(s).c + ';color:' + stratOf(s).c + '"></i>' +
          (s.pattern || '—') + '</span>' +
```
