"""Сборка итоговой страницы отчёта.

Единственный экран — дашборд. Таблицы срезов и карточки монет живут
в том же документе и показываются по клику.
"""

from __future__ import annotations

from core_models import Candidate, RunSnapshot
from render_css import CSS
from render_dashboard import render_dashboard_page

FONTS_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Inter:wght@200;300;400;500;700;800;900&display=swap" rel="stylesheet">'
)


def build_page(candidates: list[Candidate], snapshot: RunSnapshot) -> str:
    """Полный HTML отчёта."""
    body = "\n".join([
        render_dashboard_page(candidates, snapshot),
    ])

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sleeping Alts Screener</title>
{FONTS_LINK}
<style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>
"""
