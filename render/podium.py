"""Лидеры прогона · состояние каждой монеты, отдельным экраном.

dashboard.py вызывает render_podium() и вставляет результат, как и в
случае brief.py.

Сцена со столбиками снята целиком. Она отвечала на вопрос «кто дальше
всех ушёл от дна» и на нём заканчивалась: чтобы понять, что с монетой
происходит СЕЙЧАС, приходилось идти на орбиту и открывать карточки по
одной. Экран лидеров для того и заведён, чтобы этого не делать.

Теперь карточка на монету. Четыре величины, ряд цены и вердикт — ровно
столько, сколько читается беглым взглядом. Пятая величина начала бы
дублировать одну из четырёх, а карточка, которую надо изучать, ничем
не лучше карточки на орбите.

Данных своих у модуля нет: читает window.ORB.stars, который выставляет
render.orbit. Второй источник тех же чисел разошёлся бы с орбитой при
первой правке, и монета показывала бы на двух экранах разное.

СТИЛИ ЛЕЖАТ ЗДЕСЬ, а не в css.py — намеренно. Блок подиума в css.py
трижды дублировался от повторного применения патчей, и каждый раз это
чинилось отдельным скриптом. Модуль, который несёт свою разметку, свой
скрипт и свои стили, разойтись сам с собой не может. Прежние правила
.obp-* и .pd-* в css.py после этой замены мертвы и удаляются.
"""

from __future__ import annotations


def render_podium() -> str:
    return PODIUM_CSS + PODIUM_HTML + PODIUM_JS


PODIUM_CSS = """
<style>
/* ── Экран лидеров ───────────────────────────────────────────
   Третий в очереди: сводка → лидеры → дашборд. Материал тот же, что
   у сводки, вплоть до градиента подложки: переход между экранами
   должен читаться как смена содержимого, а не как другое
   приложение.

   overflow-y:auto обязателен — карточек бывает под шесть десятков,
   и прежняя сцена не прокручивалась вовсе. */
.ob-podium{position:fixed;inset:0;z-index:41;overflow-y:auto;
  background:radial-gradient(1100px 700px at 50% -5%,#0d0b09,#050406 70%);
  opacity:0;pointer-events:none;transition:opacity .5s ease}
.ob-podium.on{opacity:1;pointer-events:auto}
.obp-in{max-width:1480px;margin:0 auto;padding:34px 22px 72px}

.obp-top{display:flex;align-items:baseline;justify-content:space-between;
  gap:20px;flex-wrap:wrap;border-bottom:1px solid rgba(255,255,255,.055);
  padding-bottom:13px}
.obp-h{font-family:ui-monospace,Menlo,monospace;font-size:11px;
  letter-spacing:.34em;text-transform:uppercase;color:#8E96A2}
.obp-stamp{font-family:ui-monospace,Menlo,monospace;font-size:10px;color:#454C57}

.obp-band{margin-top:24px}
.obp-bh{display:flex;align-items:center;gap:9px;margin-bottom:11px}
.obp-bh i{width:7px;height:7px;border-radius:50%;box-shadow:0 0 7px currentColor}
.obp-bh span{font-family:ui-monospace,Menlo,monospace;font-size:9px;
  letter-spacing:.22em;text-transform:uppercase;color:#6C7480}
.obp-bh b{margin-left:auto;font-family:ui-monospace,Menlo,monospace;
  font-size:10px;color:#454C57;font-weight:400}

.obp-grid{display:grid;gap:9px;
  grid-template-columns:repeat(auto-fill,minmax(258px,1fr))}

.obc{background:#0D0F14;border:1px solid rgba(255,255,255,.055);
  border-radius:9px;padding:11px 12px 10px;position:relative;overflow:hidden;
  cursor:pointer;transition:border-color .2s ease,background .2s ease}
.obc:hover{border-color:rgba(255,255,255,.13);background:#11141A}
/* Полоса стратегии слева: тот же цвет, что у звезды на орбите. Узкая
   и без подписи — имя стоит в шапке, полоса нужна чтобы карточки
   читались группами при беглом просмотре. */
.obc::before{content:"";position:absolute;left:0;top:0;bottom:0;width:2px;
  background:currentColor;opacity:.75}

.obc-h{display:flex;align-items:baseline;gap:7px}
.obc-t{font-family:ui-monospace,Menlo,monospace;font-size:14.5px;
  letter-spacing:.05em}
.obc-p{font-size:9.5px;opacity:.72;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}
.obc-cap{margin-left:auto;font-family:ui-monospace,Menlo,monospace;
  font-size:10px;color:#565E6A;white-space:nowrap}

.obc-spark{margin:8px 0 7px;height:34px;display:block;width:100%}

.obc-m{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;
  border-top:1px solid rgba(255,255,255,.055);padding-top:7px}
.obc-m>div{min-width:0}
.obc-k{font-family:ui-monospace,Menlo,monospace;font-size:7.5px;
  letter-spacing:.11em;text-transform:uppercase;color:#454C57;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.obc-v{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;
  margin-top:2px;white-space:nowrap;color:#D6DCE4}
.obc-v.off{color:#454C57}
.obc-v.pos{color:#7FD9A6}

.obc-w{margin-top:7px;font-size:10px;line-height:1.45;color:#6C7480;
  border-top:1px solid rgba(255,255,255,.055);padding-top:6px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
  overflow:hidden}

.obp-foot{margin-top:30px;text-align:center;font-size:7px;letter-spacing:3px;
  text-transform:uppercase;color:#2E2A24}
.obp-empty{max-width:46ch;margin:60px auto;text-align:center;font-size:12px;
  line-height:1.7;color:#5E564A}

/* ── Появление ──
   Карточки проявляются волной по полосам. Задержка приходит инлайном
   через --d: считать её в CSS нечем, а таблица задержек в скрипте
   дублировала бы порядок карточек.

   Анимации стоят на паузе до класса pd-go на слое. Управлять стартом
   через момент сборки ненадёжно: узлы могут оказаться в документе
   раньше показа, и тогда весь разбег отыграет в прозрачном слое. */
@keyframes obp-rise{
  from{opacity:0;transform:translateY(14px)}
  to  {opacity:1;transform:none}
}
.obc,.obp-bh{opacity:0;animation:obp-rise .5s cubic-bezier(.2,.7,.2,1) forwards;
  animation-delay:var(--d,0s);animation-play-state:paused}
.ob-podium.pd-go .obc,.ob-podium.pd-go .obp-bh{animation-play-state:running}

@media (prefers-reduced-motion:reduce){
  .obc,.obp-bh{opacity:1!important;animation:none!important;
    transform:none!important}
}
@media (max-width:900px){
  .obp-grid{grid-template-columns:1fr}
  .obp-in{padding:24px 14px 48px}
}
</style>
"""

PODIUM_HTML = """
<div class="ob-podium" id="obPodium">
  <div class="obp-in">
    <div class="obp-top">
      <div class="obp-h">лидеры прогона</div>
      <div class="obp-stamp" id="obPodStamp"></div>
    </div>
    <div id="obPodBands"></div>
    <div class="obp-foot">клик по карточке — к монете на орбите</div>
  </div>
</div>
"""

PODIUM_JS = """
<script>
(function () {
  var pod = document.getElementById('obPodium');
  var host = document.getElementById('obPodBands');
  if (!pod || !host) return;

  /* Молчаливый выход опаснее отказа: пустой экран неотличим от
     сломанного модуля. Все ранние выходы называют причину. */
  function bail(why) {
    var n = document.createElement('div');
    n.className = 'obp-empty';
    n.textContent = why;
    host.appendChild(n);
  }

  var O = window.ORB || {};
  var STARS = (O.stars || []).slice();

  /* Палитра и стадии — те же, что у звёзд на орбите. Берём из ORB,
     свой список только запасной: третий набор цветов на третьем
     экране гарантированно разойдётся с первыми двумя. */
  var STRAT = O.strat || {
    dormant:  { c: '#7E9AB5', stage: 0 }, hidden:   { c: '#7FE3D4', stage: 0 },
    spring:   { c: '#6FC9E8', stage: 0 }, churn:    { c: '#F0B85C', stage: 1 },
    taker:    { c: '#FFD98A', stage: 1 }, leverage: { c: '#E89AB0', stage: 1 },
    fuel:     { c: '#C4703A', stage: 2 }
  };
  var NONE = { c: '#8D97A6', stage: 1 };
  var STAGE = [
    { n: 'у предполагаемого дна', c: '#7FE3D4' },
    { n: 'движение идёт',         c: '#F0B85C' },
    { n: 'движение состоялось',   c: '#C4703A' }
  ];

  var NS = 'http://www.w3.org/2000/svg';
  function el(n, a) {
    var e = document.createElementNS(NS, n);
    for (var k in a) e.setAttribute(k, a[k]);
    return e;
  }
  function stratOf(s) { return STRAT[s.st] || NONE; }
  function volNow(s) {
    return Math.max(+s.v1h || 0, +s.v4h || 0, +s.v1d || 0);
  }
  function xfmt(v) {
    if (!v) return '\\u2014';
    return v >= 10 ? '\\u00d7' + Math.round(v) : '\\u00d7' + v.toFixed(1);
  }

  /* ── Ряд цены ──
     Настоящий, из _star_card. Рисуется заливкой под линией: у
     половины монет линия почти плоская, и одна линия там не читается
     как форма. */
  function spark(c, col, idx) {
    var ser = (c.series || []).slice(-21);
    var w = 236, h = 34, pad = 3;
    var svg = el('svg', { 'class': 'obc-spark',
      viewBox: '0 0 ' + w + ' ' + h, preserveAspectRatio: 'none' });
    if (ser.length < 4) return svg;

    var lo = Math.min.apply(null, ser), hi = Math.max.apply(null, ser);
    var rng = (hi - lo) || 1;
    var pts = ser.map(function (v, i) {
      return (i / (ser.length - 1) * w).toFixed(1) + ',' +
             (h - pad - (v - lo) / rng * (h - pad * 2)).toFixed(1);
    });

    /* Идентификатор градиента по индексу, а не по тикеру: тикеры
       бывают с не-латиницей, и они попадали бы в id как есть. */
    var gid = 'obpg' + idx;
    var defs = el('defs', {});
    var lg = el('linearGradient', { id: gid, x1: '0', y1: '0', x2: '0', y2: '1' });
    lg.appendChild(el('stop', { offset: 0, 'stop-color': col, 'stop-opacity': .34 }));
    lg.appendChild(el('stop', { offset: 1, 'stop-color': col, 'stop-opacity': 0 }));
    defs.appendChild(lg);
    svg.appendChild(defs);

    svg.appendChild(el('path', {
      d: 'M0,' + h + ' L' + pts.join(' L') + ' L' + w + ',' + h + ' Z',
      fill: 'url(#' + gid + ')' }));
    svg.appendChild(el('polyline', { points: pts.join(' '), fill: 'none',
      stroke: col, 'stroke-width': 1.3, 'stroke-linejoin': 'round' }));
    var last = pts[pts.length - 1].split(',');
    svg.appendChild(el('circle', { cx: last[0], cy: last[1], r: 2.1,
      fill: '#FFE9B8' }));
    return svg;
  }

  function card(c, delay, idx) {
    var sc = stratOf(c);
    var d = document.createElement('div');
    d.className = 'obc';
    d.setAttribute('style', 'color:' + sc.c + ';--d:' + delay.toFixed(2) + 's');

    var head = document.createElement('div');
    head.className = 'obc-h';
    head.innerHTML =
      '<span class="obc-t" style="color:' + sc.c + '">' + c.t + '</span>' +
      '<span class="obc-p" style="color:' + sc.c + '">' +
        (c.pattern || '\\u2014') + '</span>' +
      '<span class="obc-cap">' + (c.cap || '') + '</span>';
    d.appendChild(head);
    d.appendChild(spark(c, sc.c, idx));

    /* Четыре величины, отвечающие на разные вопросы: где монета
       стоит, что с объёмом сейчас, на что была способна, давно ли
       под наблюдением. Пятая начала бы дублировать одну из них. */
    var up = +c.up || 0;
    var now = volNow(c);
    var rec = +c.x || 0;
    var m = document.createElement('div');
    m.className = 'obc-m';
    m.innerHTML =
      '<div><div class="obc-k">от дна</div><div class="obc-v ' +
        (up > 0 ? 'pos' : 'off') + '">' + Math.round(up) + '%</div></div>' +
      '<div><div class="obc-k">объём</div><div class="obc-v ' +
        (now >= 2 ? '' : 'off') + '">' + xfmt(now) + '</div></div>' +
      '<div><div class="obc-k">рекорд</div><div class="obc-v ' +
        (rec >= 10 ? '' : 'off') + '">' + xfmt(rec) + '</div></div>' +
      '<div><div class="obc-k">в журнале</div><div class="obc-v off">' +
        (c.days || 0) + '\\u0434</div></div>';
    d.appendChild(m);

    if (c.verdict) {
      var w = document.createElement('div');
      w.className = 'obc-w';
      w.textContent = c.verdict;
      d.appendChild(w);
    }

    /* Клик уводит на орбиту к этой монете. Экран лидеров отвечает
       «что происходит», карточка на орбите — «почему»; разрывать эту
       пару отдельной навигацией незачем. */
    d.addEventListener('click', function () {
      pod.classList.remove('on');
      if (typeof window.obShowStar === 'function') window.obShowStar(c.t);
    });
    return d;
  }

  var built = false;
  function build() {
    if (built) return;
    built = true;
    pod.classList.remove('pd-go');

    if (!STARS.length) { bail('журнал лидеров пуст'); return; }

    var shown = 0, delay = 0.05, idx = 0;
    STAGE.forEach(function (stg, i) {
      var list = STARS.filter(function (s) { return stratOf(s).stage === i; });
      if (!list.length) return;
      /* Внутри полосы — по ходу от дна: наверху то, что дальше всего
         ушло. Порядок по скору был бы порядком уверенности детектора,
         а не состояния монеты. */
      list.sort(function (a, b) { return (+b.up || 0) - (+a.up || 0); });

      var band = document.createElement('div');
      band.className = 'obp-band';
      var bh = document.createElement('div');
      bh.className = 'obp-bh';
      bh.setAttribute('style', '--d:' + delay.toFixed(2) + 's');
      bh.innerHTML = '<i style="background:' + stg.c + ';color:' + stg.c +
        '"></i><span>' + stg.n + '</span><b>' + list.length + '</b>';
      band.appendChild(bh);
      delay += 0.06;

      var grid = document.createElement('div');
      grid.className = 'obp-grid';
      list.forEach(function (c) {
        grid.appendChild(card(c, delay, idx++));
        delay += 0.022;
        shown++;
      });
      band.appendChild(grid);
      host.appendChild(band);
    });

    if (!shown) bail('ни у одной монеты журнала нет стратегии');

    var stamp = document.getElementById('obPodStamp');
    if (stamp) stamp.textContent = STARS.length + ' монет под наблюдением';
  }

  /* ── Очередь экранов ──
     Сводка → лидеры → дашборд. Подписки на закрытие сводки нет:
     brief.js своё закрытие наружу не отдаёт, а лезть в его
     внутренности значило бы связать два модуля намертво. Следим за
     классом .on — это её публичное состояние, видимое из разметки. */
  var brief = document.getElementById('obBrief');
  var opened = false;

  function show() {
    if (opened) return;
    opened = true;
    build();
    pod.classList.add('on');
    /* Сначала узлы, потом класс, и снятие паузы через два кадра:
       браузер должен успеть применить вставку, иначе класс не даёт
       перезапуска анимаций. */
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { pod.classList.add('pd-go'); });
    });
    document.addEventListener('keydown', function () {
      pod.classList.remove('on');
    });
  }

  if (!brief) { show(); return; }

  var HANDOVER = 560;
  var seen = brief.classList.contains('on');
  var mo = new MutationObserver(function () {
    if (brief.classList.contains('on')) { seen = true; return; }
    if (seen) { mo.disconnect(); setTimeout(show, HANDOVER); }
  });
  mo.observe(brief, { attributes: true, attributeFilter: ['class'] });

  /* Запасной путь: если сводка не открылась вовсе, экран всё равно
     покажется. Молчаливая зависимость от чужого модуля хуже лишнего
     таймера. */
  setTimeout(function () {
    if (!seen && !opened) { mo.disconnect(); show(); }
  }, 4000);
})();
</script>
"""
