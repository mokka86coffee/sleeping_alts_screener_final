# Двойная анимация у нижней строки и капитализации

Правка в `render/cardscene.py`, **поверх** патчей 2, 3, 4, 6, 7 и 8.
Один блок.

Оба элемента стоят под собственным наклоном — перспектива с поворотом.
Общая анимация появления задаёт свой `transform`, и на всё время
удержания (`fill: both`) наклон подменяется плоским сдвигом: элемент
приезжает плоским и таким остаётся. На старте следующего перехода класс
появления снимается, наклон возвращается рывком — и это читается как
вторая, лишняя анимация. На планшете заметнее: там переходы идут дольше.

Даём обоим свои кадры, где собственный поворот сохранён в обоих
положениях, а сдвиг добавляется к нему. Правило ухода уже устроено так
же — теперь наклон один и тот же во всех трёх состояниях: покой, приход,
уход.

---

## 1 · свои кадры появления для наклонённых элементов — `render/cardscene.py`

### Было

```python
#obcRoot .app{animation:ocAppear 2.5s cubic-bezier(.16,.84,.3,1) both}
```

### Стало

```python
#obcRoot .app{animation:ocAppear 2.5s cubic-bezier(.16,.84,.3,1) both}

/* Нижняя строка и капитализация стоят под собственным наклоном, а общая
   анимация появления задаёт свой transform — и на всё время удержания
   (fill both) наклон подменяется плоским сдвигом. Элемент приезжает
   плоским, стоит плоским, а на старте следующего перехода класс
   снимается, наклон возвращается рывком — и это читается как вторая,
   лишняя анимация. Даём им свои кадры, где собственный поворот
   сохранён, а сдвиг добавляется к нему. */
@keyframes ocFoot{
  from{opacity:0;letter-spacing:.5em;filter:blur(4px);
       transform:perspective(900px) rotateX(16deg) translateY(10px)}
  to  {opacity:1;filter:blur(0);
       transform:perspective(900px) rotateX(16deg) translateY(0)}
}
@keyframes ocCap{
  from{opacity:0;letter-spacing:.4em;filter:blur(4px);
       transform:perspective(800px) rotateX(12deg) rotateY(9deg) translateY(10px)}
  to  {opacity:1;filter:blur(0);
       transform:perspective(800px) rotateX(12deg) rotateY(9deg) translateY(0)}
}
#obcRoot .foot.app{animation:ocFoot 2.5s cubic-bezier(.16,.84,.3,1) both}
#obcRoot .obc-cap.app{animation:ocCap 2.5s cubic-bezier(.16,.84,.3,1) both}
```
