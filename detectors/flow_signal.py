"""FLOW · контракт подкейса.

Каждый подкейс семейства получает готовый FlowContext и возвращает
FlowSignal либо None. Ничего не считает сам сверх своей фигуры, не
лезет в сеть, не знает о других подкейсах.

Правило разграничения: подкейс молчит, если его фигура не закрыта.
Слабый сигнал хуже отсутствия — он разбавляет топ и съедает место
у монеты, где фигура собралась целиком.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from detectors.flow_core import FlowContext


# ─────────────────────────────────────────────────────────────
# Результат
# ─────────────────────────────────────────────────────────────

@dataclass
class SubcaseSignal:
    """Закрытая фигура одного подкейса.

    Внутренний тип семейства. Наружу через detectors/__init__
    выходит только FlowSignal из flow.py — сведённый результат
    диспетчера. Разные сущности, разные имена: подкейс описывает
    одну фигуру, FlowSignal описывает монету.

    score — сырой вклад в шкале 0..100 ДО сведения. Приведением
    к диапазону семейства 45..100 занимается flow.py.
    """

    subcase: str
    score: float
    horizon_bars: int

    # Что именно сработало — для карточки и для разбора ошибок.
    reasons: list[str] = field(default_factory=list)

    # Числа, на которых построен вывод. Идут в карточку как есть.
    facts: dict[str, float] = field(default_factory=dict)

    # Множители, применённые к базовому скору. Хранятся отдельно,
    # чтобы при разборе кейса было видно, что именно урезало вклад.
    mults: dict[str, float] = field(default_factory=dict)

    # Уровень зоны, вокруг которой построена фигура. 0 — фигура
    # не привязана к уровню.
    zone_price: float = 0.0

    def __post_init__(self) -> None:
        self.score = max(0.0, min(100.0, float(self.score)))
        self.horizon_bars = max(1, int(self.horizon_bars))

    @property
    def weak(self) -> bool:
        """Фигура формально собралась, но вклад символический."""
        return self.score < 20.0

    def apply(self, name: str, mult: float) -> None:
        """Применяет множитель и запоминает его.

        Множители применяются последовательно и не коммутируют с
        отсечками, поэтому порядок вызовов внутри подкейса важен:
        сначала качество фигуры, затем контекст, затем вето.
        """
        mult = max(0.0, float(mult))
        self.score = max(0.0, min(100.0, self.score * mult))
        self.mults[name] = round(mult, 3)

    def add(self, reason: str, **facts: float) -> None:
        """Добавляет причину и связанные с ней числа."""
        self.reasons.append(reason)
        for key, value in facts.items():
            self.facts[key] = round(float(value), 6)


# ─────────────────────────────────────────────────────────────
# Протокол
# ─────────────────────────────────────────────────────────────

class Subcase(Protocol):
    """Интерфейс подкейса.

    Реализуется функцией detect(ctx) в каждом flow_*.py. Протокол
    нужен не ради типизации как таковой, а чтобы flow_family мог
    держать реестр подкейсов списком и не знать их внутренностей.
    """

    name: str

    def __call__(self, ctx: FlowContext) -> SubcaseSignal | None:
        ...


# ─────────────────────────────────────────────────────────────
# Общие вето
# ─────────────────────────────────────────────────────────────
# Проверки, которые обязаны отработать до любой фигуры. Вынесены
# сюда, чтобы подкейсы не дублировали их с расхождениями.

def veto_common(ctx: FlowContext) -> str | None:
    """Возвращает причину отказа либо None.

    Порядок проверок — от самых дешёвых к самым содержательным.
    """
    if not ctx.ready:
        return "мало истории"

    if ctx.growth_x >= ctx.extreme_growth_x:
        # Толпа с многократной прибылью продавливает любой уровень:
        # зоны под ней не держат, поглощение не значит ничего.
        return f"экстремальный рост перед падением (x{ctx.growth_x:.1f})"

    if not ctx.zones:
        return "нет живых зон"

    return None


def veto_bullish(ctx: FlowContext) -> str | None:
    """Дополнительные вето для подкейсов, играющих от разворота.

    Отделены от veto_common: flow_churn на распределении и
    flow_leverage смотрят на ту же картину с другой стороны, и
    обвал дельты для них не помеха.
    """
    base = veto_common(ctx)
    if base:
        return base

    if ctx.flow.collapsing:
        # Дельта валится вертикально: столкновение состоялось,
        # победитель не определён. Фигура ещё не фигура.
        return f"обвал дельты (наклон {ctx.flow.delta_slope:.4f})"

    return None
