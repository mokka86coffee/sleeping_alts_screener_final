# Часовой ряд · пустое должно выглядеть пустым

Правки в `render/cardscene.py`, **поверх** `patch-cardscene-2.md`.
Сначала применить тот, иначе якоря не совпадут.

Причина одна. В боевых данных `h48` часто пуст, и подиум это учитывает:
`h48HTML` при ряде короче шести точек не рисует ничего. Карточка же
прогоняла пустоту через `resample`, получала массив одинаковых чисел и
показывала ровную светящуюся линию через все сутки — то есть придуманное
показание вместо честного пропуска.

---

## 1 · часовой ряд: есть или нет — `render/cardscene.py`

Порог в шесть точек взят тот же, что у панели на стене зала
(`h48HTML` в podium.py): карточка и панель должны молчать в одних и
тех же случаях, иначе одна и та же монета выглядит по-разному в двух
местах отчёта.

### Было

```python
  var RIDGE_N = 28, HOURS_N = 24;
```

### Стало

```python
  var RIDGE_N = 28, HOURS_N = 24;

  /* Часовой ряд бывает пустым, и это не редкость. Плоская линия из
     подставленных нулей выглядит как показание — «объём весь день
     ровный», — хотя означает «мы ничего не знаем». Порог в шесть
     точек взят тот же, что у панели на стене зала (h48HTML), чтобы
     карточка и панель молчали в одних и тех же случаях. */
  function hoursOf(c) {
    var s = (c.h48 || []).map(Number).filter(function (v) {
      return isFinite(v) && v > 0;
    });
    return s.length < 6 ? null : resample(s, HOURS_N);
  }
```

---

## 2 · подстановка ряда в данные карточки — `render/cardscene.py`

### Было

```python
      hours: resample(c.h48, HOURS_N),
```

### Стало

```python
      hours: hoursOf(c),
```

---

## 3 · полоса: гребёнка строится, только если есть из чего — `render/cardscene.py`

Прежний `resample` при пустом ряде возвращал массив из подставленных
нулей, и полоса рисовала ровную светящуюся линию. Это читается как
показание — «объём весь день ровный», — хотя означает «мы ничего не
знаем». Худший вид вранья: не пропуск, а придуманное значение.

### Было

```python
    const px = i => x0 + (x1 - x0) * i / (d.hours.length - 1);
    const py = v => base - (base - top) * v;

    let hair = '', hn = 0;
    const dly = () => `style="animation-delay:${(.84 + hn++ * .024).toFixed(3)}s"`;
    d.hours.forEach((v, i) => {
```

### Стало

```python
    /* Ряда за сутки может не быть вовсе, и это не редкость. Плоская
       линия из подставленных нулей читалась бы как показание — «объём
       весь день ровный», — хотя означает «мы ничего не знаем». Поэтому
       при пустом ряде линия и гребёнка не рисуются, а подпись прямо
       говорит, чего нет. Приборы по краям остаются: они на этот ряд
       не опираются. */
    const H = d.hours || [], has = H.length > 1;
    const px = i => x0 + (x1 - x0) * i / Math.max(1, H.length - 1);
    const py = v => base - (base - top) * v;

    let hair = '', hn = 0, path = '', lx = x1, ly = base;
    const dly = () => `style="animation-delay:${(.84 + hn++ * .024).toFixed(3)}s"`;
    if (has) H.forEach((v, i) => {
```

---

## 4 · промежуточные волоски — по тому же ряду — `render/cardscene.py`

### Было

```python
      if (i < d.hours.length - 1)
        for (let k = 1; k < 3; k++){
          const t = (i + k/3), a = Math.floor(t), f = t - a;
          const vv = d.hours[a] + (d.hours[a+1] - d.hours[a]) * f;
```

### Стало

```python
      if (i < H.length - 1)
        for (let k = 1; k < 3; k++){
          const t = (i + k/3), a = Math.floor(t), f = t - a;
          const vv = H[a] + (H[a+1] - H[a]) * f;
```

---

## 5 · линия строится под тем же условием — `render/cardscene.py`

### Было

```python
    let path = '';
    d.hours.forEach((v, i) => {
      const x = px(i), y = py(v);
      if (!i) path = `M${x.toFixed(1)},${y.toFixed(1)}`;
      else {
        const xp = px(i-1), yp = py(d.hours[i-1]), cx = (xp + x)/2;
        path += ` C${cx.toFixed(1)},${yp.toFixed(1)} ${cx.toFixed(1)},${y.toFixed(1)} ${x.toFixed(1)},${y.toFixed(1)}`;
      }
    });
    const lx = px(d.hours.length-1), ly = py(d.hours[d.hours.length-1]);
```

### Стало

```python
    if (has) {
      H.forEach((v, i) => {
        const x = px(i), y = py(v);
        if (!i) path = `M${x.toFixed(1)},${y.toFixed(1)}`;
        else {
          const xp = px(i-1), yp = py(H[i-1]), cx = (xp + x)/2;
          path += ` C${cx.toFixed(1)},${yp.toFixed(1)} ${cx.toFixed(1)},${y.toFixed(1)} ${x.toFixed(1)},${y.toFixed(1)}`;
        }
      });
      lx = px(H.length-1); ly = py(H[H.length-1]);
    }
```

---

## 6 · разметка полосы: пусто — значит сказано, что пусто — `render/cardscene.py`

Засечки часов, линия и огонёк на конце пропадают вместе с рядом.
Подпись меняется с «24 часа · объём» на «24 часа · ряда нет».
Приборы по краям остаются: они на этот ряд не опираются.

### Было

```python
      ${[0,6,12,18,23].map(i => `<line class="tk" x1="${px(i).toFixed(1)}" y1="${base}"
          x2="${px(i).toFixed(1)}" y2="${base+7}"/>`).join('')}
      <path class="ln" d="${path}" filter="url(#gl)"/>
      <circle class="tipdot" cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="3.6"
              fill="#FFE7BE" filter="url(#gl)"/>
      <text x="${x0}" y="${base+22}" class="cap2" text-anchor="start">24 часа · объём</text>
```

### Стало

```python
      ${has ? [0,6,12,18,23].map(i => `<line class="tk" x1="${px(i).toFixed(1)}" y1="${base}"
          x2="${px(i).toFixed(1)}" y2="${base+7}"/>`).join('') : ''}
      ${has ? `<path class="ln" d="${path}" filter="url(#gl)"/>
      <circle class="tipdot" cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="3.6"
              fill="#FFE7BE" filter="url(#gl)"/>` : ''}
      <text x="${x0}" y="${base+22}" class="cap2" text-anchor="start">${
        has ? '24 часа · объём' : '24 часа · ряда нет'}</text>
```
