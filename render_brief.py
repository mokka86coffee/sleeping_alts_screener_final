"""Сводка при входе · САМОСТОЯТЕЛЬНЫЙ ДОКУМЕНТ.

Был экраном поверх дашборда, в одном с ним документе. Стал отдельным
файлом brief.html, который оболочка грузит в iframe первым.

Что из этого следует, по пунктам.

Данные приходят АРГУМЕНТОМ и вшиваются в документ при сборке. Раньше
скрипт читал window.ORB — глобальную переменную, которую выставляла
орбита рядом. В своём документе никакого «рядом» нет: у каждого iframe
своё окно, и window.ORB там пуст. Собирает эти данные render_page,
один раз на все экраны.

Список монет здесь по-прежнему не считается свой — он бы разошёлся с
карточками при первой правке порогов фаз. Но теперь это не «беру у
соседа», а «получаю то же, что и он»: build_stars() из analytics_stars
вызывается один раз, и результат уходит в оба экрана.

Выход — сообщение оболочке, а не снятие класса. Сводка не знает, что
идёт следом: она сообщает «я закончила», и очередь экранов решает
оболочка (SEQUENCE в render_shell.py).

Модуль не зависит от орбиты визуально: на мобильных орбита снимается,
а сводка остаётся, потому что это текст и он ничего не стоит.

ПЕРЕДЕЛАНО целиком (дизайн одобрен в HTML-прототипе, см. переписку):
раньше строки печатались по символу через setTimeout, блоки лидера/
объёма рисовали насыщенные SVG-карточки (график + стоп/цель/дни/
фандинг + кольцо скора). По решению пользователя детальная статистика
блоков убрана — «графика будет достаточно»: осталась одна строка
текста плюс компактный график на настоящих данных (LC.series /
VC.ratios), без стопа/цели/дней/фандинга.

Новая сцена — атмосферный фон (кольцо из пыли + дюна с рельефными
пиками + ветер, сдувающий частицы с края кольца) и посимвольный
каскад букв вместо печати. Все параметры (масштаб кольца, плотность
дюны, скорость каскада и т.д.) — результат прямого тестирования в
браузере (Playwright + скриншоты на каждом шаге), а не догадка;
числа сохранены как были откалиброваны.
"""
from __future__ import annotations

import json


def render_brief(stars: list[dict], market: dict) -> str:
    """Тело документа сводки. Данные вшиваются, а не читаются из окна."""
    blob = json.dumps({"stars": stars, "market": market},
                      ensure_ascii=False, separators=(",", ":"))
    # Данные идут в <script type="application/json">, а не в
    # присваивание переменной: внутри JSON-блока браузер не разбирает
    # разметку, и последовательность вроде </script> в тексте поля не
    # закроет скрипт раньше времени. Экранируется только сам этот
    # случай — остальное JSON.parse читает как есть.
    safe = blob.replace("</", "<\\/")
    return (BRIEF_HTML
            + f'<script id="obfData" type="application/json">{safe}</script>'
            + BRIEF_JS)


BRIEF_HTML = """
<style>
/* Стили нижней части сводки (footer/прогресс-бар автозакрытия) живут
   в модуле, а не в css.py, по той же причине, что у podium.py: общий
   файл стилей уже ловил дубли блоков при патчах. Остальное оформление
   сцены (кольцо/дюна/текст) — тоже здесь, ниже, вторым style-блоком,
   рядом со сценой, которую оно красит. */
.obf-foot,.obf-bar{opacity:0;transition:opacity .6s ease}
.obf-foot.on,.obf-bar.on{opacity:1}
</style>
<style>
  /* Сцена целиком — canvas на весь экран сводки плюс слой текста
     поверх него. .ob-brief уже position:fixed;inset:0 (css.py) —
     сцена просто заполняет собой этот контейнер. */
  #obfCanvas{position:absolute;inset:0;display:block;width:100%;height:100%;}
  #obfText{
    position:absolute; left:50%; text-align:center;
    transform:translate(-50%,-50%);
    font-family:'Segoe UI', Helvetica, Arial, sans-serif;
    font-style:normal; font-weight:300; color:#F1ECE0;
    text-transform:uppercase;
    letter-spacing:.22em; line-height:1.6;
    text-shadow:0 0 22px rgba(0,0,0,.65);
    max-width:82vw; pointer-events:none;
  }
  #obfText .ch{
    display:inline-block; white-space:pre;
    opacity:0; filter:blur(6px);
    transform:translateY(10px) scale(1.12);
    transition:opacity .5s ease, filter .5s ease,
               transform .55s cubic-bezier(.2,.8,.25,1);
  }
  #obfText .ch.on{opacity:1; filter:blur(0); transform:translateY(0) scale(1);}
  /* Раскраска по смыслу — та же палитра, что раньше была у .obf-p
     (см. css.py): числа моноширинным серым, рост/падение зелёным/
     оранжевым, тикеры светлым акцентом, капитализация мельче и тише. */
  #obfText .t{color:var(--t1);}
  #obfText .n{font-family:var(--mono);color:#c8ccd4;}
  #obfText .up{color:#48A97C;}
  #obfText .dn{color:#FF6B35;}
  #obfText .gd{color:var(--gd);}
  #obfText .mut{color:#5b606a;}
  #obfText .warn{color:var(--dn);}
  #obfText .dorm{color:#8FA8FF;}
  #obfText .obf-cap{font-family:var(--mono);font-size:.72em;color:#5f6169;}
  #obfText .obf-sep{color:#5d5c66;}

  /* ═══ Фигура дня ═══
     Отработавший сегмент не исчезает: он сжимается до «ярлык + число»
     и садится по сторонам кольца. К концу сводки на экране стоит
     карта дня целиком, а не последняя фраза. Сжатие обязательно —
     десяток абзацев прозы превратился бы в стену. */
  #obfBeams{position:absolute;inset:0;width:100%;height:100%;
    pointer-events:none;}
  #obfBeams line{stroke:#2A2F38;stroke-width:1;opacity:0;
    transition:opacity 1.4s ease;}
  #obfBeams line.on{opacity:.8;}
  #obfBeams line.fresh{stroke:#4A505C;}
  #obfFig{position:absolute;inset:0;pointer-events:none;}
  #obfFig .row{position:absolute;left:0;top:0;display:flex;
    align-items:baseline;gap:.7em;white-space:nowrap;
    transform-origin:right center;justify-content:flex-end;opacity:0;
    transition:opacity 1.4s ease,
               transform 1.4s cubic-bezier(.22,.61,.36,1);}
  #obfFig .row.on{opacity:1;}
  #obfFig .row.mirror{flex-direction:row-reverse;justify-content:flex-start;}
  #obfFig .row .k{font-size:9px;letter-spacing:.2em;text-transform:uppercase;
    color:#4E525C;text-align:right;}
  #obfFig .row .v{font-family:var(--mono,ui-monospace,monospace);
    font-size:13px;color:#D8DCE4;}
  #obfFig .row .tick{width:18px;height:1px;background:#4E525C;opacity:.55;}
  #obfFig .row .g{flex:0 0 auto;transform:translateY(3px);opacity:.95;}
  /* Иерархия по времени: свежая строка в полном тоне, прежние тише. */
  #obfFig .row.old .v{color:#8A8F99;}
  #obfFig .row.old .k{color:#3A3D45;}
  #obfFig .row.old .g{opacity:.5;}
  @media (prefers-reduced-motion:reduce){
    #obfFig .row{transition:none;}
    #obfBeams line{transition:none;}
  }
  @media (prefers-reduced-motion:reduce){
    #obfText .ch{transition:none; opacity:1; filter:none; transform:none;}
  }
</style>
<div class="ob-brief" id="obBrief">
  <canvas id="obfCanvas"></canvas>
  <svg id="obfBeams"></svg>
  <div id="obfFig"></div>
  <div id="obfText"></div>
  <div class="obf-foot" id="obfFoot">клик в любом месте — к дашборду</div>
  <div class="obf-bar" id="obfBar"><u></u></div>
</div>
"""


BRIEF_JS = """
<script>
(function () {
  /* Данные вшиты в документ при сборке — см. render_brief() выше.
     Раньше здесь читался window.ORB от орбиты; в своём iframe соседа
     нет, и читать неоткуда. */
  var O = {};
  try { O = JSON.parse(document.getElementById('obfData').textContent); }
  catch (e) { O = {}; }
  var STARS = O.stars || [];
  if (!STARS.length) return;

  /* Фаза и расстояние до стопа посчитаны в питоне (analytics_stars) и
     приехали полями звезды. Функции оставлены ради мест вызова ниже —
     их тут около десятка, и разворачивать каждое в обращение к полю
     значило бы переписать половину файла ради нуля пользы. */
  function phase(s) { return s.phase || { a: '', k: 'wait' }; }
  function toStop(s) { return s.stopPct || 0; }

  var BRIEF_LAP = 105000;

  var wrap = document.getElementById('obBrief');
  var canvas = document.getElementById('obfCanvas');
  var txtEl = document.getElementById('obfText');
  if (!wrap || !canvas || !txtEl) return;
  var ctx = canvas.getContext('2d');

  function w(){ return wrap.clientWidth || window.innerWidth; }
  function h(){ return wrap.clientHeight || window.innerHeight; }

  /* ═════════════════════════════════════════════════════════
     Атмосферная сцена: кольцо из пыли + дюна с рельефными пиками.
     Числа ниже — не эстетический произвол, а результат прямого
     тестирования в браузере (Playwright, скриншот на каждом шаге):
     плотность частиц, амплитуда пиков дюны, разрывы кольца — всё
     подбиралось глазами против референса, отражённого в переписке.
     ═════════════════════════════════════════════════════════ */

  // Глоу-спрайт для пролетающей пыли: белое ядро → цвет → прозрачность.
  var sprites = {};
  function getSprite(color){
    if (sprites[color]) return sprites[color];
    var s = 40, off = document.createElement('canvas');
    off.width = off.height = s;
    var octx = off.getContext('2d');
    var g = octx.createRadialGradient(s/2,s/2,0, s/2,s/2,s/2);
    g.addColorStop(0, 'rgba(255,255,255,1)');
    g.addColorStop(.2, 'rgba(255,255,255,.9)');
    g.addColorStop(.45, color+'cc');
    g.addColorStop(1, color+'00');
    octx.fillStyle = g; octx.fillRect(0,0,s,s);
    sprites[color] = off;
    return off;
  }

  var ringGeo = null, ringDust = [], duneDust = [], duneFront = [];

  /* СПРАЙТЫ ВМЕСТО ПЕРЕСЧЁТА.
     Кольцо и дюна — это тысячи неподвижных друг относительно друга
     точек. Пересчитывать каждой из них синус, косинус и матрицу
     поворота на каждом кадре незачем: рисунок один и тот же, меняются
     только его поворот и мерцание. Поэтому обе россыпи «печём» один
     раз в закадровые холсты, а в кадре делаем поворот трансформом и
     две отрисовки картинки.
     Мерцание сохраняем вариантами: три фазы для кольца и две для
     дюны, между которыми идёт плавный перелив. Точки продолжают
     переливаться по одиночке — они разные в разных вариантах, — но
     стоит это четыре drawImage вместо десяти тысяч заливок. */
  var baseSprite = null, ringSprite = null, spriteDPR = 1;
  var sparks = [], ringSparks = [];

  function makeSprite(w2, h2){
    var c = document.createElement('canvas');
    c.width = Math.max(1, Math.round(w2*spriteDPR));
    c.height = Math.max(1, Math.round(h2*spriteDPR));
    var g = c.getContext('2d');
    g.setTransform(spriteDPR,0,0,spriteDPR,0,0);
    return {cv:c, ctx:g, w:w2, h:h2};
  }

  // Кольцо — 1.44×0.8 от исходного черновика (несколько раундов
  // «увеличь/уменьши» в тестировании сошлись на этом масштабе).
  var RING_SCALE = 1.44 * 0.8;

  function buildAmbient(){
    var cx = w()*0.5, cy = h()*0.50;
    var rx = Math.min(250, w()*0.21) * RING_SCALE, ry = rx*0.92;
    var rot = -8*Math.PI/180;
    ringGeo = {cx:cx, cy:cy, rx:rx, ry:ry, rot:rot};

    ringDust = [];
    // Два разрыва в кольце, симметрично друг напротив друга — не
    // идеальный замкнутый круг, а разомкнутая спираль в перспективе,
    // как в референсе.
    var GAP_HALF = 8*Math.PI/180, FADE_HALF = 26*Math.PI/180;
    var G1 = 183*Math.PI/180, G2 = G1 + Math.PI;
    function gapFactor(a){
      var gaps = [G1, G2];
      for (var i=0;i<gaps.length;i++){
        var d = Math.abs(a-gaps[i]) % (Math.PI*2);
        if (d > Math.PI) d = Math.PI*2-d;
        if (d < GAP_HALF) return 0;
        if (d < GAP_HALF+FADE_HALF) return (d-GAP_HALF)/FADE_HALF;
      }
      return 1;
    }
    var RING_N = Math.max(900, Math.min(3000, Math.round(w()*h()/430)));
    var placed = 0, tries = 0;
    while (placed < RING_N && tries < RING_N*20){
      tries++;
      var a = Math.random()*Math.PI*2;
      var gf = gapFactor(a);
      if (gf <= 0) continue;
      var jitter = (Math.random()-.5)*(26+14*gf)*RING_SCALE;
      ringDust.push({a:a, jitter:jitter, cx:cx, cy:cy, rx:rx, ry:ry, rot:rot,
        r:.35+Math.random()*.55, a0:(0.10+gf*0.45),
        tw:Math.random()*Math.PI*2, speed:.4+Math.random()*1,
        driftPhase:Math.random()*Math.PI*2, driftAmp:1.5+Math.random()*2.5});
      placed++;
    }

    // Дюна: волна с тремя острыми «пиками» поверх мягкой основы —
    // читается как рельефный силуэт, а не гладкая синусоида.
    duneDust = [];
    var DUNE_DEPTH = h()*0.34;
    /* Число частиц — ОТ ПЛОЩАДИ, а не константой. Одиннадцать тысяч
       подбирались на одном экране; на большом мониторе они же дают
       ту же плотность при вдвое большей работе, а на ноутбуке — вдвое
       гуще, чем нужно. Делитель подобран так, чтобы на 1440×900
       выходило около семи тысяч: разница на глаз не читается,
       нагрузка падает на треть. */
    var DUNE_N = Math.max(2600, Math.min(11000, Math.round(w()*h()/185)));
    for (var i=0;i<DUNE_N;i++){
      var x = Math.random()*w();
      var baseWave = Math.sin(x/w()*Math.PI*1.6)*46
                   + Math.sin(x/w()*Math.PI*4.2+1)*20
                   + Math.sin(x/w()*Math.PI*9+2)*8;
      var spike1 = Math.sin(x/w()*Math.PI*2.7+2.1);
      var spike2 = Math.sin(x/w()*Math.PI*5.3+4.4);
      var spike3 = Math.sin(x/w()*Math.PI*1.3+0.6);
      var peaks = Math.sign(spike1)*Math.pow(Math.abs(spike1),4)*95
                + Math.sign(spike2)*Math.pow(Math.abs(spike2),5)*55
                + Math.sign(spike3)*Math.pow(Math.abs(spike3),6)*70;
      var wave = baseWave + peaks;
      var baseY = h()*0.58 + wave;
      var depth = Math.pow(Math.random(),1.3)*DUNE_DEPTH;
      var y = baseY + depth;
      var depthNorm = Math.min(1, depth/DUNE_DEPTH);

      // Мягкий градиент сверху вниз — с полом, не обрыв в ноль.
      var gradient = 0.22 + 0.85*Math.pow(1-depthNorm, 1.9);
      // Рябь от ветра под углом к гребню — не вертикальная штриховка.
      var ripplePhase = x*0.045 + depthNorm*11;
      var ripple = 0.82 + 0.18*Math.sin(ripplePhase);
      var grain = Math.pow(Math.random(), 2.0);
      var base = gradient * ripple * (0.35+0.75*grain);
      var warm = Math.random() > (0.22 + 0.3*depthNorm);

      duneDust.push({x0:x, y0:y, r:.3+Math.random()*.8, warm:warm,
        tw:Math.random()*Math.PI*2, speed:.3+Math.random()*.9,
        driftPhase:Math.random()*Math.PI*2, driftAmp:1+Math.random()*2.2,
        base:base});
    }

    /* Передний слой (узкая полоса поверх кольца) отбирается ОДИН раз.
       Раньше кадр заново перебирал все одиннадцать тысяч частиц, чтобы
       отбросить 95% по координате — полный проход ради сотни точек. */
    duneFront = [];
    var loY = h()*0.62-((RING_SCALE-1)*70), hiY = h()*0.685;
    for (var q=0;q<duneDust.length;q++){
      var dp = duneDust[q];
      if (dp.y0 >= loY && dp.y0 <= hiY) duneFront.push(dp);
    }

    /* Подложка-градиент неподвижна — незачем пересоздавать её каждый
       кадр. Создание градиента дороже, чем кажется: это разбор
       остановок цвета и построение таблицы. */
    // Световое пятно печётся вместе с подложкой (см. bakeSprites) —
    // отдельный градиент в кадре не нужен.
    bakeSprites();
  }

  /* Печём ОДНУ подложку на всё: фон, световое пятно и дюну.
     Разбираться стоит не в числе точек, а в числе полноэкранных
     проходов: очистка, градиент и две дюны — это четыре перерисовки
     всего экрана за кадр, по шесть миллионов пикселей каждая. Именно
     они, а не синусы, роняли частоту до девятнадцати кадров.
     Теперь подложка одна и рисуется одним drawImage.

     Кольцо печётся отдельно и малым квадратом — его надо вращать.
     Мерцание живёт в горстке точек поверх: их немного, они дешёвые,
     и без них пыль выглядит мёртвой фотографией. */
  function bakeSprites(){
    spriteDPR = Math.min(1.5, devicePixelRatio || 1);

    // Подложка с запасом по краям: она ездит на пару пикселей.
    var PAD = 6;
    baseSprite = makeSprite(w()+PAD*2, h()+PAD*2);
    var g0 = baseSprite.ctx;
    g0.fillStyle = '#07080B';
    g0.fillRect(0, 0, w()+PAD*2, h()+PAD*2);
    var gr = g0.createRadialGradient(
      w()*0.5+PAD, ringGeo.cy+PAD, 10, w()*0.5+PAD, ringGeo.cy+PAD, w()*0.35);
    gr.addColorStop(0, 'rgba(200,200,215,.10)');
    gr.addColorStop(1, 'rgba(0,0,0,0)');
    g0.fillStyle = gr;
    g0.fillRect(0, 0, w()+PAD*2, h()+PAD*2);
    for (var i=0;i<duneDust.length;i++){
      var d = duneDust[i];
      g0.globalAlpha = d.base*0.72;
      g0.fillStyle = d.warm ? '#D9A15E' : '#9a8a78';
      g0.fillRect(d.x0+PAD, d.y0+PAD, d.r*1.7, d.r*1.7);
    }
    baseSprite.pad = PAD;

    // Кольцо — квадрат с центром посередине: вращение сводится к
    // rotate вокруг середины картинки.
    var maxR = ringGeo.rx + 60*RING_SCALE;
    var side = Math.ceil(maxR*2);
    ringSprite = makeSprite(side, side);
    var g1 = ringSprite.ctx;
    g1.fillStyle = '#dfe6ec';
    for (var j=0;j<ringDust.length;j++){
      var p = ringDust[j];
      var px = Math.cos(p.a)*(p.rx+p.jitter);
      var py = Math.sin(p.a)*(p.ry+p.jitter);
      var rx2 = px*Math.cos(p.rot)-py*Math.sin(p.rot);
      var ry2 = px*Math.sin(p.rot)+py*Math.cos(p.rot);
      g1.globalAlpha = p.a0*0.72;
      g1.fillRect(maxR+rx2, maxR+ry2, p.r*1.7, p.r*1.7);
    }
    ringSprite.half = maxR;

    /* Живые искры — небольшая выборка из обеих россыпей. Мерцает
       десятая часть точек, а кажется, что вся пыль: глаз ловит
       движение, а не пересчитывает яркости. */
    sparks = [];
    var stepD = Math.max(1, Math.round(duneDust.length/260));
    for (var k=0;k<duneDust.length;k+=stepD) sparks.push(duneDust[k]);
    ringSparks = [];
    var stepR = Math.max(1, Math.round(ringDust.length/180));
    for (var m=0;m<ringDust.length;m+=stepR) ringSparks.push(ringDust[m]);
  }

  function resizeScene(){
    /* Плотность холста ограничена полутора: на ретине пыль рисуется
       вчетверо большим числом пикселей, а точка размером в пиксель от
       этого не становится красивее. Текст и разметка остаются
       чёткими — они не на холсте. */
    var DPR = Math.min(1.5, devicePixelRatio || 1);
    canvas.width = w()*DPR; canvas.height = h()*DPR;
    canvas.style.width = w()+'px'; canvas.style.height = h()+'px';
    ctx.setTransform(DPR,0,0,DPR,0,0);
    buildAmbient();
  }
  window.addEventListener('resize', resizeScene);

  /* ЧАСТИЦА — ПРЯМОУГОЛЬНИК, А НЕ КРУГ.
     arc() + fill() на точку размером меньше полутора пикселей рисует
     ровно тот же пиксель, что и fillRect, но проходит весь путь
     построения контура. На четырнадцати тысячах частиц это и есть
     главный источник тормозов — не сами точки, а способ их рисовать. */
  function drawAmbient(t){
    if (!baseSprite) return;
    var PAD = baseSprite.pad;

    /* ОДИН полноэкранный проход вместо четырёх. Подложка непрозрачна,
       поэтому очистка холста тоже не нужна — она сама себя закрывает.
       Снос дюны — общим смещением картинки на пару пикселей; ровно то
       же, что раньше считалось каждой песчинке отдельно. */
    var driftX = Math.sin(t*0.0004)*2.2, driftY = Math.cos(t*0.00035)*1.3;
    ctx.globalAlpha = 1;
    ctx.drawImage(baseSprite.cv, -PAD+driftX, -PAD+driftY,
                  baseSprite.w, baseSprite.h);

    /* ВРАЩЕНИЕ — ЧИСТЫЙ ТРАНСФОРМ: поворачивается готовая картинка, а
       не три тысячи точек по отдельности. */
    var half = ringSprite.half, size = half*2, spin = t*0.000045;
    ctx.save();
    ctx.translate(ringGeo.cx, ringGeo.cy);
    ctx.rotate(spin);
    ctx.drawImage(ringSprite.cv, -half, -half, size, size);
    ctx.restore();

    // Искры кольца — в тех же координатах, что и спрайт, с тем же
    // поворотом: иначе они «поплывут» относительно своей россыпи.
    var p, flick, i;
    ctx.save();
    ctx.translate(ringGeo.cx, ringGeo.cy);
    ctx.rotate(spin);
    ctx.fillStyle = '#dfe6ec';
    for (i=0;i<ringSparks.length;i++){
      p = ringSparks[i];
      flick = 0.5+0.5*Math.sin(t*0.0012*p.speed+p.tw);
      var px = Math.cos(p.a)*(p.rx+p.jitter), py = Math.sin(p.a)*(p.ry+p.jitter);
      var rx2 = px*Math.cos(p.rot)-py*Math.sin(p.rot);
      var ry2 = px*Math.sin(p.rot)+py*Math.cos(p.rot);
      ctx.globalAlpha = p.a0*flick*0.9;
      ctx.fillRect(rx2, ry2, p.r*2.1, p.r*2.1);
    }
    ctx.restore();

    // Искры дюны и передний слой поверх кольца.
    for (i=0;i<sparks.length;i++){
      p = sparks[i];
      flick = 0.5+0.5*Math.sin(t*0.0012*p.speed+p.tw);
      ctx.globalAlpha = p.base*flick*0.8;
      ctx.fillStyle = p.warm ? '#D9A15E' : '#9a8a78';
      ctx.fillRect(p.x0+driftX, p.y0+driftY, p.r*2.1, p.r*2.1);
    }
    for (i=0;i<duneFront.length;i++){
      p = duneFront[i];
      flick = 0.5+0.5*Math.sin(t*0.0009*p.speed+p.tw);
      ctx.globalAlpha = p.base*(0.3+flick*0.4);
      ctx.fillStyle = p.warm ? '#D9A15E' : '#9a8a78';
      ctx.fillRect(p.x0+driftX, p.y0+driftY, p.r*1.7, p.r*1.7);
    }
    ctx.globalAlpha = 1;
  }

  /* Ветер: пыль срывается с узкой полосы на правом краю кольца и
     сдувается сквозняком через него, на 100px за дальний край —
     дистанция считается от РЕАЛЬНОГО радиуса кольца, а не взята с
     потолка. Точка старта каждый раз новая (±25° вокруг правого
     края) — не всегда одна и та же высота. */
  var flyDust = [];
  function spawnFlyDust(){
    var rx = ringGeo.rx, ry = ringGeo.ry, rot = ringGeo.rot;
    var ringCx = ringGeo.cx, ringCy = ringGeo.cy;
    var N = 20;
    var baseAngle = (Math.random()-0.5) * (50*Math.PI/180);
    var bpx = Math.cos(baseAngle)*rx, bpy = Math.sin(baseAngle)*ry;
    var brx = bpx*Math.cos(rot) - bpy*Math.sin(rot);
    var bry = bpx*Math.sin(rot) + bpy*Math.cos(rot);
    var originX = ringCx + brx, originY = ringCy + bry;
    var bandHeight = 20 + Math.random()*6;
    var dist = rx*2 + 100;
    for (var i=0;i<N;i++){
      var sy = originY + (Math.random()-0.5)*bandHeight;
      var sx = originX;
      var drift = (Math.random()-0.5)*44;
      flyDust.push({
        x:sx, y:sy, tx: sx-dist, ty: sy+drift,
        t0: performance.now()+Math.random()*450,
        dur: 800+Math.random()*600,
        r: (0.5+Math.random()*0.9) / 3 / 2,
        wobble: Math.random()*Math.PI*2
      });
    }
  }
  function easeInOutSine(k){ return -(Math.cos(Math.PI*k)-1)/2; }

  /* Прорисовка/стирание графика — не альфа туда-сюда, а линия,
     растущая от начала к концу при появлении и стирающаяся тем же
     способом при скрытии (retract), как в проверенном прототипе. */
  var diagramActive = -1, diagramPhase = 'idle', diagramT0 = 0;
  var DRAW_IN_MS = 750*1.3, DRAW_OUT_MS = 520*1.3;

  function drawDiagram(idx, accent, progress){
    if (progress <= 0.002) return;
    var seg = SEGMENTS[idx];
    if (!seg || !seg.pts) return;
    var pts = seg.pts, N = pts.length;
    var cx = ringGeo.cx, cy = ringGeo.cy;
    var W = Math.min(w()*0.5, 420) * 0.5 * 1.2 * 1.3;
    var H = W * 0.42;
    var baseY = cy + H*0.62;
    var alpha = 0.9 * 0.85 * 0.9;

    var path = pts.map(function (v, i) {
      var x = cx - W/2 + (i/(N-1))*W;
      var y = baseY - H*0.55 - v*H*0.5;
      return [x, y];
    });

    var totalSeg = N-1;
    var shown = progress * totalSeg;
    var fullSeg = Math.floor(shown);
    var frac = shown - fullSeg;

    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    /* Свечение — вторым широким штрихом, а не shadowBlur.
       Размытие тени пересчитывается по всей длине линии каждый кадр и
       на графике из тридцати точек стоит дороже, чем сама линия. Два
       штриха дают тот же ореол ценой второго прохода по пути. */

    ctx.beginPath();
    ctx.moveTo(cx-W/2, baseY);
    ctx.lineTo(cx-W/2+W*progress, baseY);
    ctx.strokeStyle = accent; ctx.lineWidth = 0.6;
    ctx.globalAlpha = alpha*0.35;
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(path[0][0], path[0][1]);
    for (var i=1;i<=fullSeg && i<N;i++) ctx.lineTo(path[i][0], path[i][1]);
    if (fullSeg < totalSeg){
      var p0 = path[fullSeg], p1 = path[fullSeg+1];
      ctx.lineTo(p0[0]+(p1[0]-p0[0])*frac, p0[1]+(p1[1]-p0[1])*frac);
    }
    ctx.strokeStyle = accent;
    ctx.lineWidth = 3.4;                 // ореол
    ctx.globalAlpha = alpha*0.18;
    ctx.stroke();
    ctx.lineWidth = 1.2;                 // сама линия
    ctx.globalAlpha = alpha*0.9;
    ctx.stroke();

    ctx.fillStyle = accent;
    ctx.globalAlpha = alpha*0.7;
    path.forEach(function (pt, i) {
      if (i > fullSeg) return;
      ctx.fillRect(pt[0]-1.2, pt[1]-1.2, 2.4, 2.4);
    });

    ctx.restore();
    ctx.globalAlpha = 1;
  }

  /* Потолок частоты снят: после перехода на спрайты кадр стоит
     считанные доли миллисекунды, и ограничивать его — только делать
     движение ступенчатым. Ограничение имело смысл, пока в кадре
     пересчитывались десять тысяч точек. */
  function frame(t){
    drawAmbient(t);
    figBeams();

    if (diagramActive >= 0){
      var now2 = performance.now(), progress;
      if (diagramPhase === 'in'){
        progress = Math.min(1, (now2-diagramT0)/DRAW_IN_MS);
      } else {
        progress = Math.max(0, 1-(now2-diagramT0)/DRAW_OUT_MS);
        if (progress <= 0){ diagramActive = -1; diagramPhase = 'idle'; }
      }
      if (diagramActive >= 0){
        drawDiagram(diagramActive, SEGMENTS[diagramActive].accent, progress);
      }
    }

    var now = performance.now();
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    var sprite = getSprite('#F5E6C8');
    flyDust = flyDust.filter(function (p) {
      var k = (now-p.t0)/p.dur;
      if (k < 0) return true;
      if (k > 1) return false;
      var e = easeInOutSine(k);
      var turb = Math.sin(k*7+p.wobble)*6 + Math.sin(k*17+p.wobble*2)*2.5;
      var x = p.x+(p.tx-p.x)*e;
      var y = p.y+(p.ty-p.y)*e + turb;
      var alpha = Math.sin(k*Math.PI);
      for (var g=0; g<4; g++){
        var gk = Math.max(0, k - g*0.08);
        var ge = easeInOutSine(gk);
        var gx = p.x+(p.tx-p.x)*ge;
        var gy = p.y+(p.ty-p.y)*ge + Math.sin(gk*7+p.wobble)*6 + Math.sin(gk*17+p.wobble*2)*2.5;
        var size = Math.max(3.4, p.r*(11-g*1.3));
        ctx.globalAlpha = alpha*0.21*(1-g*0.22);
        ctx.drawImage(sprite, gx-size/2, gy-size/2, size, size);
      }
      return true;
    });
    ctx.restore();
    ctx.globalAlpha = 1;

    requestAnimationFrame(frame);
  }

  /* Разноцветность вернулась: сегмент несёт seg.html (разметка с
     <span class="up">/"dn"/"n"/"t"/... — та же палитра, что была в
     старой посимвольной печати), а не голый текст. htmlToTokens()
     разбирает эту разметку в плоский список {text, cls} — по одному
     токену на текстовый узел/цветной элемент верхнего уровня. Вложенные
     теги (было такое только в строке журнала) сознательно не
     поддерживаются: один уровень цвета на сегмент — этого достаточно
     для того, что здесь красится, и не усложняет разбор.  */
  function htmlToTokens(html){
    var div = document.createElement('div');
    div.innerHTML = html;
    var tokens = [];
    div.childNodes.forEach(function (node) {
      if (node.nodeType === 3) tokens.push({text: node.textContent, cls: ''});
      else if (node.nodeType === 1) tokens.push({text: node.textContent, cls: node.className || ''});
    });
    return tokens;
  }

  /* Перенос строк — естественный, браузерный: раньше ширина строки
     мерилась вручную на canvas (без letter-spacing, который добавляет
     CSS) и это давало текст ЧУТЬ шире реального контейнера — строки
     выходили за пределы кольца. Слово — свой inline-block (буквы не
     разъезжаются при переносе), пробел между словами — обычный
     текстовый узел (место переноса для браузера), сама ширина
     ограничена через CSS max-width на контейнере. */
  function buildTextDOM(tokens){
    var frag = document.createDocumentFragment();
    var idxChar = 0;
    tokens.forEach(function (tok) {
      var words = tok.text.split(' ');
      words.forEach(function (word, wi) {
        if (wi > 0) frag.appendChild(document.createTextNode(' '));
        if (!word) return;
        var wordSpan = document.createElement('span');
        wordSpan.style.display = 'inline-block';
        if (tok.cls) wordSpan.className = tok.cls;
        for (var i=0;i<word.length;i++){
          var chSpan = document.createElement('span');
          chSpan.className = 'ch';
          chSpan.style.transitionDelay = (idxChar*STEP_MS) + 'ms';
          idxChar++;
          chSpan.textContent = word[i];
          wordSpan.appendChild(chSpan);
        }
        frag.appendChild(wordSpan);
      });
    });
    return { frag: frag, totalChars: idxChar };
  }

  function stripTags(html){ return html.replace(/<[^>]*>/g, ''); }

  // Задержка перед следующим сегментом — на пару секунд дольше, чем
  // раньше (было 2300).
  var STEP_MS = 42*1.3, CHAR_DUR = 550*1.3, HOLD_MS = 2300 + 2000;
  // Финальная выдержка: итог дня стоит на экране до клика.
  var LAST_HOLD_MS = 30000;
  var BLOCK_ACCENTS = ['#7FB4FF', '#F5A623', '#6FE3B4', '#FFD98A', '#E89AB0'];

  var runToken = 0, running = false;

  /* ═════════ Фигура дня ═════════
     Строка садится по сторонам кольца двумя крыльями: чётные слева,
     нечётные справа. Правое зеркалим — ярлык и значение меняются
     местами, чтобы числа обоих крыльев смотрели на кольцо, а взгляд
     не гнало справа налево против чтения. */
  var figEl = document.getElementById('obfFig');
  var beamsEl = document.getElementById('obfBeams');
  var figRows = [];

  var GW = 64, GH = 16;
  function glyph(g){
    if (!g) return '';
    var col = g.tone === 'dn' ? '#FF6B35' : (g.tone === 'gd' ? '#E8C27A' : '#8A8F99');
    var p = '<svg class="g" viewBox="0 0 '+GW+' '+GH+'" width="'+GW+'" height="'+GH+'">';
    if (g.t === 'ticks' && g.all){
      var n = g.all, wd = (GW-2)/n;
      for (var i=0;i<n;i++){
        var on = i < g.on;
        p += '<rect x="'+(i*wd).toFixed(1)+'" y="'+(on?2:5)+'" width="'+
             (wd-2.2).toFixed(1)+'" height="'+(on?10:4)+'" fill="'+
             (on?col:'#2A2E36')+'" rx="0.5"/>';
      }
    } else if (g.t === 'fill'){
      var sc = g.scale || 100;
      var w2 = Math.max(0, Math.min(1, g.pct/sc))*GW;
      var mk = Math.max(0, Math.min(1, (g.mark||0)/sc))*GW;
      p += '<rect x="0" y="5" width="'+GW+'" height="4" fill="#20232A" rx="2"/>'+
           '<rect x="0" y="5" width="'+w2.toFixed(1)+'" height="4" fill="'+col+
           '" rx="2" opacity=".85"/>'+
           '<rect x="'+mk.toFixed(1)+'" y="1.5" width="1" height="11" fill="#6C7280"/>';
    } else if (g.t === 'ring'){
      var r = 5.4, cx = GW/2, cy = GH/2, C = 2*Math.PI*r;
      p += '<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="none" stroke="#20232A" stroke-width="2"/>'+
           '<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="none" stroke="#48A97C" stroke-width="2"'+
           ' stroke-dasharray="'+(C*Math.min(100,g.pct||0)/100).toFixed(1)+' '+C.toFixed(1)+
           '" stroke-linecap="round" transform="rotate(-90 '+cx+' '+cy+')"/>';
    } else if (g.t === 'dev'){
      var mid = GW/2, len = Math.min(1, Math.abs(g.val)/(g.max||1))*(GW/2-2);
      p += '<line x1="'+mid+'" y1="1" x2="'+mid+'" y2="15" stroke="#3A3D45" stroke-width="1"/>'+
           '<rect x="'+(g.val<0?(mid-len):mid).toFixed(1)+'" y="6" width="'+len.toFixed(1)+
           '" height="3" fill="'+(g.val<0?'#FF6B35':'#48A97C')+'" rx="1.5"/>';
    }
    return p + '</svg>';
  }

  /* ═══ Места вокруг кольца ═══
     Четырнадцать слотов: по пять на каждый бок и по два сверху и
     снизу. Порядок заполнения — сначала бока (там строка длиннее и
     читается ровнее), потом верх, потом низ: то есть первые сегменты
     занимают лучшие места, а поздние садятся на свободные.
     Число мест известно ЗАРАНЕЕ (FIG_TOTAL), поэтому шаг по вертикали
     считается сразу под итоговое число строк — иначе каждая новая
     раздвигала бы прежние, и фигура бы всю сводку ползала. */
  var SIDE_CAP = 5, FIG_TOTAL = 0;

  function figSlot(i, n){
    var cx = ringGeo.cx, cy = ringGeo.cy;
    var R = ringGeo.rx, RY = ringGeo.ry;
    var sideN = Math.min(n, SIDE_CAP*2);
    if (i < sideN){
      var side = (i % 2 === 0) ? -1 : 1;
      var k = Math.floor(i/2);
      var perSide = Math.ceil(sideN/2);
      var t = (perSide <= 1) ? 0.5 : k/(perSide-1);
      /* Дальше от обода: 1.34 вместо 1.06 — на прежнем расстоянии
         числа лезли в пыль кольца и спорили с ней за внимание. */
      return {dx: cx + side*(R*1.34) + (side<0 ? -6 : 6),
              dy: cy + (-0.86 + t*1.72)*RY*0.98,
              mirror: side > 0};
    }
    /* Верх и низ: по две строки, разнесённые от вертикальной оси,
       чтобы не столкнуться друг с другом и с читаемым текстом. */
    var extra = i - sideN;              // 0,1 — верх; 2,3 — низ
    var up = extra < 2;
    var left = (extra % 2 === 0);
    return {dx: cx + (left ? -R*0.34 : R*0.34),
            dy: cy + (up ? -RY*1.36 : RY*1.36),
            mirror: !left};
  }

  function figLayout(){
    var n = Math.max(figRows.length, FIG_TOTAL);
    figRows.forEach(function (r, i) {
      var p = figSlot(i, n);
      r.mirror = p.mirror;
      r.el.classList.toggle('mirror', p.mirror);
      /* Место — В ТРАНСФОРМЕ, а не в left/top: последние переходами не
         анимируются, и при появлении новой строки все прежние
         перескакивали бы на новые места мгновенно. */
      r.el.style.transform = 'translate('+Math.round(p.dx)+'px,'+
        Math.round(p.dy)+'px) translate('+(p.mirror ? '0' : '-100%')+
        ',-50%) scale(.96)';
      r.el.classList.toggle('old', i < figRows.length-1);
      r.beam.classList.toggle('fresh', i === figRows.length-1);
    });
  }

  /* Мест вокруг кольца ровно четырнадцать (5+5 по бокам, 2 сверху,
     2 снизу). Пятнадцатая строка встала бы поверх четвёртой — лучше
     не показать её вовсе, чем показать нечитаемую кашу. Сегмент при
     этом всё равно проговаривается вслух, просто не остаётся. */
  var FIG_SLOTS = 14;

  function figAdd(seg){
    if (!seg || !seg.k || !seg.v || !ringGeo) return;
    if (figRows.length >= FIG_SLOTS) return;
    var mirror = figSlot(figRows.length,
      Math.max(figRows.length+1, FIG_TOTAL)).mirror;
    var el = document.createElement('div');
    el.className = 'row' + (mirror ? ' mirror' : '');
    el.innerHTML = '<span class="k">'+seg.k+'</span><span class="tick"></span>'+
      glyph(seg.g) + '<span class="v">'+seg.v+'</span>';
    el.style.transform = 'translate('+Math.round(ringGeo.cx)+'px,'+
      Math.round(ringGeo.cy)+'px) translate('+(mirror?'0':'-100%')+',-50%) scale(.86)';
    figEl.appendChild(el);
    /* Принудительный пересчёт: без него начальное и конечное состояние
       задаются в одном кадре, браузер их схлопывает — перехода не
       происходит вовсе, и строка телепортируется на место. */
    void el.offsetWidth;
    var beam = document.createElementNS('http://www.w3.org/2000/svg','line');
    beamsEl.appendChild(beam);
    figRows.push({el: el, beam: beam, mirror: mirror});
    requestAnimationFrame(function () {
      el.classList.add('on'); beam.classList.add('on'); figLayout();
    });
  }

  /* Лучи пересчитываются каждый кадр по фактическому положению строки:
     она едет полторы секунды, и луч, посчитанный один раз, всё это
     время указывал бы туда, где строки уже нет. */
  function figBeams(){
    if (!figRows.length || !ringGeo) return;
    for (var i=0;i<figRows.length;i++){
      var r = figRows[i], box = r.el.getBoundingClientRect();
      if (!box.width) continue;
      var ax = r.mirror ? box.left : box.right, ay = box.top + box.height/2;
      var dx = ax-ringGeo.cx, dy = ay-ringGeo.cy, len = Math.hypot(dx,dy) || 1;
      r.beam.setAttribute('x1', (ringGeo.cx+dx/len*ringGeo.rx*0.94).toFixed(1));
      r.beam.setAttribute('y1', (ringGeo.cy+dy/len*ringGeo.ry*0.94).toFixed(1));
      r.beam.setAttribute('x2', ax.toFixed(1));
      r.beam.setAttribute('y2', ay.toFixed(1));
    }
  }

  function showSegment(idx, token){
    return new Promise(function (resolve) {
      var done = false, wd = 0;
      function finish(){
        if (done) return;
        done = true; clearTimeout(wd); resolve();
      }
      /* СТОРОЖ. Страховка ниже ловит только синхронный сбой; всё,
         что вырвется из таймера или кадра (leave, rAF), уходит мимо
         неё — без сторожа очередь висла бы на таком сегменте вечно,
         а экран молча замирал. */
      wd = setTimeout(function () {
        if (window.console) console.warn('бриф: сегмент ' + idx +
          ' застрял — пропускаю');
        finish();
      }, HOLD_MS + LAST_HOLD_MS + 25000);
      try { showSegmentInner(idx, token, finish); }
      catch (e) {
        /* СТРАХОВКА. Исключение внутри сегмента раньше убивало всю
           очередь молча: экран замирал на последней успевшей фразе.
           Теперь сбойный сегмент пропускается, причина с его номером
           уходит в консоль, а сводка доигрывает до конца. */
        if (window.console) console.warn('бриф: сегмент ' + idx +
          ' не показан — ' + (e && e.message ? e.message : e));
        setTimeout(finish, 60);
      }
    });
  }

  function showSegmentInner(idx, token, resolve){
    {
      var seg = SEGMENTS[idx];
      /* Сегмент без текста — только для фигуры (альт-доля, резервуар:
         в центре они уже прозвучали хвостом строки разрешения).
         Садится сразу и не занимает время показа. */
      if (!seg.html){ figAdd(seg); resolve(); return; }
      var cx = ringGeo.cx, cy = ringGeo.cy, rx = ringGeo.rx;
      var fontPx = (Math.min(27, Math.max(16, w()/48)) * Math.min(1.15, RING_SCALE)) * 0.5 * 0.8;

      txtEl.style.fontSize = fontPx+'px';
      txtEl.style.top = cy+'px';
      // Сужено с rx*1.55: строка реально вылезала за силуэт кольца —
      // 1.55 был запас больше, чем видимый диаметр.
      txtEl.style.maxWidth = Math.min(w()*0.7, rx*1.3) + 'px';

      var tokens = htmlToTokens(seg.html);
      var built = buildTextDOM(tokens);
      txtEl.innerHTML = '';
      txtEl.appendChild(built.frag);
      var totalChars = built.totalChars;

      requestAnimationFrame(function () {
        if (token !== runToken) return;
        var chs = txtEl.querySelectorAll('.ch');
        for (var i=0;i<chs.length;i++) chs[i].classList.add('on');
      });
      spawnFlyDust();
      if (seg.pts){
        diagramActive = idx; diagramPhase = 'in'; diagramT0 = performance.now();
      } else {
        diagramActive = -1; diagramPhase = 'idle';
      }

      var revealDur = (totalChars-1)*STEP_MS + CHAR_DUR;
      var hold = HOLD_MS + (seg.pts ? 900 : 0);

      /* Финал не гаснет сам: последний сегмент ждёт полминуты или
         клика. «Дочитал» решает человек, а не таймер — иначе итог
         исчезает ровно тогда, когда его можно наконец прочесть. */
      var last = (idx === LAST_SHOW);
      var fired = false;
      function leave(){
        if (fired || token !== runToken) return;
        fired = true;
        document.removeEventListener('click', leave);
        document.removeEventListener('keydown', leave);
        try {
          var chs = txtEl.querySelectorAll('.ch');
          for (var i=0;i<chs.length;i++){
            chs[i].style.transitionDelay = '0ms';
            chs[i].classList.remove('on');
          }
          if (seg.pts){ diagramPhase = 'out'; diagramT0 = performance.now(); }
          /* Текст гаснет — смысл садится в фигуру. */
          figAdd(seg);
        } catch (e) {
          /* Ошибке ухода нельзя держать очередь: строка в фигуре
             пропадёт, показ продолжится. */
          if (window.console) console.warn('бриф: сегмент ' + idx +
            ' не сел в фигуру — ' + (e && e.message ? e.message : e));
        }
        setTimeout(function () { if (token === runToken) resolve(); }, 900);
      }
      setTimeout(function () {
        if (token !== runToken) return;
        if (last){
          document.addEventListener('click', leave);
          document.addEventListener('keydown', leave);
        }
        setTimeout(leave, last ? LAST_HOLD_MS : hold);
      }, revealDur);
    }
  }

  async function playAll(){
    if (running) return;
    var myToken = runToken;
    running = true;
    for (var i=0;i<SEGMENTS.length;i++){
      if (myToken !== runToken) return;
      await showSegment(i, myToken);
    }
    if (myToken === runToken) running = false;
  }

  /* ═════════════════════════════════════════════════════════
       Данные. Логика сбора и формулировок не менялась — только
       финальная форма: раньше строка несла пару {p, h} (простой
       текст и HTML с цветными span), теперь только текст, который
       уже есть в бывшем .p почти везде без изменений. Насыщенные
       блоки лидера потока и объёма (график + стоп/цель/дни/
       фандинг + кольцо скора) по решению пользователя схлопнуты
       в одну строку текста плюс компактный график на тех же самых
       данных (LC.series / VC.ratios) — деталей меньше, но график
       настоящий, не нарисованный по случайному блужданию.
       ═════════════════════════════════════════════════════════ */

  var go = [], wait = [], hold = [];
  STARS.forEach(function (s) {
    var p = phase(s);
    if ((s.streak || 1) >= 3 && (s.days || 0) >= 4) hold.push(s);
    else if (p.k === 'go' && !s.firstRun) go.push(s);
    else wait.push(s);
  });

  go.sort(function (a, b) { return (b.score || 0) - (a.score || 0); });
  wait.sort(function (a, b) { return (b.f || 0) - (a.f || 0); });
  hold.sort(function (a, b) { return (b.streak || 0) - (a.streak || 0); });

  var near = STARS.filter(function (s) { return s.stop && toStop(s) <= 8; })
    .sort(function (a, b) { return toStop(a) - toStop(b); }).slice(0, 3);

  function fmtMoney(v) {
    var n = +v || 0, a = Math.abs(n), t = n < 0 ? '−$' : '$';
    return t + (a >= 10000 ? (a / 1000).toFixed(1) + 'K' : Math.round(a));
  }
  function signed(v) {
    var n = +v || 0;
    return (n >= 0 ? '+' : '') + n.toFixed(1) + '%';
  }
  function waitWhy(s) {
    if (s.ath === undefined) return 'нет данных прогона';
    if ((s.ath || 0) > -80) return 'вне зоны дна, ' + Math.round(s.ath) + '% от ATH';
    if (s.firstRun) return 'первый разгон, входить рано';
    return 'ровный рост, ждать сквиза';
  }
  function pct(v, d) {
    if (v === null || v === undefined) return '—';
    return (v > 0 ? '+' : '') + v.toFixed(d === undefined ? 1 : d) + '%';
  }
  /* Склонять надо ВСЮ группу, а не одно существительное. «Ушли
     всего 1 монета» — типичная ошибка: число согласовали с
     существительным и забыли глагол. Формы для глагола те же три:
     ушла / ушли / ушло (1 — 2..4 — 5.. и 11..14). */
  function plural(n, one, few, many) {
    var a = Math.abs(n) % 100;
    if (a >= 11 && a <= 14) return many;
    a %= 10;
    if (a === 1) return one;
    if (a >= 2 && a <= 4) return few;
    return many;
  }
  function capP(s) { return s.cap ? ' ' + s.cap : ''; }

  var M = O.market || {};
  var J = M.journal || {};
  var DORM = M.dormant || [];
  var L = M.leader || {};

  var heldT = {};
  hold.forEach(function (s) { heldT[s.t] = true; });
  function freshOnly(list) {
    return list.filter(function (v) { return !heldT[v.t]; });
  }

  var HRfull = M.hourly || { n: 0, list: [] };
  var HR = { n: HRfull.n, list: freshOnly(HRfull.list || []) };
  var bigVolAll = M.flowVol || [];
  var bigVol = freshOnly(bigVolAll).slice(0, 5);

  /* Цветной cap() — та же справка о капитализации, что и раньше,
     мельче и тише (класс .obf-cap), не голым довеском к тикеру. */
  function cap(s) { return s.cap ? ' <span class="obf-cap">' + s.cap + '</span>' : ''; }

  /* ── Р-1: строка разрешения рынка, первый сегмент ──
     «Пока не понятно, что с рынком, список альтов читать
     бессмысленно» — поэтому строка открывает бриф, до портфеля и
     фона. Выходные в перечень причин НЕ включаются: у них ниже своя
     развёрнутая строка, а правило одно — у каждой причины ровно одно
     место в тексте. Счёт же считает все причины, включая выходные:
     число и перечень отвечают на разные вопросы. */
  var P = M.permission || {};
  var AS = M.altShare || {};
  var permLine = '';
  if (P.knownCount) {
    var pp = P.parts || {};
    /* Причины — это notes сработавших составляющих, единым правилом:
       новая составляющая в permission попадает в строку сама, без
       правки брифа. Выходные исключены — у них ниже своя развёрнутая
       строка (правило «у причины одно место в тексте»). */
    var reasons = [];
    ['btc', 'funding', 'oi', 'cascade', 'calendar'].forEach(function (k) {
      var part = pp[k] || {};
      if (part.warn && part.note) reasons.push(part.note);
    });
    /* Шорт-перекос — не предупреждение, а состояние заряда: топливо
       имеет сторону, и заряд вверх печатается отдельным хвостом,
       спокойным тоном, вне перечня причин. */
    var fuelTail = ((pp.funding || {}).side === 'short')
      ? ' <span class="gd">Толпа в шорте — топливо сквиза вверх.</span>'
      : '';
    var head = (P.warnCount
      ? 'Окно рынка: <span class="warn">' + P.warnCount + ' ' +
        plural(P.warnCount, 'предупреждение', 'предупреждения',
               'предупреждений') + '</span>'
      : 'Окно рынка: <span class="gd">явных предупреждений нет</span>') +
      ' из ' + P.knownCount + ' составляющих';
    var altTail = (AS.d7 !== undefined && AS.d7 !== null)
      ? ' Биткоин за неделю обошли <span class="n">' + AS.d7 +
        '%</span> выборки' +
        (AS.d7 < 50 ? ' — <span class="mut">прилив до альтов не дошёл</span>.'
                    : '.')
      : '';
    /* Резервуар — не причина и не предупреждение, а объяснение,
       почему журнал лежит: печатается после альт-доли, тем же
       спокойным тоном. Нет файла — нет строки: подсказка «заведите
       файл» уместна в консоли прогона, не в утреннем брифе. */
    /* Календарь без предупреждения — тоже новость: «серия выкупов
       идёт» это состояние, которое меняет чтение фазы. Печатается
       спокойным хвостом, как резервуар; при warn он уже ушёл в
       причины выше и здесь не дублируется. */
    var cal = pp.calendar || {};
    var calTail = (cal.known && !cal.warn && (cal.items || []).length)
      ? ' <span class="mut">' + cal.note + '.</span>'
      : '';
    var rsv = pp.reservoir || {};
    var rsvTail = (rsv.known && rsv.note)
      ? ' <span class="mut">' + rsv.note + '.</span>'
      : '';
    permLine = head + (reasons.length ? ': ' + reasons.join('; ') : '') +
      '.' + fuelTail + altTail + calTail + rsvTail;
  }

  var wk = M.weekend || '';
  var wknd = '';
  if (wk === 'soon') {
    wknd = '<span class="warn">Завтра выходные</span> — ликвидность начнёт ' +
           'уходить уже к вечеру, торговать сегодня с осторожностью.';
  } else if (wk === 'now') {
    wknd = '<span class="warn">Выходные</span> — тонкий стакан, движения ' +
           'рваные. Лучше не торговать.';
  }

  /* Фон рынка — та же цепочка условий, что и раньше (см. Ч-12
     тех.долга про биткоин/доминацию), с той же раскраской, что была
     у .obf-p до упрощения на голый текст. */
  /* Строки фона тоже садятся в фигуру: раньше они были голыми
     строками без ярлыка, figAdd их отбрасывал — и половина сводки
     просто исчезала с экрана вместо того, чтобы встать у кольца.
     tag() навешивает ярлык и значение прямо там, где строка
     рождается: у места создания известны числа, из которых она
     собрана, а разбирать готовый текст регулярками — гарантированно
     сломаться на первой правке формулировки. */
  var bg = [];
  function bgPush(html, k, v, g){ bg.push(tagSeg({html: html}, k, v, g)); }
  if (M.frozen) {
    bgPush('Рынок сейчас <span class="warn">замер</span>. Лучшая монета дня ' +
      'прибавила <span class="n">' + pct(M.maxChange, 0) + '</span>, и дальше ' +
      'плюс двадцати ' +
      plural(M.tail || 0, 'ушла', 'ушли', 'ушло') +
      ' всего <span class="n">' + (M.tail || 0) + '</span> ' +
      plural(M.tail || 0, 'монета', 'монеты', 'монет') +
      ' — при живом рынке их бывают десятки. Ехать сегодня некуда.',
      'рынок', 'замер · ' + (M.tail || 0),
      {t:'ticks', on: Math.min(7, M.tail || 0), all: 7, tone: 'dn'});
  } else {
    bgPush('Рынок <span class="gd">двигается</span>. Лучшая монета дня ' +
      '<span class="n">' + pct(M.maxChange, 0) + '</span>, дальше плюс ' +
      'двадцати ' + plural(M.tail || 0, 'ушла', 'ушли', 'ушло') +
      ' <span class="n">' + (M.tail || 0) + '</span> ' +
      plural(M.tail || 0, 'монета', 'монеты', 'монет') +
      ' — движение широкое, а не один выброс.',
      'рынок', 'двигается · ' + (M.tail || 0),
      {t:'ticks', on: Math.min(7, M.tail || 0), all: 7});
  }
  if (M.peakVol && M.peakVol.sym) {
    bgPush('Деньги в рынке ' + (M.frozen ? 'при этом ' : '') +
      'есть: максимум объёма на <span class="gd">' + M.peakVol.sym +
      '</span>, <span class="n">×' + M.peakVol.x + '</span> к своей норме.',
      'деньги', M.peakVol.sym + ' ×' + M.peakVol.x, null);
  }
  var gs = M.greenShare;
  if (gs !== null && gs !== undefined) {
    bgPush('В плюсе <span class="n">' + Math.round(gs) + '%</span> выборки' +
      (gs >= 55 ? ', растёт почти весь рынок.'
       : gs <= 42 ? ', то есть падает большинство.'
       : ', рынок разделился примерно поровну.'),
      'в плюсе', Math.round(gs) + '% выборки',
      {t:'fill', pct: gs, mark: 50});
  }
  if (M.btc !== null && M.btc !== undefined) {
    /* btcTail, а НЕ tail: имя tail уже занято функцией показа подвала
       ниже, а var поднимается на всю область — строка затеняла функцию,
       и tail() в конце падал (в ветке без анимации) или молча
       игнорировался промисом (в обычной): подпись «клик в любом месте»
       и полоса прогресса не включались вовсе. Столкновение жило здесь
       до строки разрешения и вскрылось её проверкой. */
    var btcTail = '.';
    var dom = parseFloat(M.dom);
    if (M.btc7d <= -1.5 && dom >= 57) {
      btcTail = ' — деньги уходят из риска, альтам ничего не достаётся.';
    } else if (M.btc7d <= -1.5 && dom < 57) {
      btcTail = ' — падают вместе: биткоин без роста доминации, альтам ' +
        'спрятаться некуда.';
    } else if (M.btc7d >= 1.5 && dom < 56) {
      btcTail = ' — биткоин растёт, а доминация сдаёт: окно для альтов.';
    } else if (M.btc7d >= 1.5 && dom >= 56) {
      btcTail = ' — биткоин растёт и тянет доминацию за собой: деньги идут ' +
        'в рынок широко, а не утекают из альтов.';
    } else if (Math.abs(M.btc7d) < 1.5) {
      btcTail = ' — за неделю почти без движения.';
    }
    bgPush('Биткоин ' + (M.btc >= 0 ? 'прибавил' : 'потерял') + ' ' +
      '<span class="' + sgn(M.btc) + ' n">' + Math.abs(M.btc).toFixed(1) +
      '%</span> за сутки, за неделю <span class="' + sgn(M.btc7d) + ' n">' +
      pct(M.btc7d) + '</span>, доминация <span class="n">' +
      (isFinite(parseFloat(M.dom)) ? parseFloat(M.dom).toFixed(1) + '%' : '—') +
      '</span>' + btcTail,
      'биткоин',
      (M.btc >= 0 ? '+' : '') + Math.abs(M.btc).toFixed(1) + '%' +
        (isFinite(parseFloat(M.dom)) ? ' · ' + parseFloat(M.dom).toFixed(1) + '%' : ''),
      isFinite(parseFloat(M.dom)) ? {t:'fill', pct: parseFloat(M.dom), mark: 50} : null);
  }
  function sgn(v) { return v > 0 ? 'up' : (v < 0 ? 'dn' : ''); }

  /* ── Сводка счетов (Р-29/Р-30) ──
     Один источник про деньги — analytics_portfolio, словарь
     M.portfolios. Прежняя строка «по тысяче в каждую» читала второй
     расчёт из журнала лидеров (J.port); он снят 23.08 — два
     источника одной истины разошлись бы.

     Два подхода к ОДНИМ монетам. HOLD — попал в журнал, взял,
     держу, правил нет. Трейдинг — те же монеты по правилам, книга
     начинается пустой. Разница между ними — цена стратегии, и
     печатается она только когда есть что судить: после десяти
     сделок, как условлено. */
  var PF = M.portfolios || {};
  var PH = PF.hold || {}, PT = PF.trade || {};

  var portLine = [];
  if (PH.invested || PT.trades) {
    var txt = 'HOLD: <span class="n">' + (PH.open || 0) + '</span> позиций на <b>' +
      fmtMoney(PH.invested || 0) + '</b>, <b class="' + sgn(PH.pnlPct) + '">' +
      signed(PH.pnlPct || 0) + '</b> — взял и держу. Трейдинг: ';
    if (PT.open) {
      txt += '<span class="n">' + PT.open + '</span> на <b>' +
        fmtMoney(PT.invested) + '</b>, <b class="' + sgn(PT.pnlPct) + '">' +
        signed(PT.pnlPct || 0) + '</b> по правилам.';
    } else if (PT.trades) {
      txt += 'позиций нет, зафиксировано <b class="' + sgn(PT.realized) +
        '">' + fmtMoney(PT.realized) + '</b> за ' + PT.trades + ' сделок.';
    } else {
      txt += '<span class="mut">книга пуста — правила ещё не входили.</span>';
    }
    if (PT.trades >= 10 && PT.pnlPct !== null && PT.pnlPct !== undefined &&
        PH.pnlPct !== null && PH.pnlPct !== undefined) {
      var dpp = PT.pnlPct - PH.pnlPct;
      /* Пункты, не проценты: signed() дописал бы «%», и единица
         задвоилась бы — «−4.0% п.п.» читается как опечатка. */
      txt += ' Разница <b class="' + sgn(dpp) + '">' +
        (dpp >= 0 ? '+' : '') + dpp.toFixed(1) +
        ' п.п.</b> — трейдинг минус HOLD, цена стратегии.';
    } else if (PT.trades > 0 && PH.invested) {
      /* Разница — единственное, ради чего оба счёта ведутся, но на
         горстке сделок она ничего не значит, и это сказано прямо. */
      txt += ' <span class="mut">Сделок пока мало — разницу не читать.</span>';
    }
    /* Потолок находок — не украшение, а мера того, сколько стоит
       отсутствие правила выхода: разрыв между «держали до сих пор»
       и «зафиксировали в лучшей точке каждой позиции». */
    if (PF.peakPct !== undefined && PF.peakPct !== null) {
      txt += ' Потолок находок <b class="up">' + signed(PF.peakPct) +
        '</b> <span class="mut">— столько стоит отсутствие выхода.</span>';
    }
    portLine = [txt];
  }

  var lossLine = (PF.losers || []).length
    ? ['Разобрать: ' + PF.losers.map(function (d) {
        return '<span class="t">' + d.t + '</span> <b class="dn">' +
          signed(d.chg) + '</b> <span class="mut">' + (d.case || '?') + ', ' +
          (d.at || '').slice(5) + '</span>'; }).join(', ') + '.']
    : [];

  var LC = M.leaderChart || {}, VC = M.volChart || {};

  /* Нормировка ряда к [-1,1] — тот же приём, что и в прототипе, но
     теперь на настоящих числах: LC.series (цена лидера потока) и
     VC.ratios (кратности объёма по дням), а не случайное блуждание. */
  function normPts(arr) {
    var lo = Math.min.apply(null, arr), hi = Math.max.apply(null, arr);
    var span = (hi-lo) || 1;
    return arr.map(function (v) { return ((v-lo)/span)*2 - 1; });
  }

  var leaderSeg = (L.t && (LC.series || []).length >= 4)
    ? { html: 'лидер потока — <span class="t">' + L.t + '</span>' + cap(L) +
             ', фигура <span class="gd">' + (LC.case || '—') + '</span>' +
             (LC.horizonDays ? ', горизонт <span class="n">' + LC.horizonDays +
               '</span> дн' : '') +
             ', скор <span class="n">' + (LC.score || 0) + '</span>.',
        pts: normPts(LC.series),
        tag: L.t + ' ' + (LC.score || 0),
        glyph: {t:'ring', pct: (LC.score || 0)} }
    : null;

  var volSeg = ((VC.ratios || []).length >= 4)
    ? { html: 'максимум объёма — <span class="t">' + VC.sym + '</span>' +
             cap(VC) + ', <span class="n">×' + VC.x + '</span> к своей норме ' +
             'за 30 дней.',
        pts: normPts(VC.ratios),
        tag: VC.sym + ' ×' + VC.x,
        glyph: {t:'dev', val: 1, max: 1} }
    : null;

  /* Р-6: при закрытом окне список НЕ пустеет и не переупорядочивается
     — меняется только подпись: те же монеты, но как наблюдение, а не
     входы. Порог «две независимые причины» — правило ПОКАЗА, живёт
     здесь и в скор не проникает; одна причина (например, просто
     выходные) окно не закрывает — у неё есть своя строка. */
  var gateClosed = (P.warnCount || 0) >= 2;
  var goHead = gateClosed
    ? '<span class="warn">Окно закрыто</span> — список наблюдения, не входов: '
    : 'Рассмотреть стоит (первая фаза, у дна): ';
  var goLine = go.length
    ? goHead +
      go.slice(0, 3).map(function (s) {
        return '<span class="t">' + s.t + '</span>' + cap(s); }).join(', ') + '.'
    : '<span class="mut">Сегодня брать нечего.</span>';

  var dormLine = DORM.length
    ? 'Спят ' + DORM.map(function (d) {
        return '<span class="t dorm">' + d.t + '</span>' +
          (d.cap ? ' <span class="obf-cap">' + d.cap + '</span>' : ''); })
        .join(', ') + ' — <span class="dorm">цикл был, база узкая</span>. ' +
        'Движения ещё нет: наблюдать, не входить.'
    : '';

  var waitLine = wait.length
    ? 'Ждут сигнала ' + wait.slice(0, 3).map(function (s) {
        return '<span class="t">' + s.t + '</span>' + cap(s) +
          ' <span class="mut">— ' + waitWhy(s) + '</span>'; })
        .join(' <span class="obf-sep">·</span> ') + '.'
    : '';

  var bigVolT = {};
  bigVolAll.forEach(function (v) { bigVolT[v.t] = true; });

  var holdLine = hold.length
    ? 'В работе ' + hold.slice(0, 3).map(function (s) {
        return '<span class="t gd">' + s.t + '</span>' + cap(s) +
          ' <span class="n">' + (s.up >= 0 ? '+' : '') + s.up + '%</span> за ' +
          (s.days || 0) + ' дн' +
          (bigVolT[s.t] ? ' <span class="up">· объём</span>' : '');
      }).join(', ') + '.'
    : '';

  var nearLine = near.length
    ? 'У уровня ' + near.map(function (s) {
        return '<span class="t">' + s.t + '</span>' + cap(s) +
          ' <span class="dn n">−' + toStop(s) + '%</span>'; }).join(', ') +
      ' — решаются сегодня.'
    : '';

  var journalLine = J.n
    ? 'Журнал: <b>' + J.n + '</b> ' + plural(J.n, 'монета', 'монеты', 'монет') +
      (J.fresh && J.fresh.length
        ? ', новых этим прогоном — <b>' + J.fresh.join(', ') + '</b>' : '') +
      '. Лучший ход от входа <b class="up">' + J.best.t + ' ' +
      (J.best.chg >= 0 ? '+' : '') + J.best.chg + '%</b>' +
      (J.worst.t !== J.best.t
        ? ', худший <b class="dn">' + J.worst.t + ' ' +
          (J.worst.chg >= 0 ? '+' : '') + J.worst.chg + '%</b>'
        : '') + '.'
    : '';

  var bigVolLine = bigVol.length
    ? 'Аномалия объёма ×30+ у ' + bigVol.map(function (v) {
        return '<span class="t">' + v.t + '</span>' + cap(v) +
          ' <span class="n">×' + v.x + '</span>'; }).join(', ') + '.'
    : '';

  var hrLine = HR.list.length
    ? 'За час ожили <span class="n">' + HR.n + '</span>: ' +
      HR.list.map(function (v) {
        return '<span class="t">' + v.t + '</span>' + cap(v) +
          ' <span class="n">×' + v.x + '</span>'; }).join(', ') + '.'
    : '';

  /* Порядок строк — тот же, что и раньше: портфель и разбор убытков
     сразу (это про то, чего стоят находки), потом фон рынка, потом
     лидер потока с графиком, аномалии объёма, максимум объёма с
     графиком, часовая активность, отбор, спячка, ожидание, работа,
     уровни, журнал. */
  /* ═══ Закрывающий сегмент ═══
     Он остаётся на экране до клика (см. LAST_HOLD), поэтому говорит
     про РЕШЕНИЕ, а не повторяет числа начала. Открывающая строка
     отвечает «что с рынком», эта — «с чем я остаюсь»: сколько ставить
     и чего ждать. Ступень размера и ближайшая дата иначе видны только
     в карточке зала, то есть их надо искать — а это самые действенные
     величины дня. */
  /* ═══ Два счёта (Р-29) ═══
     HOLD — попал в лидеры, взял на $1000, держу; правила не
     применяются. Трейдинг — те же монеты по правилам, со своими
     входами и выходами. Считаны на ОДНИХ ценах, поэтому разница между
     ними читается прямо: стоило ли торговать то, что можно было
     просто держать. Пустой счёт не печатается вовсе — «правила ещё не
     сделали ни одной сделки» и «ноль долларов» разные утверждения. */
  var PF = M.portfolios || {};
  /* Сегмент счетов ЗВУЧАЛ ДВАЖДЫ: ранняя строка (второй в
     очереди, сразу после окна рынка) и поздний acctLine перед
     итогом — два рассказа об одном и два места «счета» в фигуре.
     Поздний снят вместе со своими помощниками (money/acct):
     деньги должны звучать один раз и рано, пока внимание свежее;
     его формулировка про малое число сделок перенесена в раннюю
     строку. */

  var closeLine = '';
  (function () {
    var pp2 = (M.permission || {}).parts || {};
    var cal2 = (pp2.calendar || {}).items || [];
    var bits = [];
    if ((M.permission || {}).knownCount)
      bits.push('окно рынка <span class="n">' +
        ((M.permission || {}).warnCount || 0) + ' из ' +
        (M.permission || {}).knownCount + '</span>');
    /* Ступень берётся у ЛИДЕРА потока: размер — свойство монеты, и
       усреднять его по журналу нельзя. Нет лидера — нет строки. */
    var lead2 = null;
    for (var q=0;q<STARS.length;q++) if (STARS[q].lead) { lead2 = STARS[q]; break; }
    if (lead2 && lead2.size && lead2.size.tier)
      bits.push('размер по правилу — <span class="gd">' +
        lead2.size.tier + '</span>');
    if (cal2.length){
      var ev = cal2[0];
      bits.push(ev.title + (ev.running ? ' идёт'
        : ' через <span class="n">' + ev.days + '</span> дн'));
    }
    if (bits.length)
      closeLine = 'Итог: ' + bits.join(', ') + '.' +
        (((M.permission || {}).warnCount || 0) >= 2
          ? ' <span class="mut">Список наблюдения, не входов.</span>' : '');
  })();

  /* Ярлыки и глифы — только тем сегментам, у которых есть короткое
     честное значение. Остальные проговариваются и уходят: держать на
     экране «деньги в рынке есть» без числа незачем. */
  var permSeg = permLine ? tagSeg({html: permLine}, 'окно рынка',
        ((M.permission || {}).warnCount || 0) + ' из ' +
        ((M.permission || {}).knownCount || 0),
        {t:'ticks', on:((M.permission || {}).warnCount || 0),
         all:((M.permission || {}).knownCount || 0), tone:'dn'}) : null;

  var closeSeg = closeLine ? tagSeg({html: closeLine}, 'итог',
      (((M.permission || {}).warnCount || 0) >= 2 ? 'наблюдение' : 'можно'),
      null) : null;

  /* В фигуру идут ВСЕ сегменты, у которых есть короткое честное
     значение. Пустые списки строк не дают вовсе, поэтому фигура сама
     подстраивается под день: в тихий соберётся шесть строк, в живой —
     двенадцать. */
  function T(line, k, v, g){
    return line ? [tagSeg({html: line}, k, v, g)] : [];
  }
  var AS2 = M.altShare || {};
  var rsv2 = ((M.permission || {}).parts || {}).reservoir || {};

  /* Альт-доля и резервуар проговариваются хвостами строки разрешения,
     но в фигуре им нужно СВОЁ место: это числа месячного горизонта, и
     терять их вместе с текстом жаль. Отдельного сегмента у них нет —
     значит, и текста в центре они не займут: пустой html просто не
     показывается, а строка в фигуре появляется. */
  var altSeg = (AS2.d7 !== undefined && AS2.d7 !== null)
    ? tagSeg({html: ''}, 'альты к btc', AS2.d7 + '% за 7д',
             {t:'fill', pct: AS2.d7, mark: 50})
    : null;
  var rsvSeg = (rsv2.known && rsv2.share !== undefined && rsv2.share !== null)
    ? tagSeg({html: ''}, 'резервуар', rsv2.share + '% капы',
             {t:'fill', pct: rsv2.share, mark: 13, scale: 20, tone: 'gd'})
    : null;

  var raw = (permSeg ? [permSeg] : [])
    .concat(T(portLine, 'счета',
      (PH.invested ? fmtMoney(PH.invested) : ''), null))
    .concat(T(lossLine, 'разобрать',
      ((PF.losers || []).length || '') + '', null))
    .concat(bg)
    .concat(wknd ? [tagSeg({html: wknd}, 'выходные', 'тонкий стакан', null)] : [])
    .concat([leaderSeg ? tagSeg(leaderSeg, 'лидер', leaderSeg.tag,
             leaderSeg.glyph) : leaderSeg])
    .concat(T(bigVolLine, 'аномалия', bigVol.length + ' монет',
      {t:'ticks', on: Math.min(7, bigVol.length), all: 7}))
    .concat([volSeg ? tagSeg(volSeg, 'объём', volSeg.tag, volSeg.glyph) : volSeg])
    .concat(T(hrLine, 'за час', HR.n + ' ожили', null))
    .concat([tagSeg({html: goLine}, 'брать',
      go.length ? go.length + ' монет' : 'нечего',
      {t:'ticks', on: Math.min(7, go.length), all: 7,
       tone: go.length ? '' : 'dn'})])
    .concat(T(dormLine, 'спят', DORM.length + '', null))
    .concat(T(waitLine, 'ждут сигнала', wait.length + '', null))
    .concat(T(holdLine, 'в работе', hold.length + '', null))
    .concat(T(nearLine, 'у уровня', near.length + '', null))
    .concat(T(journalLine, 'журнал', (J.n || 0) + '', null))
    .concat(altSeg ? [altSeg] : [])
    .concat(rsvSeg ? [rsvSeg] : [])
    .concat(closeSeg ? [closeSeg] : []);

  /* Приводим всё к единому виду {html, pts, accent}: строки-строки
     оборачиваются как есть (это уже готовая цветная разметка),
     leaderSeg/volSeg уже несут и html, и pts. */
  var SEGMENTS = raw.filter(Boolean).map(function (item, i) {
    var seg = (typeof item === 'string') ? { html: item } : item;
    seg.accent = BLOCK_ACCENTS[i % BLOCK_ACCENTS.length];
    return seg;
  });

  /* ═══ Что от сегмента остаётся в фигуре ═══
     Ярлык и число задаются ЯВНО, а не выдираются из готовой фразы:
     разбор своего же текста регулярками сломается на первой правке
     формулировки, и сломается молча. Сегменты без пары ярлык-значение
     просто не садятся в фигуру — это нормально, не всё стоит держать
     на экране до конца.
     Глиф — шкала своей величины, а не значок: одинаковая иконка у
     восьми чисел обещала бы смысл, которого нет. */
  function tagSeg(seg, k, v, g){
    if (!seg) return seg;
    seg.k = k; seg.v = v; seg.g = g || null;
    return seg;
  }

  if (!SEGMENTS.length) return;

  /* Сколько строк соберётся в фигуре — известно до начала показа:
     это сегменты с ярлыком и значением. Знать заранее обязательно,
     иначе шаг по вертикали пришлось бы пересчитывать на каждой новой
     строке, и фигура ползала бы всю сводку. */
  FIG_TOTAL = Math.min(FIG_SLOTS,
    SEGMENTS.filter(function (x) { return x.k && x.v; }).length);

  /* Последний ВИДИМЫЙ сегмент, а не последний в списке. Сегменты без
     текста (альт-доля, резервуар) садятся в фигуру мгновенно и стоят
     в конце — из-за них «last» приходился на невидимую запись, тридцать
     секунд ожидания доставались ей, а настоящий финальный текст гас
     через обычные четыре. Именно это и выглядело как «исчезает сразу». */
  var LAST_SHOW = -1;
  for (var li = SEGMENTS.length - 1; li >= 0; li--) {
    if (SEGMENTS[li].html) { LAST_SHOW = li; break; }
  }

  function tail() {
    document.getElementById('obfFoot').classList.add('on');
    document.getElementById('obfBar').classList.add('on');
  }

  var reduce = window.matchMedia('(prefers-reduced-motion:reduce)').matches;

  resizeScene();
  if (reduce) {
    // Без анимации: последняя строка выводится статично сразу — сама
    // сцена (кольцо/дюна) достаточно тиха, чтобы не требовать полного
    // отключения, но набор текста и полёт частиц не идут.
    txtEl.textContent = stripTags(SEGMENTS[SEGMENTS.length - 1].html);
    txtEl.style.opacity = '1';
    tail();
  } else {
    requestAnimationFrame(frame);
    setTimeout(function () {
      playAll().then(function () {
        tail();
        /* Переход — по СОБЫТИЮ «очередь доиграла», а не по
           секундомеру. Финальный сегмент уже отстоял свои полминуты
           (или получил клик), фигуре — мгновение на прочтение, и
           экран отдаётся оболочке. */
        setTimeout(close, 1400);
      });
    }, 500);
  }

  wrap.style.setProperty('--lap', (BRIEF_LAP / 1000) + 's');
  requestAnimationFrame(function () { wrap.classList.add('on'); });

  /* ── Выход ──
     Сводка больше не «закрывается», оставаясь в документе: документ и
     есть сводка. Она сообщает оболочке, что доиграла, и оболочка
     уничтожает этот документ вместе со сценой, таймерами и кадрами —
     останавливать что-либо руками не нужно и нечего забыть.

     Куда переходить, сводка не говорит: очередь экранов знает
     оболочка. Раньше преемник (зал) сам следил за классом .on на этом
     узле через MutationObserver — то есть знал и о существовании
     сводки, и о её разметке.

     Класс .on снимается всё равно: между сообщением и сменой
     документа проходит кадр-другой, и без затухания это выглядело бы
     обрывом. */
  var doneSent = false;
  function close() {
    clearTimeout(closeTimer);
    wrap.classList.remove('on');
    if (doneSent) return;           // клик по уже уходящему экрану
    doneSent = true;
    try {
      window.parent.postMessage(
        { type: 'ob:done', screen: 'brief' }, window.location.origin);
    } catch (e) { /* открыт вне оболочки — просто гаснем */ }
  }

  /* ПРЕДОХРАНИТЕЛЬ, а не расписание. Прежде здесь стоял выход по
     BRIEF_LAP — кругу СТАРОЙ сводки на восемь фраз: очередь с двумя
     крыльями выросла до ~16 сегментов и трёх минут, а таймер остался
     на 105 секундах и резал показ на восьмом-девятом сегменте —
     всегда в одном месте и без финальных тридцати секунд. Снаружи
     это выглядело «после объёма всё вылетает». Теперь выход зовёт
     сама очередь (playAll().then выше); таймер оставлен страховкой
     на случай, если очередь встала бы намертво, — с запасом на самый
     длинный сценарий. При reduced-motion очереди нет — там прежний
     круг. */
  var closeBudget = reduce ? BRIEF_LAP
      : SEGMENTS.length * (HOLD_MS + 9000) + LAST_HOLD_MS + 20000;
  var closeTimer = setTimeout(close, closeBudget);
  wrap.addEventListener('click', close);
  document.addEventListener('keydown', function () {
    if (wrap.classList.contains('on')) close();
  });
})();
</script>
"""
