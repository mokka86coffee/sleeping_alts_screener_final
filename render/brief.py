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
    var frostLine = null;
    if (M.frozen) {
      var mx = (M.maxChange === null || M.maxChange === undefined)
        ? '—' : ('+' + Math.round(M.maxChange) + '%');
      var tp = Math.round(M.tailPct || 20);
      frostLine = {
        p: 'Рынок замер: лучшая монета дня ' + mx + ', выше +' + tp +
           '% всего ' + (M.tail || 0) + '. Ехать сегодня некуда.',
        h: '<span class="warn">Рынок замер</span>: лучшая монета дня ' +
           '<span class="n">' + mx + '</span>, выше +' + tp +
           '% всего <span class="n">' + (M.tail || 0) +
           '</span>. Ехать сегодня некуда.',
      };
    }

    /* ── Фон рынка ──────────────────────────────────────────
       Семь фраз, из них пять про фон. Числа не выносятся в подписи
       и не собираются в таблицу: каждое идёт внутри предложения
       вместе с тем, что оно означает. */
    function pct(v, d) {
      if (v === null || v === undefined) return '—';
      return (v > 0 ? '+' : '') + v.toFixed(d === undefined ? 1 : d) + '%';
    }
    function sgn(v) { return v > 0 ? 'up' : (v < 0 ? 'dn' : ''); }

    var bg = [];

    /* Объём отдельной фразой, потому что отвечает на другой вопрос.
       Стоящая цена при живом объёме и стоящая цена при мёртвом —
       разные дни, и по ценам их не различить. */
    if (M.peakVol && M.peakVol.sym) {
      bg.push({p: '', h: 'Деньги в рынке ' + (M.frozen ? 'при этом ' : '') +
        'есть: максимум объёма на <span class="gd">' + M.peakVol.sym +
        '</span>, <span class="n">×' + M.peakVol.x + '</span> к своей норме.'});
    }

    /* Ширина рынка — три состояния, а не число с подписью. */
    var gs = M.greenShare;
    if (gs !== null && gs !== undefined) {
      bg.push({p: '', h: 'В плюсе <span class="n">' + Math.round(gs) + '%</span> выборки' +
        (gs >= 55 ? ', растёт почти весь рынок.'
         : gs <= 42 ? ', то есть падает большинство.'
         : ', рынок разделился примерно поровну.')});
    }

    /* Биткоин: вывод делается по СОЧЕТАНИЮ суточного, недельного и
       доминации. По одному числу вывода не бывает — падение при
       растущей доминации и падение при падающей означают разное. */
    if (M.btc !== null && M.btc !== undefined) {
      var tail = '.';
      if (M.btc < 0 && parseFloat(M.dom) >= 57) {
        tail = ' — деньги сидят в биткоине, альтам ничего не достаётся.';
      } else if (M.btc7d > 0 && parseFloat(M.dom) < 56) {
        tail = ' — доминация сдаёт, это окно для альтов.';
      }
      bg.push({p: '', h: 'Биткоин ' + (M.btc >= 0 ? 'прибавил' : 'потерял') +
        ' <span class="' + sgn(M.btc) + ' n">' + pct(Math.abs(M.btc)) +
        '</span> за сутки и <span class="' + sgn(M.btc7d) + ' n">' +
        pct(M.btc7d) + '</span> за неделю, доминация <span class="n">' +
        (M.dom || '—') + '</span>' + tail});
    }

    var lines = (frostLine ? [frostLine] : []).concat(bg).concat(wknd.p ? [wknd] : []).concat([
      { p: 'Сегодня фон ' + (calm ? 'спокойный' : 'осторожный') +
             ', аппетит ' + (M.appetite || '—') + '.',
        h: 'Сегодня фон <span class="gd">' + (calm ? 'спокойный' : 'осторожный') +
           '</span>, аппетит <span class="n">' + (M.appetite || '—') +
           '</span>.' },
      { p: 'Биткоин ' + btcTxt + ' за сутки, доминация ' + (M.dom || '—') +
             ', сектор дня ' + (M.sector || '—') + '.',
        h: 'Биткоин <span class="' + (M.btcUp ? 'up' : 'dn') + ' n">' + btcTxt +
           '</span> за сутки' + btcSpark + ', доминация <span class="n">' +
           (M.dom || '—') + '</span>, сектор дня <span class="up">' +
           (M.sector || '—') + '</span>.' },
      wknd,

      /* Лидер потока — та же монета, что «ПОТОК» на орбите: лучший
         score среди FLOW-детектированных. */
      L.t
        ? { p: 'Лидер потока ' + L.t + capP(L) + ' — ' + L.case + ', score ' + L.score + '.',
            h: 'Лидер потока <span class="t gd">' + L.t + '</span>' + cap(L) +
               ' — ' + L.case + ', score <span class="n">' + L.score +
               '</span>.' }
        : null,

      /* Все монеты FLOW с объёмом ×30+ на любом ТФ — не только лидер:
         сильный по score не обязан быть объёмным, и наоборот. */
      bigVol.length
        ? { p: 'Объём ×30+ у ' + bigVol.map(function (v) {
              return v.t + capP(v) + ' ×' + v.x; }).join(', ') + '.',
            h: 'Объём ×30+ у ' + bigVol.map(function (v) {
              return '<span class="t">' + v.t + '</span>' + cap(v) +
                ' <span class="n">×' + v.x + '</span>'; }).join(', ') + '.' }
        : null,

      /* Топ-3 по объёму за сутки — те же монеты, что под графиком
         в блоке ОБЪЁМ на орбите. */
      TV.length
        ? { p: 'Больше всех объёма ' + TV.map(function (v) {
              return v.t + capP(v) + ' ×' + v.x; }).join(', ') + '.',
            h: 'Больше всех объёма ' + TV.map(function (v) {
              return '<span class="t">' + v.t + '</span>' + cap(v) +
                ' <span class="n">×' + v.x + '</span>'; }).join(', ') + '.' }
        : null,

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
      d.className = 'obf-p';
      if (reduce) d.innerHTML = l.h;
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
    function typeLine(i) {
      if (i >= lines.length) { tail(); return; }
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
