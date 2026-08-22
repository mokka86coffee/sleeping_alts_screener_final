"""Разрешение рынка (Р-1, минимальный состав) и индекс альтсезона (Р-19).

Одна величина на весь прогон: можно ли сегодня вообще заходить.
Считается ИЗ УЖЕ СКАЧАННОГО — дневки биткоина в кэше, фандинг лежит в
raw каждой монеты, день недели бесплатный. Ни одного нового запроса.

Что этот модуль ПЕЧАТАЕТ и чего НЕ делает — по нулевому разделу
техдолга: окно влияет на порядок показа и на подпись, но не на скор и
не на стратегию. Наружу идут состояния составляющих и их причины
словами; бинарного вердикта «не входить» здесь нет и не будет —
попытка свести условия к порогу-приговору названа в техдолге ошибкой
того же рода, что и прежние.

Состав — минимальный, и это записано прямо. Из пяти составляющих Р-1
здесь считаются три (биткоин, день недели, фандинг по выборке) и
принципиально помечается отсутствие двух: суммарный OI по выборке
появится с десятиминутным циклом Р-8 (истории OI по всем монетам в
raw нет — она есть только у монет со сработавшим FLOW, и считать
«выборку» по ним значило бы мерить хвост, виляющий собакой), разлоки
по рынку — с Р-7. Отсутствие честнее нулей: строка «нет данных»
отличима от строки «всё спокойно».

ПОРОГИ ПРЕДУПРЕЖДЕНИЙ — ПЕРВАЯ ПРИКИДКА, НЕ ИСТИНА. Каждый обязан
получить процентиль против собственной истории (Р-9) вместо
абсолюта. Они вынесены в константы с именами и живут здесь до замера,
а не вместо него.
"""

from __future__ import annotations

import json

from analytics_calendar import calendar_state
from analytics_metrics import weekend_state
from analytics_pulse import PULSE_PATH
from analytics_reservoir import reservoir_state
from core_models import Candidate

# ── Пороги-прикидки (заменить процентилями по Р-9) ─────────────

# «Сильный рост биткоина — не сигнал заходить, а предупреждение»:
# он почти всегда заканчивается сквизом или откатом и тянет рынок.
# 19.08 биткоин прошёл +11% за двое суток — 22-го альты собрали иглы.
BTC_SURGE_1D_PCT = 8.0
BTC_SURGE_7D_PCT = 15.0

# Перекос фандинга: после выноса шортов толпа переворачивается в
# лонг, держать лонг платно, слабые руки выносит первыми. По пробе
# BTC 22.08: 91 период подряд положительный, отрицательных ноль.
#
# Порог один на оба хвоста: перекос — это перекос, с какой стороны
# ни смотри. Разное У НИХ следствие, и оно ниже, в компоненте.
FUNDING_CROWD_SHARE = 0.70

# Раздутие суммарного OI по выборке: условие каскада, не предсказание
# момента. Прикидка; 19–21.08 сквиз дал +8% за 48ч БЕЗ раздутия по
# этому порогу — и каскад 22.08 всё равно случился, потому что бил по
# перекосу толпы, а не по сумме. Порог живёт до процентилей Р-9.
OI_SWELL_48H_PCT = 15.0

# Каскад прямо сейчас (Р-2): доля монет, у которых на ПОСЛЕДНЕМ шаге
# пульса одновременно упал OI и дёрнулась цена. Калибровка на живом
# событии 22.08: каскадное окно дало 82% выборки при фоне 0–16% с
# медианой ~5% — порог 25% отделяет с многократным запасом с обеих
# сторон.
CASCADE_SHARE = 0.25
CASCADE_OI_DROP = 0.97   # OI ниже 97% прошлой точки = падение
CASCADE_PX_JERK = 0.03   # цена дальше ±3% за шаг = игла


def _btc_component(btc: dict | None) -> dict:
    """Состояние биткоина: ход за сутки и неделю, предупреждение о рывке."""
    if not btc:
        return {"known": False, "warn": False, "note": "биткоин: нет данных"}
    d1 = float(btc.get("ch_24h") or 0.0)
    d7 = float(btc.get("ch_7d") or 0.0)
    surge = d1 >= BTC_SURGE_1D_PCT or d7 >= BTC_SURGE_7D_PCT
    note = f"BTC {d1:+.1f}% за сутки · {d7:+.1f}% за неделю"
    if surge:
        note += " — рывок, окно каскада"
    return {"known": True, "warn": surge, "d1": round(d1, 1),
            "d7": round(d7, 1), "note": note}


def _weekend_component(now=None) -> dict:
    """Выходные — тонкий стакан. Правило уже жило в голове; теперь в данных."""
    state = weekend_state(now)
    if state == "now":
        return {"known": True, "warn": True, "state": state,
                "note": "выходные — тонкий стакан"}
    if state == "soon":
        return {"known": True, "warn": False, "state": state,
                "note": "пятница — ликвидность уходит к вечеру"}
    return {"known": True, "warn": False, "state": "", "note": ""}


def _funding_component(candidates: list[Candidate]) -> dict:
    """Перекос фандинга по выборке. ТОПЛИВО ИМЕЕТ СТОРОНУ.

    Симметрия обязательна, и хвосты НЕ равнозначны. Перекос в лонг —
    предупреждение: это топливо каскада против нас, слабые руки
    выносит первыми. Перекос в шорт — НЕ предупреждение и НЕ сигнал
    входа: это строка состояния «заряжено вверх». Ровно она была
    измерима перед 19 августа, когда четыре миллиарда шортов стали
    горючим хода, а новостной фон говорил ждать продолжения падения.
    Момент поджига (повод) в данных не бывает — печатается только
    заряд.

    Наружу: side — "long" / "short" / "" (без перекоса).
    """
    vals = []
    for c in candidates:
        try:
            vals.append(float((c.raw or {}).get("funding") or 0.0))
        except (TypeError, ValueError):
            continue
    if not vals:
        return {"known": False, "warn": False, "side": "",
                "note": "фандинг: нет данных"}
    pos = sum(1 for v in vals if v > 0) / len(vals)
    neg = sum(1 for v in vals if v < 0) / len(vals)
    if pos >= FUNDING_CROWD_SHARE:
        return {"known": True, "warn": True, "side": "long",
                "posShare": round(pos, 2),
                "note": f"фандинг положителен у {pos * 100:.0f}% выборки "
                        "— толпа в лонге, топливо каскада"}
    if neg >= FUNDING_CROWD_SHARE:
        return {"known": True, "warn": False, "side": "short",
                "posShare": round(pos, 2),
                "note": f"фандинг отрицателен у {neg * 100:.0f}% выборки "
                        "— толпа в шорте, топливо сквиза вверх"}
    return {"known": True, "warn": False, "side": "",
            "posShare": round(pos, 2),
            "note": f"фандинг положителен у {pos * 100:.0f}% выборки"}


def _pulse_series() -> dict:
    """Ряды пульса как лежат: {symbol: [точки]}. Пульс пишет вся
    выборка каждый прогон (analytics_pulse.record), окно 48 часов.
    Нет файла — пустой словарь: составляющие честно скажут «нет
    данных», как OI-заглушка говорила до подключения."""
    try:
        with open(PULSE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items()
            if k != "_meta" and isinstance(v, list) and len(v) >= 2}


def _oi_component(series: dict) -> dict:
    """Суммарный OI по выборке и его ход. ОКНА — В ПОДПИСИ (24ч/48ч):
    рост OI на часах и на месяцах — разные величины с разными
    смыслами (Р-10), и здесь печатаются только короткие окна пульса."""
    if not series:
        return {"known": False, "warn": False,
                "note": "суммарный OI: пульса нет"}
    def total(frac: float) -> float:
        tot = 0.0
        for rows in series.values():
            v = rows[min(int(len(rows) * frac), len(rows) - 1)].get("oi_usd")
            if v:
                tot += float(v)
        return tot
    now, d24, d48 = total(0.999), total(0.5), total(0.0)
    if not (now and d48):
        return {"known": False, "warn": False,
                "note": "суммарный OI: в пульсе нет oi_usd"}
    ch24 = now / d24 * 100 - 100 if d24 else 0.0
    ch48 = now / d48 * 100 - 100
    swollen = ch48 >= OI_SWELL_48H_PCT
    note = (f"OI выборки ${now / 1e9:.1f} млрд · "
            f"{ch24:+.0f}% за 24ч · {ch48:+.0f}% за 48ч")
    if swollen:
        note += " — раздут, топливо каскада накоплено"
    return {"known": True, "warn": swollen, "usd": round(now),
            "ch24": round(ch24, 1), "ch48": round(ch48, 1), "note": note}


def _cascade_component(series: dict) -> dict:
    """Каскад прямо сейчас: рыночное событие, а не монетное (Р-2).

    Считает долю монет, у которых на последнем шаге пульса
    ОДНОВРЕМЕННО упал OI и дёрнулась цена. Одна монета так падает от
    собственных новостей; две трети выборки в одну метку времени —
    это движок закрывает счета, и внутрь такого не входят.
    """
    if not series:
        return {"known": False, "warn": False, "note": "каскад: пульса нет"}
    n = hit = 0
    for rows in series.values():
        p, r = rows[-2], rows[-1]
        if not (p.get("oi_usd") and r.get("oi_usd")
                and p.get("price") and r.get("price")):
            continue
        n += 1
        if (r["oi_usd"] < p["oi_usd"] * CASCADE_OI_DROP
                and abs(r["price"] / p["price"] - 1) > CASCADE_PX_JERK):
            hit += 1
    if not n:
        return {"known": False, "warn": False, "note": "каскад: нет пар точек"}
    share = hit / n
    live = share >= CASCADE_SHARE
    note = f"каскадных монет на последнем шаге: {share * 100:.0f}%"
    if live:
        note += " — каскад идёт, движок закрывает счета"
    return {"known": True, "warn": live, "share": round(share, 2),
            "note": note}


def market_permission(candidates: list[Candidate],
                      btc: dict | None,
                      now=None) -> dict:
    """Разрешение рынка минимальным составом.

    Возвращает составляющие с их причинами словами плюс счёт
    предупреждений — ЧИСЛО, не вердикт. Как читать счёт и когда
    подписывать топ «списком наблюдения», решает показ (Р-6), а не
    этот модуль: здесь состояние, там правило показа.
    """
    pulse = _pulse_series()
    parts = {
        "btc": _btc_component(btc),
        "weekend": _weekend_component(now),
        "funding": _funding_component(candidates),
        # Резервуарный контур (Р-20): ручной файл, одно число в
        # неделю. warn не поднимает никогда — гейт объясняет, а не
        # предупреждает; см. docstring reservoir_state.
        "reservoir": reservoir_state(),
        # Календарь частокола (Р-7): единственная составляющая, которая
        # знает БУДУЩЕЕ — даты поводов известны заранее, сами поводы в
        # наших данных не бывают. Предупреждает только риск в окне
        # ожидания; поддержка и фон известны, но не запрещают.
        "calendar": calendar_state(),
        # Плечевой контур из пульса: заглушка «появится с Р-8»
        # закрыта 22.08 — пульс уже пишет oi_usd по всей выборке
        # каждый прогон, десятиминутный цикл для этого не нужен.
        "oi": _oi_component(pulse),
        "cascade": _cascade_component(pulse),
        # Заглушка разлоков снята 22.08: их место занял календарь
        # (записи kind="unlock"). Отдельная составляющая означала бы
        # два источника одного факта — а BLESS 23.09 и HYPE 6.09
        # ничем не отличаются от прочего частокола, кроме адресности.
    }
    known = [p for p in parts.values() if p["known"]]
    warns = [p["note"] for p in known if p["warn"]]
    return {
        "parts": parts,
        "knownCount": len(known),
        "warnCount": len(warns),
        # Причины словами — их и печатать. Пустой список тоже ответ.
        "warns": warns,
    }


def altseason_share(candidates: list[Candidate],
                    btc: dict | None) -> dict:
    """Р-19: доля монет выборки, обошедших биткоин. ОКНО — В ИМЕНИ КЛЮЧА.

    d1 и d7 — это РАЗНЫЕ величины, а не уточнения друг друга (Р-10), и
    обе несравнимы с публичным индексом альтсезона: тот считается на
    90 днях и запаздывает по построению. Наши короткие окна опережают —
    ценой шума; поэтому наружу идут оба, а не среднее.

    По сути это Р-5, применённая ко всему рынку сразу: не «альты
    выросли», а «альты обошли биткоин за то же окно».
    """
    if not btc:
        return {}
    out: dict = {}
    for key, raw_key in (("d1", "ch_24h"), ("d7", "ch_7d"),
                         ("d30", "ch_30d")):
        # Нет базы по биткоину за это окно — нет и доли: сравнение с
        # нулём вместо биткоина посчитало бы «долю выросших», другую
        # величину под тем же именем. get_btc_context отдаёт ch_30d
        # не всегда — тогда ключа d30 просто нет.
        if btc.get(raw_key) is None:
            continue
        try:
            base = float(btc[raw_key])
        except (TypeError, ValueError):
            continue
        vals = []
        for c in candidates:
            v = (c.raw or {}).get(raw_key)
            if v is None:
                continue
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                continue
        if not vals:
            continue
        ahead = sum(1 for v in vals if v > base) / len(vals)
        out[key] = round(ahead * 100)

    return out
