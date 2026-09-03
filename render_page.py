"""Сборка документов отчёта.

Раньше здесь собиралась ОДНА страница: дашборд, а внутри него —
сводка, зал и сцена карточки, показываемые переключением видимости.
Теперь собирается НАБОР документов: оболочка плюс по файлу на экран.

Кто кого грузит:

    index.html      оболочка (render_shell) — лоадер и пустой iframe
      └── dashboard.html   экран, который грузится первым
      └── brief.html       ↑ каждый в тот же iframe, по очереди
      └── podium.html      ↑ предыдущий при этом уничтожается

Сводка и зал переехали вместе, и по-другому было нельзя: их связывала
очередь показа. Зал дожидался сводки, следя за классом на её узле, —
разнеси их по документам поодиночке, и наблюдение сорвалось бы в
сторожевой таймер, показав зал поверх ещё играющей сводки. Очередь
теперь ведёт оболочка (SEQUENCE в render_shell.py), и оба экрана о
существовании друг друга не знают.

Сцена карточки осталась внутри дашборда намеренно: это не экран
очереди, а модальное окно, открываемое кликом по карточке. Свой
документ ей не нужен и мешал бы — она обязана лежать поверх того, из
чего её открыли.

ЭТОТ МОДУЛЬ — единственное место, где данные собираются для всех
экранов сразу. Звёзды считаются одним вызовом build_stars() и уходят
и в сводку, и в зал, и в дашборд: второй источник тех же чисел
разошёлся бы при первой правке, и монета показывала бы на двух
экранах разное.
"""

from __future__ import annotations

from core_models import Candidate, RunSnapshot
from analytics_portfolio import portfolios
from analytics_stars import build_stars
from core_config import REPORT_PATH
from render_css import CSS
from render_brief import render_brief          # листалка (запасная)
from render_scheme import render_scheme        # сводка-схема — ЛИЦО брифа
from render_coin import render_coin            # единый экран монеты (03.09)
from render_dashboard import build_slices, render_dashboard_page
from render_orbit import orbit_market
from render_podium import render_podium
from render_shell import build_shell

FONTS_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Inter:wght@200;300;400;500;700;800;900&display=swap" rel="stylesheet">'
)


def document(body: str, title: str = "Sleeping Alts Screener") -> str:
    """HTML-обвязка одного экрана.

    Стили кладутся в КАЖДЫЙ документ целиком, а не подключаются одним
    общим файлом. Так и задумано: изоляция стилей — половина смысла
    затеи, и общий <link> вернул бы ровно ту связанность, от которой
    уходим, только через сеть вместо DOM. Плата — повторение CSS в
    каждом файле; браузер отдаёт их из своего кеша по одному и тому же
    содержимому, а на диске это несколько сотен килобайт статики.
    """
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
{FONTS_LINK}
<style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>
"""


from core_http import log


def _attach_coinglass(stars: list[dict]) -> None:
    """Г-15 (29.08): срез Coinglass — в ПОКАЗ карточки зала.

    Скор и вето не трогает — запрет 26.08 действует. Читается готовый
    output/coinglass_fetch.json через coinglass_fetch.for_screens();
    нет файла — нет полей, карточка молчит. Одна функция на ОБЕ сборки
    (build_pages и build_page): два места дописывания разошлись бы.
    Ликвидации дописываются только если звезда своих не принесла: два
    источника одной строки — два шанса разойтись.
    """
    try:
        from coinglass_fetch import for_screens
        cg = for_screens()
    except Exception as e:
        log(f"Coinglass в показ пропущен: {type(e).__name__}: {e}")
        return
    for s in stars:
        g = cg.get(s.get("t"))
        if not g:
            continue
        s["cg"] = g
        if not s.get("liq24h") and (g.get("liqLong") or g.get("liqShort")):
            s["liq24h"] = {"long": g.get("liqLong"),
                           "short": g.get("liqShort")}
    # Пилюли свода (Э-7, одобрен 29.08): разлоки и балансы — те же
    # готовые файлы суточных контуров, сети ноль. Нет файла — нет
    # пилюли, карточка молчит; Клингер приходит из метрик сам.
    try:
        from unlocks_coinglass import for_screens as unlocks_screens
        ul = unlocks_screens()
        for s in stars:
            u = ul.get(s.get("t"))
            if u:
                s["unlock"] = u
    except Exception as e:
        log(f"Разлоки в показ пропущены: {type(e).__name__}: {e}")
    try:
        from balances_coinglass import for_screens as balances_screens
        bl = balances_screens()
        for s in stars:
            v = bl.get(s.get("t"))
            if v:
                s["balances"] = v
    except Exception as e:
        log(f"Балансы в показ пропущены: {type(e).__name__}: {e}")

    # Крикун на ТИХУЮ массовую пропажу (урок 29.08: oi_spark молчал
    # у всех, и никто не знал — гашение отказа в метриках честно по
    # замыслу, но немо по исполнению). Кричим только при пропаже у
    # ВСЕХ разом: единичные пустоты — штатный случай вне покрытия.
    for field, name in (("oiSpark", "ряд OI"), ("liqZones", "зоны ликвидаций"),
                        ("cg", "срез Coinglass")):
        if stars and not any(s.get(field) for s in stars):
            log(f"  ⚠ {name}: пусто у ВСЕХ {len(stars)} монет — "
                f"труба питания, не рынок")


def build_pages(candidates: list[Candidate],
                snapshot: RunSnapshot) -> dict[str, str]:
    """Все документы отчёта: имя файла → готовый HTML.

    Словарём, а не несколькими возвращаемыми значениями: добавление
    экрана не должно менять сигнатуру и заставлять править run.py.
    Тот просто пишет всё, что пришло.

    Ключ — имя файла, и оно обязано совпадать с именем экрана в
    render_shell.SCREENS: оболочка переходит по name + '.html'.
    """
    # Считается ОДИН раз на все экраны. Срезы и строка рынка нужны и
    # дашборду для его блоков, и сводке с залом как содержимое, —
    # пересчёт в каждом дал бы три независимых прохода по выборке и
    # три возможности разойтись.
    slices = build_slices(candidates, snapshot)
    # Рынок считается ПЕРВЫМ: в нём живёт разрешение (Р-1), которое
    # звёздам нужно для ступени размера (Р-15). Обратный порядок
    # заставил бы считать разрешение дважды — и однажды разойтись.
    market = orbit_market(candidates, snapshot, slices)
    # write_log: журнал предположений пишет ТОЛЬКО эта, боевая сборка
    # страниц — один раз за прогон. Одиночный file://-документ ниже
    # не пишет ничего: это просмотр, а не прогон (см. analytics_stars).
    stars = build_stars(candidates, market.get("permission"),
                        write_log=True)
    # Р-29: два счёта считаются ПОСЛЕ звёзд — им нужны цены и ступени
    # размера. Рынок при этом уже собран, поэтому дописываем в него:
    # это по-прежнему один словарь на все экраны, второго источника
    # тех же чисел не заводим.
    market["portfolios"] = portfolios(stars)
    _attach_coinglass(stars)

    # ── ОЗВУЧКА СВОДКИ (27.08) ──
    # Здесь, а не в run.py: stars и market уже посчитаны один раз, и
    # второй проход по выборке ради текста был бы и лишней работой, и
    # вторым источником тех же чисел — ровно тем, чего этот модуль
    # избегает во всём остальном.
    #
    # Только в БОЕВОЙ сборке (эта ветка, write_log=True). Одиночный
    # file://-документ ниже — просмотр, а не прогон: он не пишет ни
    # журнал предположений, ни флэт-вотч, и звук ему тоже не нужен.
    #
    # Синтез есть только на macOS: на другой системе модуль молча
    # вернёт отказ, звука не будет, экран не покажет кнопку. Прогон
    # это не роняет — озвучка побочный продукт, а не часть отчёта.
    try:
        from render_voice import render_voice
        render_voice(stars, market, REPORT_PATH.parent)
    except ImportError:
        pass
    except Exception as e:
        log(f"озвучка пропущена: {type(e).__name__}: {e}")

    # Мост к внешнему пузырь-боту: список флэтовых монет у дна.
    # Пишет только боевая сборка (persist=True) — как журнал и
    # unlocks_seen; file://-сборка ниже файл не трогает. На сам
    # скринер мост не влияет: он только выписывает наружу то, что
    # звёзды уже знают.
    try:
        from analytics_flatwatch import collect_flow_watch
        log(f"→ FLOW-вотч: {collect_flow_watch(candidates, persist=True)}")
    except Exception as e:
        log(f"✗ Флэт-вотч: {type(e).__name__}: {e}")

    return {
        "index.html": build_shell(),
        "dashboard.html": document(
            render_dashboard_page(candidates, snapshot, slices,
                                  market, stars)),
        # СВОДКА — ЛИСТАЛКА (31.08): секция «Пойдёт?», режим в ленте.
        # Схема НЕ выброшена: публикуется рядом своим документом
        # scheme.html — открывается прямой ссылкой, очередь оболочки
        # не трогает. Поменять экраны местами — поменять две строки.
        "brief.html": document(render_scheme(stars, market)),
        "podium.html": document(render_podium(stars, market)),
        # ЕДИНЫЙ ЭКРАН МОНЕТЫ (03.09): не в очереди оболочки — открывается
        # золотой кнопкой из схемы (coin.html) и хвостом адреса #ТИКЕР,
        # как журнал. Те же stars/market, что у сводки и зала.
        "coin.html": document(render_coin(stars, market), "Монета · один экран"),
    }


def build_page(candidates: list[Candidate], snapshot: RunSnapshot) -> str:
    """Один документ со всем содержимым — как было до разделения.

    Оставлено намеренно и не является мёртвым кодом: это способ
    открыть отчёт как ОДИН файл, без оболочки и без iframe. Нужен
    ровно в том случае, когда отчёт смотрят с диска (file://), где
    iframe с соседними файлами упирается в политику источника, а
    postMessage между документами не проходит вовсе.

    Сводки и зала здесь НЕТ: они теперь самостоятельные документы и
    поверх дашборда не ложатся. Это именно дашборд одним файлом, а не
    прежний отчёт целиком.
    """
    slices = build_slices(candidates, snapshot)
    # Тот же порядок, что в build_pages: рынок первым, звёзды от его
    # разрешения. Здесь это просмотр с диска, но расходиться двум
    # сборкам нельзя — иначе file:// покажет другие ступени размера.
    market = orbit_market(candidates, snapshot, slices)
    stars = build_stars(candidates, market.get("permission"))
    market["portfolios"] = portfolios(stars)
    # Тот же срез Coinglass, что в build_pages: file://-просмотр не
    # должен показывать другую карточку, чем боевой отчёт.
    _attach_coinglass(stars)
    return document(render_dashboard_page(
        candidates, snapshot, slices, market, stars))
