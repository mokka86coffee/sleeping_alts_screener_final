# Нижняя часть сводки: ряды отбора, спячка, причины ожидания, хвост журнала

## файл: `render/brief.py`


Стили новых элементов живут в самом модуле, как у podium.py: css.py
уже ловил дубли блоков при патчах, добавлять туда новые классы не
хочется. Все имена с префиксом obf-.

### было

```python
BRIEF_HTML = """
<div class="ob-brief" id="obBrief">
  <div class="obf-glow"></div>
```

### стало

```python
BRIEF_HTML = """
<style>
/* Стили нижней части сводки. Живут в модуле, а не в css.py, по той
   же причине, что у podium.py: общий файл стилей уже ловил дубли
   блоков при патчах. Дублирование правил у .obf-ring ниже —
   страховка: базовые размеры кольца объявлены в css.py рядом с
   блоками лидеров, и если их когда-нибудь заскопируют под .obf-br,
   кольца в рядах не должны развалиться. */
.obf-go{margin:10px 0 4px;opacity:0;transition:opacity .5s ease}
.obf-go.on{opacity:1}
.obf-sk{font-size:10px;letter-spacing:.4em;color:#8b8a92;margin-bottom:2px}
.obf-sw{font-size:12px;color:#5d5c66;margin-bottom:10px}
.obf-row{display:grid;grid-template-columns:3px 112px 62px 1fr 215px 46px;
  gap:13px;align-items:center;padding:8px 12px 8px 0;border-radius:8px;
  background:linear-gradient(90deg,rgba(255,255,255,.025),transparent 55%);
  margin-bottom:7px;opacity:0;transform:translateY(6px);
  transition:opacity .6s ease var(--d,0s),transform .6s ease var(--d,0s)}
.obf-go.on .obf-row{opacity:1;transform:none}
.obf-rr{height:100%;border-radius:2px;background:#4FCF8A}
.obf-rt{font-size:16px;font-weight:600;letter-spacing:.07em}
.obf-rc{font-size:12.5px;color:#4FCF8A}
.obf-rw{font-size:13px;color:#8b8a92}
.obf-rw b{color:#E8EEF4;font-weight:600}
.obf-rh{font-size:12px;color:#5d5c66;text-align:right}
.obf-rh b{color:#8b8a92;font-weight:600}
.obf-row .obf-ring{width:44px;height:44px}
.obf-row .obf-ring circle.v{stroke-dasharray:113;stroke-dashoffset:var(--off)}
.dorm{color:#8FA8FF}
.obf-sep{color:#5d5c66;padding:0 2px}
.obf-tail{font-size:13px;color:#8b8a92}
.obf-tail b{color:#E8EEF4;font-weight:600}
@media (max-width:760px){
  .obf-row{grid-template-columns:3px 90px 1fr 42px;gap:10px}
  .obf-rc,.obf-rh{display:none}
}
</style>
<div class="ob-brief" id="obBrief">
  <div class="obf-glow"></div>
```

### было

```python
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
```

### стало

```python
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

    /* Порядок внутри групп. STARS отсортированы по свежести ПО
       ВОЗРАСТАНИЮ (так рисует орбита: лидер поверх всех), и прежний
       slice(0,3) без пересортировки брал три самые СТАРЫЕ записи
       журнала. «Рассмотреть» ранжируется силой текущего прогона:
       вопрос строки — готовность, и это то же число, что в кольце
       лидера. Персистентность журнала (hits/runsSeen) в ранг не
       вмешивается и стоит рядом справкой — готовность и «кто
       возвращается» отвечают на разные вопросы, смешивать их в один
       балл нельзя. «Ждут» — свежестью по убыванию: score им пока
       нечем набрать, единственная новость про них — что появились. */
    go.sort(function (a, b) { return (b.score || 0) - (a.score || 0); });
    wait.sort(function (a, b) { return (b.f || 0) - (a.f || 0); });
    hold.sort(function (a, b) { return (b.streak || 0) - (a.streak || 0); });

    var near = STARS.filter(function (s) { return s.stop && toStop(s) <= 8; })
      .sort(function (a, b) { return toStop(a) - toStop(b); }).slice(0, 3);

    /* Причина ожидания у каждой монеты своя. Прежняя подпись
       «первый разгон, входить рано» приписывала одну причину всем,
       хотя в wait сваливаются и «вне зоны дна», и «ровный рост».
       Порядок проверок повторяет phase(): сначала гейт по ATH,
       потом первый разгон, остальное — ровный рост без сквиза. */
    function waitWhy(s) {
      if (s.ath === undefined) return 'нет данных прогона';
      if ((s.ath || 0) > -80) return 'вне зоны дна, ' +
        Math.round(s.ath) + '% от ATH';
      if (s.firstRun) return 'первый разгон, входить рано';
      return 'ровный рост, ждать сквиза';
    }

    /* Ряд отбора. Один ряд — одна монета, порядок рядов и есть ранг:
       верхняя строка сильнее нижней, и это видно без чисел. Кольцо —
       тот же chartRing, что у лидера потока: одно понятие «силы» на
       весь экран, а не два разных числа в двух местах. */
    function rowHTML(s, i) {
      var hist = (s.runsSeen || 0) > 0
        ? 'в лидерах <b>' + (s.hits || 0) + ' из ' + s.runsSeen +
          '</b> прогонов · ' + (s.days || 0) + ' дн в журнале'
        : '—';
      var move = '<b>' + (s.up >= 0 ? '+' : '') + (s.up || 0) +
        '%</b> от дна за <b>' + (s.updays || 0) + ' дн</b>' +
        (s.chg !== undefined
          ? ' · от входа <b>' + (s.chg >= 0 ? '+' : '') + s.chg + '%</b>'
          : '');
      return '<div class="obf-row" style="--d:' + (i * 0.22).toFixed(2) +
        's"><div class="obf-rr"></div>' +
        '<div class="obf-rt">' + s.t + cap(s) + '</div>' +
        '<div class="obf-rc">' + (s.st || '—') + '</div>' +
        '<div class="obf-rw">' + move + '</div>' +
        '<div class="obf-rh">' + hist + '</div>' +
        chartRing('obfRow' + i, '#2E7A55', '#8FE8B4',
          (s.score || 0) / 100, s.score || 0, 12) +
      '</div>';
    }
```

### было

```python
    /* Новые в топ-3 по FLOW: не «в журнале вообще», а те, кто поднялся
       в тройку именно этим прогоном. Это единственная строка про
       изменение, а не про состояние — и потому самая заметная. */
    var fresh3 = STARS.filter(function (s) { return s.newTop3; }).slice(0, 3);
```

### стало

```python
    /* «Новые в топ-3» удалены: поле newTop3 никто никогда не писал,
       строка была мертва с заведения. Честная замена — «новые в
       журнале этим прогоном»: она считается в Python
       (_orbit_journal, since_run == счётчику прогонов) и приходит
       готовой в M.journal, вместе с лучшим и худшим ходом от входа.
       Спячка — из кандидатов прогона (M.dormant), не из журнала:
       в журнал попадают лидеры, а спячка случается раньше. */
    var J = M.journal || {};
    var DORM = M.dormant || [];
```

### было

```python
    function names(list, cls) {
      return list.slice(0, 3).map(function (s) {
        return '<span class="t ' + (cls || '') + '">' + s.t + '</span>' + cap(s);
      }).join(', ');
    }
    function plain(list) {
      return list.slice(0, 3).map(function (s) {
        return s.t + capP(s); }).join(', ');
    }
```

### стало

```python
    /* names()/plain() удалены: последние читатели — старые строки
       «новые в топ-3», «рассмотреть» и «ждут» — заменены рядами и
       строками с индивидуальной причиной, где разметка своя. */
```

### было

```python
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
```

### стало

```python
      /* Отбор — рядами, не перечислением: у строки-действия должно
         быть видно, ПОЧЕМУ монета здесь и какая сильнее. */
      go.length
        ? { rows: go.slice(0, 3), label: 'РАССМОТРЕТЬ СТОИТ',
            why: 'первая фаза, у дна · порядок — по силе прогона' }
        : { p: 'Сегодня брать нечего.', h: '<span class="mut">Сегодня брать нечего.</span>' },

      /* Спячка — единственное состояние ДО движения; до этой строки
         сводка пересказывала только то, что уже идёт или прошло.
         «База узкая» — гейт подкейса, а не оценка, поэтому фраза
         честна для любой монеты списка. */
      DORM.length
        ? { p: 'Спят ' + DORM.map(function (d) {
              return d.t + (d.cap ? ' ' + d.cap : ''); }).join(', ') +
              ' — цикл был, база узкая. Движения ещё нет: наблюдать, ' +
              'не входить.',
            h: 'Спят ' + DORM.map(function (d) {
              return '<span class="t dorm">' + d.t + '</span>' +
                (d.cap ? ' <span class="obf-cap">' + d.cap + '</span>' : '');
            }).join(', ') +
            ' — <span class="dorm">цикл был, база узкая</span>. ' +
            'Движения ещё нет: наблюдать, не входить.' }
        : null,

      wait.length
        ? { p: 'Ждут сигнала ' + wait.slice(0, 3).map(function (s) {
              return s.t + capP(s) + ' — ' + waitWhy(s); }).join(' · ') + '.',
            h: 'Ждут сигнала ' + wait.slice(0, 3).map(function (s) {
              return '<span class="t">' + s.t + '</span>' + cap(s) +
                ' <span class="mut">— ' + waitWhy(s) + '</span>';
            }).join(' <span class="obf-sep">·</span> ') + '.' }
        : null,
```

### было

```python
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
```

### стало

```python
      near.length
        ? { p: 'У уровня ' + near.map(function (s) {
              return s.t + capP(s) + ' −' + toStop(s) + '%'; }).join(', ') +
              ' — решаются сегодня.',
            h: 'У уровня ' + near.map(function (s) {
              return '<span class="t">' + s.t + '</span>' + cap(s) +
                ' <span class="dn n">−' + toStop(s) + '%</span>';
            }).join(', ') + ' — решаются сегодня.' }
        : null,

      /* Хвост журнала — единственная строка экрана про сам скринер:
         работает ли отбор. Первый потребитель счётчиков hits/runs_seen
         и лучшего/худшего хода от входа. */
      J.n
        ? { p: 'Журнал: ' + J.n + ' ' +
              plural(J.n, 'монета', 'монеты', 'монет') +
              (J.fresh && J.fresh.length
                ? ', новых этим прогоном — ' + J.fresh.join(', ') : '') +
              '. Лучший ход от входа ' + J.best.t + ' ' +
              (J.best.chg >= 0 ? '+' : '') + J.best.chg + '%' +
              (J.worst.t !== J.best.t
                ? ', худший ' + J.worst.t + ' ' +
                  (J.worst.chg >= 0 ? '+' : '') + J.worst.chg + '%'
                : '') + '.',
            h: '<span class="obf-tail">Журнал: <b>' + J.n + '</b> ' +
              plural(J.n, 'монета', 'монеты', 'монет') +
              (J.fresh && J.fresh.length
                ? ', новых этим прогоном — <b>' + J.fresh.join(', ') +
                  '</b>' : '') +
              '. Лучший ход от входа <b class="up">' + J.best.t + ' ' +
              (J.best.chg >= 0 ? '+' : '') + J.best.chg + '%</b>' +
              (J.worst.t !== J.best.t
                ? ', худший <b class="dn">' + J.worst.t + ' ' +
                  (J.worst.chg >= 0 ? '+' : '') + J.worst.chg + '%</b>'
                : '') + '.</span>' }
        : null
    ]).filter(Boolean);
```

### было

```python
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
```

### стало

```python
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
      } else if (l.rows) {
        /* Секция рядов отбора: как блок — не печатается, въезжает
           классом, ряды со ступенчатой задержкой через --d. */
        d.className = 'obf-go';
        d.innerHTML = '<div class="obf-sk">' + l.label + '</div>' +
          '<div class="obf-sw">' + l.why + '</div>' +
          l.rows.map(rowHTML).join('');
        if (reduce) d.classList.add('on');
      } else {
        d.className = 'obf-p';
        if (reduce) d.innerHTML = l.h;
      }
      host.appendChild(d);
      return d;
    });
```

### было

```python
    var BLOCK_HOLD = 7400;
```

### стало

```python
    var BLOCK_HOLD = 7400;

    /* Пауза на секцию рядов. Въезд короткий (три ряда за ~1.1с),
       но это самая плотная строка экрана — три монеты с числами,
       на чтение нужно больше, чем на график с одной кривой. */
    var ROWS_HOLD = 5200;
```

### было

```python
      /* Блок не печатается: он рисуется сам, и посимвольный набор
         поверх прорисовки читался бы как два движения разом. */
      if (lines[i].block) {
        els[i].classList.add('on');
        setTimeout(function () { typeLine(i + 1); }, BLOCK_HOLD);
        return;
      }
```

### стало

```python
      /* Блок не печатается: он рисуется сам, и посимвольный набор
         поверх прорисовки читался бы как два движения разом.
         Секция рядов ведёт себя так же, но пауза своя. */
      if (lines[i].block || lines[i].rows) {
        els[i].classList.add('on');
        setTimeout(function () { typeLine(i + 1); },
          lines[i].rows ? ROWS_HOLD : BLOCK_HOLD);
        return;
      }
```
