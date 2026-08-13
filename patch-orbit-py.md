# Патч · `render/orbit.py`

1994 строки, поэтому патчем. Шесть блоков.

Цвет звезды переходит от кратности объёма к стратегии, семейство цвета
несёт стадию движения. Признак `hot` остаётся, но говорит теперь только
вспышкой и кольцом.

**Стадию радиусом здесь не выражаю.** `starSpot` берёт точку из `SKY` и
требует `band > 0.18` — звезда не садится на кольцо орбиты. При
`CX 500, RX 372, RY 148, CY 281` доступный `rr` идёт до 1.47, из него
вырезано 0.82…1.18, и внешняя область остаётся только по углам кадра.
Двух зон на три стадии не хватает. В прототипе поле было свободным
эллипсом без запретного кольца — там пояса ложились, здесь нет.

---

## 1. Стратегия монеты · `_orbit_stars`

### было

```python
        ratio = _max_vol_ratio(flow_j.get(sym) or {})
        c = by_symbol.get(sym.upper())
```

### стало

```python
        # Запись журнала связывается один раз: раньше она читалась
        # заново в двух местах.
        rec = flow_j.get(sym) or {}
        ratio = _max_vol_ratio(rec)
        c = by_symbol.get(sym.upper())

        # Стратегия, которой монета попала в журнал.
        #
        # Сначала текущий прогон, потом entry_case из журнала. Порядок
        # именно такой: фигура могла смениться с момента попадания, и
        # на экране должно стоять то, что видно сейчас. Но монеты из
        # журнала, выпавшие из текущей выборки, иначе остались бы
        # вовсе без цвета — для них entry_case единственный источник.
        #
        # Префикс flow_ снимается здесь, а не в JS: имя подкейса —
        # это ключ палитры, и разбирать его на стороне отрисовки
        # значит держать знание о формате имён в двух местах.
        case = ""
        if c is not None and c.flow:
            case = str(c.flow.get("case") or "")
        if not case:
            case = str(rec.get("entry_case") or "")
        st = case[5:] if case.startswith("flow_") else case
```

---

## 2. Поле `st` в звезде

### было

```python
            "hot": bool(ratio >= LEAD_X1),
            "x": round(ratio),
```

### стало

```python
            "hot": bool(ratio >= LEAD_X1),
            "x": round(ratio),
            "st": st,
```

---

## 3. Контейнер легенды

### было

```html
  </svg>

<div class="ob-core">
    <div class="ob-core-k">РЕЖИМ РЫНКА</div>
```

### стало

```html
  </svg>

<!-- Легенда рисуется скриптом из той же таблицы STRAT, что красит
     звёзды. Подписи руками однажды разойдутся с палитрой, а легенда,
     которая врёт про цвет, хуже отсутствующей. -->
<div class="ob-leg" id="ob-leg"></div>

<div class="ob-core">
    <div class="ob-core-k">РЕЖИМ РЫНКА</div>
```

---

## 4. Палитра, градиенты и легенда · перед `buildStars`

### было

```js
  function buildStars() {
    var host = document.getElementById('ob-stars');
    STARS.forEach(function (s, idx) {
      var p = starSpot(s.t, idx);
```

### стало

```js
  /* ── Стратегии ───────────────────────────────────────────────
     Цвет звезды несёт подкейс, семейство цвета — стадию движения:
     холодные у предполагаемого дна, тёплые пока движение идёт,
     догорающий когда состоялось.

     Почему не шесть произвольных цветов: семь узлов орбиты уже
     занимают янтарь, золото, зелёный, синий, фиолетовый и ржавый.
     Шесть независимых оттенков сверху дали бы тринадцать значащих
     цветов и два разных языка на одном экране — фиолетовая звезда
     читалась бы как «сектор». Температурная логика отличает звёзды
     от узлов правилом, а не подбором хексов.

     Стадия здесь выражена ТОЛЬКО цветом. Радиусом её выразить
     нельзя: starSpot запрещает полосу ±0.18 вокруг кольца, и на
     три пояса поля не хватает (см. шапку патча). */
  var STRAT = {
    hidden:   { c: '#7FE3D4', n: 'скрытый набор',  stage: 0 },
    spring:   { c: '#6FC9E8', n: 'пружина',        stage: 0 },
    churn:    { c: '#F0B85C', n: 'поглощение',     stage: 1 },
    taker:    { c: '#FFD98A', n: 'агрессия',       stage: 1 },
    leverage: { c: '#E89AB0', n: 'перекос плеча',  stage: 1 },
    fuel:     { c: '#C4703A', n: 'топливо сверху', stage: 2 }
  };

  /* Монета из журнала, выпавшая из текущей выборки и не имеющая
     entry_case. Серый, а не цвет какой-нибудь стратегии: неизвестное
     обязано выглядеть неизвестным, иначе оно читается как факт. */
  var STRAT_NONE = { c: '#8D97A6', n: 'фигура неизвестна', stage: -1 };

  var STAGE = [
    'у предполагаемого дна',
    'движение идёт',
    'движение состоялось'
  ];

  /* Градиенты под каждую стратегию делаются скриптом, а не руками в
     defs: шесть подкейсов на два градиента — двенадцать блоков,
     которые пришлось бы править синхронно с палитрой. Здесь цвет
     живёт в одном месте. */
  function tintGrad(id, c, halo) {
    if (document.getElementById(id)) return id;
    /* defs берётся у того же SVG, в котором лежат звёзды, а не первым
       попавшимся в документе: карточки монет тоже рисуют инлайновые
       SVG со спарклайнами, и querySelector нашёл бы их, если бы они
       оказались раньше по разметке. Здесь связь прямая. */
    var stars = document.getElementById('ob-stars');
    var scene = stars && stars.ownerSVGElement;
    if (!scene) return id;
    var defs = scene.querySelector('defs');
    if (!defs) {
      defs = el('defs', {});
      scene.insertBefore(defs, scene.firstChild);
    }
    var g = el('radialGradient', { id: id });
    var stops = halo
      ? [[0, '#FFFDF6', .85], [0.14, c, .48], [0.42, c, .14], [1, c, 0]]
      : [[0, '#FFFDF6', 1], [0.20, c, 1], [0.55, c, .74], [1, c, 0]];
    stops.forEach(function (st) {
      g.appendChild(el('stop', {
        offset: st[0], 'stop-color': st[1], 'stop-opacity': st[2] }));
    });
    defs.appendChild(g);
    return id;
  }

  function stratOf(s) { return STRAT[s.st] || STRAT_NONE; }

  /* Легенда строится только по тем стратегиям, которые в прогоне
     реально сработали. Полный список из шести объяснял бы цвета,
     которых на экране нет, и заставлял бы искать несуществующее. */
  function buildLegend() {
    var host = document.getElementById('ob-leg');
    if (!host) return;
    var live = {};
    STARS.forEach(function (s) { if (STRAT[s.st]) live[s.st] = 1; });
    var keys = Object.keys(live);
    if (!keys.length) { host.style.display = 'none'; return; }

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
  }

  function buildStars() {
    var host = document.getElementById('ob-stars');
    Object.keys(STRAT).forEach(function (k) {
      tintGrad('ob-sg-' + k, STRAT[k].c, false);
      tintGrad('ob-sh-' + k, STRAT[k].c, true);
    });
    tintGrad('ob-sg-none', STRAT_NONE.c, false);
    tintGrad('ob-sh-none', STRAT_NONE.c, true);
    buildLegend();

    STARS.forEach(function (s, idx) {
      var sc = stratOf(s);
      var sid = STRAT[s.st] ? s.st : 'none';
      var p = starSpot(s.t, idx);
```

---

## 5. Цвет звезды

### было

```js
      var col = s.hot ? '#FFD98A' : '#BFDCFF';
      var grad = s.hot ? 'url(#ob-starG)' : 'url(#ob-starS)';
      var accent = 'url(#ob-starG)';

      /* Ореол ярче и плотнее у центра: именно он читается как свечение,
         лучи только задают характер. */
      g.appendChild(el('circle', { r: r * 2.2,
        fill: s.hot ? 'url(#ob-starH)' : 'url(#ob-starHc)',
        opacity: op.toFixed(2) }));
```

### стало

```js
      /* Цвет отдан стратегии. Прежде его нёс объём: золото у ×50 и
         выше, холодное серебро ниже — то есть «горячая» и «золотая»
         были одним и тем же признаком. Кратность объёма при этом
         никуда не делась: она осталась вспышкой и кольцом ниже, а
         цвет освободился под то, чего на экране не было вовсе, —
         под то, КАКАЯ фигура сработала. */
      var col = sc.c;
      var grad = 'url(#ob-sg-' + sid + ')';
      var accent = grad;

      /* Ореол ярче и плотнее у центра: именно он читается как свечение,
         лучи только задают характер. */
      g.appendChild(el('circle', { r: r * 2.2,
        fill: 'url(#ob-sh-' + sid + ')',
        opacity: op.toFixed(2) }));
```

---

## 6. Подпись тикера

### было

```js
      var t = el('text', {
        class: 'ob-star-lbl' + (s.lead ? ' lead' : ''),
        x: dx, y: s.up ? -0.6 : 1.8, 'text-anchor': anchor,
        fill: s.hot || s.lead ? '#FFD98A' : '#DCE6F2', opacity: '.95'
      });
```

### стало

```js
      /* Подпись красится стратегией, а не признаком объёма: тикер и
         звезда обязаны читаться как одно целое, иначе цвет придётся
         сопоставлять глазами. Лидер прогона сохраняет своё золото —
         это про место в прогоне, а не про фигуру. */
      var t = el('text', {
        class: 'ob-star-lbl' + (s.lead ? ' lead' : ''),
        x: dx, y: s.up ? -0.6 : 1.8, 'text-anchor': anchor,
        fill: s.lead ? '#FFD98A' : col, opacity: '.95'
      });
```
