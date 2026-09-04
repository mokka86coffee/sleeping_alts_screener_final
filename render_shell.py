"""Оболочка отчёта · единственный документ, который никогда не уходит.

Что это. Крошечная страница, в которой нет ни одного экрана: только
лоадер и пустой <iframe>. Экраны (дашборд, сводка, зал) — отдельные
самостоятельные HTML-файлы, они грузятся ВНУТРЬ этого iframe по
очереди. Смена экрана = смена содержимого iframe, при которой браузер
уничтожает предыдущий документ целиком.

Почему так, а не переключение видимости внутри одной страницы.

  1. CSS и JS каждого экрана заперты в своём документе. У iframe своя
     таблица стилей и своя область видимости скрипта: .ob-brief и
     #dash могли бы называться одинаково в разных экранах и не
     столкнуться никогда. Ту связанность на именах классов, из-за
     которой затевался диспетчер экранов, здесь нельзя допустить даже
     нарочно — не «мы договорились аккуратно её избегать», а
     структурно невозможно.

  2. Остановка чужого JS достаётся бесплатно и гарантированно.
     Раньше требовалось помнить про stopScene(), сбрасывать
     requestAnimationFrame, не забыть таймеры. Уничтоженный документ
     не может забыть остановиться. Поэтому здесь iframe не
     переиспользуется: старый элемент удаляется из DOM, и только
     потом создаётся новый (см. switchScreen ниже).

  3. Искать тормоза негде, кроме одного места. Тормозит — открываете
     девтулы и смотрите ровно тот документ, что сейчас в iframe.

Почему postMessage, а не window.parent напрямую. Экран и оболочка
лежат на одном источнике, и прямой вызов сработал бы сегодня. Но
политики изоляции окон (COOP/COEP и родственные) всё активнее режут
доступ к window.parent по умолчанию, и отвалиться это может молча, в
какой-то будущей версии браузера, без единого предупреждения.
postMessage с явной проверкой origin переживёт это ужесточение.

Лоадер — кристалл на поле зала. Сводка стала схемой в языке зала
(render_scheme, 26.08): та же синь с куполом света, тот же кристалл в
центре, те же моноширинные подписи. Лоадер повторяет её начало — тот же
октаэдр, тот же тихий синий ореол, — и переход из лоадера в сводку
читается как продолжение одного кадра, а не как смена приложения. До
этого лоадер был светло-серым под белый лист прежней сводки, а ещё
раньше — пульсирующей звездой на чёрном.

Оформление и логика показа не связаны: чтобы поменять вид, достаточно
содержимого #obShellLoader и его стилей, MIN_SHOW_MS к нему не привязан.

Подпись под кристаллом называет экран, который грузится: лоадер —
проход, и проход говорит, куда ведёт. Имена берутся из SCREEN_NAMES.
"""

from __future__ import annotations

import json

# Экраны, которые оболочке разрешено грузить. Список ведётся здесь и
# отсюда же попадает в JS: белый список в браузере не должен
# расходиться с набором файлов, которые реально пишет run.py.
#
# Имя = имя файла без расширения: "dashboard" → "dashboard.html".
SCREENS = ("dashboard", "brief", "podium", "coin")

# Экран, с которого начинается отчёт.
START_SCREEN = "brief"

# Что показывать после того, как экран доиграл сам себя. Экран,
# которого здесь нет, — конечный: доиграв, он просто остаётся.
#
# Последовательность живёт ЗДЕСЬ, а не внутри экранов, и это главное
# отличие от прежней схемы. Раньше зал сам следил за сводкой через
# MutationObserver: ждал, когда с чужого узла снимется класс .on, и
# запускался через 560 мс после этого. Работало, но означало, что зал
# знает о существовании сводки, о её разметке и о том, каким классом
# она отмечает своё состояние. Теперь экран сообщает только «я
# закончил» и не знает, кто идёт следом и идёт ли вообще.
SEQUENCE = {
    "brief": "coin",        # 05.09: после сводки — экран монеты; в зал ведёт золотой узел в шапке сводки
    "podium": "dashboard",
}

# Как экран называется в подписи лоадера. Экран без имени подписи не
# получает — лоадер покажет одну звезду.
SCREEN_NAMES = {
    "brief": "сводка",
    "podium": "зал",
    "coin": "монета",
    "dashboard": "дашборд",
}

# Сколько лоадер висит минимум. Без нижней границы лоадер, мелькнувший
# на сорок миллисекунд при переходе на закешированный экран, читается
# как дефект отрисовки, а не как загрузка.
#
# 700, а не 350: на живых экранах переход выглядел скачком. Затухание
# занимает 350 мс само по себе, то есть при прежнем пороге лоадер
# начинал гаснуть ровно тогда, когда закончил появляться, и стадии
# «висит» не было вовсе — глаз читал это как рывок, а не как паузу.
MIN_SHOW_MS = 700

# Предохранитель: если экран не догрузился (404, оборванная сеть),
# событие load может не прийти вовсе. Лоадер обязан сняться в любом
# случае — застрявшая заставка непоправима без перезагрузки страницы.
FAILSAFE_MS = 12000


def build_shell(screens: tuple[str, ...] = SCREENS,
                start: str = START_SCREEN) -> str:
    """Полный HTML оболочки. Ни одного экрана внутри."""
    allowed = json.dumps(list(screens), ensure_ascii=False)
    start_js = json.dumps(start)
    sequence = json.dumps(SEQUENCE, ensure_ascii=False)
    names = json.dumps(SCREEN_NAMES, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sleeping Alts Screener</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;300;400&display=swap" rel="stylesheet">
<style>
  /* Свои стили, не из render_css.py. Общий файл стилей принадлежит
     экранам и уезжает внутрь iframe вместе с ними; оболочке из него
     не нужно ничего, а тянуть его сюда значит вернуть ту самую
     общность, ради устранения которой всё и затевалось. */
  /* ПОЛЕ ЗАЛА. Цвета сняты с его экрана: верх-центр #2e335c, светлее к
     куполу #3f3f67, низ #1b1c34; снизу синий купол и тёплый отсвет, как
     там. Ровно то же поле у сводки-схемы, поэтому между документами не
     мигает ни белым, ни чёрным. Сменится поле у зала — сменить здесь. */
  html, body {{
    margin: 0; padding: 0; height: 100%;
    background: #23263f;
    overflow: hidden;
  }}
  #obShellFrame {{
    position: fixed; inset: 0;
    width: 100%; height: 100%;
    border: 0; display: block;
    background: #23263f;
  }}
  #obShellLoader {{
    position: fixed; inset: 0;
    z-index: 10;                     /* поверх iframe, всегда */
    display: flex; align-items: center; justify-content: center;
    background:
      radial-gradient(60% 52% at 50% 100%, rgba(60,110,220,.20), transparent 70%),
      radial-gradient(40% 30% at 50% 88%, rgba(120,70,40,.18), transparent 70%),
      radial-gradient(1100px 700px at 50% -5%, #3f3f67, #2b2e51 45%, #1b1c34 100%);
    pointer-events: none;            /* не перехватывает клики, пока
                                        уходит */
  }}
  /* УХОД — КОСОЙ СРЕЗ, тот же, каким листаются страницы сводки:
     лоадер не растворяется, а съезжает косой гранью и открывает экран.
     .gone ставится скриптом ПОСЛЕ конца среза (см. hideLoader). */
  #obShellLoader.off {{
    animation: obShellWipe .8s cubic-bezier(.4,0,.5,1) forwards;
  }}
  #obShellLoader.gone {{ display: none; }}
  @keyframes obShellWipe {{
    from {{ clip-path: polygon(-30% 0, 125% 0, 125% 100%, 0 100%); }}
    to   {{ clip-path: polygon(-30% 0, -30% 0, -30% 100%, -55% 100%); }}
  }}

  /* ── Кристалл ─────────────────────────────────────────────
     Тот же октаэдр, что стоит в центре сводки-схемы: две
     четырёхгранные пирамиды основаниями друг к другу, восемь граней,
     размытые рёбра, вращение вокруг своей оси. Здесь он вдвое меньше и
     крутится быстрее — двенадцать секунд на оборот против сорока
     восьми: лоадер живёт около секунды, и медленное вращение выглядело
     бы неподвижным. Ореол в два слоя, синий и тихий, как там.

     Прежняя орбита со звездой снята не по вкусу: сводка теперь сама
     начинается кристаллом, и лоадер показывает её первый кадр до того,
     как она загрузилась. */
  .obShellGem {{
    position: relative;
    display: flex; flex-direction: column; align-items: center; gap: 30px;
  }}
  .obShellGem .halo {{
    position: absolute; left: 50%; top: 46px; border-radius: 50%;
    pointer-events: none; transform: translate(-50%, -50%);
  }}
  .obShellGem .h1 {{
    width: 190px; height: 190px;
    background: radial-gradient(closest-side,
      rgba(110,150,240,.38), rgba(90,130,225,.24) 30%,
      rgba(75,110,205,.10) 60%, transparent 100%);
    filter: blur(14px); animation: obShellHalo 5s ease-in-out infinite;
  }}
  .obShellGem .h2 {{
    width: 340px; height: 340px;
    background: radial-gradient(closest-side,
      rgba(90,130,225,.16), rgba(75,110,205,.06) 50%, transparent 100%);
    filter: blur(24px); animation: obShellHalo 7s ease-in-out infinite reverse;
  }}
  @keyframes obShellHalo {{
    0%, 100% {{ transform: translate(-50%,-50%) scale(.94); opacity: .85; }}
    50%      {{ transform: translate(-50%,-50%) scale(1.06); opacity: 1; }}
  }}
  .obShellGem .orb {{
    position: relative; width: 0; height: 0; margin: 46px 0;
    transform-style: preserve-3d;
    animation: obShellSpin 12s linear infinite;
  }}
  @keyframes obShellSpin {{
    from {{ transform: rotateX(-14deg) rotateY(0); }}
    to   {{ transform: rotateX(-14deg) rotateY(360deg); }}
  }}
  .obShellGem .half {{ position: absolute; left: 0; top: 0; transform-style: preserve-3d; }}
  .obShellGem .half.b {{ transform: rotateX(180deg); }}
  /* Размытие стоит на грани, а обрезка треугольника — на её вложенном
     слое: так размывается уже вырезанная грань, и мягкими становятся
     сами рёбра. Размытие на всём кристалле нельзя — фильтр на родителе
     сплющит объём. */
  .obShellGem .f {{
    position: absolute; left: -38px; top: -66px; width: 76px; height: 66px;
    transform-origin: 50% 100%; filter: blur(1.1px); opacity: .9;
  }}
  .obShellGem .f s {{
    position: absolute; inset: 0; display: block; text-decoration: none;
    clip-path: polygon(50% 0, 100% 100%, 0 100%);
    background: linear-gradient(160deg,
      rgba(125,165,240,.58), rgba(90,125,220,.28) 60%, rgba(110,150,235,.42));
  }}
  .obShellGem .f:nth-child(1) {{ transform: rotateY(0)      translateZ(38px) rotateX(35.26deg); }}
  .obShellGem .f:nth-child(2) {{ transform: rotateY(90deg)  translateZ(38px) rotateX(35.26deg); }}
  .obShellGem .f:nth-child(3) {{ transform: rotateY(180deg) translateZ(38px) rotateX(35.26deg); }}
  .obShellGem .f:nth-child(4) {{ transform: rotateY(270deg) translateZ(38px) rotateX(35.26deg); }}
  .obShellGem .half.b .f {{ opacity: .5; }}
  .obShellGem .half.b .f s {{
    background: linear-gradient(160deg, rgba(95,130,225,.3), rgba(70,100,195,.1) 60%);
  }}
  /* Подпись — моноширинная вразрядку, как штампы зала и схемы. */
  .obShellGem .cap {{
    position: relative; z-index: 2;
    font-family: ui-monospace, Menlo, Consolas, monospace;
    font-size: 10px; letter-spacing: .3em; text-transform: uppercase;
    color: #8b93bd;
    animation: obShellUp .6s cubic-bezier(.22,.61,.36,1) .25s both;
  }}
  .obShellGem .cap b {{ font-weight: 400; color: #c9d2e8; }}
  .obShellGem .cap:empty {{ display: none; }}
  @keyframes obShellUp {{
    from {{ opacity: 0; transform: translateY(6px); }}
    to   {{ opacity: 1; transform: none; }}
  }}

  /* Движение снимается целиком, но кристалл остаётся: пустое поле на
     месте лоадера неотличимо от зависшей загрузки. */
  @media (prefers-reduced-motion: reduce) {{
    .obShellGem .orb, .obShellGem .halo, .obShellGem .cap,
    #obShellLoader.off {{ animation: none; }}
    #obShellLoader.off {{ opacity: 0; transition: opacity .3s; }}
  }}
  /* ── /Кристалл ───────────────────────────────────────────── */
</style>
</head>
<body>

<div id="obShellLoader">
  <div class="obShellGem" aria-hidden="true">
    <i class="halo h2"></i><i class="halo h1"></i>
    <div class="orb">
      <div class="half"><i class="f"><s></s></i><i class="f"><s></s></i><i class="f"><s></s></i><i class="f"><s></s></i></div>
      <div class="half b"><i class="f"><s></s></i><i class="f"><s></s></i><i class="f"><s></s></i><i class="f"><s></s></i></div>
    </div>
    <div class="cap" id="obShellCap"></div>
  </div>
</div>

<script>
(function () {{
  // Белый список приходит из питона, а не пишется здесь руками:
  // расхождение между тем, что оболочка готова открыть, и тем, что
  // реально лежит на диске, иначе обнаруживается только пустым
  // экраном у пользователя.
  var ALLOWED = {allowed};
  var START = {start_js};
  var SEQUENCE = {sequence};
  var NAMES = {names};
  var MIN_SHOW_MS = {MIN_SHOW_MS};
  var FAILSAFE_MS = {FAILSAFE_MS};

  var loader = document.getElementById('obShellLoader');
  var cap = document.getElementById('obShellCap');
  var frame = null;          // текущий iframe; между экранами — null
  var current = '';          // имя экрана в рамке; нужно для ob:done
  var shownAt = 0;           // когда лоадер показан, для MIN_SHOW_MS
  var hideTimer = 0, failTimer = 0;

  function showLoader(name) {{
    clearTimeout(hideTimer); clearTimeout(failTimer);
    // Подпись: куда идём. Экран без имени — одна звезда.
    var label = NAMES[name];
    cap.innerHTML = label ? 'дальше · <b></b>' : '';
    if (label) cap.querySelector('b').textContent = label;
    loader.classList.remove('gone');
    // Пересчёт стилей между снятием display:none и снятием класса
    // .off — иначе браузер склеит оба изменения в одно, и срез при
    // следующем уходе не проиграется заново.
    void loader.offsetWidth;
    loader.classList.remove('off');
    shownAt = Date.now();
    failTimer = setTimeout(hideLoader, FAILSAFE_MS);
  }}

  function hideLoader() {{
    clearTimeout(hideTimer); clearTimeout(failTimer);
    var waited = Date.now() - shownAt;
    if (waited < MIN_SHOW_MS) {{
      hideTimer = setTimeout(hideLoader, MIN_SHOW_MS - waited);
      return;
    }}
    loader.classList.add('off');
    // Экрану сообщается, что его ПОКАЗАЛИ. Без этого сигнала экран
    // знает только момент своей загрузки — а при тёплом кэше она
    // мгновенна, и вся вступительная анимация успевала отыграть ПОД
    // лоадером (найдено пользователем 24.08: первый сегмент сводки
    // после перезагрузки появлялся уже допечатанным). Экраны, не
    // ждущие сигнала, просто не слушают его — совместимо в обе
    // стороны.
    // Сигнал уходит на середине среза, а не в его начале: у сводки
    // первая страница въезжает своим клином, и два клина разом
    // читались бы кашей.
    hideTimer = setTimeout(function () {{
      if (frame && frame.contentWindow) {{
        try {{
          frame.contentWindow.postMessage({{type: 'ob:shown'}},
                                          window.location.origin);
        }} catch (err) {{ /* рамку могли убрать между кадрами */ }}
      }}
      // display:none только после того, как срез доиграл (800 мс):
      // снять его раньше значит оборвать переход на полпути.
      //
      // Ждём КОНЕЦ АНИМАЦИИ, а не только таймер: на планшете срез —
      // это clip-path поверх трёх размытых слоёв ореола, и он может
      // начаться позже, чем поставлен класс. Таймер остаётся вторым
      // условием: что случится раньше, то и снимет лоадер.
      var done = false;
      var finish = function () {{
        if (done) return;
        done = true;
        loader.classList.add('gone');
      }};
      loader.addEventListener('animationend', finish, {{once: true}});
      hideTimer = setTimeout(finish, 450);
    }}, 400);
  }}

  function switchScreen(name) {{
    if (ALLOWED.indexOf(name) === -1) return;   // молча, не бросая:
                                                // это защита, а не
                                                // отладочный канал
    showLoader(name);

    // Старый iframe УДАЛЯЕТСЯ, а не переиспользуется под новый src.
    // Две причины. Первая: удаление из DOM уничтожает документ вместе
    // со всеми его циклами и таймерами прямо сейчас, а не когда
    // догрузится следующий, — иначе две сцены секунду рисуются
    // одновременно, ровно те тормоза, от которых уходим. Вторая:
    // присваивание src существующему iframe добавляет запись в
    // историю браузера, и кнопка «назад» начинает листать экраны
    // внутри рамки. У свежесозданного элемента со сразу выставленным
    // src записи в историю не появляется.
    if (frame) {{ frame.remove(); frame = null; }}

    // ЛОАДЕР ДОЛЖЕН УСПЕТЬ ОТРИСОВАТЬСЯ. Найдено на планшете 27.08:
    // лоадер «зависал» и появлялся только после того, как первый экран
    // отыграл. Причина не в его анимации: вставка iframe со сразу
    // выставленным src запускает разбор и раскладку документа экрана
    // (сотни килобайт со вшитыми данными) в том же главном потоке, и
    // браузер не успевает нарисовать ни одного кадра лоадера до того,
    // как поток занят. На быстрой машине это незаметно, на планшете —
    // целая сцена.
    // Поэтому рамка создаётся ПОСЛЕ двух кадров отрисовки: первый
    // показывает лоадер, второй даёт ему начать движение. Задержка
    // порядка тридцати миллисекунд, MIN_SHOW_MS её покрывает, очередь
    // экранов не меняется.
    // ДВА КАДРА — ЖЕЛАТЕЛЬНЫЕ, А НЕ ОБЯЗАТЕЛЬНЫЕ. Кадры просит
    // requestAnimationFrame, и он их НЕ ДАЁТ, пока вкладка не
    // отрисовывается: на планшете при первом открытии, при
    // восстановлении из фона, при выключенном экране. Найдено 27.08:
    // рамка не создавалась вовсе, лоадер висел, и всё сдвигалось
    // только от поворота планшета — поворот заставляет браузер
    // перерисовать страницу, и отложенные кадры наконец приходят.
    //
    // Поэтому у кадров есть срок: не пришли за 120 мс — создаём
    // рамку по таймеру. Таймеры работают и в невидимой вкладке.
    var made = false;
    var makeFrame = function () {{
      if (made) return;          // кадр и таймер могли сработать оба
      made = true;
      var f = document.createElement('iframe');
      f.id = 'obShellFrame';
      f.setAttribute('title', 'screen');
      f.addEventListener('load', hideLoader);
      // СТРАХОВКА НА СОБЫТИЕ ЗАГРУЗКИ. Событие load у рамки приходит
      // не всегда: при восстановлении из фона, при загрузке из кэша,
      // при ошибке сети его может не быть вовсе — а лоадер снимался
      // ТОЛЬКО по нему, и висел до самого конца экрана под ним.
      // Общий предохранитель на двенадцать секунд для этого слишком
      // велик: экран уже виден, а лоадер ещё нет.
      setTimeout(hideLoader, 2500);
      f.src = name + '.html';
      document.body.appendChild(f);
      frame = f;
    }};
    if (window.requestAnimationFrame) {{
      requestAnimationFrame(function () {{ requestAnimationFrame(makeFrame); }});
      setTimeout(makeFrame, 120);
    }} else {{
      setTimeout(makeFrame, 32);
    }}
    current = name;
  }}

  window.addEventListener('message', function (e) {{
    // Проверяются оба: и откуда пришло, и что пришло. Свой источник
    // не делает содержимое сообщения доверенным — в рамке может
    // оказаться что угодно, что туда однажды загрузят.
    if (e.origin !== window.location.origin) return;
    var msg = e.data;
    if (!msg) return;

    // Явный переход: экран сам называет, куда идти.
    if (msg.type === 'ob:switchScreen') {{
      switchScreen(String(msg.screen || ''));
      return;
    }}

    // «Я закончил» — куда дальше, решает оболочка по SEQUENCE. Экран
    // не называет преемника и потому не обязан о нём знать.
    if (msg.type === 'ob:done') {{
      var from = String(msg.screen || '');
      var next = SEQUENCE[from];
      // Сверка с тем, что сейчас в рамке: сообщение от экрана,
      // который уже сменили, иначе увело бы с нового экрана. Такое
      // бывает при закрытии по таймеру, который успел сработать
      // после ручного перехода.
      if (next && from === current) switchScreen(next);
      return;
    }}
  }});

  switchScreen(START);
}})();
</script>

</body>
</html>
"""
