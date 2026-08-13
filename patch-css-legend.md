# Патч · `render/css.py`

1982 строки, поэтому патчем. Один блок — стили легенды, перед `.ob-core`.

Материал тот же, что у панели макро в прототипе: обе объясняют экран,
а не показывают монеты, и разный стиль делал бы вид, что это разные
сущности.

---

### было

```css
.ob-core{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
  text-align:center;width:340px;pointer-events:none;z-index:3;
  transition:opacity .35s ease}
```

### стало

```css
/* ── Легенда стратегий ───────────────────────────────────────
   Внизу слева. Цвет звезды перестал быть украшением и несёт
   подкейс, а шесть подкейсов на память не читаются — без подписи
   палитра превращается в шум.

   Сгруппирована по стадиям, а не одним списком из шести: список
   объяснил бы только цвет, группировка объясняет заодно, почему
   холодные и тёплые оттенки стоят рядом. Одной подписью две вещи.

   Скрывается вместе с ядром на тех же состояниях: когда открыта
   карточка монеты или выбрана звезда, объяснение палитры мешает,
   а не помогает. */
.ob-leg{position:absolute;left:22px;bottom:22px;z-index:3;
  width:212px;padding:12px 14px 13px;border-radius:10px;
  background:rgba(6,8,12,.62);backdrop-filter:blur(9px);
  border:1px solid rgba(255,255,255,.05);pointer-events:none;
  transition:opacity .35s ease}
.ob.showing .ob-leg,.ob.starred .ob-leg{opacity:0}

.ob-leg-h{font-size:7px;letter-spacing:3px;text-transform:uppercase;
  color:#43434e;margin-bottom:9px}
.ob-leg-g{margin-bottom:9px}
.ob-leg-g:last-child{margin-bottom:0}
.ob-leg-s{font-size:7px;letter-spacing:1.6px;color:#5a5a66;
  margin-bottom:5px}
.ob-leg-r{display:flex;align-items:center;gap:7px;margin-bottom:4px;
  font-size:8.5px;letter-spacing:.6px;color:var(--m2)}
.ob-leg-r:last-child{margin-bottom:0}
/* Точка светится своим цветом через currentColor: цвет задаётся
   один раз в разметке и работает и на заливку, и на свечение. */
.ob-leg-d{width:6px;height:6px;border-radius:50%;flex:0 0 auto;
  box-shadow:0 0 6px currentColor}
.ob-leg-n{color:var(--t1);opacity:.82}
/* Счётчик прижат вправо: он отвечает на другой вопрос, чем название,
   и в общей строке они спорили бы за начало. */
.ob-leg-x{margin-left:auto;font-size:8px;letter-spacing:1px;
  color:#43434e}

@media (max-width:900px){
  /* На узком экране легенда съедает поле звёзд, ради которых экран
     и существует. Прячем целиком, а не ужимаем: половина легенды
     объясняет хуже, чем её отсутствие. */
  .ob-leg{display:none}
}

.ob-core{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
  text-align:center;width:340px;pointer-events:none;z-index:3;
  transition:opacity .35s ease}
```
