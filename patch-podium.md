# Патч · сцена лидеров под сводкой

Новый файл `render/podium.py` кладётся целиком (он в отдельной
выдаче). Здесь три патча на существующие файлы: контейнер в брифе,
вызов в дашборде, стили и анимации.

Данных своих у модуля нет — он читает `window.ORB.stars`, как и
`brief.py`. Все величины настоящие: `up` это `up_from_low`, `x` —
рекорд объёма из журнала, `v1h/v4h/v1d` — текущий, `series` — ряд
цены, `cap` — капитализация. Заглушек не осталось ни одной.

---

# 1 · `render/brief.py` — трогать не нужно

Первая редакция вставляла контейнер внутрь сводки, и сцена не
появлялась вовсе: `.ob-brief` — это `position:fixed` с
`justify-content:center` и без прокрутки, а текст плюс сцена в
шестьсот пикселей высотой в окно не помещаются. Столбики уезжали за
нижний край без возможности доскроллить.

Теперь у сцены свой экран, и `brief.py` остаётся нетронутым. Если
предыдущая версия патча уже применена — убери из `BRIEF_HTML` две
строки с `obf-podium` и `obf-podium-cap`, они больше не используются.

---

# 2 · `render/dashboard.py` — вызов

### было

```python
from render.orbit import render_orbit
from render.brief import render_brief
```

### стало

```python
from render.orbit import render_orbit
from render.brief import render_brief
from render.podium import render_podium
```

### было

```python
{render_brief()}
{DASH_JS}"""
```

### стало

```python
{render_brief()}
{render_podium()}
{DASH_JS}"""
```

Порядок важен: `render_podium()` ищет `#obfPodium`, который создаёт
`render_brief()`, и оба скрипта выполняются по мере разбора страницы.

---

# 3 · `render/css.py` — стили и появление

Вставить перед `.obf-foot,.obf-bar{opacity:0;...}`.

### было

```css
.obf-foot,.obf-bar{opacity:0;transition:opacity .6s ease}
.obf-foot.on,.obf-bar.on{opacity:1}
```

### стало

```css
/* ── Экран лидеров ───────────────────────────────────────────
   Третий экран в очереди: сводка → лидеры → дашборд. Своим слоем, а
   не блоком внутри сводки: там центрирование без прокрутки, и сцена
   в шестьсот пикселей высотой просто не помещается в окно.

   Материал тот же, что у сводки, вплоть до градиента подложки —
   переход между экранами должен читаться как смена содержимого, а
   не как переход в другое приложение. */
.ob-podium{position:fixed;inset:0;z-index:41;display:flex;
  flex-direction:column;align-items:center;justify-content:center;
  background:radial-gradient(1100px 700px at 50% 46%,#0d0b09,#050406 70%);
  opacity:0;pointer-events:none;transition:opacity .5s ease}
.ob-podium.on{opacity:1;pointer-events:auto}
.obp-in{width:min(1240px,96vw)}
.obp-h{font-size:11px;letter-spacing:.58em;text-transform:uppercase;
  color:#6E6656;text-align:center;text-indent:.58em}
.obp-scene{margin-top:18px}
.pd-svg{width:100%;height:auto;display:block;overflow:visible}
.obp-cap{margin-top:12px;text-align:center;font-size:7px;
  letter-spacing:3px;text-transform:uppercase;color:#3C362D}
.obp-foot{margin-top:26px;text-align:center;font-size:7px;
  letter-spacing:3px;text-transform:uppercase;color:#2E2A24}

/* ── Появление ──
   Сцена собирается снизу вверх и по слоям: основание, затем столбики
   от левого края к правому, потом линии и звёзды. Порядок повторяет
   порядок чтения — глаз успевает понять устройство сцены прежде, чем
   она станет плотной.

   Задержка приходит инлайном через --d: считать её в CSS нечем, а
   таблица задержек в скрипте дублировала бы порядок столбиков. */
@keyframes pd-rise{
  from{opacity:0;transform:translateY(26px)}
  to  {opacity:1;transform:none}
}
@keyframes pd-grow{
  from{opacity:0;transform:scaleY(.04)}
  to  {opacity:1;transform:none}
}
@keyframes pd-pop{
  0%  {opacity:0;transform:scale(.2)}
  62% {opacity:1;transform:scale(1.16)}
  100%{opacity:1;transform:none}
}
@keyframes pd-draw{to{stroke-dashoffset:0}}
@keyframes pd-fade{from{opacity:0}to{opacity:1}}

.pd-rise{opacity:0;animation:pd-rise .78s cubic-bezier(.18,.72,.22,1) forwards;
  animation-delay:var(--d,0s)}
/* transform-box обязателен: без него точка отсчёта у SVG-элемента
   берётся от начала координат холста, и столбик не растёт из
   основания, а уезжает за кадр. */
.pd-grow{opacity:0;transform-box:fill-box;transform-origin:bottom;
  animation:pd-grow .8s cubic-bezier(.18,.72,.22,1) forwards;
  animation-delay:var(--d,0s)}
.pd-pop{opacity:0;transform-box:fill-box;transform-origin:center;
  animation:pd-pop .62s cubic-bezier(.2,1.5,.4,1) forwards;
  animation-delay:var(--d,0s)}
.pd-fade{opacity:0;animation:pd-fade 1.1s ease forwards;
  animation-delay:var(--d,0s)}
.pd-px{stroke-dasharray:420;stroke-dashoffset:420;
  animation:pd-draw 1.5s cubic-bezier(.3,.7,.2,1) forwards;
  animation-delay:var(--d,0s)}

@media (prefers-reduced-motion:reduce){
  .pd-rise,.pd-grow,.pod-pop,.pd-pop,.pd-fade{
    opacity:1!important;animation:none!important;transform:none!important}
  .pd-px{stroke-dashoffset:0!important;animation:none!important}
}

/* На узком экране экран лидеров пропускается целиком, а не ужимается:
   половина сцены объясняет хуже, чем её отсутствие. Сводка при этом
   остаётся — это текст, он ничего не стоит. */
@media (max-width:900px){
  .ob-podium{display:none}
}

.obf-foot,.obf-bar{opacity:0;transition:opacity .6s ease}
.obf-foot.on,.obf-bar.on{opacity:1}
```

---

## Что стоит проверить после применения

**Очередь экранов.** Сцена показывается, когда сводка снимает класс
`.on`. Подписки на её закрытие нет намеренно: `brief.js` наружу этого
не отдаёт, а лезть в его внутренности значило бы связать два модуля
намертво. Наблюдатель следит за классом — это публичное состояние,
видимое из разметки. Если сводка отключена совсем, сцена показывается
сразу.

**Монеты без данных прогона.** Они уходят в блоки переднего плана. С
правкой `run.py` таких почти не остаётся: журнальные монеты теперь
добираются в выборку принудительно. Если блоков много — значит добавка
не работает, и смотреть надо туда, а не в сцену.

**Кэш браузера.** Модуль новый, стили тоже — обычная перезагрузка
может отдать старый CSS.
