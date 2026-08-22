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

ЛОАДЕР ЗДЕСЬ — ЗАГЛУШКА. Разметка и механика настоящие, оформление
намеренно минимальное: сама анимация загрузки — задача на прототип, а
не на то, чтобы её молча придумал этот файл. Менять нужно только
содержимое #obShellLoader и его стили; вся логика показа/скрытия к
оформлению не привязана.
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

# Сколько лоадер висит минимум. Без нижней границы лоадер, мелькнувший
# на сорок миллисекунд при переходе на закешированный экран, читается
# как дефект отрисовки, а не как загрузка.
MIN_SHOW_MS = 350

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

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sleeping Alts Screener</title>
<style>
  /* Свои стили, не из render_css.py. Общий файл стилей принадлежит
     экранам и уезжает внутрь iframe вместе с ними; оболочке из него
     не нужно ничего, а тянуть его сюда значит вернуть ту самую
     общность, ради устранения которой всё и затевалось. */
  html, body {{
    margin: 0; padding: 0; height: 100%;
    background: #050506;   /* тот же фон, что у экранов: без него
                              между документами мигает белым */
    overflow: hidden;
  }}
  #obShellFrame {{
    position: fixed; inset: 0;
    width: 100%; height: 100%;
    border: 0; display: block;
    background: #050506;
  }}
  #obShellLoader {{
    position: fixed; inset: 0;
    z-index: 10;                     /* поверх iframe, всегда */
    display: flex; align-items: center; justify-content: center;
    background: #050506;
    opacity: 1; transition: opacity .35s ease;
    pointer-events: none;            /* не перехватывает клики, пока
                                        гаснет */
  }}
  #obShellLoader.off {{ opacity: 0; }}
  #obShellLoader.gone {{ display: none; }}

  /* ── ЗАГЛУШКА ─────────────────────────────────────────────
     Всё, что ниже, — временное оформление, чтобы механику можно
     было проверить сейчас. Настоящая анимация загрузки идёт
     отдельным прототипом. */
  .obShellDot {{
    width: 6px; height: 6px; border-radius: 50%;
    background: #C9915A; opacity: .25;
    animation: obShellPulse 1.4s ease-in-out infinite;
  }}
  @keyframes obShellPulse {{
    0%, 100% {{ opacity: .18; transform: scale(1); }}
    50%      {{ opacity: .75; transform: scale(1.6); }}
  }}
  /* ── /ЗАГЛУШКА ───────────────────────────────────────────── */
</style>
</head>
<body>

<div id="obShellLoader"><div class="obShellDot"></div></div>

<script>
(function () {{
  // Белый список приходит из питона, а не пишется здесь руками:
  // расхождение между тем, что оболочка готова открыть, и тем, что
  // реально лежит на диске, иначе обнаруживается только пустым
  // экраном у пользователя.
  var ALLOWED = {allowed};
  var START = {start_js};
  var SEQUENCE = {sequence};
  var MIN_SHOW_MS = {MIN_SHOW_MS};
  var FAILSAFE_MS = {FAILSAFE_MS};

  var loader = document.getElementById('obShellLoader');
  var frame = null;          // текущий iframe; между экранами — null
  var current = '';          // имя экрана в рамке; нужно для ob:done
  var shownAt = 0;           // когда лоадер показан, для MIN_SHOW_MS
  var hideTimer = 0, failTimer = 0;

  function showLoader() {{
    clearTimeout(hideTimer); clearTimeout(failTimer);
    loader.classList.remove('gone');
    // Пересчёт стилей между снятием display:none и снятием класса
    // .off — иначе браузер склеит оба изменения в одно и перехода
    // не будет вовсе.
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
    // display:none только после того, как затухание доиграло: снять
    // его сразу значит оборвать переход на первом кадре.
    hideTimer = setTimeout(function () {{
      loader.classList.add('gone');
    }}, 400);
  }}

  function switchScreen(name) {{
    if (ALLOWED.indexOf(name) === -1) return;   // молча, не бросая:
                                                // это защита, а не
                                                // отладочный канал
    showLoader();

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
