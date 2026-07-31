from __future__ import annotations

from dataclasses import asdict, dataclass, field

from detectors.flow_core import FlowContext, build_context
from detectors.flow_signal import SubcaseSignal

import detectors.flow_churn as flow_churn
import detectors.flow_fuel as flow_fuel
import detectors.flow_spring as flow_spring

MIN_SCORE = 45

# Реестр подкейсов. Добавление нового модуля — одна строка здесь,
# candidate.py и scoring.py не трогаются.
_RUNNERS = (
    flow_spring,
    flow_churn,
    flow_fuel,
)

# Приоритет при близком скоре. Spring выше churn: взведённая
# пружина — более зрелая фигура, чем одиночное поглощение,
# у неё за спиной серия попыток, а не одно событие.
CASE_PRIORITY = {
    "flow_spring": 3,
    "flow_churn": 2,
    "flow_fuel": 2,
    "flow_hidden": 1,
    "flow_taker": 1,
    "none": 0,
}

# Разница меньше этого — подкейсы считаются равными, решает зрелость.
TIE_MARGIN = 5


@dataclass
class FlowSignal:
    """Публичный сигнал семейства. Один на монету.

    Контракт с candidate.py: detected, score, case, strength_label,
    horizon_days, verdict, to_dict(). Эти поля не меняются при
    добавлении новых подкейсов — воронку править больше не нужно.
    """

    symbol: str = ""

    detected: bool = False
    score: int = 0
    case: str = "none"
    strength_label: str = ""

    horizon_days: int = 0
    horizon_tf: str = ""
    horizon_readable: bool = False

    cases: dict = None
    verdict: str = ""

    parts: list[dict] = field(default_factory=list)
    context: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.cases is None:
            self.cases = {}

    def to_dict(self) -> dict:
        return asdict(self)


def _strength(score: int) -> str:
    if score >= 75:
        return "экстремальный"
    if score >= 60:
        return "сильный"
    if score >= MIN_SCORE:
        return "умеренный"
    return ""


def _to_family_score(raw: float) -> int:
    """Приводит шкалу подкейса 0..100 к шкале семейства 45..100.

    scoring.py отображает 45..100 в 14..34 и на входе ниже 45 даёт
    отрицательные баллы. Подкейсы про эту шкалу не знают и не
    должны: они меряют силу фигуры, а не место монеты в отчёте.
    """
    raw = max(0.0, min(100.0, raw))
    return int(round(MIN_SCORE + raw * (100 - MIN_SCORE) / 100))


def _horizon(ctx: FlowContext) -> dict:
    """Ярлык времени. В пороги и скор не входит."""
    days = ctx.horizon_bars
    return {
        "wait_days": days,
        "label": ctx.horizon_label,
        "readable": ctx.horizon_scale > 1,
    }


def _verdict(name: str, sig: SubcaseSignal) -> str:
    """Собирает вердикт из причин победителя.

    Причины уже отсортированы по порядку применения: сначала
    качество фигуры, затем контекст. Берём первые три — дальше
    идут поправки, они интересны только при разборе ошибок.
    """
    head = {
        "flow_spring": "Пружина",
        "flow_churn": "Поглощение на уровне",
        "flow_fuel": "Карта предложения",
    }.get(name, "Поток")

    if not sig.reasons:
        return f"{head}."
    body = "; ".join(sig.reasons[:3])
    return f"{head}: {body}."


def detect_flow(symbol: str, quote_volume_24h: float = 0.0) -> FlowSignal:
    """Прогоняет подкейсы по общему контексту и возвращает сильнейший.

    Контекст считается ОДИН раз: дневки берутся из RunCache,
    агрегаты строятся из них, поэтому масштабы бесплатны. Дорогие
    сетевые запросы (funding, OI) делаются только после
    срабатывания дневного ядра — без него detected всё равно ложь.
    """
    ctx = build_context(symbol, quote_volume_24h)
    if not ctx.valid:
        return FlowSignal(symbol=symbol)

    results: list[tuple[str, SubcaseSignal]] = []
    for module in _RUNNERS:
        try:
            sig = module.detect(ctx)
        except Exception:
            # Падение одного подкейса не должно ронять семейство:
            # монет двести, а модулей пять.
            continue
        if sig is not None:
            results.append((sig.subcase, sig))

    cases = {
        name: {
            "score": round(sig.score, 1),
            "reasons": sig.reasons[:3],
            "mults": sig.mults,
        }
        for name, sig in results
    }

    if not results:
        return FlowSignal(symbol=symbol, cases={}, context=ctx.to_dict())

    # ── Победитель ───────────────────────────────────────────
    # Сравниваем по скору, при близких значениях решает зрелость
    # фигуры: разница в пару баллов между подкейсами ничего не
    # значит, а зрелость значит. Пружина над подтверждённой зоной
    # надёжнее одиночного поглощения даже при равном числе.
    best_name, best_sig = results[0]
    for name, sig in results[1:]:
        if sig.score > best_sig.score + TIE_MARGIN:
            best_name, best_sig = name, sig
        elif abs(sig.score - best_sig.score) <= TIE_MARGIN:
            if CASE_PRIORITY.get(name, 0) > CASE_PRIORITY.get(best_name, 0):
                best_name, best_sig = name, sig

    score = _to_family_score(best_sig.score)
    if score < MIN_SCORE:
        # Фигура собралась, но вклад символический. Разбор
        # отдаём — воронке нужно видеть, насколько не дотянули.
        return FlowSignal(
            symbol=symbol,
            score=score,
            cases=cases,
            context=ctx.to_dict(),
        )

    hz = _horizon(ctx)
    verdict = _verdict(best_name, best_sig)
    if hz["readable"] and hz["wait_days"]:
        verdict += (
            f" Картина читается на {hz['label']}, "
            f"ожидание порядка {hz['wait_days']} дней."
        )

    return FlowSignal(
        symbol=symbol,
        detected=True,
        score=score,
        case=best_name,
        strength_label=_strength(score),
        horizon_days=hz["wait_days"],
        horizon_tf=hz["label"],
        horizon_readable=hz["readable"],
        cases=cases,
        verdict=verdict,
        parts=[
            {
                "zone_price": best_sig.zone_price,
                "reasons": best_sig.reasons,
                "facts": best_sig.facts,
                "mults": best_sig.mults,
            }
        ],
        context=ctx.to_dict(),
    )
