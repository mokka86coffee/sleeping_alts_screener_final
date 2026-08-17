# Парус, след предыдущей монеты и починка переходов

Правки в `render/cardscene.py`, **поверх** патчей 2, 3, 4 и 6.
(Пятый не нужен — он поглощён шестым.)

Три группы, откатываются по отдельности: 1 и 14–15 — переходы,
2–4 — парус и крен, 5–6 — левый прибор, 7–8 — след, 9–13 — берег.

---

## 1 · уходит всё, что написано словами — `render/cardscene.py`

Гасли только подписи столбов, полоса приборов и фраза. Тикер,
стратегия и капитализация в списке отсутствовали — стояли
неподвижно всю первую половину перехода и подменялись рывком.

Отдельно: у нижней строки и капитализации есть собственный наклон, и
правило ухода его затирало — перспектива слетала в первом же кадре.
Свой поворот теперь перенесён в правило ухода целиком, а сдвиг
добавляется к нему, а не вместо него.

### Было

```python
#obcRoot .col, #obcRoot .foot, #obcRoot #obcDiag{transition:opacity 1.35s ease,transform 1.35s ease}
#obcRoot .lay.out .col, #obcRoot .lay.out .foot, #obcRoot .lay.out #obcDiag{opacity:0;transform:translateY(14px)}
```

### Стало

```python
/* Уходить должно всё, что написано словами, иначе половина кадра
   растворяется, а вторая подменяется рывком — это и читается как
   дефект. Имя, стратегия, фраза и капитализация теперь гаснут вместе
   с подписями и приборной полосой. */
#obcRoot .col, #obcRoot .foot, #obcRoot #obcDiag,
#obcRoot .bname, #obcRoot .bstr, #obcRoot .obc-note, #obcRoot .obc-cap{
  transition:opacity 1.75s ease,transform 1.75s ease}
#obcRoot .lay.out .col, #obcRoot .lay.out #obcDiag,
#obcRoot .lay.out .obc-note{opacity:0;transform:translateY(14px)}
/* У нижней строки и капитализации есть собственный наклон, и правило
   ухода его затирало: перспектива слетала в первом же кадре, отчего
   уход читался рывком, а не уходом. Свой поворот переносим сюда
   целиком и добавляем сдвиг к нему, а не вместо него. */
#obcRoot .lay.out .foot{opacity:0;
  transform:perspective(900px) rotateX(16deg) translateY(14px)}
#obcRoot .lay.out .obc-cap{opacity:0;
  transform:perspective(800px) rotateX(12deg) rotateY(9deg) translateY(14px)}
/* Столбец тикера уходит вверх, откуда и пришёл, — вниз ему некуда:
   он стоит вертикально и упирается в край кадра. */
#obcRoot .lay.out .bname, #obcRoot .lay.out .bstr{opacity:0;transform:translateY(-12px)}
```

---

## 2 · парус несёт вортекс — `render/cardscene.py`

У лодки был парус, который ничего не значил. Теперь он наполнен в ту
сторону, куда тянет вортекс, а крен корпуса взят из скорости хода.
«Вниз двенадцать баров при 1.3 ATR» видно на воде раньше, чем
прочитано хоть одно число, — и в кадре не появилось ни одного нового
предмета, только объяснился тот, что уже плавал.

Зеркалим парус относительно мачты: она стоит на x=150, значит
отражение это x' = 300 − x.

### Было

```python
#obcRoot .boat{position:absolute;left:17%;top:54%;width:11.5%;pointer-events:none}
#obcRoot .boat .drift{animation:ocDrift 26s ease-in-out infinite alternate}
```

### Стало

```python
#obcRoot .boat{position:absolute;left:17%;top:54%;width:11.5%;pointer-events:none}
/* ── Парус несёт вортекс ────────────────────────────────────
   У лодки был парус, который ничего не значил. Теперь он наполнен в
   ту сторону, куда тянет вортекс, а крен корпуса взят из скорости
   хода. «Вниз двенадцать баров при 1.3 ATR» видно на воде раньше,
   чем прочитано хоть одно число, — и мы не добавили в кадр ни одного
   нового предмета, только объяснили тот, что уже плавал.

   Зеркалим парус относительно мачты: она стоит на x=150, значит
   отражение это x' = 300 − x. */
#obcRoot .boat .sail{transform-origin:0 0}
#obcRoot .boat.wind-l .sail{transform:translateX(300px) scaleX(-1)}
#obcRoot .boat{transform:rotate(var(--heel,0deg));
  transform-origin:50% 68%;transition:transform 1.6s ease}
#obcRoot .boat .drift{animation:ocDrift 26s ease-in-out infinite alternate}
/* Лодку на переходе не трогаем. Смена длительности у идущей анимации
   пересчитывает фазу, и качка прыгает — а лодка и так всё время
   покачивается, этого достаточно. Единственное живое движение в
   кадре не должно спотыкаться ровно там, где на него смотрят. */
```

---

## 3 · отражение кренится вместе с лодкой — `render/cardscene.py`

### Было

```python
#obcRoot .boat.mir{opacity:.24;filter:blur(1.7px);
  transform:scaleY(-1);transform-origin:50% 66%;
```

### Стало

```python
#obcRoot .boat.mir{opacity:.24;filter:blur(1.7px);
  transform:scaleY(-1) rotate(var(--heel,0deg));transform-origin:50% 66%;
```

---

## 4 · парус в разметке лодки становится отдельной группой — `render/cardscene.py`

Группа нужна, чтобы зеркалить только парус, не трогая корпус и мачту.

### Было

```python
      <div class="boat" id="obcBoat">
        <div class="drift"><div class="bob"><div class="tilt">
          <svg viewBox="0 0 340 230">
    <!-- Парус несёт имя, поэтому он и есть главная форма: пять
    реек как на джонке, лёгкий пузырь по ветру, светлая
    кромка по наветренной стороне. -->
    <path d="M150,18 C214,34 246,74 250,132 L150,146 Z"
    fill="rgba(24,32,42,.92)" stroke="rgba(190,215,235,.30)" stroke-width="1.2"/>
    <g stroke="rgba(190,215,235,.16)" stroke-width="1" fill="none">
    <path d="M150,44 C196,54 218,78 224,110"/>
    <path d="M150,70 C186,78 204,96 212,122"/>
    <path d="M150,96 C178,102 194,114 202,130"/>
    <path d="M150,122 C170,126 182,132 190,138"/>
    </g>
```

### Стало

```python
      <div class="boat" id="obcBoat">
        <div class="drift"><div class="bob"><div class="tilt">
          <svg viewBox="0 0 340 230">
    <!-- Парус несёт имя, поэтому он и есть главная форма: пять
    реек как на джонке, лёгкий пузырь по ветру, светлая
    кромка по наветренной стороне. -->
    <g class="sail">
    <path d="M150,18 C214,34 246,74 250,132 L150,146 Z"
    fill="rgba(24,32,42,.92)" stroke="rgba(190,215,235,.30)" stroke-width="1.2"/>
    <g stroke="rgba(190,215,235,.16)" stroke-width="1" fill="none">
    <path d="M150,44 C196,54 218,78 224,110"/>
    <path d="M150,70 C186,78 204,96 212,122"/>
    <path d="M150,96 C178,102 194,114 202,130"/>
    <path d="M150,122 C170,126 182,132 190,138"/>
    </g>
    </g>
```

---

## 4б · то же в отражении лодки — `render/cardscene.py`

### Было

```python
      <div class="boat mir" id="obcBoatM" aria-hidden="true">
        <div class="drift"><div class="bob"><div class="tilt">
          <svg viewBox="0 0 340 230">
    <!-- Парус несёт имя, поэтому он и есть главная форма: пять
    реек как на джонке, лёгкий пузырь по ветру, светлая
    кромка по наветренной стороне. -->
    <path d="M150,18 C214,34 246,74 250,132 L150,146 Z"
    fill="rgba(24,32,42,.92)" stroke="rgba(190,215,235,.30)" stroke-width="1.2"/>
    <g stroke="rgba(190,215,235,.16)" stroke-width="1" fill="none">
    <path d="M150,44 C196,54 218,78 224,110"/>
    <path d="M150,70 C186,78 204,96 212,122"/>
    <path d="M150,96 C178,102 194,114 202,130"/>
    <path d="M150,122 C170,126 182,132 190,138"/>
    </g>
```

### Стало

```python
      <div class="boat mir" id="obcBoatM" aria-hidden="true">
        <div class="drift"><div class="bob"><div class="tilt">
          <svg viewBox="0 0 340 230">
    <!-- Парус несёт имя, поэтому он и есть главная форма: пять
    реек как на джонке, лёгкий пузырь по ветру, светлая
    кромка по наветренной стороне. -->
    <g class="sail">
    <path d="M150,18 C214,34 246,74 250,132 L150,146 Z"
    fill="rgba(24,32,42,.92)" stroke="rgba(190,215,235,.30)" stroke-width="1.2"/>
    <g stroke="rgba(190,215,235,.16)" stroke-width="1" fill="none">
    <path d="M150,44 C196,54 218,78 224,110"/>
    <path d="M150,70 C186,78 204,96 212,122"/>
    <path d="M150,96 C178,102 194,114 202,130"/>
    <path d="M150,122 C170,126 182,132 190,138"/>
    </g>
    </g>
```

---

## 5 · левый прибор: полезная величина вместо повтора — `render/cardscene.py`

Форма кольца, цифра внутри и подпись остаются как были. Менялось
только содержимое: «объём к рекорду» повторял высоту столба объёма
слово в слово — то же самое выражение. Положение в диапазоне суток
не повторяет ничего, и у него есть настоящий потолок, а кольцу без
потолка нельзя.

### Было

```python
      arcs: [['объём к рекорду', rec > 1 && vol > 1 ? Math.min(1, Math.log(vol) / Math.log(rec)) : 0]],
```

### Стало

```python
      /* Прибор прежний, величина другая. «Объём к рекорду» повторял
         высоту столба объёма слово в слово: log(vol)/log(rec) — то же
         выражение. Положение в диапазоне суток не повторяет ничего,
         и у него есть настоящий потолок, а кольцу без потолка нельзя. */
      arcs: [['в диапазоне', num(c.rangePos) === null ? 0
                             : Math.min(1, Math.max(0, c.rangePos / 100))]],
```

---

## 6 · «в диапазоне» уходит из нижней строки — `render/cardscene.py`

Иначе та же величина стояла бы в двух местах сразу. Строку не удаляем
молча, а заменяем пояснением: через месяц «почему в подвале нет
диапазона» — законный вопрос, и ответ должен лежать там же.

### Было

```python
    if (c.speedV) foot.push(['скорость хода', c.speedV + ' ATR/бар', '']);
    if (num(c.rangePos) !== null) foot.push(['в диапазоне', Math.round(c.rangePos) + '% снизу', '']);
```

### Стало

```python
    if (c.speedV) foot.push(['скорость хода', c.speedV + ' ATR/бар', '']);
    /* «В диапазоне» переехало в левый прибор: в подвале эта величина
       стояла бы вторым экземпляром той же самой. */
```

---

## 7 · прозрачность как отдельный множитель в drawSet — `render/cardscene.py`

### Было

```python
  function drawSet(g, set, fs){
    set.forEach((c, i) => {
      const f = fs[i];
      if (f <= .002) return;
      g.globalAlpha = Math.min(1, f * 1.5);
      g.drawImage(c.cv, c.x, WATER - c.h * f, c.w, c.h * f);
    });
    g.globalAlpha = 1;
  }
```

### Стало

```python
  function drawSet(g, set, fs, mul){
    set.forEach((c, i) => {
      const f = fs[i];
      if (f <= .002) return;
      g.globalAlpha = Math.min(1, f * 1.5) * (mul === undefined ? 1 : mul);
      g.drawImage(c.cv, c.x, WATER - c.h * f, c.w, c.h * f);
    });
    g.globalAlpha = 1;
  }
```

---

## 8 · след предыдущей монеты — `render/cardscene.py`

Столбы у всех монет стоят на одних и тех же местах, поэтому слабая
копия старой видна ровно там, где та была выше новой, и нигде
больше. Получается не вторая картинка поверх первой, а разница между
ними — то самое «выше или ниже», которое иначе приходится держать в
памяти при листании.

### Было

```python
    } else {
      drawSet(g, prepare(to), prepare(to).map(() => 1));
    }
```

### Стало

```python
    } else {
      /* След предыдущей монеты. Столбы у всех монет стоят на одних и
         тех же местах, поэтому слабая копия старой видна ровно там,
         где та была ВЫШЕ новой, и нигде больше. Получается не вторая
         картинка, а разница между двумя — то самое «выше или ниже»,
         которое иначе приходится держать в памяти при листании. */
      if (from !== to) drawSet(g, prepare(from), prepare(from).map(() => 1), .13);
      drawSet(g, prepare(to), prepare(to).map(() => 1));
    }
```

---

## 9 · берег принимает порыв и меняет свет — `render/cardscene.py`

Слой берега теперь можно пересобрать с двумя параметрами: силой ветра
и яркостью окон. Второе дерево качается слабее и в противофазе —
одинаковый ход у обоих читался бы качанием кадра, а не ветром.

### Было

```python
  function buildFG(){
    const g = fgL.getContext('2d'), r = mulberry(7);
    rock(g, 690, WATER, 190, 34, r);
    rock(g, 930, WATER, 150, 28, r);
    rock(g, 205, WATER, 120, 26, r);
    bonsai(g, 700, WATER - 18, 52, -1.5, 6, 4, r);
    bonsai(g, 940, WATER - 14, 44, -1.45, 5, 4, r);
    pagoda(g, 118, WATER - 6, 240);
  }
```

### Стало

```python
  function buildFG(sway, lamp){
    const g = fgL.getContext('2d'), r = mulberry(7);
    g.clearRect(0, 0, W, WATER);
    rock(g, 690, WATER, 190, 34, r);
    rock(g, 930, WATER, 150, 28, r);
    rock(g, 205, WATER, 120, 26, r);
    bonsai(g, 700, WATER - 18, 52, -1.5, 6, 4, r, sway || 0);
    // второе дерево качается слабее и с запозданием: одинаковый
    // ход у обоих читался бы качанием кадра, а не ветром
    bonsai(g, 940, WATER - 14, 44, -1.45, 5, 4, r, (sway || 0) * -.7);
    pagoda(g, 118, WATER - 6, 240, lamp === undefined ? 1 : lamp);
  }
```

---

## 10 · ветка принимает добавку к углу — `render/cardscene.py`

Добавка накапливается вглубь ветвей, поэтому ствол почти стоит, а
концы качаются заметно. Амплитуда выбрана так, чтобы у концов вышло
около трёх градусов: видно, что воздух шевельнулся, и не видно, что
кто-то качает деревья.

### Было

```python
  function bonsai(g, x, y, len, ang, wid, depth, r){
    if (depth === 0 || len < 4) return;
    const x2 = x + Math.cos(ang) * len, y2 = y + Math.sin(ang) * len;
    g.strokeStyle = '#04070A'; g.lineWidth = wid; g.lineCap = 'round';
    g.beginPath(); g.moveTo(x, y);
    g.quadraticCurveTo(x + Math.cos(ang - .3)*len*.6, y + Math.sin(ang - .3)*len*.6, x2, y2);
    g.stroke();
    if (depth <= 2){
      // крона — облако точек, а не заливка: у сосны на референсе
      // читается силуэт из отдельных хвойных подушек
      g.fillStyle = '#04070A';
      for (let i = 0; i < 90; i++){
        const a = r()*Math.PI*2, rr = Math.pow(r(),.55)*len*.85;
        g.fillRect(x2 + Math.cos(a)*rr, y2 + Math.sin(a)*rr*.42, 1.6, 1.6);
      }
    }
    const br = 2 + (r() > .6 ? 1 : 0);
    for (let i = 0; i < br; i++)
      bonsai(g, x2, y2, len*(.62 + r()*.16), ang + (r()-.5)*1.5 - .1, wid*.6, depth-1, r);
```

### Стало

```python
  /* sw — порыв ветра: добавка к углу, накапливающаяся вглубь ветвей,
     поэтому ствол почти стоит, а концы качаются заметно. */
  function bonsai(g, x, y, len, ang, wid, depth, r, sw){
    if (depth === 0 || len < 4) return;
    const x2 = x + Math.cos(ang) * len, y2 = y + Math.sin(ang) * len;
    g.strokeStyle = '#04070A'; g.lineWidth = wid; g.lineCap = 'round';
    g.beginPath(); g.moveTo(x, y);
    g.quadraticCurveTo(x + Math.cos(ang - .3)*len*.6, y + Math.sin(ang - .3)*len*.6, x2, y2);
    g.stroke();
    if (depth <= 2){
      // крона — облако точек, а не заливка: у сосны на референсе
      // читается силуэт из отдельных хвойных подушек
      g.fillStyle = '#04070A';
      for (let i = 0; i < 90; i++){
        const a = r()*Math.PI*2, rr = Math.pow(r(),.55)*len*.85;
        g.fillRect(x2 + Math.cos(a)*rr, y2 + Math.sin(a)*rr*.42, 1.6, 1.6);
      }
    }
    const br = 2 + (r() > .6 ? 1 : 0);
    for (let i = 0; i < br; i++)
      bonsai(g, x2, y2, len*(.62 + r()*.16), ang + (r()-.5)*1.5 - .1 + (sw || 0), wid*.6, depth-1, r, sw);
```

---

## 11 · пагода принимает силу света — `render/cardscene.py`

### Было

```python
  function pagoda(g, x, base, hgt){
```

### Стало

```python
  function pagoda(g, x, base, hgt, lamp){
```

---

## 12 · и применяет её к окнам — `render/cardscene.py`

### Было

```python
    g.fillStyle = 'rgba(255,132,50,.75)';
```

### Стало

```python
    g.fillStyle = 'rgba(255,132,50,' + (.75 * (lamp === undefined ? 1 : lamp)).toFixed(3) + ')';
```

---

## 13 · пересчёт берега на переходе — `render/cardscene.py`

Сила берётся как половина синусоиды от начала к концу: сильнее всего
в середине, где меняются данные. Слой пересобирается только пока идёт
переход; в покое он печётся один раз и просто копируется.

### Было

```python
      buildBG(a.map((v, i) => v + (b[i] - v) * m),
              CARDS[from].entry + (CARDS[to].entry - CARDS[from].entry) * m);
      // подписи меняем в момент, когда старые столбы уже утонули,
      // а новые ещё не поднялись: провал в середине перехода
      if (!swapped && tp >= .42){ swapped = true; labels(CARDS[to]); lay.classList.remove('out'); }
```

### Стало

```python
      buildBG(a.map((v, i) => v + (b[i] - v) * m),
              CARDS[from].entry + (CARDS[to].entry - CARDS[from].entry) * m);

      /* Берег на переходе не стоит истуканом: по деревьям проходит
         порыв, а свет в окнах приседает и разгорается обратно. Сильнее
         всего в середине, где меняются данные, — env как раз и есть
         половина синусоиды от начала к концу. Пересчёт слоя идёт
         только пока идёт переход; в покое он печётся один раз. */
      const env = Math.sin(Math.PI * tp);
      /* Порыв на треть градуса у концов веток: заметно, что воздух
         шевельнулся, и не заметно, что кто-то качает деревья. */
      buildFG(Math.sin(t * .0032) * .018 * env, 1 - .72 * env);
      if (tp === 1) { buildFG(0, 1); root.classList.remove('moving'); }
      // подписи меняем в момент, когда старые столбы уже утонули,
      // а новые ещё не поднялись: провал в середине перехода
      if (!swapped && tp >= .42){ swapped = true; applyCard(CARDS[to]); }
```

---

## 14 · снятие удержания при старте перехода — `render/cardscene.py`

Анимация появления заведена с `fill: both` и после проигрывания
продолжает удерживать конечную прозрачность. Удержанное анимацией
значение сильнее любого перехода, поэтому правило ухода до таких
элементов просто не доходило. Класс снимается на старте и
возвращается при подстановке.

### Было

```python
    from = cur; to = k; cur = k; tp = 0; swapped = false; hover = -1;
    lay.querySelectorAll('.col').forEach(el => el.style.opacity = '');
    lay.classList.add('out');
```

### Стало

```python
    from = cur; to = k; cur = k; tp = 0; swapped = false; hover = -1;
    lay.querySelectorAll('.col').forEach(el => el.style.opacity = '');

    /* Снимаем класс появления с текстов, которые его носят. Анимация
       заведена с fill both, то есть после проигрывания она продолжает
       держать конечные значения прозрачности и сдвига — и правило
       ухода до элемента просто не доходит. Отсюда и то, что тикер,
       стратегия, капитализация и нижняя строка висели неподвижно всю
       первую половину перехода, а потом подменялись рывком: гасли
       только те, у кого этой анимации нет. */
    ['obcName', 'obcStr', 'obcCap', 'obcFoot'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.classList.remove('app');
    });

    lay.classList.add('out');
    root.classList.add('moving');
```

---

## 15 · содержимое ставится в провале, вход анимируется — `render/cardscene.py`

Текст, ящик и счётчик менялись в тот же миг, когда начинался переход:
старая фраза ещё висела и вдруг становилась новой. Теперь всё
содержимое ставится одним куском в провале посередине.

И вход из зала: прежде карточка возникала целиком и сразу, без
единого движения, а при первом же листании вдруг оказывалась живой.
Теперь вход идёт тем же переходом, только уходить нечему — начальная
и конечная монета совпадают, фаза утопления пропускается сама, и
остаётся один подъём из воды.

### Было

```python
  function show(i, animated) {
    IDX = (i + CARDS.length) % CARDS.length;
    var card = CARDS[IDX];
    var det = DETAIL ? DETAIL(card.raw) : null;
    note.innerHTML = levels(det && det.note);
    draw.innerHTML = (det && det.body) || '';
    pos.innerHTML = '<b>' + (IDX + 1) + '</b> из ' + CARDS.length;
    root.classList.remove('drawer');
    root.classList.toggle('buyers', !!card.buyers);
    if (animated) go(IDX);
    else {
      cur = from = to = IDX; tp = 1;
      buildBG(card.price, card.entry);
      compose();
      labels(card);
    }
  }
```

### Стало

```python
  /* Подстановка содержимого. Раньше текст, ящик и счётчик менялись в
     тот же миг, когда начинался переход: старая фраза ещё висела на
     экране и вдруг становилась новой. Отсюда и ощущение скачка —
     столбы плавно тонули, а слова подменялись рывком.

     Теперь всё содержимое ставится одним куском в провале посередине,
     когда старое уже утонуло, а новое ещё не поднялось. */
  function applyCard(card) {
    var det = DETAIL ? DETAIL(card.raw) : null;
    note.innerHTML = levels(det && det.note);
    draw.innerHTML = (det && det.body) || '';
    pos.innerHTML = '<b>' + (IDX + 1) + '</b> из ' + CARDS.length;
    root.classList.toggle('buyers', !!card.buyers);

    /* Крен от скорости хода, сторона — от вортекса. Потолок в шесть
       градусов: дальше лодка выглядит опрокидывающейся, а не идущей. */
    var vx = card.raw && card.raw.vxDir, sp = parseFloat(card.raw && card.raw.speedV) || 0;
    var heel = Math.min(6, 1.4 + sp * 1.7) * (vx === 'down' ? -1 : 1);
    [document.getElementById('obcBoat'), document.getElementById('obcBoatM')]
      .forEach(function (b) {
        b.style.setProperty('--heel', (vx ? heel.toFixed(1) : 0) + 'deg');
        b.classList.toggle('wind-l', vx === 'down');
      });

    labels(card);
    lay.classList.remove('out');
  }

  function show(i, animated) {
    IDX = (i + CARDS.length) % CARDS.length;
    root.classList.remove('drawer');
    if (animated) { go(IDX); return; }

    /* Первый заход из зала. Прежде карточка возникала целиком и сразу,
       без единого движения, — а потом при первом же листании вдруг
       оказывалась живой. Теперь вход идёт тем же переходом, только
       уходить нечему: from и to совпадают, поэтому фаза утопления
       пропускается сама, и остаётся один подъём из воды. */
    cur = from = to = IDX; tp = 0; swapped = false;
    lay.classList.add('out');
    root.classList.add('moving');
    buildBG(CARDS[IDX].price, CARDS[IDX].entry);
    compose();
  }
```
