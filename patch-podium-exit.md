# Выход из зала

## файл: `render/podium.py`

Сейчас зал закрывается только клавишей — про это нигде не написано, и
мышью выйти нельзя вовсе. Кнопка стоит в шапке, рядом с заголовком:
угол, куда смотрят при входе на экран.

Три вещи, которые пришлось учесть.

Кнопка гасит `mousedown` до всплытия: без этого нажатие на неё
начинает перетаскивание зала, и палец уезжает вместе со сценой.

Клик по фону зала выходом НЕ становится — рядом живёт перетаскивание,
и любой промах мимо карточки закрывал бы экран посреди осмотра.
Выход остаётся явным: кнопка либо клавиша.

Подсказка внизу перечисляет способы управления и теперь обязана
называть выход — иначе он есть, но про него знает только тот, кто
читал код.

### было

```python
.obp-stamp{font-family:ui-monospace,Menlo,monospace;font-size:10px;color:#454C57}
```

### стало

```python
.obp-stamp{font-family:ui-monospace,Menlo,monospace;font-size:10px;color:#454C57}

/* Выход. Не крестик: значок пришлось бы объяснять, а слово говорит
   само. Рамка тонкая и холодная — кнопка обязана быть найдена, но
   не обязана спорить за внимание с карточками. */
.obp-exit{position:absolute;right:26px;top:14px;z-index:8;
  font-family:ui-monospace,Menlo,monospace;font-size:9px;
  letter-spacing:.3em;text-transform:uppercase;color:#6E7684;
  padding:7px 14px;border:1px solid rgba(255,255,255,.10);
  border-radius:999px;cursor:pointer;background:rgba(8,10,16,.55);
  transition:color .2s ease,border-color .2s ease,background .2s ease}
.obp-exit:hover{color:#D6DCE6;border-color:rgba(255,255,255,.24);
  background:rgba(18,22,32,.8)}
.obp-exit:focus-visible{outline:2px solid #7FE3D4;outline-offset:2px}
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
    <div class="obp-stamp" id="obPodStamp"></div>
  </div>
  <button class="obp-exit" id="obpExit" type="button">к дашборду</button>
```

### было

```python
  <div class="obp-hint">тяните мышью · колесо · клик по карточке</div>
```

### стало

```python
  <div class="obp-hint">тяните мышью · колесо · клик по карточке · esc — выход</div>
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
  function show() {
    if (opened) return;
    opened = true;
    build();
    apply();
    pod.classList.add('on');
  }

  /* Выход один на все способы: кнопка, Esc и любая клавиша ведут
     сюда. Раскрытую карточку закрываем вместе с залом — иначе она
     останется висеть и всплывёт поверх дашборда при следующем
     открытии. */
  function hide() {
    closeZoom();
    pod.classList.remove('on');
  }

  var exitBtn = document.getElementById('obpExit');
  if (exitBtn) {
    /* mousedown гасится до всплытия: на зале висит перетаскивание,
       и без этого нажатие на кнопку уводит сцену вбок. */
    exitBtn.addEventListener('mousedown', function (e) { e.stopPropagation(); });
    exitBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      hide();
    });
  }
```

### было

```python
    if (e.key === 'ArrowRight') { target += BASE_STEP; kick(); return; }
    if (e.key === 'ArrowLeft')  { target -= BASE_STEP; kick(); return; }
    pod.classList.remove('on');
  });
```

### стало

```python
    if (e.key === 'ArrowRight') { target += BASE_STEP; kick(); return; }
    if (e.key === 'ArrowLeft')  { target -= BASE_STEP; kick(); return; }
    hide();
  });
```
