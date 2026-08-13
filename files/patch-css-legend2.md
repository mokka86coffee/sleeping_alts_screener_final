# Патч · `render/css.py` — сворачиваемая легенда

Ставится поверх `patch-css-legend.md`. Два блока.

Легенда больше не исчезает при открытой карточке: сворачивается в
полоску с цветными точками и раскрывается наведением. Исчезать ей
нельзя — под карточкой цвет звезды становится нечитаемым именно тогда,
когда монету и разглядывают.

---

## 1. Сворачивание вместо исчезновения

### было

```css
.ob-leg{position:absolute;left:22px;bottom:22px;z-index:3;
  width:212px;padding:12px 14px 13px;border-radius:10px;
  background:rgba(6,8,12,.62);backdrop-filter:blur(9px);
  border:1px solid rgba(255,255,255,.05);pointer-events:none;
  transition:opacity .35s ease}
.ob.showing .ob-leg,.ob.starred .ob-leg{opacity:0}

.ob-leg-h{font-size:7px;letter-spacing:3px;text-transform:uppercase;
  color:#43434e;margin-bottom:9px}
```

### стало

```css
/* pointer-events включены: легенда обязана ловить наведение, иначе
   свёрнутую не раскрыть. Блок маленький и стоит в углу, звёздам он
   не мешает. */
.ob-leg{position:absolute;left:22px;bottom:22px;z-index:3;
  width:212px;padding:12px 14px 13px;border-radius:10px;
  background:rgba(6,8,12,.62);backdrop-filter:blur(9px);
  border:1px solid rgba(255,255,255,.05);pointer-events:auto;
  transition:opacity .35s ease,background .3s ease}

/* Свёрнутое состояние. Тело схлопывается, шапка с точками остаётся —
   она и есть тот заметный элемент на месте легенды. Наведение
   возвращает всё обратно.

   max-height, а не display: скачок высоты без перехода читается как
   подёргивание блока, а анимировать display нельзя. Потолок взят с
   запасом под шесть стратегий с тикерами. */
.ob-leg-body{overflow:hidden;max-height:520px;
  transition:max-height .3s ease,opacity .25s ease}
.ob.showing .ob-leg-body,.ob.starred .ob-leg-body{max-height:0;opacity:0}
.ob.showing .ob-leg:hover .ob-leg-body,
.ob.starred .ob-leg:hover .ob-leg-body{max-height:520px;opacity:1}

/* В свёрнутом виде подложка чуть плотнее и рамка теплее: полоска
   должна читаться как живой элемент, к которому имеет смысл
   подвести курсор, а не как остаток панели. */
.ob.showing .ob-leg,.ob.starred .ob-leg{
  background:rgba(10,12,17,.72);border-color:rgba(255,217,138,.16)}
.ob.showing .ob-leg:hover,.ob.starred .ob-leg:hover{
  background:rgba(6,8,12,.72);border-color:rgba(255,255,255,.05)}

.ob-leg-h{display:flex;align-items:center;gap:8px;
  font-size:7px;letter-spacing:3px;text-transform:uppercase;
  color:#43434e;margin-bottom:9px;transition:margin .3s ease}
.ob.showing .ob-leg-h,.ob.starred .ob-leg-h{margin-bottom:0}
.ob.showing .ob-leg:hover .ob-leg-h,
.ob.starred .ob-leg:hover .ob-leg-h{margin-bottom:9px}

/* Ряд точек в шапке. Виден всегда, но работает как опознавательный
   знак именно в свёрнутом виде. */
.ob-leg-dots{display:flex;gap:4px;margin-left:auto}
.ob-leg-dots i{width:5px;height:5px;border-radius:50%;
  box-shadow:0 0 5px currentColor}
```

---

## 2. Тикеры под названием стратегии

Счётчик убран, вместо него список монет. Держится отдельной строкой, а
не в одну с названием: тикеров бывает десяток, и в общей строке они
вытолкнули бы название за край.

### было

```css
.ob-leg-n{color:var(--t1);opacity:.82}
/* Счётчик прижат вправо: он отвечает на другой вопрос, чем название,
   и в общей строке они спорили бы за начало. */
.ob-leg-x{margin-left:auto;font-size:8px;letter-spacing:1px;
  color:#43434e}
```

### стало

```css
.ob-leg-n{color:var(--t1);opacity:.82}

/* Список тикеров стратегии. Отступ слева ровно под точкой и зазором,
   чтобы колонка названий и колонка монет читались как одна вещь.
   Цвет наследует стратегию, но приглушён: это перечисление, а не
   заголовок. */
.ob-leg-c{margin:2px 0 7px 13px;font-size:8px;letter-spacing:.8px;
  line-height:1.5;opacity:.62;word-break:break-word}
.ob-leg-g .ob-leg-c:last-child{margin-bottom:0}

/* Точка стратегии в чипе карточки монеты. Карточка называет фигуру
   словом, звезда — цветом, и связать их глазами было нечем. */
.ob-sc-dot{display:inline-block;width:5px;height:5px;border-radius:50%;
  margin-right:5px;vertical-align:middle;
  box-shadow:0 0 5px currentColor}
```
