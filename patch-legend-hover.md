# Патч · легенда не раскрывается сама

Один блок в `render/css.py`.

Сейчас тело легенды раскрыто по умолчанию, а сворачивается только при
`.showing` или `.starred` — то есть её вид зависит от того, открыта ли
карточка монеты. Связь лишняя: легенда объясняет палитру, а палитра не
меняется от того, что происходит на орбите.

Правильное поведение проще: свёрнута всегда, раскрывается наведением.
Видна при этом остаётся шапка с цветными точками — она и служит тем
заметным элементом, к которому имеет смысл подвести курсор.

---

## `render/css.py`

### было

```css
.ob-leg-body{overflow:hidden;max-height:520px;
  transition:max-height .3s ease,opacity .25s ease}
.ob.showing .ob-leg-body,.ob.starred .ob-leg-body{max-height:0;opacity:0}
.ob.showing .ob-leg:hover .ob-leg-body,
.ob.starred .ob-leg:hover .ob-leg-body{max-height:520px;opacity:1}
```

### стало

```css
/* Свёрнута по умолчанию, раскрывается наведением. Состояние орбиты
   на это больше не влияет: палитра не меняется от того, открыта
   карточка или нет, и привязывать к этому вид легенды было незачем. */
.ob-leg-body{overflow:hidden;max-height:0;opacity:0;
  transition:max-height .3s ease,opacity .25s ease}
.ob-leg:hover .ob-leg-body{max-height:520px;opacity:1}
```

### было

```css
/* В свёрнутом виде подложка чуть плотнее и рамка теплее: полоска
   должна читаться как живой элемент, к которому имеет смысл
   подвести курсор, а не как остаток панели. */
.ob.showing .ob-leg,.ob.starred .ob-leg{
  background:rgba(10,12,17,.72);border-color:rgba(255,217,138,.16)}
.ob.showing .ob-leg:hover,.ob.starred .ob-leg:hover{
  background:rgba(6,8,12,.72);border-color:rgba(255,255,255,.05)}
```

### стало

```css
/* В свёрнутом виде подложка чуть плотнее и рамка теплее: полоска
   должна читаться как живой элемент, к которому имеет смысл
   подвести курсор, а не как остаток панели. Теперь это состояние по
   умолчанию, а наведение возвращает обычный материал. */
.ob-leg{background:rgba(10,12,17,.72);
  border-color:rgba(255,217,138,.16)}
.ob-leg:hover{background:rgba(6,8,12,.72);
  border-color:rgba(255,255,255,.05)}
```

### было

```css
.ob.showing .ob-leg-h,.ob.starred .ob-leg-h{margin-bottom:0}
.ob.showing .ob-leg:hover .ob-leg-h,
.ob.starred .ob-leg:hover .ob-leg-h{margin-bottom:9px}
```

### стало

```css
.ob-leg-h{margin-bottom:0}
.ob-leg:hover .ob-leg-h{margin-bottom:9px}
```
