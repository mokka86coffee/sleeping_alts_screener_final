"""Сборка документов отчёта.

Раньше здесь собиралась ОДНА страница: дашборд, а внутри него —
сводка, зал и сцена карточки, показываемые переключением видимости.
Теперь собирается НАБОР документов: оболочка плюс по файлу на экран.

Кто кого грузит:

    index.html      оболочка (render_shell) — лоадер и пустой iframe
      └── dashboard.html   экран, который грузится первым
      └── brief.html       ↑ каждый в тот же iframe, по очереди
      └── podium.html      ↑ предыдущий при этом уничтожается

Переезд идёт по одному экрану, и это намеренно. Сейчас в свой файл
вынесен только дашборд, а сводка, зал и сцена карточки по-прежнему
лежат внутри него и переключаются как раньше. Отчёт от этого шага
работает ровно так же, как работал, — добавилась только оболочка
снаружи. Вынести все три сразу значило бы поменять точку входа,
источник данных и способ выхода у каждого одним прогоном, и при
первой же поломке было бы неизвестно, какая из девяти правок виновата.

Список SCREENS в render_shell.py опережает реальность: он уже
перечисляет brief и podium. Это не ошибка — белый список оболочки
описывает, что ей РАЗРЕШЕНО грузить, а попытка перейти на ещё не
существующий файл кончается снятым лоадером и пустой рамкой, а не
поломкой. Файлы появятся на следующих шагах.
"""

from __future__ import annotations

from core_models import Candidate, RunSnapshot
from render_css import CSS
from render_dashboard import render_dashboard_page
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
    return {
        "index.html": build_shell(),
        "dashboard.html": document(render_dashboard_page(candidates, snapshot)),
    }


def build_page(candidates: list[Candidate], snapshot: RunSnapshot) -> str:
    """Один документ со всем содержимым — как было до разделения.

    Оставлено намеренно и не является мёртвым кодом: это способ
    открыть отчёт как ОДИН файл, без оболочки и без iframe. Нужен
    ровно в том случае, когда отчёт смотрят с диска (file://), где
    iframe с соседними файлами упирается в политику источника, а
    postMessage между документами не проходит вовсе.
    """
    return document(render_dashboard_page(candidates, snapshot))
