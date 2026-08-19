# Мёртвый блок FLOW после закрытия зала

Правки в `render/podium.py` и `render/css.py`.

Закрытый зал оставался в странице: прозрачным, с `pointer-events:none`,
но живым. На узком экране он вдобавок превращается в прокручиваемый
слой во весь экран — так устроена ветка `max-width:900px`. Такой слой на
планшете продолжает ловить касания и после отключения указателей:
инерция прокрутки живёт своей жизнью и съедает первые нажатия. Отсюда и
мёртвый блок FLOW на дашборде сразу после выхода.

Лечим с двух сторон. `visibility` снимает попадания надёжно, в том числе
для прокрутки, и гасится с задержкой в полсекунды — ровно после
затухания, иначе зал пропадал бы мгновенно, без перехода. И прокрутка
возвращается в начало при закрытии, чтобы остановленная инерция никого
не ждала.

---

## 1 · закрытый зал исчезает из страницы — `render/podium.py`

### Было

```python
.ob-podium{position:fixed;inset:0;z-index:41;overflow:hidden;
  background:radial-gradient(1100px 700px at 50% -5%,#0d0b09,#050406 70%);
  opacity:0;pointer-events:none;transition:opacity .5s ease;
  cursor:grab;perspective:1200px;perspective-origin:50% 46%}
.ob-podium.on{opacity:1;pointer-events:auto}
```

### Стало

```python
/* Закрытый зал должен исчезать из страницы, а не становиться
   прозрачным. На узком экране он превращается в прокручиваемый слой
   во весь экран (см. ветку max-width:900px), а такой слой на
   планшете продолжает ловить касания даже с pointer-events:none —
   инерция прокрутки живёт своей жизнью и съедает первые нажатия.
   Отсюда и мёртвый блок FLOW на дашборде после закрытия.

   visibility снимает попадания надёжно и для прокрутки тоже, но
   гасить её надо ПОСЛЕ затухания: с нулевой задержкой зал пропадал
   бы мгновенно, без перехода. */
.ob-podium{position:fixed;inset:0;z-index:41;overflow:hidden;
  background:radial-gradient(1100px 700px at 50% -5%,#0d0b09,#050406 70%);
  opacity:0;pointer-events:none;visibility:hidden;
  transition:opacity .5s ease, visibility 0s linear .5s;
  cursor:grab;perspective:1200px;perspective-origin:50% 46%}
.ob-podium.on{opacity:1;pointer-events:auto;visibility:visible;
  transition:opacity .5s ease, visibility 0s}
```

---

## 2 · то же во втором описании зала — `render/css.py`

Правило из `render/podium.py` идёт позже и перекрывает это, но
расходиться они не должны — иначе однажды поменяют одно и будут искать,
почему поведение прежнее.

### Было

```python
.ob-podium{position:fixed;inset:0;z-index:41;display:flex;
  flex-direction:column;align-items:center;justify-content:center;
  background:radial-gradient(1100px 700px at 50% 46%,#0d0b09,#050406 70%);
  opacity:0;pointer-events:none;transition:opacity .5s ease}
.ob-podium.on{opacity:1;pointer-events:auto}
```

### Стало

```python
/* Второе описание зала: правило из render/podium.py идёт позже и
   перекрывает его, но расходиться они не должны — иначе однажды
   поменяют одно и будут искать, почему поведение прежнее. */
.ob-podium{position:fixed;inset:0;z-index:41;display:flex;
  flex-direction:column;align-items:center;justify-content:center;
  background:radial-gradient(1100px 700px at 50% 46%,#0d0b09,#050406 70%);
  opacity:0;pointer-events:none;visibility:hidden;
  transition:opacity .5s ease, visibility 0s linear .5s}
.ob-podium.on{opacity:1;pointer-events:auto;visibility:visible;
  transition:opacity .5s ease, visibility 0s}
```

---

## 3 · прокрутка возвращается в начало — `render/podium.py`

### Было

```python
    closeZoom();
    pod.classList.remove('on');
  }
```

### Стало

```python
    closeZoom();
    pod.classList.remove('on');
    /* Прокрутку возвращаем в начало: на узком экране зал прокручивается,
       и его остановленная инерция — вторая причина, по которой первые
       касания после закрытия уходили в никуда. */
    pod.scrollTop = 0;
  }
```
