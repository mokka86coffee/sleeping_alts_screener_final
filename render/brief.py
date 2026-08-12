"""Сводка при входе · экран поверх дашборда.

dashboard.py только вызывает render_brief() и вставляет результат.

Разметка пустая: текст собирает скрипт из window.ORB, который
выставляет render.orbit. Отдельного списка монет здесь нет намеренно —
он разошёлся бы с карточками при первой правке порогов фаз.

Модуль не зависит от орбиты визуально: на мобильных орбита снимается,
а сводка остаётся, потому что это текст и он ничего не стоит.
"""
from __future__ import annotations


def render_brief() -> str:
    return BRIEF_HTML + BRIEF_JS


BRIEF_HTML = """
<div class="ob-brief" id="obBrief">
  <div class="obf-glow"></div>
  <div class="obf-in">
    <div class="obf-date rise" style="--d:.1s" id="obfDate"></div>
    <div class="obf-text" id="obfText"></div>
    <div class="obf-foot" id="obfFoot">клик в любом месте — к дашборду</div>
    <div class="obf-bar" id="obfBar"><u></u></div>
  </div>
</div>
"""


BRIEF_JS = """
<script>
(function () {
  /* Сводка при входе. Работает поверх дашборда и не зависит от орбиты:
     на мобильных орбита снимается, а текст остаётся — он ничего не
     стоит. Данные и чтение фазы берём из window.ORB, который орбита
     выставляет до своего мобильного гейта. */
  var O = window.ORB || {};
  var STARS = O.stars || [], phase = O.phase, toStop = O.toStop;
  if (!phase || !STARS.length) return;

  var BRIEF_LAP = 105000;

  /* Печать по символу. Задержка одна на строку, а не на каждый символ —
     иначе при длинном тексте набегает секунда лишнего ожидания. */
  function typeIn(el, text, delay) {
    if (!el) return;
    var reduce = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
    if (reduce) { el.textContent = text; el.parentNode.classList.add('done'); return; }
    el.textContent = '';
    setTimeout(function () {
      var i = 0;
      (function step() {
        el.textContent = text.slice(0, ++i);
        if (i < text.length) setTimeout(step, 55);
        else setTimeout(function () { el.parentNode.classList.add('done'); }, 700);
      })();
    }, delay);
  }

  /* Счётчики: число, доехавшее до значения, читается как измеренное,
     а не как подставленное. Знак и суффикс берутся из разметки. */
  function countUp(root, delay) {
    var reduce = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
    root.querySelectorAll('[data-num]').forEach(function (el) {
      var to = parseFloat(el.dataset.num), suf = el.dataset.suf || '';
      var sign = el.hasAttribute('data-sign') || to < 0;
      var frac = (String(to).split('.')[1] || '').length;
      if (reduce) { el.textContent = (sign && to > 0 ? '+' : '') + to + suf; return; }
      setTimeout(function () {
        var t0 = performance.now(), dur = 850;
        (function step(now) {
          var k = Math.min(1, (now - t0) / dur);
          var v = to * (1 - Math.pow(1 - k, 3));
          el.textContent = (sign && to > 0 ? '+' : '') + v.toFixed(frac) + suf;
          if (k < 1) requestAnimationFrame(step);
        })(t0);
      }, delay);
    });
  }

  /* ═════════════════════════════════════════════════════════
       Графики лидеров. Строятся из рядов, которые уже лежат в
       снимке: spark_1d и spark_vol по 24 точки, оставлены в
       KEEP_SERIES. Дополнительных данных не запрашивается.
       ═════════════════════════════════════════════════════════ */
    var CH_W = 214, CH_H = 76, CH_PAD = 2, CH_RIGHT = 182;

    /* Сглаживание Катмулла-Рома, переведённое в кубические кривые.
       Ломаная из 24 точек в поле шириной 200px выглядит рваной.
       Помнить при этом надо: сглаживание рисует значения МЕЖДУ
       днями, которых не было. Для иллюстрации в тексте это
       допустимо, для разбора уровней — нет. */
    function smoothPath(pts) {
      if (pts.length < 2) return '';
      var d = 'M' + pts[0][0].toFixed(1) + ' ' + pts[0][1].toFixed(1);
      for (var i = 0; i < pts.length - 1; i++) {
        var p0 = pts[i > 0 ? i - 1 : 0], p1 = pts[i],
            p2 = pts[i + 1], p3 = pts[i + 2 < pts.length ? i + 2 : i + 1];
        d += ' C' + (p1[0] + (p2[0] - p0[0]) / 12).toFixed(1) + ' ' +
                    (p1[1] + (p2[1] - p0[1]) / 12).toFixed(1) + ', ' +
                    (p2[0] - (p3[0] - p1[0]) / 12).toFixed(1) + ' ' +
                    (p2[1] - (p3[1] - p1[1]) / 12).toFixed(1) + ', ' +
                    p2[0].toFixed(1) + ' ' + p2[1].toFixed(1);
      }
      return d;
    }

    /* График лидера потока. Шкала строится по цене И уровню зоны
       сразу: если считать только по цене, зона уезжает за пределы
       поля ровно тогда, когда цена от неё далеко ушла — то есть в
       самом интересном случае. */
    function leaderChart(d) {
      var s = d.series || [];
      if (s.length < 4) return '';

      var lo = Math.min.apply(null, s), hi = Math.max.apply(null, s);
      if (d.zone > 0) { lo = Math.min(lo, d.zone); hi = Math.max(hi, d.zone); }
      var span = (hi - lo) || 1, top = 12, bottom = 70;

      function y(v) { return bottom - (v - lo) / span * (bottom - top); }
      var pts = s.map(function (v, i) {
        return [CH_PAD + i * (CH_RIGHT - CH_PAD) / (s.length - 1), y(v)];
      });

      var line = smoothPath(pts), last = pts[pts.length - 1];
      var side = pts.map(function (p) { return [p[0] + 6, p[1] + 10]; });
      var wall = line + ' L' + side[side.length - 1][0].toFixed(1) + ' ' +
                 side[side.length - 1][1].toFixed(1) + ' ' +
                 smoothPath(side.slice().reverse()).replace(/^M[^C]*/, '') + ' Z';

      var zone = '';
      if (d.zone > 0) {
        var zy = y(d.zone);
        zone = '<g class="obf-lat" style="--d:0s">' +
          '<line x1="2" y1="' + zy.toFixed(1) + '" x2="' + CH_RIGHT + '" y2="' +
            zy.toFixed(1) + '" stroke="#F5A623" stroke-width=".6" ' +
            'stroke-dasharray="2.5 4" opacity=".5"/>' +
          '<text x="' + (CH_RIGHT + 4) + '" y="' + (zy + 2.5).toFixed(1) +
            '" font-size="6" fill="#F5A623" opacity=".85" ' +
            'letter-spacing=".8">зона</text></g>';
      }

      return '<svg class="obf-mini" viewBox="0 0 ' + CH_W + ' ' + CH_H + '">' +
        '<defs>' +
          '<linearGradient id="obfPS" x1="0" y1="0" x2="1" y2="0">' +
            '<stop offset="0" stop-color="#2E7A55"/>' +
            '<stop offset="0.55" stop-color="#4FCF8A"/>' +
            '<stop offset="1" stop-color="#E4FFF0"/></linearGradient>' +
          '<linearGradient id="obfPW" x1="0" y1="0" x2="0" y2="1">' +
            '<stop offset="0" stop-color="#2E7A55" stop-opacity=".7"/>' +
            '<stop offset="1" stop-color="#12321F" stop-opacity=".12"/>' +
          '</linearGradient>' +
          '<radialGradient id="obfFL">' +
            '<stop offset="0" stop-color="#FFFFFF" stop-opacity=".95"/>' +
            '<stop offset="0.3" stop-color="#BFFFD9" stop-opacity=".45"/>' +
            '<stop offset="1" stop-color="#4FCF8A" stop-opacity="0"/>' +
          '</radialGradient>' +
          '<linearGradient id="obfST" x1="0" y1="0" x2="1" y2="0">' +
            '<stop offset="0" stop-color="#4FCF8A" stop-opacity="0"/>' +
            '<stop offset="0.5" stop-color="#DFFFEC" stop-opacity=".65"/>' +
            '<stop offset="1" stop-color="#4FCF8A" stop-opacity="0"/>' +
          '</linearGradient>' +
          '<filter id="obfSO" x="-30%" y="-50%" width="160%" height="200%">' +
            '<feGaussianBlur stdDeviation="3"/></filter>' +
        '</defs>' + zone +
        '<path class="obf-lat" style="--d:1.6s" d="' + wall +
          '" fill="url(#obfPW)"/>' +
        '<path class="obf-drawn" style="--d:0s" filter="url(#obfSO)" ' +
          'opacity=".5" d="' + line + '" fill="none" stroke="url(#obfPS)" ' +
          'stroke-width="5" stroke-linecap="round"/>' +
        '<path class="obf-drawn" style="--d:0s" d="' + line +
          '" fill="none" stroke="url(#obfPS)" stroke-width="1.9" ' +
          'stroke-linecap="round"/>' +
        '<g class="obf-lat" style="--d:3.4s">' +
          '<ellipse cx="' + last[0].toFixed(1) + '" cy="' + last[1].toFixed(1) +
            '" rx="30" ry="1.1" fill="url(#obfST)"/>' +
          '<circle cx="' + last[0].toFixed(1) + '" cy="' + last[1].toFixed(1) +
            '" r="13" fill="url(#obfFL)"/>' +
          '<circle class="obf-pulse" cx="' + last[0].toFixed(1) + '" cy="' +
            last[1].toFixed(1) + '" r="4.5" fill="#4FCF8A"/>' +
          '<circle cx="' + last[0].toFixed(1) + '" cy="' + last[1].toFixed(1) +
            '" r="2.4" fill="#F2FFF7"/></g>' +
      '</svg>';
    }

    /* График лидера объёма. Шкала логарифмическая, и это не выбор
       оформления: кратность ×635 рядом с обычными днями на линейной
       шкале не рисуется вовсе — столбик выходил выше соседей раза в
       четыре вместо шестисот, то есть график врал. Здесь шаг вверх
       это умножение на десять, и три порядка укладываются честно.

       Зеркальность даёт всплеску вдвое больше высоты при той же
       высоте блока. */
    function volChart(d) {
      var r = d.ratios || [];
      if (r.length < 4) return '';

      var hs = r.map(function (v) { return Math.log10(Math.max(v, 0) + 1); });
      var mx = Math.max.apply(null, hs) || 1;

      /* Подсвечивается МАКСИМУМ, а не последний день: аномалия
         бывает и в середине ряда, и тогда подпись «максимум объёма»
         относилась бы к другому дню, чем горящая линия. */
      var hot = hs.indexOf(mx);
      var cy = 38, maxH = 30;
      var step = (CH_RIGHT - 6 - CH_PAD * 2) / (r.length - 1);
      var out = '';

      hs.forEach(function (h, i) {
        if (i === hot) return;
        var x = CH_PAD + 4 + i * step;
        var a = Math.max(1.6, h / mx * maxH);
        out += '<line style="--d:' + (i * 0.095).toFixed(3) + 's" x1="' +
          x.toFixed(1) + '" y1="' + (cy - a).toFixed(1) + '" x2="' +
          x.toFixed(1) + '" y2="' + (cy + a).toFixed(1) + '"/>';
      });

      var hx = CH_PAD + 4 + hot * step;
      var hd = (r.length * 0.095 + 0.3).toFixed(2);

      return '<svg class="obf-mini obf-wave" viewBox="0 0 ' + CH_W + ' ' +
        CH_H + '">' +
        '<defs>' +
          '<linearGradient id="obfWG" x1="0" y1="0" x2="0" y2="1">' +
            '<stop offset="0" stop-color="#FFF0CE"/>' +
            '<stop offset="0.5" stop-color="#F5A623"/>' +
            '<stop offset="1" stop-color="#FFF0CE"/></linearGradient>' +
          '<filter id="obfWL" x="-140%" y="-40%" width="380%" height="180%">' +
            '<feGaussianBlur stdDeviation="4.5"/></filter>' +
        '</defs>' +
        '<g class="obf-lat" style="--d:0s">' +
          '<line x1="2" y1="' + cy + '" x2="' + CH_RIGHT + '" y2="' + cy +
            '" stroke="#8b8a92" stroke-width=".5" stroke-dasharray="2 3.5" ' +
            'opacity=".4"/>' +
          '<text x="' + (CH_RIGHT + 4) + '" y="' + (cy + 2.5) +
            '" font-size="6" fill="#8b8a92" opacity=".8" ' +
            'letter-spacing=".8">норма</text></g>' +
        '<g stroke="#7e848e" stroke-width="2.6" stroke-linecap="round" ' +
          'opacity=".55">' + out + '</g>' +
        '<g class="obf-lat" style="--d:' + hd + 's">' +
          '<line x1="' + hx.toFixed(1) + '" y1="' + (cy - maxH) + '" x2="' +
            hx.toFixed(1) + '" y2="' + (cy + maxH) + '" stroke="#F5A623" ' +
            'stroke-width="5" stroke-linecap="round" opacity=".5" ' +
            'filter="url(#obfWL)"/>' +
          '<line x1="' + hx.toFixed(1) + '" y1="' + (cy - maxH) + '" x2="' +
            hx.toFixed(1) + '" y2="' + (cy + maxH) + '" stroke="url(#obfWG)" ' +
            'stroke-width="3.2" stroke-linecap="round"/>' +
          '<circle class="obf-pulse" cx="' + hx.toFixed(1) + '" cy="' + cy +
            '" r="9" fill="#FFD98A"/></g>' +
      '</svg>';
    }

    function chartRing(id, from, to, frac, label, size) {
      var C = 2 * Math.PI * 18;
      var off = C * (1 - Math.max(0.04, Math.min(1, frac)));
      return '<svg class="obf-ring" viewBox="0 0 44 44">' +
        '<defs><linearGradient id="' + id + '" x1="0" y1="1" x2="1" y2="0">' +
          '<stop offset="0" stop-color="' + from + '"/>' +
          '<stop offset="1" stop-color="' + to + '"/></linearGradient></defs>' +
        '<circle cx="22" cy="22" r="18" fill="none" ' +
          'stroke="rgba(255,255,255,.06)" stroke-width="2.5"/>' +
        '<circle class="v" cx="22" cy="22" r="18" fill="none" ' +
          'stroke="url(#' + id + ')" stroke-width="2.5" stroke-linecap="round" ' +
          'transform="rotate(-90 22 22)" style="--off:' + off.toFixed(1) +
          ';--d:1s"/>' +
        '<text x="22" y="' + (size > 11 ? 25.5 : 25) + '" font-size="' + size +
          '" font-weight="300" text-anchor="middle" fill="#E8EEF4">' + label +
          '</text></svg>';
    }

    /* Сборка блока. Разметка одна на оба вида — различаются только
       акцентный цвет, подписи и то, какой график внутри. */
    function blockHTML(b) {
      return '<div class="obf-rail"><u></u></div>' +
        '<div class="obf-ghost">' + b.ghost + '</div>' +
        '<div class="obf-bl">' +
          '<div class="obf-k">' + b.role + '</div>' +
          '<div class="obf-meta">' + b.meta + '</div>' +
          '<div class="obf-stat">' + b.stat + '</div>' +
        '</div>' +
        '<div class="obf-br">' + b.chart + b.ring + '</div>';
    }

  function buildBrief() {
    var wrap = document.getElementById('obBrief');
    var host = document.getElementById('obfText');
    if (!wrap || !host) return;

    /* Отчёт статический: важно не «сегодня», а когда был прогон —
       иначе легко читать вчерашние числа как свежие. */
    document.getElementById('obfDate').textContent = 'ПРОГОН · ' +
      new Date().toLocaleString('ru-RU', { day: 'numeric', month: 'long',
        hour: '2-digit', minute: '2-digit' }).toUpperCase();

    /* Группы — тот же срез дерева фаз, что и в карточках, только
       пересказанный словами. Отдельного списка нет намеренно: он бы
       разошёлся с карточками при первой правке порогов. */
    var go = [], wait = [], hold = [];
    STARS.forEach(function (s) {
      var p = phase(s);
      if ((s.streak || 1) >= 3 && (s.days || 0) >= 4) hold.push(s);
      else if (p.k === 'go' && !s.firstRun) go.push(s);
      else wait.push(s);
    });
    var near = STARS.filter(function (s) { return s.stop && toStop(s) <= 8; })
      .sort(function (a, b) { return toStop(a) - toStop(b); }).slice(0, 3);

    function names(list, cls) {
      return list.slice(0, 3).map(function (s) {
        return '<span class="t ' + (cls || '') + '">' + s.t + '</span>' + cap(s);
      }).join(', ');
    }
    function plain(list) {
      return list.slice(0, 3).map(function (s) {
        return s.t + capP(s); }).join(', ');
    }

    /* Формулировка фона выводится из режима, а не придумывается:
       «спокойный» и «осторожный» — это пересказ RISK-ON / RISK-OFF,
       а не прогноз. Дальше по тексту нет ни одного утверждения о
       будущем — только состояние. */
    var M = O.market || {};
    var calm = !!M.calm;
    /* Недельная форма BTC, а не один процент: −2.1% одинаково выглядит
       и у ровного сползания, и у отскока от провала. Источника пока
       нет (см. render/orbit.py, _orbit_market) — при пустом ряде
       график просто не рисуется, а не подставляет нули. */
    var bs = M.series || [], btcSpark = '';
    if (bs.length > 1) {
      var blo = Math.min.apply(null, bs), bhi = Math.max.apply(null, bs);
      btcSpark = '<svg class="sp" viewBox="0 0 64 14" preserveAspectRatio="none">' +
        '<polyline points="' + bs.map(function (v, i) {
          return (i / (bs.length - 1) * 64).toFixed(1) + ' ' +
                 (12 - (v - blo) / ((bhi - blo) || 1) * 10).toFixed(1);
        }).join(' ') + '" stroke="' + (M.btcUp ? '#48A97C' : '#FF6B35') +
        '"/></svg>';
    }
    var btcTxt = M.btc || '—';

    /* Положение относительно выходных приходит готовым из
       _weekend_state в orbit.py. Раньше считалось здесь второй раз,
       по часовому поясу браузера — то есть у читателя из другого
       пояса пятничная строка появлялась не в пятницу. Расчёт в одном
       месте, здесь только чтение. */
    var wk = M.weekend || '';
    var wknd = {p: '', h: ''};

    if (wk === 'soon') {
      wknd = { p: 'Завтра выходные — ликвидность начнёт уходить уже ' +
                  'к вечеру, торговать сегодня с осторожностью.',
               h: '<span class="warn">Завтра выходные</span> — ликвидность ' +
                  'начнёт уходить уже к вечеру, торговать сегодня ' +
                  'с осторожностью.' };
    } else if (wk === 'now') {
      wknd = { p: 'Выходные — тонкий стакан, движения рваные. ' +
                  'Лучше не торговать.',
               h: '<span class="warn">Выходные</span> — тонкий стакан, ' +
                  'движения рваные. Лучше не торговать.' };
    }

    /* Новые в топ-3 по FLOW: не «в журнале вообще», а те, кто поднялся
       в тройку именно этим прогоном. Это единственная строка про
       изменение, а не про состояние — и потому самая заметная. */
    var fresh3 = STARS.filter(function (s) { return s.newTop3; }).slice(0, 3);

    function cap(s) { return s.cap ? ' <span class="obf-cap">' + s.cap + '</span>' : ''; }
    function capP(s) { return s.cap ? ' ' + s.cap : ''; }

    var L = M.leader || {};

    /* Объём — новость только на входе из спячки. Монете, которая уже
       подтвердилась (сидит в «В работе»), отдельная строка «у неё
       объём» не нужна — это не открытие, а его подтверждение, и ему
       место рядом с самой монетой в «В работе». Поэтому все три
       объёмных списка ниже отфильтрованы от тикеров «В работе». */
    var heldT = {};
    hold.forEach(function (s) { heldT[s.t] = true; });
    function freshOnly(list) {
      return list.filter(function (v) { return !heldT[v.t]; });
    }

    var TV = freshOnly(M.topVol || []).slice(0, 3);
    var HRfull = M.hourly || { n: 0, list: [] };
    var HR = { n: HRfull.n, list: freshOnly(HRfull.list || []) };
    /* Полный список ×30+, до фильтра — нужен ещё раз ниже, чтобы
       пометить «· объём» у тех из «В работе», кто в него попал. */
    var bigVolAll = M.flowVol || [];
    var bigVol = freshOnly(bigVolAll).slice(0, 5);
    var bigVolT = {};
    bigVolAll.forEach(function (v) { bigVolT[v.t] = true; });

    /* Замирание — первая строка сводки. Если ехать некуда, всё
       остальное ниже описывает движение, которого нет.
       Строка не печатается на живом рынке: тогда эти числа
       сообщают только то, что всё в порядке. */

    /* ── Фон рынка ──────────────────────────────────────────
       Семь фраз, из них пять про фон. Числа не выносятся в подписи
       и не собираются в таблицу: каждое идёт внутри предложения
       вместе с тем, что оно означает. */
    function pct(v, d) {
      if (v === null || v === undefined) return '—';
      return (v > 0 ? '+' : '') + v.toFixed(d === undefined ? 1 : d) + '%';
    }
    function sgn(v) { return v > 0 ? 'up' : (v < 0 ? 'dn' : ''); }
    /* Русские числительные: 1 монета, 2-4 монеты, 5+ монет.
       Исключение — 11-14, они ведут себя как множественное число
       несмотря на последнюю цифру. */
    function plural(n, one, few, many) {
      var a = Math.abs(n) % 100;
      if (a >= 11 && a <= 14) return many;
      a %= 10;
      if (a === 1) return one;
      if (a >= 2 && a <= 4) return few;
      return many;
    }
    var bg = [];

    if (M.frozen) {
      bg.push('Рынок сейчас <span class="warn">замер</span>. Лучшая монета ' +
        'дня прибавила <span class="n">' + pct(M.maxChange, 0) + '</span>, ' +
        'и дальше плюс двадцати ушли всего <span class="n">' + (M.tail || 0) + '</span> ' +
                                                   plural(M.tail || 0, 'монета', 'монеты', 'монет') +
        ' — при живом рынке их бывают десятки. ' +
        'Ехать сегодня некуда.');
    } else {
      bg.push('Рынок <span class="gd">двигается</span>. Лучшая монета дня ' +
        '<span class="n">' + (M.tail || 0) + '</span> ' +
                plural(M.tail || 0, 'монета', 'монеты', 'монет') + '</span> ' +
                                                                   ' — движение широкое, а не один выброс.');
    }

    /* Объём отдельной фразой, потому что отвечает на другой вопрос.
       Стоящая цена при живом объёме и стоящая цена при мёртвом —
       разные дни, и по ценам их не различить. */
    if (M.peakVol && M.peakVol.sym) {
      bg.push('Деньги в рынке ' + (M.frozen ? 'при этом ' : '') +
        'есть: максимум объёма на <span class="gd">' + M.peakVol.sym +
        '</span>, <span class="n">×' + M.peakVol.x + '</span> к своей норме.');
    }

    /* Ширина рынка — три состояния, а не число с подписью. */
    var gs = M.greenShare;
    if (gs !== null && gs !== undefined) {
      bg.push('В плюсе <span class="n">' + Math.round(gs) + '%</span> выборки' +
        (gs >= 55 ? ', растёт почти весь рынок.'
         : gs <= 42 ? ', то есть падает большинство.'
         : ', рынок разделился примерно поровну.'));
    }

    /* Биткоин: вывод делается по СОЧЕТАНИЮ суточного, недельного и
       доминации. По одному числу вывода не бывает — падение при
       растущей доминации и падение при падающей означают разное. */
    if (M.btc !== null && M.btc !== undefined) {
      /* Вывод делается по НЕДЕЛЬНОМУ движению, а не по суточному.
         Суточное в пределах процента — шум: −0.3% давало фразу
         «деньги сидят в биткоине», то есть диагноз по величине,
         которой нет. Неделя усредняет шум и отвечает на вопрос,
         который фраза и задаёт: куда идут деньги, а не что было
         вчера.

         Порог в полтора процента за неделю — примерно та граница,
         за которой движение перестаёт быть дрейфом. Проверяется
         наблюдением: если фраза не появляется неделями, порог
         высок. */
      var tail = '.';
      var dom = parseFloat(M.dom);
      if (M.btc7d <= -1.5 && dom >= 57) {
        tail = ' — деньги уходят из риска, альтам ничего не достаётся.';
      } else if (M.btc7d >= 1.5 && dom < 56) {
        tail = ' — биткоин растёт, а доминация сдаёт: окно для альтов.';
      } else if (Math.abs(M.btc7d) < 1.5) {
        tail = ' — за неделю почти без движения.';
      }
      /* Знак несёт глагол, поэтому число печатается без него.
         pct() ставит плюс всему положительному, а Math.abs() делает
         положительным всё — вместе выходило «потерял +0.3%». */
      bg.push('Биткоин ' + (M.btc >= 0 ? 'прибавил' : 'потерял') +
        ' <span class="' + sgn(M.btc) + ' n">' +
        Math.abs(M.btc).toFixed(1) + '%</span> за сутки, за неделю ' +
        '<span class="' + sgn(M.btc7d) + ' n">' + pct(M.btc7d) +
        '</span>, доминация <span class="n">' + (M.dom || '—') +
        '</span>' + tail);
    }
function removeTags(str) {
  if (str === null || str === '') {
    return '';
  }
  return str.replace(/<[^>]*>/g, '');
}

    bg = bg.map(function (h) { return { p: removeTags(h), h: h }; })

    /* Блоки лидеров. Возвращают null, если рядов нет: пустой
           график хуже отсутствующего — он выглядит поломкой, а не
           нехваткой данных. */
        var LC = M.leaderChart || {}, VC = M.volChart || {};

        var leaderBlock = (L.t && (LC.series || []).length >= 4) ? {
          block: {
            acc: '79,207,138',
            ghost: L.t,
            role: 'лидер потока',
            meta: 'фигура <b>' + (LC.case || '—') + '</b>' +
              (LC.horizonDays ? ' · горизонт <b>' + LC.horizonDays + ' дн</b>' : '') +
              ' <span class="obf-cap">· ' + (L.cap || '') + '</span>',
            stat: (LC.stop ? '<span>стоп <b>' + LC.stop + '</b></span>' : '') +
              (LC.target ? '<span>цель <b>' + LC.target + '</b></span>' : '') +
              '<span>' + LC.series.length + ' дней</span>',
            chart: leaderChart(LC),
            ring: chartRing('obfR1', '#2E7A55', '#8FE8B4',
              (LC.score || 0) / 100, LC.score || 0, 13),
          }
        } : null;

        var volBlock = ((VC.ratios || []).length >= 4) ? {
          block: {
            acc: '245,166,35',
            ghost: VC.sym,
            role: 'максимум объёма',
            meta: '<b>×' + VC.x + '</b> к своей норме за 30 дней ' +
              '<span class="obf-cap">· ' + (VC.cap || '') + '</span>',
            stat: '<span>1ч <b>×' + VC.v1h + '</b></span>' +
              '<span>4ч <b>×' + VC.v4h + '</b></span>' +
              '<span>1д <b>×' + VC.v1d + '</b></span>' +
              '<span>фандинг <b>' + VC.funding + '%</b></span>',
            chart: volChart(VC),
            // Кольцо всегда полное: это не доля от чего-то, а рекорд
            // прогона. Дуга в 60% рядом с «×635» читалась бы как
            // «шестьсот тридцать пять из тысячи».
            ring: chartRing('obfR2', '#B4761A', '#FFE0A0', 1, '×' + VC.x, 10),
          }
        } : null;

    var lines = bg.concat(wknd.p ? [wknd] : []).concat([
      wknd,

     /* Текстовая строка про лидера убрана: блок ниже говорит то же
              самое и подробнее. Оставить обе значило бы дважды сообщить
              имя, фигуру и скор. */
           leaderBlock,

      /* Все монеты FLOW с объёмом ×30+ на любом ТФ — не только лидер:
         сильный по score не обязан быть объёмным, и наоборот. */
      bigVol.length
        ? { p: 'Аномалия объёма ×30+ у ' + bigVol.map(function (v) {
              return v.t + capP(v) + ' ×' + v.x; }).join(', ') + '.',
            h: 'Объём ×30+ у ' + bigVol.map(function (v) {
              return '<span class="t">' + v.t + '</span>' + cap(v) +
                ' <span class="n">×' + v.x + '</span>'; }).join(', ') + '.' }
        : null,

      volBlock,

      /* Активность за час — единственная строка про «прямо сейчас» */
      HR.list.length
        ? { p: 'За час ожили ' + HR.n + ': ' + HR.list.map(function (v) {
              return v.t + capP(v) + ' ×' + v.x; }).join(', ') + '.',
            h: 'За час ожили <span class="n">' + HR.n + '</span>: ' +
               HR.list.map(function (v) {
                 return '<span class="t">' + v.t + '</span>' + cap(v) +
                   ' <span class="n">×' + v.x + '</span>'; }).join(', ') + '.' }
        : null,

      fresh3.length
        ? { p: 'Новые в топ-3 по flow: ' + plain(fresh3) + '.',
            h: 'Новые в <span class="gd">топ-3 по flow</span>: ' +
               names(fresh3) + '.' }
        : null,
      go.length
        ? { p: 'Рассмотреть стоит ' + plain(go) + ' — первая фаза, у дна.',
            h: 'Рассмотреть стоит ' + names(go) +
               ' — <span class="up">первая фаза</span>, у дна.' }
        : { p: 'Сегодня брать нечего.', h: '<span class="mut">Сегодня брать нечего.</span>' },
      wait.length
        ? { p: 'Ждут сигнала ' + plain(wait) + ' — первый разгон, входить рано.',
            h: 'Ждут сигнала ' + names(wait) +
               ' — <span class="mut">первый разгон, входить рано</span>.' }
        : null,
    /* Прогресс у каждой свой — общая фраза «тренд подтверждается»
         не отличала быстрого разгонщика от монеты, которая неделю
         топчется у дна. Метка «· объём» — то же подтверждение, что
         раньше жило отдельной строкой, теперь пришита к своей монете. */
      hold.length
        ? { p: 'В работе ' + hold.slice(0, 3).map(function (s) {
              return s.t + capP(s) + ' ' + (s.up >= 0 ? '+' : '') + s.up +
                '% за ' + (s.days || 0) + ' дн' + (bigVolT[s.t] ? ' · объём' : '');
            }).join(', ') + '.',
            h: 'В работе ' + hold.slice(0, 3).map(function (s) {
              return '<span class="t gd">' + s.t + '</span>' + cap(s) +
                ' <span class="n">' + (s.up >= 0 ? '+' : '') + s.up +
                '%</span> за ' + (s.days || 0) + ' дн' +
                (bigVolT[s.t] ? ' <span class="up">· объём</span>' : '');
            }).join(', ') + '.' }
        : null,
      near.length
        ? { p: 'У уровня ' + near.map(function (s) {
              return s.t + capP(s) + ' −' + toStop(s) + '%'; }).join(', ') +
              ' — решаются сегодня.',
            h: 'У уровня ' + near.map(function (s) {
              return '<span class="t">' + s.t + '</span>' + cap(s) +
                ' <span class="dn n">−' + toStop(s) + '%</span>';
            }).join(', ') + ' — решаются сегодня.' }
        : null
    ]).filter(Boolean);

    var reduce = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
    var els = lines.map(function (l) {
      var d = document.createElement('div');
      if (l.block) {
        d.className = 'obf-blk';
        d.style.setProperty('--acc-rgb', l.block.acc);
        /* Разметка вставляется сразу, а показ откладывается классом:
           если строить SVG в момент показа, первый кадр уходит на
           разбор дерева и прорисовка начинается рывком. */
        d.innerHTML = blockHTML(l.block);
        if (reduce) d.classList.add('on');
      } else {
        d.className = 'obf-p';
        if (reduce) d.innerHTML = l.h;
      }
      host.appendChild(d);
      return d;
    });

    function tail() {
      document.getElementById('obfFoot').classList.add('on');
      document.getElementById('obfBar').classList.add('on');
    }

    /* Набор идёт спокойно: около двадцати секунд на весь текст при
       окне показа в минуту. Быстрая печать превращается в мигание —
       строка появляется раньше, чем глаз успевает начать читать. */
    /* Пауза на блок. Складывается из самой длинной анимации внутри
       (прорисовка кривой 4.6с) плюс время на разглядывание. Меньше
       — и следующая строка начинает печататься поверх ещё
       рисующегося графика. */
    /* Складывается из очереди текста внутри блока (последняя строка
       стартует на 2.1с) и самой длинной анимации графика — кривая
       рисуется 4.6с. Меньше — и следующая строка начинает
       печататься поверх ещё рисующегося графика. */
    var BLOCK_HOLD = 7400;

    function typeLine(i) {
      if (i >= lines.length) { tail(); return; }

      /* Блок не печатается: он рисуется сам, и посимвольный набор
         поверх прорисовки читался бы как два движения разом. */
      if (lines[i].block) {
        els[i].classList.add('on');
        setTimeout(function () { typeLine(i + 1); }, BLOCK_HOLD);
        return;
      }

      var el = els[i], txt = lines[i].p, k = 0;
      el.classList.add('typing');
      (function step() {
        el.textContent = txt.slice(0, ++k);
        if (k < txt.length) return setTimeout(step, 48);
        el.classList.remove('typing');
        el.innerHTML = lines[i].h;          // подмена на размеченную версию
        setTimeout(function () { typeLine(i + 1); }, 700);
      })();
    }

    wrap.style.setProperty('--lap', (BRIEF_LAP / 1000) + 's');
    requestAnimationFrame(function () { wrap.classList.add('on'); });
    if (reduce) tail(); else setTimeout(function () { typeLine(0); }, 700);

    var t = setTimeout(close, BRIEF_LAP);
    function close() { clearTimeout(t); wrap.classList.remove('on'); }
    wrap.addEventListener('click', close);
    document.addEventListener('keydown', function () {
      if (wrap.classList.contains('on')) close();
    });
    window.showBrief = function () {
      wrap.classList.add('on');
      t = setTimeout(close, BRIEF_LAP);
    };
  }

  buildBrief();
})();
</script>
"""
