# Зал вращается пальцем

## файл: `render/podium.py`

Показать зал на планшете мало: вращение висит на `mousemove`, а на
тач-экране его нет. Без этого патча планшет получает неподвижную
сцену, где видно четыре панели из двадцати — хуже, чем сетка, которая
там была.

Почему не `pointer`-события целиком: перевод существующих
обработчиков на них тронул бы работающее мышиное управление, а оно
проверено. Тач добавляется рядом, тем же состоянием (`down`, `x0`,
`a0`) и той же формулой — расхождение раскладок исключено по
построению.

Применять ПОСЛЕ `patch-podium-exit.md`.

### было

```python
  window.addEventListener('mousemove', function (e) {
    if (!down) return;
    // Перетаскивание напрямую, без доводки: рука уже задаёт темп,
    // и сглаживание поверх неё ощущается как залипание.
    ang = target = a0 + (e.clientX - x0) * -0.073;
    apply();
  });
```

### стало

```python
  window.addEventListener('mousemove', function (e) {
    if (!down) return;
    // Перетаскивание напрямую, без доводки: рука уже задаёт темп,
    // и сглаживание поверх неё ощущается как залипание.
    ang = target = a0 + (e.clientX - x0) * -0.073;
    apply();
  });

  /* ── Палец ──
     Те же три переменные и та же формула, что у мыши: развести
     раскладки означало бы чинить потом две.

     touchmove гасит прокрутку страницы (passive: false), иначе
     горизонтальный смах уводит экран вместо сцены. Одним пальцем —
     вращение; два и больше отдаём системе, это масштабирование.

     Тап по панели остаётся кликом: браузер шлёт click после
     короткого касания сам, и обработчик карточки срабатывает без
     нашего участия. Поэтому здесь только вращение. */
  pod.addEventListener('touchstart', function (e) {
    if (zoom.classList.contains('on')) return;
    if (e.touches.length !== 1) return;
    down = true; x0 = e.touches[0].clientX; a0 = ang; target = ang;
    if (raf) { cancelAnimationFrame(raf); raf = 0; }
    pod.classList.add('obp-drag');
  }, { passive: true });

  pod.addEventListener('touchmove', function (e) {
    if (!down || e.touches.length !== 1) return;
    e.preventDefault();
    ang = target = a0 + (e.touches[0].clientX - x0) * -0.073;
    apply();
  }, { passive: false });

  function touchEnd() {
    if (!down) return;
    down = false;
    pod.classList.remove('obp-drag');
  }
  window.addEventListener('touchend', touchEnd);
  window.addEventListener('touchcancel', touchEnd);
```

### было

```python
  <div class="obp-hint">тяните мышью · колесо · клик по карточке · esc — выход</div>
```

### стало

```python
  <div class="obp-hint" id="obpHint">тяните мышью · колесо · клик по карточке · esc — выход</div>
```

### было

```python
  var exitBtn = document.getElementById('obpExit');
```

### стало

```python
  /* Подсказка по способу ввода. Тип указателя здесь как раз к месту:
     вопрос не в размере экрана, а в том, есть ли мышь и клавиатура.
     На планшете строка про колесо и Esc описывает то, чего у
     человека в руках нет. */
  if (window.matchMedia('(pointer: coarse)').matches) {
    var hintEl = document.getElementById('obpHint');
    if (hintEl) hintEl.textContent = 'смахните · касание по карточке';
  }

  var exitBtn = document.getElementById('obpExit');
```

### было

```python
  if (exitBtn) {
    /* mousedown гасится до всплытия: на зале висит перетаскивание,
       и без этого нажатие на кнопку уводит сцену вбок. */
    exitBtn.addEventListener('mousedown', function (e) { e.stopPropagation(); });
```

### стало

```python
  if (exitBtn) {
    /* mousedown гасится до всплытия: на зале висит перетаскивание,
       и без этого нажатие на кнопку уводит сцену вбок. touchstart —
       по той же причине: палец на кнопке иначе начинает вращение, и
       сцена уезжает из-под пальца ещё до отпускания. */
    exitBtn.addEventListener('mousedown', function (e) { e.stopPropagation(); });
    exitBtn.addEventListener('touchstart', function (e) { e.stopPropagation(); },
                             { passive: true });
```
