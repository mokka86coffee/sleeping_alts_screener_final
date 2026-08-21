"""Общее для render_dashboard.py и render_orbit.py · Ч-8 тех.долга.

Раньше эти функции и константы жили в render_dashboard.py, а
render_orbit.py доставал их отложенным (внутрифункционным) импортом:
render_dashboard.py импортирует render_orbit на уровне модуля
(`from render_orbit import render_orbit`), и обратный импорт на уровне
модуля дал бы цикл. Обходили это восемью отложенными `from
render_dashboard import ...` внутри разных функций orbit.py — рабочим,
но хрупким приёмом: новый помощник в этом наборе нужно было заводить
в dashboard.py и не забыть протащить в нужную функцию orbit.py.

Модуль без зависимостей от dashboard.py и orbit.py решает это раз и
навсегда: оба импортируют отсюда на уровне модуля, третьей стороной,
и цикла нет в принципе.
"""

from __future__ import annotations

from core_models import Candidate
from render_theme import esc

# ─────────────────────────────────────────────────────────────
# Хелперы
# ─────────────────────────────────────────────────────────────
def _num(c: Candidate, key: str, default: float = 0.0) -> float:
    try:
        return float((c.raw or {}).get(key) or default)
    except (TypeError, ValueError):
        return default


def _get(obj, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _tick(c: Candidate) -> str:
    return esc(c.symbol.replace("USDT", ""))


def _pick(slices: list[dict], sid: str) -> dict:
    for s in slices:
        if s["id"] == sid:
            return s
    return {"id": sid, "label": sid, "note": "", "items": []}


# ─────────────────────────────────────────────────────────────
# Константы, общие для дашборда и орбиты
# ─────────────────────────────────────────────────────────────

# Порядок узлов ленты FLOW фиксирован макетом, cx пересчитаны
# из холста 1200×950 в локальный viewBox (сдвиг x−352, y−410).
FLOW_NODES = [
    ("dormant",   85, 24.0, "спит после падения",   True),
    ("hidden",   124, 22.0, "скрытый набор",        True),
    ("spring",   165, 16.0, "сжатие в тишине",      False),
    ("churn",    221, 35.0, "объём есть, цена стоит", True),
    ("fuel",     287, 26.0, "сверху пусто",         True),
    ("taker",    335, 19.0, "сменился агрессор",    False),
    ("lever", 373, 13.0, "шорты перегружены",    False),
]

RR_MIN = "2"
SURGE_NOTE = "монет · surge ≥ 4×"        # было "surge ≥ 3×"
IMP_NOTE = "rvol ≥ 2.2× сейчас"
# BTC_D-константа убрана (Ч-9 тех.долга): доминация теперь читается
# по-настоящему через core_binance.get_btc_dominance() в местах,
# которые её показывают, а не подставляется числом-заглушкой.
