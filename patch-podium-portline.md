# Верхняя строка оверлея: сводка портфеля и глубокие просадки

## файл: `render/podium.py`

Применять ПОСЛЕ `patch-podium-note-size.md` и
`patch-leaders-rules.md`.

Верхняя строка зала до сих пор говорила «лидеры прогона» и число
монет. Первое видно и так, второе — тоже. Место отдаётся сводке: во
что превратились находки и какие монеты требуют разбора.

Просадка показывается с фигурой и датой входа, а не одним процентом:
вопрос при разборе не «сколько потеряли», а «какая стратегия и когда
завела нас сюда». Без этих двух полей строка не отвечает ни на что.

Данные берутся из `ORB.market.journal.port` — той же сводки, что
читает бриф. Второго расчёта не заводится: правило вложения живёт в
журнале, экраны его только показывают.

### было

```python
.obp-stamp{font-family:ui-monospace,Menlo,monospace;font-size:10px;color:#454C57}
```

### стало

```python
.obp-stamp{font-family:ui-monospace,Menlo,monospace;font-size:10px;color:#454C57}

/* Сводка портфеля в шапке. Занимает середину строки: слева заголовок,
   справа кнопка выхода, и обе уже прижаты к краям. */
.obp-port{position:absolute;left:210px;right:210px;top:16px;z-index:7;
  text-align:center;font-family:ui-monospace,Menlo,monospace;
  font-size:11px;letter-spacing:.04em;color:#8D97A6;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.obp-port b{font-weight:600;color:#E3E8EF}
.obp-port b.up{color:#5FE39C} .obp-port b.dn{color:#FF8A72}
.obp-port .sep{color:#3A414C;padding:0 8px}
.obp-port .loss{color:#B9C2CE}
.obp-port .loss i{font-style:normal;color:#5A6270}
@media (max-width:1100px){ .obp-port{display:none} }
```

### было

```python
  <div class="obp-top">
    <div class="obp-h">лидеры прогона</div>
    <div class="obp-stamp" id="obPodStamp"></div>
  </div>
```

### стало

```python
  <div class="obp-top">
    <div class="obp-h">лидеры прогона</div>
    <div class="obp-port" id="obpPort"></div>
    <div class="obp-stamp" id="obPodStamp"></div>
  </div>
```

### было

```python
  function show() {
    if (opened) return;
    opened = true;
    build();
    apply();
    pod.classList.add('on');
  }
```

### стало

```python
  /* ── Сводка портфеля в шапке ──
     Две части. Итог отвечает «чего стоят находки», список просадок —
     «что разбирать руками». Второе без первого выглядело бы
     жалобой, первое без второго — отчётом без работы над ошибками.

     Просадка идёт с фигурой и датой входа: при разборе вопрос не
     «сколько потеряли», а «какая стратегия и когда сюда завела». */
  function portLine() {
    var host = document.getElementById('obpPort');
    if (!host) return;
    var j = (O.market && O.market.journal) || {};
    var p = j.port;
    if (!p || !p.invested) { host.innerHTML = ''; return; }

    var money = function (v) {
      var n = +v || 0;
      return n >= 10000 ? '$' + (n / 1000).toFixed(1) + 'K' :
             '$' + Math.round(n);
    };
    var sign = function (v) {
      var n = +v || 0;
      return (n >= 0 ? '+' : '') + n.toFixed(1) + '%';
    };

    var out = money(p.value) + ' <b class="' +
      (p.pnl_pct >= 0 ? 'up' : 'dn') + '">' + sign(p.pnl_pct) + '</b>';
    if (p.rules_pnl_pct !== undefined && p.rules_pnl_pct !== p.pnl_pct) {
      out += ' <span class="sep">·</span> по правилам <b class="' +
        (p.rules_pnl_pct >= 0 ? 'up' : 'dn') + '">' +
        sign(p.rules_pnl_pct) + '</b>';
    }

    var L = p.losers || [];
    if (L.length) {
      out += ' <span class="sep">·</span> <span class="loss">разобрать: ' +
        L.map(function (d) {
          return d.t + ' <b class="dn">' + sign(d.chg) + '</b> <i>' +
            (d.case || '?') + ', ' + (d.at || '').slice(5) + '</i>';
        }).join(', ');
      if (p.losers_all > L.length) {
        out += ' <i>и ещё ' + (p.losers_all - L.length) + '</i>';
      }
      out += '</span>';
    }
    host.innerHTML = out;
  }

  function show() {
    if (opened) return;
    opened = true;
    build();
    apply();
    portLine();
    pod.classList.add('on');
  }
```
