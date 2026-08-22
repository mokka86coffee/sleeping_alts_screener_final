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
  @media (prefers-reduced-motion:reduce){
    #obfText .ch{transition:none; opacity:1; filter:none; transform:none;}
  }
</style>
<div class="ob-brief" id="obBrief">
  <canvas id="obfCanvas"></canvas>
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

  var ringGeo = null, ringDust = [], duneDust = [];

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
    var placed = 0, tries = 0;
    while (placed < 3000 && tries < 60000){
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
    for (var i=0;i<11000;i++){
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
  }

  function resizeScene(){
    canvas.width = w()*devicePixelRatio; canvas.height = h()*devicePixelRatio;
    canvas.style.width = w()+'px'; canvas.style.height = h()+'px';
    ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
    buildAmbient();
  }
  window.addEventListener('resize', resizeScene);

  function drawAmbient(t){
    var g = ctx.createRadialGradient(w()*0.5, ringGeo.cy, 10, w()*0.5, ringGeo.cy, w()*0.35);
    g.addColorStop(0, 'rgba(200,200,215,.10)'); g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g; ctx.fillRect(0,0,w(),h());

    var p, flick, dx, dy;
    for (var i=0;i<duneDust.length;i++){
      p = duneDust[i];
      flick = 0.5+0.5*Math.sin(t*0.0009*p.speed+p.tw);
      dx = Math.sin(t*0.0004+p.driftPhase)*p.driftAmp;
      dy = Math.cos(t*0.00035+p.driftPhase)*p.driftAmp*0.6;
      p.x = p.x0+dx; p.y = p.y0+dy;
      ctx.globalAlpha = p.base * (0.35+flick*0.65);
      ctx.fillStyle = p.warm ? '#D9A15E' : '#9a8a78';
      ctx.beginPath(); ctx.arc(p.x,p.y,p.r,0,Math.PI*2); ctx.fill();
    }
    var spin = t*0.000045;
    for (var j=0;j<ringDust.length;j++){
      p = ringDust[j];
      flick = 0.5+0.5*Math.sin(t*0.0009*p.speed+p.tw);
      var drift = Math.sin(t*0.0006+p.driftPhase)*p.driftAmp;
      var aa = p.a+spin;
      var px = Math.cos(aa)*(p.rx+p.jitter+drift), py = Math.sin(aa)*(p.ry+p.jitter+drift);
      var rx2 = px*Math.cos(p.rot)-py*Math.sin(p.rot), ry2 = px*Math.sin(p.rot)+py*Math.cos(p.rot);
      ctx.globalAlpha = p.a0*(0.45+flick*0.55)*0.85;
      ctx.fillStyle = '#dfe6ec';
      ctx.beginPath(); ctx.arc(p.cx+rx2,p.cy+ry2,p.r,0,Math.PI*2); ctx.fill();
    }
    for (var k=0;k<duneDust.length;k++){
      p = duneDust[k];
      if (p.y < h()*0.62-((RING_SCALE-1)*70) || p.y > h()*0.685) continue;
      flick = 0.5+0.5*Math.sin(t*0.0009*p.speed+p.tw);
      ctx.globalAlpha = p.base * (0.3+flick*0.4);
      ctx.fillStyle = p.warm ? '#D9A15E' : '#9a8a78';
      ctx.beginPath(); ctx.arc(p.x,p.y,p.r,0,Math.PI*2); ctx.fill();
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
    ctx.shadowColor = accent;
    ctx.shadowBlur = 6;

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
    ctx.strokeStyle = accent; ctx.lineWidth = 1.2;
    ctx.globalAlpha = alpha*0.9;
    ctx.stroke();

    path.forEach(function (pt, i) {
      if (i > fullSeg) return;
      ctx.beginPath();
      ctx.arc(pt[0], pt[1], 1.4, 0, Math.PI*2);
      ctx.fillStyle = accent;
      ctx.globalAlpha = alpha*0.7;
      ctx.fill();
    });

    ctx.shadowBlur = 0;
    ctx.restore();
    ctx.globalAlpha = 1;
  }

  function frame(t){
    ctx.clearRect(0,0,w(),h());
    drawAmbient(t);

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
  var BLOCK_ACCENTS = ['#7FB4FF', '#F5A623', '#6FE3B4', '#FFD98A', '#E89AB0'];

  var runToken = 0, running = false;

  function showSegment(idx, token){
    return new Promise(function (resolve) {
      var seg = SEGMENTS[idx];
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

      setTimeout(function () {
        if (token !== runToken) return;
        var chs = txtEl.querySelectorAll('.ch');
        for (var i=0;i<chs.length;i++){
          chs[i].style.transitionDelay = '0ms';
          chs[i].classList.remove('on');
        }
        if (seg.pts){ diagramPhase = 'out'; diagramT0 = performance.now(); }
        setTimeout(function () { if (token === runToken) resolve(); }, 550);
      }, revealDur + hold);
    });
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
    var n = +v || 0;
    return n >= 10000 ? '$' + (n / 1000).toFixed(1) + 'K' : '$' + Math.round(n);
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
    var reasons = [];
    if ((pp.btc || {}).warn)
      reasons.push('рывок биткоина — окно каскада');
    if ((pp.funding || {}).warn)
      reasons.push('толпа в лонге, фандинг положителен у ' +
        Math.round(((pp.funding || {}).posShare || 0) * 100) + '%');
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
    permLine = head + (reasons.length ? ': ' + reasons.join('; ') : '') +
      '.' + fuelTail + altTail;
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
  var bg = [];
  if (M.frozen) {
    bg.push('Рынок сейчас <span class="warn">замер</span>. Лучшая монета дня ' +
      'прибавила <span class="n">' + pct(M.maxChange, 0) + '</span>, и дальше ' +
      'плюс двадцати ушли всего <span class="n">' + (M.tail || 0) + '</span> ' +
      plural(M.tail || 0, 'монета', 'монеты', 'монет') +
      ' — при живом рынке их бывают десятки. Ехать сегодня некуда.');
  } else {
    bg.push('Рынок <span class="gd">двигается</span>. Лучшая монета дня ' +
      '<span class="n">' + pct(M.maxChange, 0) + '</span>, дальше плюс ' +
      'двадцати ушли <span class="n">' + (M.tail || 0) + '</span> ' +
      plural(M.tail || 0, 'монета', 'монеты', 'монет') +
      ' — движение широкое, а не один выброс.');
  }
  if (M.peakVol && M.peakVol.sym) {
    bg.push('Деньги в рынке ' + (M.frozen ? 'при этом ' : '') +
      'есть: максимум объёма на <span class="gd">' + M.peakVol.sym +
      '</span>, <span class="n">×' + M.peakVol.x + '</span> к своей норме.');
  }
  var gs = M.greenShare;
  if (gs !== null && gs !== undefined) {
    bg.push('В плюсе <span class="n">' + Math.round(gs) + '%</span> выборки' +
      (gs >= 55 ? ', растёт почти весь рынок.'
       : gs <= 42 ? ', то есть падает большинство.'
       : ', рынок разделился примерно поровну.'));
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
    bg.push('Биткоин ' + (M.btc >= 0 ? 'прибавил' : 'потерял') + ' ' +
      '<span class="' + sgn(M.btc) + ' n">' + Math.abs(M.btc).toFixed(1) +
      '%</span> за сутки, за неделю <span class="' + sgn(M.btc7d) + ' n">' +
      pct(M.btc7d) + '</span>, доминация <span class="n">' + (M.dom || '—') +
      '</span>' + btcTail);
  }
  function sgn(v) { return v > 0 ? 'up' : (v < 0 ? 'dn' : ''); }

  var portLine = (J.port && J.port.invested)
    ? ['По тысяче в каждую: <b>' + fmtMoney(J.port.value) + '</b> из ' +
       fmtMoney(J.port.invested) + ', <b class="' +
       (J.port.pnl_pct >= 0 ? 'up' : 'dn') + '">' + signed(J.port.pnl_pct) +
       '</b>' + (J.port.rules_pnl_pct !== undefined
         ? ', по правилам <b class="' +
           (J.port.rules_pnl_pct >= 0 ? 'up' : 'dn') + '">' +
           signed(J.port.rules_pnl_pct) + '</b>' : '') +
       '. По максимумам вышло бы <b class="up">' + signed(J.port.peak_pct) +
       '</b>.']
    : [];

  var lossLine = (J.port && (J.port.losers || []).length)
    ? ['Разобрать: ' + J.port.losers.map(function (d) {
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
        pts: normPts(LC.series) }
    : null;

  var volSeg = ((VC.ratios || []).length >= 4)
    ? { html: 'максимум объёма — <span class="t">' + VC.sym + '</span>' +
             cap(VC) + ', <span class="n">×' + VC.x + '</span> к своей норме ' +
             'за 30 дней.',
        pts: normPts(VC.ratios) }
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
  var raw = (permLine ? [permLine] : [])
    .concat(portLine).concat(lossLine).concat(bg)
    .concat(wknd ? [wknd] : [])
    .concat([leaderSeg])
    .concat(bigVolLine ? [bigVolLine] : [])
    .concat([volSeg])
    .concat(hrLine ? [hrLine] : [])
    .concat([goLine])
    .concat(dormLine ? [dormLine] : [])
    .concat(waitLine ? [waitLine] : [])
    .concat(holdLine ? [holdLine] : [])
    .concat(nearLine ? [nearLine] : [])
    .concat(journalLine ? [journalLine] : []);

  /* Приводим всё к единому виду {html, pts, accent}: строки-строки
     оборачиваются как есть (это уже готовая цветная разметка),
     leaderSeg/volSeg уже несут и html, и pts. */
  var SEGMENTS = raw.filter(Boolean).map(function (item, i) {
    var seg = (typeof item === 'string') ? { html: item } : item;
    seg.accent = BLOCK_ACCENTS[i % BLOCK_ACCENTS.length];
    return seg;
  });

  if (!SEGMENTS.length) return;

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
    setTimeout(function () { playAll().then(tail); }, 500);
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

  var closeTimer = setTimeout(close, BRIEF_LAP);
  wrap.addEventListener('click', close);
  document.addEventListener('keydown', function () {
    if (wrap.classList.contains('on')) close();
  });
})();
</script>
"""
