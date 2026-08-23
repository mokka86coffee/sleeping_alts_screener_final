"""Разлоки токенов: ручные данные о том, когда в рынок придёт предложение.

Единственная величина в проекте, которая смотрит ВПЕРЁД. Всё остальное —
импакт, отскоки, вершина, пузыри — описывает прошлое и надеется, что оно
повторится. Расписание разлоков известно заранее и от наших расчётов не
зависит.

Почему руками. У DefiLlama раздел unlocks в платном тарифе ($300/мес), у
DropsTab свой коммерческий API, а страницы собираются на клиенте и
скрейпингу не поддаются. При этом расписание меняется раз в квартал, а не
раз в час: для тридцати монет журнала это разовая работа и правка строки,
когда транш отработал. Тот же случай, что manual_fields — граница данных,
а не ошибка расчёта.

Путь к файлу держится здесь, а не в core_config, по той же причине, что и
у manual_fields: это собственные данные модуля, а не настройка поведения.

Три правила, вынесенные из разбора LAB и BLESS:

1. Пустая запись означает НЕТ ДАННЫХ, а не отсутствие разлоков. Наружу
   уходит пустой словарь, отрисовка показывает пробел. Ноль здесь соврал
   бы: незаполненная монета выглядела бы безопасной.

2. Размер меряется В ТОКЕНАХ: долей от всей эмиссии и долей от
   циркуляции. Дни оборота считать нельзя, и это не мелочь — знаменатель
   заражён ровно тем, что мы ищем. Оборот берётся текущий, а карточку
   смотрят в момент всплеска, когда он выше нормы в десятки раз. Тот же
   транш на пампе выглядит безобидным именно тогда, когда он опаснее
   всего: в этот всплеск и раздают. Токены на токены не делятся ни на
   цену, ни на объём, и «4.7% эмиссии» значит одно и то же в тишине и на
   разгоне.

   Двух долей мало по одиночке и достаточно вместе: доля от эмиссии
   говорит о масштабе события, доля от циркуляции — о давлении на то
   предложение, которое уже торгуется. У BLESS сентябрьский транш это
   4.7% эмиссии и 18% циркуляции; вторая цифра и объясняет, почему такое
   событие рынок отрабатывает заранее.

3. Считается расстояние до даты, а не сама дата. LAB обвалилась за пять
   дней ДО разлока: рынок отрабатывает событие заранее, и чем крупнее
   транш, тем раньше.

Вердикт модуль не выносит. Отдаёт дни, доли и признак инсайдерского
транша; «опасно» или «пора выходить» решает человек.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

# Файл лежит рядом с модулем: правится руками, ходит вместе с кодом.
UNLOCKS_PATH = Path(__file__).resolve().parent / "unlocks.json"

# Кэш на время процесса с проверкой времени правки. Планировщик крутит
# прогоны в одном процессе, и закешированное навсегда расписание
# устарело бы на первой же правке файла.
_CACHE: dict = {"mtime": None, "data": {}}


def _load() -> dict:
    """Содержимое файла. Любая ошибка означает «данных нет»."""
    try:
        mtime = UNLOCKS_PATH.stat().st_mtime
    except OSError:
        return {}

    if _CACHE["mtime"] != mtime:
        try:
            raw = json.loads(UNLOCKS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _CACHE["data"]
        _CACHE["data"] = {k: v for k, v in raw.items() if not k.startswith("_")}
        _CACHE["mtime"] = mtime
    return _CACHE["data"]


def _days_until(iso: str, today: date | None = None) -> int | None:
    """Сколько дней до даты. Отрицательное значит уже прошло."""
    try:
        when = datetime.strptime(iso[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    now = today or datetime.now(timezone.utc).date()
    return (when - now).days


def for_symbol(symbol: str, quote_volume_24h: float = 0.0,
               today: date | None = None) -> dict:
    """Ближайший разлок и постоянные величины монеты.

    quote_volume_24h нужен, чтобы перевести объём разлока в дни оборота —
    без него величина не считается, но остальное отдаётся.

    Пустой словарь означает, что монеты нет в файле. Это не «разлоков
    нет», а «не заполняли», и отрисовка обязана показать пробел.
    """
    rec = (_load() or {}).get(symbol) or {}
    if not rec:
        return {}

    out: dict = {}
    for key in ("circ_pct", "fdv_ratio", "insiders_now", "insiders_final",
                "events_done", "events_total"):
        if rec.get(key) is not None:
            out[key] = rec[key]
    if rec.get("inferred"):
        # Часть расписаний DefiLlama выводит из графика источника, а не из
        # документов проекта. Такие числа на экране обязаны отличаться от
        # подтверждённых, иначе мы сами создаём ложную точность.
        out["inferred"] = True
    if rec.get("source"):
        out["source"] = rec["source"]
    if rec.get("checked_at"):
        out["checked_at"] = rec["checked_at"]

    # Доля инсайдеров, которая РАСТЁТ, говорит больше любого отдельного
    # события: значит всё невыпущенное идёт к ним.
    now_, fin = rec.get("insiders_now"), rec.get("insiders_final")
    if now_ is not None and fin is not None:
        out["insiders_grow"] = round(float(fin) - float(now_), 1)

    events = [e for e in (rec.get("events") or []) if e.get("date")]
    ahead = []
    for e in events:
        days = _days_until(e["date"], today)
        if days is None or days < 0:
            continue
        ahead.append((days, e))
    if not ahead:
        return out

    ahead.sort(key=lambda p: p[0])
    days, ev = ahead[0]
    out["next_days"] = days
    out["next_date"] = ev["date"][:10]
    if ev.get("usd") is not None:
        out["next_usd"] = float(ev["usd"])
        if quote_volume_24h > 0:
            out["next_days_vol"] = round(float(ev["usd"]) / quote_volume_24h, 2)
    if ev.get("pct_float") is not None:
        out["next_pct_float"] = float(ev["pct_float"])
    if ev.get("pct_supply") is not None:
        out["next_pct_supply"] = float(ev["pct_supply"])
    # Доля ОБРАЩЕНИЯ выводится из доли эмиссии, когда своей нет:
    # pct_supply / circ_pct. Это арифметика единиц, а не новое
    # правило — ступени Р-27 считаются по обращению, и событие с
    # заполненной эмиссией, но пустым float молчало (HYPE 29.08:
    # 1.4% эмиссии при 22.2% в обращении = 6.3% обращения — ступень
    # «сократить», а не фон). Найдено 23.08 по молчанию HEMI.
    if out.get("next_pct_float") is None and out.get("next_pct_supply") is not None:
        try:
            circ = float(rec.get("circ_pct") or 0.0)
        except (TypeError, ValueError):
            circ = 0.0
        if circ > 0:
            out["next_pct_float"] = round(
                float(out["next_pct_supply"]) / circ * 100.0, 1)

    rounds = ev.get("rounds") or []
    if rounds:
        ins = [r for r in rounds if r.get("insider")]
        out["next_insider"] = bool(ins)
        # Доля инсайдерской части в самом событии: транш в фонд или на
        # экосистему до рынка может и не дойти, поэтому сумма без этого
        # разделения переоценивает давление.
        total = sum(float(r.get("usd") or 0) for r in rounds)
        if total > 0:
            share = sum(float(r.get("usd") or 0) for r in ins) / total
            out["next_insider_share"] = round(share * 100, 1)
        out["next_rounds"] = [str(r.get("name") or "") for r in rounds][:6]

    if len(ahead) > 1:
        out["next_after_days"] = ahead[1][0]
    return out
