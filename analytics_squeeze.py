"""Заряд на сжим (техдолг «сжим на тонком флоате», С-2 и флаг С-1).

Предвестник, а не след: отрицательный фандинг несколько баров подряд
ПРИ растущей цене означает, что коротких больше, чем длинных, и они
уже в убытке — их вынос и есть сжим. Считается целиком из пульса,
ноль новых запросов (С-2). Отдельным флагом — условие тонкого флоата
из С-1 (floatPct < 15 при fdvRatio > 5): сочетание сильнее каждого
по отдельности, но в ОТБОР ни то ни другое отсюда не идёт — порог
объявлен обсуждаемым, решение об отборе за человеком.

По рамке проекта это ЗАРЯД ВВЕРХ, не предупреждение: фандинг
симметричен, шорт-перекос — топливо сжима (та же симметрия, что в
разрешении рынка). Скор не трогается — правило всех техдолгов.

SKYAI (готовый размеченный пример из С-5) в текущем окне пульса
детектор честно НЕ отмечает: там послесжимовое остывание — фандинг
положителен, OI сдувается. Заряд был до пампа, а пульс хранит 48
часов; задним числом такие случаи проверяются только архивом пульса
(решение об архиве уже висит — теперь на нём и С-4/С-5).
"""

from __future__ import annotations

import json

from analytics_pulse import PULSE_PATH

# Сколько подряд минусовых баров считаются зарядом. Три бара пульса —
# около трёх часов: разовый минус на перекосе одной сделки отсеивается,
# устойчивый перекос коротких — нет. Порог поведения не меняет ничьего
# скора и калибруется отдельно, когда появится архив.
SQUEEZE_NEG_BARS = 3

# Условие тонкого флоата из С-1 — как флаг рядом с зарядом.
THIN_FLOAT_PCT = 15.0
THIN_FDV_RATIO = 5.0


def charge_from_rows(rows: list[dict],
                     neg_bars: int = SQUEEZE_NEG_BARS) -> dict:
    """Заряд по ряду точек пульса одной монеты.

    Возвращает {"negRun", "pxChg", "charged", "note"}. negRun — сколько
    подряд последних баров фандинг отрицателен; pxChg — ход цены за эти
    бары в процентах (цена последнего бара к цене перед серией);
    charged — negRun >= neg_bars И цена выше, чем перед серией. note —
    готовая тёплая строка для показа, None если заряда нет.
    """
    out = {"negRun": 0, "pxChg": None, "charged": False, "note": None,
           "capped": False}
    if not rows:
        return out
    run = 0
    for r in reversed(rows):
        f = r.get("funding")
        if f is not None and f < 0:
            run += 1
        else:
            break
    out["negRun"] = run
    if run == 0:
        return out
    # Серия может покрывать всё окно пульса (48 часов): бара «перед
    # серией» тогда просто нет в хранимом ряду. Это не повод молчать —
    # хронический шорт-перекос интереснее разового. Сравниваем цену с
    # первой точкой окна и честно помечаем серию усечённой («48+»).
    capped = run >= len(rows)
    out["capped"] = capped
    base = (rows[0] if capped else rows[-(run + 1)]).get("price")
    last = rows[-1].get("price")
    if not base or not last:
        return out
    chg = (last / base - 1.0) * 100.0
    out["pxChg"] = round(chg, 1)
    if run >= neg_bars and chg > 0:
        out["charged"] = True
        shown = f"{run}+" if capped else f"{run}"
        out["note"] = (f"заряжен: фандинг минус {shown} "
                       f"{_bars_word(run)} при росте {chg:+.1f}% — "
                       f"шорты платят и уже в убытке")
    return out


def discharge_from_rows(rows: list[dict],
                        back: int = 6,
                        oi_drop_pct: float = 8.0) -> dict:
    """С-4: заменитель ликвидаций — РАЗРЯД после сжима.

    Настоящий поток ликвидаций недоступен (Binance закрыл, агрегаторы
    платные). Заменитель из пульса: на отрезке последних `back` баров
    фандинг переходит из минуса в плюс (шорты вынесены), а OI падает
    от пика отрезка не меньше oi_drop_pct (позиции закрыты силой).

    НА ЭКРАН НЕ ВЫВОДИТЬ: документ требует сперва проверить на
    истории, насколько заменитель совпадает с настоящими
    ликвидациями, а истории нет до архива пульса. Функция готова к
    этой проверке — и только к ней.
    """
    out = {"discharged": False, "oiDropPct": None, "fundingFrom": None}
    if len(rows) < back + 1:
        return out
    seg = rows[-(back + 1):]
    funds = [r.get("funding") for r in seg]
    ois = [r.get("oi_usd") for r in seg]
    if any(v is None for v in funds) or any(not v for v in ois):
        return out
    f_min, f_now = min(funds[:-1]), funds[-1]
    peak, now = max(ois), ois[-1]
    drop = (1.0 - now / peak) * 100.0 if peak else 0.0
    out["fundingFrom"] = f_min
    out["oiDropPct"] = round(drop, 1)
    out["discharged"] = f_min < 0 <= f_now and drop >= oi_drop_pct
    return out


def _bars_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "бар"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "бара"
    return "баров"


def thin_float(unlock_state: dict | None) -> bool:
    """Флаг С-1: тонкий флоат при высоком FDV, из уже посчитанного."""
    u = unlock_state or {}
    fp, fr = u.get("floatPct"), u.get("fdvRatio")
    try:
        return (fp is not None and fr is not None and
                float(fp) < THIN_FLOAT_PCT and float(fr) > THIN_FDV_RATIO)
    except (TypeError, ValueError):
        return False


def squeeze_for(symbol: str, unlock_state: dict | None = None) -> dict:
    """Заряд для одной монеты по текущему пульсу.

    Читает пульс сам, как это делает analytics_exit: пульс — общий
    файл, а не поле звезды. При недоступном пульсе — пустой заряд,
    сборка не падает.
    """
    try:
        with open(PULSE_PATH, encoding="utf-8") as f:
            pulse = json.load(f)
    except (OSError, ValueError):
        return {"negRun": 0, "pxChg": None, "charged": False,
                "note": None, "thin": thin_float(unlock_state)}
    rows = pulse.get(symbol)
    # В пульсе рядом с монетами живут служебные ключи (не-списки);
    # заряд считается только по настоящему ряду.
    out = charge_from_rows(rows if isinstance(rows, list) else [])
    # thin считается из переданного состояния, если оно есть; звёзды
    # передают его вторым проходом (см. analytics_stars) — там
    # floatPct/fdvRatio уже разложены, и хвост «флоат тонкий — сжиму
    # есть где разогнаться» дописывается именно там, один раз.
    out["thin"] = thin_float(unlock_state)
    return out
