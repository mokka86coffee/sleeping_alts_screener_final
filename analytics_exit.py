"""Правило выхода (Р-11, уточнённое Р-17). Говорит «пора смотреть».

Самая дорогая дыра проекта: правила выхода не было. BLESS сходила
×2.4 от входа и вернулась на 36% ниже — весь разрыв между
механическим портфелем и портфелем по правилам сидел здесь.

Стоп и выход — РАЗНЫЕ защиты (Р-17). build_stop держит уровень в
коридоре 2–14% и защищает от УДАРА. В фигуре, где монета ходит вдвое
и медленно возвращается, стоп на 14% срабатывает на обычном дыхании,
а просадка на 36% не срабатывает никогда: цена пришла туда постепенно,
ни разу не дав дневного хода до уровня. Выход защищает от
ИСТОЩЕНИЯ — и одно не заменяет другое ни в какую сторону.

Три половины, и по отдельности они не работают.

1. КАЛЕНДАРНАЯ — дедлайн. Крупный инсайдерский транш есть окончание
   любого роста, и рынок отрабатывает дату ЗА НЕСКОЛЬКО ДНЕЙ ДО
   (показала LAB). Расширена 22.08: не только разлоки монеты, но и
   макродаты частокола (Р-7) — Джексон-Хоул и ФРС двигают весь рынок
   с непредсказуемым знаком, и календарь из одних разлоков слеп
   наполовину.
2. ПОТОКОВАЯ — открытый интерес против цены. Рост OI при стоящей или
   падающей цене ПОСЛЕ хода означает, что толпу завели и идёт
   раздача. Проверено на ESPORTS и ONG, подтверждено формой BLESS.
   Читается из пульса: он пишет цену и oi_usd по всей выборке каждый
   прогон.
3. СДЕЛОЧНАЯ — крупная продажа на свежих барах при монете выше входа.
   Поле bigSells/bigMarks уже считается интрадей-слоем.

Почему вместе. Календарь без потока выгонит из живого движения раньше
времени. Поток без календаря продержит до самой даты, когда выходить
уже поздно. Сделочная половина одна ничего не значит: крупная продажа
на монете НИЖЕ входа — это чужой убыток, а не раздача нашей прибыли.

Чего пункт НЕ делает и делать не будет: не выходит автоматически и не
предсказывает вершину. Он говорит «пора смотреть» и называет причину;
решение остаётся за человеком — ровно как со входом.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from analytics_pulse import PULSE_PATH

# Календарная половина: за сколько дней до даты история теряет смысл.
# Тот же горизонт, что у календаря частокола (Р-7) и связки (Р-12) —
# один на весь проект, чтобы не объяснять разницу при расхождении.
EXIT_DEADLINE_DAYS = 5

# Потоковая половина. Раздача = OI прибавил при цене, которая стоит
# или падает. Пороги прикидочные (Р-9 заменит процентилями), но
# асимметричные намеренно: рост OI должен быть ЗАМЕТНЫМ, а движение
# цены — всего лишь невыразительным. Раздача не требует падения; ей
# достаточно, чтобы цена перестала расти, пока плечо прибывает.
EXIT_OI_UP_PCT = 8.0
EXIT_PX_FLAT_PCT = 1.0
EXIT_FLOW_HOURS = 24

# Сделочная половина: сколько крупных продаж на свежем хвосте считать
# сигналом. Двойка, а не единица: одна крупная продажа бывает у любой
# монеты в любой день, две подряд — уже поведение.
EXIT_BIG_SELLS = 2


def _pulse_flow(symbol: str, hours: int = EXIT_FLOW_HOURS) -> dict | None:
    """Ход цены и OI по монете за последние часы. None — нет ряда."""
    try:
        with open(PULSE_PATH, encoding="utf-8") as f:
            rows = (json.load(f) or {}).get(symbol) or []
    except (OSError, ValueError):
        return None
    if len(rows) < 3:
        return None
    now_t = float(rows[-1].get("t") or 0)
    cut = now_t - hours * 3600
    window = [r for r in rows if float(r.get("t") or 0) >= cut]
    if len(window) < 2:
        return None
    first, last = window[0], window[-1]
    try:
        p0, p1 = float(first["price"]), float(last["price"])
        o0, o1 = float(first["oi_usd"]), float(last["oi_usd"])
    except (KeyError, TypeError, ValueError):
        return None
    if p0 <= 0 or o0 <= 0:
        return None
    return {"px": (p1 / p0 - 1) * 100.0, "oi": (o1 / o0 - 1) * 100.0}


def exit_watch(star: dict, calendar_items: list[dict] | None = None) -> dict:
    """Сигнал «пора смотреть» по трём половинам.

    star — словарь звезды (в нём уже лежат unlockDays, chg, bigSells).
    calendar_items — items из составляющей calendar разрешения (Р-7);
    макродаты общие для всей выборки и приходят снаружи, а не читаются
    здесь заново.

    Возвращает {"watch": bool, "why": [...], "deadlineDays": int|None}.
    Пустой список причин — не «всё хорошо», а «поводов смотреть нет
    СЕЙЧАС»: правило не выносит вердикта о позиции.
    """
    why: list[str] = []
    deadline: int | None = None

    # Половины 1 и 3 имеют смысл только на монете ВЫШЕ входа: мы
    # защищаем прибыль от истощения, а не убыток от углубления — тем
    # занят стоп (Р-17).
    try:
        above = float(star.get("chg") or 0.0) > 0
    except (TypeError, ValueError):
        above = False

    # ── 1. Календарь монеты ──
    days = star.get("unlockDays")
    if days is not None:
        try:
            d = int(days)
        except (TypeError, ValueError):
            d = -1
        if 0 <= d <= EXIT_DEADLINE_DAYS:
            deadline = d
            when = ("сегодня" if d == 0 else
                    "завтра" if d == 1 else f"через {d} дн")
            why.append(f"транш {when} — дедлайн истории")

    # ── 1б. Календарь рынка (Р-7) ──
    for it in (calendar_items or []):
        if it.get("kind") in ("risk", "unlock") and not it.get("running"):
            d = int(it.get("days") or 0)
            if d <= EXIT_DEADLINE_DAYS:
                deadline = d if deadline is None else min(deadline, d)
                why.append(f"{it.get('title')} через {d} дн — рынок качнёт")
                break            # одного макро-повода достаточно

    # ── 2. Поток: OI против цены ──
    flow = _pulse_flow(str(star.get("t") or "") + "USDT")
    if flow and above:
        if flow["oi"] >= EXIT_OI_UP_PCT and flow["px"] <= EXIT_PX_FLAT_PCT:
            why.append(f"OI +{flow['oi']:.0f}% при цене {flow['px']:+.0f}% "
                       "— толпу завели, идёт раздача")

    # ── 3. Крупные продажи выше входа ──
    try:
        sells = int(star.get("bigSells") or 0)
        buys = int(star.get("bigBuys") or 0)
    except (TypeError, ValueError):
        sells = buys = 0
    if above and sells >= EXIT_BIG_SELLS and sells > buys:
        why.append(f"крупных продаж {sells} против {buys} покупок")

    return {"watch": bool(why), "why": why, "deadlineDays": deadline}
