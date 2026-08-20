# Патч: этаж 2 — дельты pulse.json в подвале карточки

Применять после обновлённого `analytics_momentum.py` (дописан —
добавлены `pulse_note()`/`star_pulse()`) и после
`patch-oi-state-common.md`.

Данные для этажа 2 копятся в `pulse.json` с того момента, как ожил
`record()` в `run.py` (см. patch-run-pulse-import.md) — на первых
нескольких прогонах после применения строка может не появляться
вовсе: `for_symbol()` честно возвращает пусто при истории короче двух
точек, это не баг, а нормальное состояние до накопления истории.

## файл: `render_orbit.py`

### было
```python
from analytics_momentum import star_oi, star_late
```

### стало
```python
from analytics_momentum import star_oi, star_late, star_pulse
```

### было
```python
            **_star_intraday(raw),
            **_star_unlocks(raw),
            **star_oi(c),
            **star_late(c),
```

### стало
```python
            **_star_intraday(raw),
            **_star_unlocks(raw),
            **star_oi(c),
            **star_late(c),
            **star_pulse(sym),
```

## файл: `render_cardscene.py`

### было
```
    /* Ч-4: fuel помечает себя late на свежем росте (growth_load) —
       диспетчер это уже знает при выборе победителя, экран молчал. */
    if (c.late) foot.push(['осторожно', 'фигура уже отыграна', 'hot']);
```

### стало
```
    /* Ч-4: fuel помечает себя late на свежем росте (growth_load) —
       диспетчер это уже знает при выборе победителя, экран молчал. */
    if (c.late) foot.push(['осторожно', 'фигура уже отыграна', 'hot']);

    /* Этаж 2: что изменилось за последние часы — единственная строка
       подвала, отвечающая не «какое состояние сейчас», а «куда оно
       движется». Источник — analytics_pulse через
       analytics_momentum.star_pulse(): одно наблюдение, самое
       значимое из score/плеча/перевеса сторон/цены/разворота
       вортекса за ближайший из трёх горизонтов (прошлый прогон,
       6 часов, сутки). Пусто, пока история короче двух точек —
       это нормально в первые прогоны после подключения pulse. */
    if (c.pulseKind) {
      var pSpan = c.pulseSpan === 'prev' ? 'с прошлого прогона'
        : c.pulseSpan === 'h6' ? 'за 6 часов' : 'за сутки';
      var pTxt = '';
      if (c.pulseKind === 'score')
        pTxt = (c.pulseDelta >= 0 ? '+' : '') + Math.round(c.pulseDelta) + ' очков';
      else if (c.pulseKind === 'oi_x')
        pTxt = (c.pulseDelta >= 0 ? '+' : '') + c.pulseDelta.toFixed(2) + ' плечо';
      else if (c.pulseKind === 'buy_share')
        pTxt = (c.pulseDelta >= 0 ? 'покупка +' : 'продажа ') +
          Math.abs(c.pulseDelta * 100).toFixed(1) + ' п.п.';
      else if (c.pulseKind === 'price_pct')
        pTxt = (c.pulseDelta >= 0 ? '+' : '') + c.pulseDelta.toFixed(1) + '%';
      else if (c.pulseKind === 'vx_flip')
        pTxt = 'вортекс ' + c.pulseFrom + ' → ' + c.pulseTo;
      if (pTxt) foot.push(['за час-двое', pTxt + ' · ' + pSpan,
        c.pulseKind === 'vx_flip' ? 'hot' : '']);
    }
```
