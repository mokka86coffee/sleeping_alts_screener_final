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

    /* День недели считаем в МСК явно (UTC+3, без перевода часов):
       окно привязано к торговой неделе, а не к часовому поясу читателя.
       В прототипе день подменяется константой ниже — иначе строку не
       увидеть до пятницы. В проекте BRIEF_DAY должен быть null. */
    var BRIEF_DAY = null;   // 5 пт · 6 сб · 0 вс · null — реальный день
    var mskNow = new Date(Date.now() + new Date().getTimezoneOffset() * 60000
                          + 3 * 3600000);
    var day = BRIEF_DAY === null ? mskNow.getDay() : BRIEF_DAY;

    var wknd = null;
    if (day === 5) {
      wknd = { p: 'Завтра выходные — торговать сегодня с осторожностью.',
               h: '<span class="warn">Завтра выходные</span> — торговать ' +
                  'сегодня с осторожностью.' };
    } else if (day === 6 || day === 0) {
      wknd = { p: 'Выходные — лучше не торговать, риск высокий.',
               h: '<span class="warn">Выходные</span> — лучше не торговать, ' +
                  '<span class="dn">риск высокий</span>.' };
    }

    /* Новые в топ-3 по FLOW: не «в журнале вообще», а те, кто поднялся
       в тройку именно этим прогоном. Это единственная строка про
       изменение, а не про состояние — и потому самая заметная. */
    var fresh3 = STARS.filter(function (s) { return s.newTop3; }).slice(0, 3);

    function cap(s) { return s.cap ? ' <span class="obf-cap">' + s.cap + '</span>' : ''; }
    function capP(s) { return s.cap ? ' ' + s.cap : ''; }

    var L = M.leader || {};
    var TV = (M.topVol || []).slice(0, 3);
    var HR = M.hourly || { n: 0, list: [] };
    /* Все монеты FLOW с объёмом ×30+ на любом ТФ */
    var bigVol = (M.flowVol || []).slice(0, 5);
    /* Пересечение с журналом ищем здесь, а не в Python: обоим спискам
       уже нужно было прийти на страницу, и сверять тикеры проще на
       том же массиве STARS, чем тащить отдельный флаг из снимка. */
    var VI = bigVol.filter(function (v) {
      return STARS.some(function (s) { return s.t === v.t; });
    }).slice(0, 3);

    var lines = [
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

      /* Совпадение объёмного отбора и журнала — редкое событие,
         поэтому отдельная строка, а не пометка внутри списка. */
      VI.length
        ? { p: 'Объём пришёл в ' + plain(VI) + ' — они уже в потоке.',
            h: 'Объём пришёл в ' + names(VI, 'gd') +
               ' — они <span class="gd">уже в потоке</span>.' }
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
      hold.length
        ? { p: 'В работе ' + plain(hold) + ' — тренд подтверждается.',
            h: 'В работе ' + names(hold, 'gd') +
               ' — тренд подтверждается.' }
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
    ].filter(Boolean);

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
