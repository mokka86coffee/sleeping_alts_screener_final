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

from analytics_metrics import weekend_state
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


def market_permission(candidates: list[Candidate],
                      btc: dict | None,
                      now=None) -> dict:
    """Разрешение рынка минимальным составом.

    Возвращает составляющие с их причинами словами плюс счёт
    предупреждений — ЧИСЛО, не вердикт. Как читать счёт и когда
    подписывать топ «списком наблюдения», решает показ (Р-6), а не
    этот модуль: здесь состояние, там правило показа.
    """
    parts = {
        "btc": _btc_component(btc),
        "weekend": _weekend_component(now),
        "funding": _funding_component(candidates),
        # Резервуарный контур (Р-20): ручной файл, одно число в
        # неделю. warn не поднимает никогда — гейт объясняет, а не
        # предупреждает; см. docstring reservoir_state.
        "reservoir": reservoir_state(),
        # Честные заглушки: строка «нет данных» отличима от «спокойно».
        "oi": {"known": False, "warn": False,
               "note": "суммарный OI: появится с циклом Р-8"},
        "unlocks": {"known": False, "warn": False,
                    "note": "разлоки по рынку: появятся с Р-7"},
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
    for key, raw_key in (("d1", "ch_24h"), ("d7", "ch_7d")):
        try:
            base = float(btc.get(raw_key) or 0.0)
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
