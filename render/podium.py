"""Лидеры прогона · объёмная сцена под сводкой при входе.

dashboard.py только вызывает render_podium() и вставляет результат,
как и в случае brief.py.

Экран свой, а не блок внутри сводки. Первая редакция жила внутри
.ob-brief — и не появлялась вовсе: там position:fixed с
justify-content:center и без прокрутки, а текст плюс сцена в шестьсот
пикселей высотой в окно не помещаются. Столбики уезжали за нижний край
без возможности доскроллить. Своим слоем сцена получает всю высоту, и
порядок чтения становится явным: сначала что происходит сейчас, потом
кто в журнале и что с ними.

Данных своих у модуля нет: он читает window.ORB.stars, который
выставляет render.orbit. Второй источник тех же чисел разошёлся бы
с орбитой при первой правке, и монета показывала бы на двух экранах
разные значения.

Что чем закодировано — и почему именно так:

  высота столбика   расстояние от дна (up_from_low)
                    Ход с момента попадания в журнал сюда не годится:
                    он зависит от даты, когда монету заметили, и
                    одинаковые столбики означали бы лишь совпадение
                    дат. Расстояние от дна — свойство самой монеты,
                    поэтому столбики сравнимы между собой.

  цвет              подкейс, та же палитра, что у звёзд на орбите.
                    Семейство цвета несёт стадию: холодные у дна,
                    тёплые в движении, ржавый после.

  линия над         объём СЕЙЧАС, максимум кратности по 1ч/4ч/1д.
                    Единственная величина здесь, которая меняется
                    между прогонами, — ей и место в самом заметном
                    канале.

  радиус звезды     РЕКОРД объёма за всё наблюдение (поле x). В
                    журнале vol_ratio сливается через _merge_max,
                    то есть хранит максимум, а не последнее значение.
                    Пара говорящая: линия про сегодня, радиус про то,
                    на что монета была способна.

  линия внутри      две недели цены, время снизу вверх.

Монеты без данных текущего прогона рисуются блеклыми блоками на
переднем плане. Они в журнале и обязаны быть на экране: сцена,
показывающая одни успехи, отвечает не на тот вопрос — журнал заведён
мерить, чем кончилось.
"""

from __future__ import annotations


def render_podium() -> str:
    return PODIUM_HTML + PODIUM_JS


PODIUM_HTML = """
<div class="ob-podium" id="obPodium">
  <div class="obp-in">
    <div class="obp-h">лидеры прогона</div>
    <div class="obp-scene" id="obfPodium"></div>
    <div class="obp-cap" id="obfPodiumCap"></div>
    <div class="obp-foot">клик в любом месте — к дашборду</div>
  </div>
</div>
"""


PODIUM_JS = """
<script>
(function () {
  var host = document.getElementById('obfPodium');
  if (!host) return;

  /* Молчаливый выход опаснее отказа: пустой экран неотличим от
     сломанного модуля, и первый же прогон на --limit 1 стоил
     получаса разбора — сцены не было, а почему, сказать было
     нечем. Дальше все ранние выходы пишут причину. */
  function bail(why) {
    var n = document.createElement('div');
    n.className = 'obp-empty';
    n.textContent = why;
    host.appendChild(n);
  }

  var O = window.ORB || {};
  var STARS = (O.stars || []).slice();
  if (!STARS.length) { bail('журнал лидеров пуст'); return; }

  /* Палитра и стадии — те же, что у звёзд на орбите. Держать здесь
     копию таблицы пришлось бы синхронизировать руками, поэтому берём
     из ORB, а свой список оставляем только запасным. */
  var STRAT = O.strat || {
    hidden:  { c: '#7FE3D4', stage: 0 }, spring:   { c: '#6FC9E8', stage: 0 },
    churn:   { c: '#F0B85C', stage: 1 }, taker:    { c: '#FFD98A', stage: 1 },
    leverage:{ c: '#E89AB0', stage: 1 }, fuel:     { c: '#C4703A', stage: 2 }
  };
  var NONE = { c: '#8D97A6', stage: -1 };
  var stratOf = function (s) { return STRAT[s.st] || NONE; };

  var NS = 'http://www.w3.org/2000/svg';
  function el(n, a) {
    var e = document.createElementNS(NS, n);
    for (var k in a) e.setAttribute(k, a[k]);
    return e;
  }
  function anim(node, cls, d) {
    node.setAttribute('class', cls);
    node.setAttribute('style', '--d:' + d.toFixed(2) + 's');
    return node;
  }
  /* Осветление цвета стратегии под текст: чистый цвет на теле
     столбика, тонированном тем же цветом, съедается подложкой. */
  function lift(hex, k) {
    var n = parseInt(hex.slice(1), 16), m = function (v) {
      return Math.round(v + (255 - v) * k); };
    return '#' + [m(n >> 16 & 255), m(n >> 8 & 255), m(n & 255)]
      .map(function (v) { return ('0' + v.toString(16)).slice(-2); }).join('');
  }
  function hash(s) {
    var h = 0;
    for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
    return function () { h = (h * 1103515245 + 12345) | 0;
      return ((h >>> 16) & 0x7fff) / 0x7fff; };
  }

  var volNow = function (s) {
    return Math.max(+s.v1h || 0, +s.v4h || 0, +s.v1d || 0); };

  /* Столбик получают монеты, по которым есть данные прогона и виден
     ход от дна. Остальные — блоки переднего плана: у них нечего
     ставить в высоту, и рисовать им плинтус значило бы утверждать,
     что они у самого дна, хотя мы просто не знаем. */
  var BARS = [], CUBES = [];
  STARS.forEach(function (s) {
    ((s.series && s.series.length >= 4 && (+s.up || 0) >= 12) ? BARS : CUBES)
      .push(s);
  });
  if (!BARS.length) {
    /* Самый частый случай — отладочный прогон: при явном --limit
       монеты журнала в выборку не добираются, у них нет ни ряда
       цены, ни расстояния от дна, и столбику неоткуда взяться. */
    bail('в журнале ' + STARS.length + ' монет, но ни по одной нет ' +
         'данных прогона — столбику неоткуда взяться. Обычно это ' +
         'прогон с --limit: монеты журнала в выборку не добираются.');
    return;
  }

  var VB_W = 1240, VB_H = 600;
  var CX = VB_W / 2, GROUND = 452;
  var GAP = 10, DX = 13, DY = -10;
  var HMIN = 46, HMAX = 196;

  /* Ширина столбика подстраивается под число монет: журнал держит
     записи LEADERS_MAX_AGE_DAYS, и их бывает и восемь, и тридцать.
     Фиксированная ширина в первом случае оставляла бы дыру, во
     втором уводила бы край сцены за кадр. */
  var BW = Math.max(14, Math.min(36, Math.floor(980 / BARS.length) - GAP));

  var maxLow = Math.max.apply(null, BARS.map(function (s) {
    return +s.up || 0; })) || 1;
  /* Степенная шкала: расстояние от дна расходится на порядок, и при
     линейной весь хвост лёг бы в плинтус. */
  var hOf = function (v) {
    return HMIN + (HMAX - HMIN) * Math.pow((+v || 0) / maxLow, 0.62); };

  /* Порядок — гора: самое высокое в центре, дальше по убыванию в обе
     стороны. Ранг слева направо от этого не читается, и его несут
     подписи; зато центральная группа становится самой плотной, что и
     держит композицию. */
  var sorted = BARS.slice().sort(function (a, b) {
    return (+b.up || 0) - (+a.up || 0); });
  var L = [], R = [];
  sorted.forEach(function (x, i) { (i % 2 ? L : R).push(x); });
  var ORDER = L.reverse().concat(R);

  var svg = el('svg', { viewBox: '0 0 ' + VB_W + ' ' + VB_H,
    'class': 'pd-svg', role: 'img',
    'aria-label': 'Лидеры прогона: расстояние от дна и объём' });
  var defs = el('defs');
  svg.appendChild(defs);

  function grad(id, stops, x1, y1, x2, y2) {
    var g = el('linearGradient', { id: id, x1: x1, y1: y1, x2: x2, y2: y2 });
    stops.forEach(function (s) {
      g.appendChild(el('stop', { offset: s[0], 'stop-color': s[1],
        'stop-opacity': s[2] === undefined ? 1 : s[2] }));
    });
    defs.appendChild(g);
  }
  function rgrad(id, stops) {
    var g = el('radialGradient', { id: id });
    stops.forEach(function (s) {
      g.appendChild(el('stop', { offset: s[0], 'stop-color': s[1],
        'stop-opacity': s[2] === undefined ? 1 : s[2] }));
    });
    defs.appendChild(g);
  }

  /* Тело столбика тонируется стратегией К ВЕРШИНЕ, низ у всех общий.
     Разный цвет по всей высоте разорвал бы сцену на группы; общий
     расплав внизу говорит, что растут все из одного места. */
  Object.keys(STRAT).forEach(function (k) {
    grad('pd-f-' + k, [[0, '#2A1105'], [.26, '#8E3A0B'], [.58, '#F08A2A'],
      [.84, STRAT[k].c], [1, '#FFF0C8']], '0%', '100%', '0%', '0%');
  });
  grad('pd-f-none', [[0, '#2A1105'], [.5, '#6B4A38'], [1, '#B9B3AA']],
    '0%', '100%', '0%', '0%');
  grad('pd-side', [[0, '#180A03'], [.5, '#6B2A08'], [1, '#B85E1B']],
    '0%', '100%', '0%', '0%');
  grad('pd-top', [[0, '#FFF6DC'], [1, '#FFC24D']], '0%', '0%', '100%', '100%');
  rgrad('pd-lava', [[0, '#FFE9B8', .95], [.28, '#FF8A1E', .65],
    [.62, '#C43C05', .25], [1, '#3A0F02', 0]]);
  rgrad('pd-haze', [[0, '#FF8A1E', .22], [1, '#FF8A1E', 0]]);

  [['pd-soft', 9], ['pd-soft-s', 3.2], ['pd-glow', 2.4],
   ['pd-soft-l', 24]].forEach(function (f) {
    var fl = el('filter', { id: f[0], x: '-60%', y: '-60%',
      width: '220%', height: '220%' });
    fl.appendChild(el('feGaussianBlur', { stdDeviation: f[1] }));
    defs.appendChild(fl);
  });

  var lava = el('g'), behind = el('g'), bars = el('g'), front = el('g');
  [lava, behind, bars, front].forEach(function (g) { svg.appendChild(g); });

  /* Основание: зарево, пятна, каркасные дуги. Каркас важнее свечения —
     без него рельеф читается как туман, а не как масса. */
  lava.appendChild(anim(el('ellipse', { cx: CX, cy: GROUND + 40, rx: 470,
    ry: 82, fill: 'url(#pd-lava)', filter: 'url(#pd-soft-l)',
    opacity: .85 }), 'pd-fade', 0));
  var r0 = hash('lava');
  for (var i = 0; i < 18; i++) {
    var a = r0() * Math.PI * 2, rr = Math.pow(r0(), .6);
    lava.appendChild(el('ellipse', {
      cx: CX + Math.cos(a) * rr * 420, cy: GROUND + 26 + Math.sin(a) * rr * 52,
      rx: 24 + r0() * 62, ry: 7 + r0() * 16, fill: 'url(#pd-lava)',
      filter: 'url(#pd-soft)', opacity: (.14 + r0() * .44).toFixed(2) }));
  }
  for (var i = 0; i < 8; i++) {
    lava.appendChild(el('ellipse', { cx: CX, cy: GROUND + 30,
      rx: 120 + i * 44, ry: 20 + i * 7.2, fill: 'none', stroke: '#FF9A2E',
      'stroke-width': (.9 - i * .07).toFixed(2),
      opacity: (.26 - i * .028).toFixed(3) }));
  }

  var totalW = ORDER.length * BW + (ORDER.length - 1) * GAP;
  var x0 = CX - totalW / 2;

  ORDER.forEach(function (c, i) {
    var r = hash(c.t);
    var sc = stratOf(c);
    var sid = STRAT[c.st] ? c.st : 'none';
    var h = hOf(c.up);
    var x = x0 + i * (BW + GAP);
    var y = GROUND - h;
    var d = Math.abs(x + BW / 2 - CX) / (totalW / 2);
    var core = +(1 - d * 0.42).toFixed(2);
    var dB = 0.22 + i * 0.03;

    bars.appendChild(el('ellipse', { cx: x + BW / 2, cy: GROUND + 5,
      rx: BW * 1.35, ry: 13, fill: 'url(#pd-haze)', filter: 'url(#pd-soft)',
      opacity: (.5 * core).toFixed(2) }));

    bars.appendChild(anim(el('path', { d: 'M' + (x + BW) + ' ' + y +
      ' L' + (x + BW + DX) + ' ' + (y + DY) +
      ' L' + (x + BW + DX) + ' ' + (GROUND + DY) +
      ' L' + (x + BW) + ' ' + GROUND + ' Z',
      fill: 'url(#pd-side)', opacity: core }), 'pd-grow', dB));

    bars.appendChild(anim(el('rect', { x: x, y: y, width: BW, height: h,
      fill: 'url(#pd-f-' + sid + ')', opacity: core }), 'pd-grow', dB));

    /* ── Две недели цены внутри столбика ──
       Время снизу вверх, отклонение влево-вправо. Утверждение цельное:
       столбик говорит, СКОЛЬКО прошло, линия внутри — КАК шло.

       Три слоя. Тёмный канал обязателен: оранжевое на оранжевом без
       него не отделяется, а с ним линия читается прорезью в теле, а
       не наклейкой поверх. */
    var ser = (c.series || []).slice(-14);
    if (ser.length >= 4) {
      var lo = Math.min.apply(null, ser), hi = Math.max.apply(null, ser);
      var rng = (hi - lo) || 1, amp = BW * 0.30;
      var path = ser.map(function (v, k) {
        var t = k / (ser.length - 1);
        return (k ? 'L' : 'M') +
          (x + BW / 2 + ((v - lo) / rng - 0.5) * 2 * amp).toFixed(1) + ' ' +
          (GROUND - 5 - t * (h - 10)).toFixed(1);
      }).join(' ');
      var dPx = 0.5 + i * 0.03;
      bars.appendChild(anim(el('path', { d: path, fill: 'none',
        stroke: '#150902', 'stroke-width': 4, opacity: (.68 * core).toFixed(2),
        'stroke-linejoin': 'round', 'stroke-linecap': 'round' }), 'pd-px', dPx));
      bars.appendChild(anim(el('path', { d: path, fill: 'none',
        stroke: '#FF7A18', 'stroke-width': 3.4, filter: 'url(#pd-glow)',
        opacity: (.85 * core).toFixed(2),
        'stroke-linejoin': 'round', 'stroke-linecap': 'round' }), 'pd-px', dPx));
      bars.appendChild(anim(el('path', { d: path, fill: 'none',
        stroke: '#FFC44D', 'stroke-width': 1.4, opacity: core,
        'stroke-linejoin': 'round', 'stroke-linecap': 'round' }), 'pd-px', dPx));

      var lastX = x + BW / 2 +
        ((ser[ser.length - 1] - lo) / rng - 0.5) * 2 * amp;
      bars.appendChild(el('circle', { cx: lastX.toFixed(1),
        cy: (GROUND - 5 - (h - 10)).toFixed(1), r: 5,
        fill: '#FF9A1E', opacity: (.5 * core).toFixed(2),
        filter: 'url(#pd-glow)' }));
      bars.appendChild(el('circle', { cx: lastX.toFixed(1),
        cy: (GROUND - 5 - (h - 10)).toFixed(1), r: 2.1,
        fill: '#FFE9B8', opacity: core }));
    }

    bars.appendChild(anim(el('path', { d: 'M' + x + ' ' + y +
      ' L' + (x + DX) + ' ' + (y + DY) + ' L' + (x + BW + DX) + ' ' + (y + DY) +
      ' L' + (x + BW) + ' ' + y + ' Z',
      fill: 'url(#pd-top)', opacity: core }), 'pd-rise', dB + 0.3));
    bars.appendChild(anim(el('path', { d: 'M' + x + ' ' + y +
      ' L' + (x + BW) + ' ' + y, stroke: '#FFF6DC', 'stroke-width': 1.6,
      opacity: core }), 'pd-rise', dB + 0.3));

    /* Имя на вершине. Пять знаков — предел при таком шаге колонки;
       обрезанные помечены многоточием, иначе «1000C» читается как
       настоящий тикер, а «MUBAR» и «MUBARAK» — как разные монеты. */
    var short = c.t.length > 5 ? c.t.slice(0, 5) + '\\u2026' : c.t;
    var tk = el('text', { x: x + BW / 2 + DX / 2, y: y + DY - 11,
      'text-anchor': 'middle', 'font-size': 9, 'letter-spacing': 1.1,
      'font-weight': 500, fill: lift(sc.c, .55), stroke: '#1A0B04',
      'stroke-width': 3, 'paint-order': 'stroke',
      opacity: (.95 * core).toFixed(2) });
    tk.textContent = short;
    bars.appendChild(anim(tk, 'pd-rise', dB + 0.42));

    /* ── Линия объёма и звезда ──
       Линия начинается выше имени, а не от кромки: иначе проходит
       сквозь надпись, и обводка спасает лишь частично. */
    var vol = volNow(c);
    var vn = Math.min(1, Math.log(1 + vol) / Math.log(27));
    var lh = 30 + vn * 190;
    var lx = x + BW / 2 + DX / 2;
    var foot = y + DY - 22;
    var sy = foot - lh;

    behind.appendChild(anim(el('path', { d: 'M' + lx + ' ' + foot +
      ' L' + lx + ' ' + sy, stroke: sc.c,
      'stroke-width': (0.5 + vn * 1.9).toFixed(2),
      opacity: (.14 + vn * .46).toFixed(2) }), 'pd-grow', 0.7 + i * 0.03));
    if (vn > .62) {
      behind.appendChild(el('path', { d: 'M' + lx + ' ' + foot +
        ' L' + lx + ' ' + sy, stroke: sc.c, 'stroke-width': 5,
        opacity: (vn * .22).toFixed(2), filter: 'url(#pd-soft-s)' }));
    }

    /* Радиус — рекорд объёма (поле x), яркость — свежесть записи.
       Две величины на одном объекте, но по разным каналам: размер
       спрашивает «на что способна», свечение — «давно ли в журнале». */
    var fr = Math.max(0, Math.min(1, +c.f || 0));
    var vmn = Math.min(1, Math.log(1 + (+c.x || 0)) / Math.log(61));
    var sr = 3 + vmn * 8.6;
    behind.appendChild(el('circle', { cx: lx, cy: sy, r: sr * 2.9,
      fill: sc.c, opacity: (.09 + fr * .09).toFixed(2),
      filter: 'url(#pd-soft-s)' }));
    behind.appendChild(anim(el('circle', { cx: lx, cy: sy, r: sr,
      fill: sc.c, opacity: (.55 + fr * .4).toFixed(2) }),
      'pd-pop', 1.05 + i * 0.03));
    behind.appendChild(anim(el('circle', { cx: lx, cy: sy, r: sr * 0.42,
      fill: '#FFFDF4', opacity: (.5 + fr * .4).toFixed(2) }),
      'pd-pop', 1.1 + i * 0.03));
    if (c.hot) {
      behind.appendChild(el('circle', { cx: lx, cy: sy, r: sr + 4.5,
        fill: 'none', stroke: sc.c, 'stroke-width': .7, opacity: .34 }));
    }

    /* Капитализация: ×20 на трёхмиллионной монете и на трёхмиллиардной —
       разные события, а масштаб больше взять неоткуда. */
    if (c.cap) {
      var ct = el('text', { x: lx + sr + 6, y: sy + 3, 'text-anchor': 'start',
        'font-size': 7.5, 'letter-spacing': .4, fill: '#9C907C',
        stroke: '#07080C', 'stroke-width': 2.2, 'paint-order': 'stroke',
        opacity: .9 });
      ct.textContent = c.cap;
      behind.appendChild(anim(ct, 'pd-rise', 1.22 + i * 0.03));
    }
  });

  /* Передний план: монеты журнала без данных прогона. */
  var rc = hash('cubes');
  var span = Math.min(1040, Math.max(320, CUBES.length * 96));
  CUBES.forEach(function (c, i) {
    var sc = stratOf(c);
    var w = 46 + rc() * 26, hh = 12 + rc() * 14;
    var x = CX - span / 2 + (i + 0.5) * (span / CUBES.length) - w / 2;
    var y = GROUND + 34 + rc() * 22;
    var op = .16;
    front.appendChild(anim(el('rect', { x: x, y: y - hh, width: w,
      height: hh, fill: sc.c, opacity: op }), 'pd-grow', 1.4 + i * 0.05));
    front.appendChild(el('path', { d: 'M' + x + ' ' + (y - hh) +
      ' L' + (x + 8) + ' ' + (y - hh - 6) + ' L' + (x + w + 8) + ' ' +
      (y - hh - 6) + ' L' + (x + w) + ' ' + (y - hh) + ' Z',
      fill: sc.c, opacity: op * 1.7 }));
    var t = el('text', { x: x + w / 2, y: y + 14, 'text-anchor': 'middle',
      'font-size': 8, 'letter-spacing': 1.2, fill: lift(sc.c, .2),
      stroke: '#07080C', 'stroke-width': 2.2, 'paint-order': 'stroke',
      opacity: .75 });
    t.textContent = c.t.length > 5 ? c.t.slice(0, 5) + '\\u2026' : c.t;
    front.appendChild(anim(t, 'pd-rise', 1.52 + i * 0.05));
  });

  host.appendChild(svg);

  var cap = document.getElementById('obfPodiumCap');
  if (cap) {
    cap.textContent = 'высота · от дна   ·   линия · объём сейчас   ·   ' +
      'радиус · рекорд объёма';
  }

  /* ── Очередь экранов ──────────────────────────────────────────
     Сводка → сцена → дашборд. Подписки на закрытие сводки нет:
     brief.js своё закрытие наружу не отдаёт, а лезть в его
     внутренности значило бы связать два модуля намертво. Вместо
     этого следим за классом .on на самой сводке — он и есть её
     публичное состояние, видимое из разметки.

     Наблюдатель снимается после первого срабатывания: сцена
     показывается один раз за загрузку, дальше она обычный экран. */
  var brief = document.getElementById('obBrief');
  var pod = document.getElementById('obPodium');
  if (!pod) return;

  function show() {
    pod.classList.add('on');
    var t = setTimeout(hide, 26000);
    function hide() { clearTimeout(t); pod.classList.remove('on'); }
    pod.addEventListener('click', hide);
    document.addEventListener('keydown', function () {
      if (pod.classList.contains('on')) hide();
    });
  }

  if (!brief) { show(); return; }

  var seen = brief.classList.contains('on');
  var mo = new MutationObserver(function () {
    var on = brief.classList.contains('on');
    if (on) { seen = true; return; }
    /* Сводка закрылась — но только если до этого открывалась.
       Без флага сцена выскакивала бы сразу при загрузке, пока
       сводка ещё не успела получить свой класс. */
    if (seen) { mo.disconnect(); show(); }
  });
  mo.observe(brief, { attributes: true, attributeFilter: ['class'] });
})();
</script>
"""
