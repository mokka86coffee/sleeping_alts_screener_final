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
# Узлы ленты FLOW: ключ подкейса, подпись, положение, размер, описание,
# подчёркивание.
#
# Ключ и подпись РАЗДЕЛЕНЫ, и это не украшательство. Раньше подпись
# получалась из ключа через .upper(), поэтому узел плеча назывался
# "lever" — коротко, чтобы влезть в кольцо радиусом 13. А detectors_flow
# зовёт этот подкейс "leverage", и счётчик by_case.get("lever") не
# находил своих монет НИКОГДА: узел плеча стоял потушенным с нулём при
# любом состоянии рынка. Совместить одно имя с двумя требованиями —
# совпасть с детектором и влезть в кольцо — нельзя, поэтому их двое.
FLOW_NODES = [
    ("dormant",  "DORMANT",  85, 24.0, "спит после падения",     True),
    ("hidden",   "HIDDEN",  124, 22.0, "скрытый набор",          True),
    ("spring",   "SPRING",  165, 16.0, "сжатие в тишине",        False),
    ("churn",    "CHURN",   221, 35.0, "объём есть, цена стоит", True),
    ("fuel",     "FUEL",    287, 26.0, "сверху пусто",           True),
    ("taker",    "TAKER",   335, 19.0, "сменился агрессор",      False),
    ("leverage", "LEVER",   373, 13.0, "шорты перегружены",      False),
]

RR_MIN = "2"
SURGE_NOTE = "монет · surge ≥ 4×"        # было "surge ≥ 3×"
IMP_NOTE = "rvol ≥ 2.2× сейчас"
# BTC_D-константа убрана (Ч-9 тех.долга): доминация теперь читается
# по-настоящему через core_binance.get_btc_dominance() в местах,
# которые её показывают, а не подставляется числом-заглушкой.
