"""Календарь событий рынка (Р-7). Частокол, который видно заранее.

Зачем. Повод приходит извне и в наших данных не бывает — но ДАТА
повода часто известна заранее. Заседание ФРС, разлок, операция
Казначейства стоят в календаре за недели. Скринер, который этого не
показывает, бесполезен ровно в тот момент, когда нужен: решение
«входить сегодня» принимается иначе, когда послезавтра ФРС.

Правило «рынок отрабатывает заранее». Событие входит в поле зрения не
в свой день, а за LOOKAHEAD_DAYS до него: позиции разгружают до, а не
после. Поэтому «через 5 дней» — это уже сейчас, а не «потом».

Два знака, и оба обязательны. Сентябрь-2026 показал, почему: в нём и
разгрузка (ФРС, разлоки), и поддержка (серия выкупов Казначейства
9.09–4.11). Календарь, печатающий только риски, прочитается однобоко
и превратится в вечное «не входи».

Формат events.json — список записей, порядок любой:

    [
      {"date": "2026-09-15", "title": "заседание ФРС",
       "kind": "risk", "note": "ставка"},
      {"date": "2026-09-09", "until": "2026-11-04",
       "title": "серия выкупов Казначейства", "kind": "support"}
    ]

kind: "risk" — разгрузка перед событием (предупреждение);
      "support" — окно поддержки (НЕ предупреждение, состояние);
      "unlock" — разлок конкретной монеты (риск, но адресный);
      "macro" — фон без явного знака.
until — для интервалов: пока идёт, событие показывается как «идёт».

Файл ведётся руками, как reservoir.json и decisions.json: события
приходят из новостей, а не из свечей. Прошедшие записи не удаляются
— они и есть история частокола (Р-16 когда-нибудь спросит, что было
в тот день).
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from core_config import BASE_DIR

EVENTS_PATH = BASE_DIR / "output" / "events.json"

# За сколько дней событие попадает в поле зрения. Пять — не догадка:
# по правилу «рынок отрабатывает заранее» разгрузка перед крупным
# макро-событием начинается за рабочую неделю. Величина прикидочная и
# помечена как таковая; уточнить её сможет замер Р-16, когда журнал
# решений накопит записи «вошёл перед событием».
LOOKAHEAD_DAYS = 5

# Ярлыки знаков для показа. Живут здесь, а не в рендере: знак — это
# свойство события, а не оформление.
KIND_RU = {
    "risk": "разгрузка",
    "support": "поддержка",
    "unlock": "разлок",
    "macro": "фон",
}


def _parse(value: str | None) -> date | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def load_events(path: Path = EVENTS_PATH) -> list[dict]:
    """Записи файла как есть. Нет файла — пусто, это не ошибка."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in data if isinstance(e, dict) and e.get("date")]


def calendar_state(path: Path = EVENTS_PATH,
                   today: date | None = None) -> dict:
    """Ближайшие события в контракте составляющих market_permission.

    warn поднимается ТОЛЬКО риском в окне ожидания. Поддержка и фон
    известны, но не предупреждают: гейт объясняет, а не запрещает —
    то же правило, что у резервуара (Р-20).

    Наружу: items — список ближайших с днями до, warn/known/note.
    """
    today = today or date.today()
    events = load_events(path)
    if not events:
        return {"known": False, "warn": False, "items": [],
                "note": "календарь: файла нет (Р-7, события руками)"}

    items = []
    for e in events:
        start = _parse(e.get("date"))
        if start is None:
            continue
        end = _parse(e.get("until")) or start
        if today > end:
            continue                      # прошедшее — история, не показ
        days = (start - today).days
        running = start <= today <= end
        if days > LOOKAHEAD_DAYS and not running:
            continue                      # ещё за горизонтом внимания
        kind = str(e.get("kind") or "macro")
        items.append({
            "title": str(e.get("title") or "событие"),
            "kind": kind,
            "days": max(0, days),
            "running": running,
            "note": str(e.get("note") or ""),
        })
    if not items:
        return {"known": True, "warn": False, "items": [],
                "note": "календарь чист на ближайшие "
                        f"{LOOKAHEAD_DAYS} дней"}

    items.sort(key=lambda i: (not i["running"], i["days"]))
    warn = any(i["kind"] in ("risk", "unlock") and not i["running"]
               for i in items)

    def _phrase(i: dict) -> str:
        when = "идёт" if i["running"] else (
            "сегодня" if i["days"] == 0 else
            "завтра" if i["days"] == 1 else f"через {i['days']} дн")
        return f"{i['title']} ({when})"

    head = "; ".join(_phrase(i) for i in items[:3])
    more = f" и ещё {len(items) - 3}" if len(items) > 3 else ""
    return {"known": True, "warn": warn, "items": items,
            "note": f"впереди: {head}{more}"}
