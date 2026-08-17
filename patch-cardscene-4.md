# Закрытая карточка не должна ни рисоваться, ни открываться сама

Правки в `render/cardscene.py` и `render/podium.py`, **поверх**
`patch-cardscene-2.md` и `patch-cardscene-3.md`.

Две жалобы, две разные причины.

Карточка вылезала при нажатии на блок FLOW. Она лежала во весь экран
всегда, просто с `display:none` — а открывалась потому, что нажатие
доходило до панели закрытого зала. Лечится с двух сторон: слой убираем
из страницы целиком, а зал перестаёт открывать карточку, когда сам
закрыт.

Тормозило на планшете отражение: по вызову `drawImage` на каждый
пиксель высоты воды, каждый кадр. Там, где машина слабее, шаг строки
удваивается.

---

## 1 · закрытая карточка не ловит нажатия — `render/cardscene.py`

`display:none` снимает отрисовку, но слой всё равно лежал во весь
экран как объект разметки. Добавляем `visibility` и `pointer-events`:
закрытая карточка перестаёт существовать для страницы целиком.

### Было

```python
#obcRoot{position:fixed;inset:0;z-index:60;display:none;
  align-items:center;justify-content:center;background:#04070B;
  opacity:0;transition:opacity .45s ease;
```

### Стало

```python
/* Закрытая карточка не должна ни рисоваться, ни ловить нажатия.
   display:none снимает отрисовку, visibility и pointer-events —
   попадания: на планшете промах по невидимому слою открывал карточку
   поверх дашборда, потому что слой лежал во весь экран. */
#obcRoot{position:fixed;inset:0;z-index:60;display:none;
  visibility:hidden;pointer-events:none;
  align-items:center;justify-content:center;background:#04070B;
  opacity:0;transition:opacity .45s ease;
```

---

## 2 · и возвращается при открытии — `render/cardscene.py`

### Было

```python
#obcRoot.on{display:flex;opacity:1}
```

### Стало

```python
#obcRoot.on{display:flex;visibility:visible;pointer-events:auto;opacity:1}
```

---

## 3 · отражение вдвое дешевле на слабой машине — `render/cardscene.py`

Отражение — самая дорогая часть кадра: по `drawImage` на каждый
пиксель высоты воды, триста пятьдесят вызовов за кадр. Это и есть
тормоз на планшете. Шаг увеличиваем вдвое там, где мало ядер или
нет мыши: строки рисуются вдвое толще, на глаз в размытой воде
разницы нет, вызовов вдвое меньше.

### Было

```python
  function water(t){
    const hgt = H - WATER;
    for (let j = 0; j < hgt; j++){
```

### Стало

```python
  /* Отражение — самая дорогая часть кадра: по строке drawImage на
     каждый пиксель высоты воды, триста пятьдесят вызовов за кадр.
     На слабой машине это и есть тормоз. Шаг увеличиваем вдвое —
     строки рисуются вдвое толще, на глаз разница в размытой воде не
     видна, а вызовов вдвое меньше. */
  const STEP = (navigator.hardwareConcurrency || 4) <= 4 ||
               matchMedia('(hover: none)').matches ? 2 : 1;

  function water(t){
    const hgt = H - WATER;
    for (let j = 0; j < hgt; j += STEP){
```

---

## 4 · строка рисуется на всю толщину шага — `render/cardscene.py`

### Было

```python
      ctx.drawImage(sky, 0, Math.floor(src), W, 1, dx, WATER + j, W, 1.2);
```

### Стало

```python
      ctx.drawImage(sky, 0, Math.floor(src), W, 1, dx, WATER + j, W, STEP + .2);
```

---

## 5 · закрытая карточка не дорисовывает кадр — `render/cardscene.py`

Проверка переезжает в начало функции. Раньше она стояла в конце, и
после закрытия успевал пройти ещё один полный кадр.

### Было

```python
  function frame(t){
    const dt = last ? Math.min(64, t - last) : 16; last = t;
```

### Стало

```python
  function frame(t){
    /* Проверка стоит первой, а не в конце: закрытая карточка не должна
       дорисовать даже один лишний кадр — на планшете он заметен. */
    if (!live) return;
    const dt = last ? Math.min(64, t - last) : 16; last = t;
```

---

## 6 · хвост цикла — `render/cardscene.py`

### Было

```python
    if (live) requestAnimationFrame(frame);
```

### Стало

```python
    requestAnimationFrame(frame);
```

---

## 7 · закрытие вычищает за собой — `render/cardscene.py`

Холст и разметка чистятся, чтобы карточка не держала последнюю
монету и не показывала её вспышкой при следующем открытии, до
первого кадра.

### Было

```python
  function close() {
    live = false;                 /* кадр остановится сам на ближайшем тике */
    root.classList.remove('on', 'drawer');
  }
```

### Стало

```python
  function close() {
    live = false;                 /* кадр остановится сам на ближайшем тике */
    root.classList.remove('on', 'drawer');
    /* Холст и разметку чистим: закрытая карточка не держит в памяти
       последнюю монету и не показывает её на долю секунды при
       следующем открытии, до первого кадра. */
    ctx.clearRect(0, 0, W, H);
    document.getElementById('obcDiag').innerHTML = '';
    lay.querySelectorAll('.col').forEach(function (e) { e.remove(); });
  }
```

---

## 8 · зал — единственная дверь в карточку — `render/podium.py`

Без открытого зала карточки быть не может. На планшете промах по
панели проходил сквозь закрытый зал, и карточка вылезала поверх
дашборда.

### Было

```python
  function openZoom(c, zi) {
    /* Карточка-пейзаж живёт в render/cardscene.py и берёт на себя весь
       показ. Если модуль не подключён, работает прежняя карточка ниже —
       это и есть способ сравнить обе, не откатывая правку. */
    if (window.OBCARD && ZLIST.length) {
```

### Стало

```python
  function openZoom(c, zi) {
    /* Без открытого зала карточки быть не может. Проверка нужна на
       планшете: там промах по панели проходил сквозь закрытый зал и
       карточка вылезала поверх дашборда. Зал — единственная дверь в
       неё, и дверь должна быть открыта. */
    if (!pod.classList.contains('on')) return;

    /* Карточка-пейзаж живёт в render/cardscene.py и берёт на себя весь
       показ. Если модуль не подключён, работает прежняя карточка ниже —
       это и есть способ сравнить обе, не откатывая правку. */
    if (window.OBCARD && ZLIST.length) {
```
