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

Лоадер — звезда с орбитой на светлом поле сводки. Утверждён по
HTML-прототипу proto_switch_orbit.html (26.08) вместо прежней
пульсирующей звезды на чёрном: сводка стала светлой, и чёрный проход
между экранами читался как другое приложение. Оформление и логика
показа не связаны: чтобы поменять вид, достаточно содержимого
#obShellLoader и его стилей, MIN_SHOW_MS к нему не привязан.

Подпись под звездой называет экран, который грузится: лоадер — проход,
и проход говорит, куда ведёт. Имена берутся из SCREEN_NAMES ниже.
"""

from __future__ import annotations

import json

# Экраны, которые оболочке разрешено грузить. Список ведётся здесь и
# отсюда же попадает в JS: белый список в браузере не должен
# расходиться с набором файлов, которые реально пишет run.py.
#
# Имя = имя файла без расширения: "dashboard" → "dashboard.html".
SCREENS = ("dashboard", "brief", "podium")

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
    "brief": "podium",
    "podium": "dashboard",
}

# Как экран называется в подписи лоадера. Экран без имени подписи не
# получает — лоадер покажет одну звезду.
SCREEN_NAMES = {
    "brief": "сводка",
    "podium": "зал",
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
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400&display=swap" rel="stylesheet">
<style>
  /* Свои стили, не из render_css.py. Общий файл стилей принадлежит
     экранам и уезжает внутрь iframe вместе с ними; оболочке из него
     не нужно ничего, а тянуть его сюда значит вернуть ту самую
     общность, ради устранения которой всё и затевалось. */
  /* ПОЛЕ. Серое поле сводки (#8d939c, её --pg): оболочка, рамка и
     лоадер одного цвета, чтобы между документами не мигало ни белым,
     ни чёрным. Зал и дашборд тёмные — к ним лоадер уходит косым
     срезом, и контраст на срезе читается как переворот листа, а зал
     со своей стороны ещё и проявляется полсекунды. Сменится поле у
     сводки — сменить здесь. */
  html, body {{
    margin: 0; padding: 0; height: 100%;
    background: #8d939c;
    overflow: hidden;
  }}
  #obShellFrame {{
    position: fixed; inset: 0;
    width: 100%; height: 100%;
    border: 0; display: block;
    background: #8d939c;
  }}
  #obShellLoader {{
    position: fixed; inset: 0;
    z-index: 10;                     /* поверх iframe, всегда */
    display: flex; align-items: center; justify-content: center;
    background: #8d939c;
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

  /* ── Орбита ───────────────────────────────────────────────
     Звезда осталась звездой, но из свечения стала знаком: белая точка
     в центре, одна тонкая орбита, по ней бежит оранжевая точка — язык
     дашборда на поле сводки. Свечения на светлом не бывает, потому
     нет ни ореола, ни лучей.

     Утверждено по прототипу proto_switch_orbit.html (26.08). Прежде
     орбита была отклонена по делу: период 2.6 с при показе около
     секунды — полного оборота никто не видел, оставалась дёргающаяся
     крошка. Здесь период 0.9 с, короче минимального показа в 700 мс
     плюс уход: полный оборот виден даже на самом быстром переходе, а
     ход ровный, без ускорений, — ровно то, чего не хватало тогда. */
  .obShellOrbit {{
    display: flex; flex-direction: column; align-items: center; gap: 26px;
  }}
  .obShellOrbit .orb {{ position: relative; width: 96px; height: 96px; }}
  .obShellOrbit .ring {{
    position: absolute; inset: 0; border-radius: 50%;
    border: 1px solid rgba(70,76,87,.35);
  }}
  .obShellOrbit .core {{
    position: absolute; left: 50%; top: 50%; width: 14px; height: 14px;
    margin: -7px 0 0 -7px; border-radius: 50%; background: #fff;
    box-shadow: 0 6px 16px rgba(34,38,46,.25);
  }}
  .obShellOrbit .sat {{
    position: absolute; inset: 0;
    animation: obShellTurn .9s linear infinite;
  }}
  .obShellOrbit .sat i {{
    position: absolute; left: 50%; top: -4px; width: 8px; height: 8px;
    margin-left: -4px; border-radius: 50%; background: #e8873f; display: block;
  }}
  /* Подпись — антиква вразрядку, как штампы сводки. Стек запасных
     подобран по рисунку: Didot и Bodoni — та же антиква с тонкими
     засечками, если сеть закрыта. */
  .obShellOrbit .cap {{
    font-family: 'Playfair Display', Didot, 'Bodoni MT', Georgia, serif;
    font-size: 10.5px; letter-spacing: .4em; text-transform: uppercase;
    color: #6c737f;
    animation: obShellUp .6s cubic-bezier(.22,.61,.36,1) .25s both;
  }}
  .obShellOrbit .cap b {{ font-weight: 400; color: #464c57; }}
  .obShellOrbit .cap:empty {{ display: none; }}
  @keyframes obShellTurn {{ to {{ transform: rotate(360deg); }} }}
  @keyframes obShellUp {{
    from {{ opacity: 0; transform: translateY(6px); }}
    to   {{ opacity: 1; transform: none; }}
  }}

  /* Движение снимается целиком, но знак остаётся: пустое поле на
     месте лоадера неотличимо от зависшей загрузки. */
  @media (prefers-reduced-motion: reduce) {{
    .obShellOrbit .sat, .obShellOrbit .cap, #obShellLoader.off {{ animation: none; }}
    #obShellLoader.off {{ opacity: 0; transition: opacity .3s; }}
  }}
  /* ── /Орбита ─────────────────────────────────────────────── */
</style>
</head>
<body>

<div id="obShellLoader">
  <div class="obShellOrbit" aria-hidden="true">
    <div class="orb"><span class="ring"></span><span class="sat"><i></i></span><span class="core"></span></div>
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
      hideTimer = setTimeout(function () {{
        loader.classList.add('gone');
      }}, 450);
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

    var f = document.createElement('iframe');
    f.id = 'obShellFrame';
    f.setAttribute('title', 'screen');
    f.addEventListener('load', hideLoader);
    f.src = name + '.html';
    document.body.appendChild(f);
    frame = f;
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
