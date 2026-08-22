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
from analytics_stars import build_stars
from render_css import CSS
from render_brief import render_brief
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
    stars = build_stars(candidates)
    market = orbit_market(candidates, snapshot, slices)

    return {
        "index.html": build_shell(),
        "dashboard.html": document(
            render_dashboard_page(candidates, snapshot, slices,
                                  market, stars)),
        "brief.html": document(render_brief(stars, market)),
        "podium.html": document(render_podium(stars, market)),
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
    return document(render_dashboard_page(
        candidates, snapshot, slices,
        orbit_market(candidates, snapshot, slices),
        build_stars(candidates)))
