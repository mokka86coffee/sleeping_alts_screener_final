"""FLOW · диспетчер семейства.

Один сигнал на монету. Контекст считается один раз, подкейсы
прогоняются по нему, сильнейший становится вердиктом.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from detectors.flow_config import (
    CAP_CHURN,
    CAP_FUEL,
    CAP_HIDDEN,
    CAP_LEVERAGE,
    CAP_SPRING,
    CAP_TAKER,
    FLOW_MAX_SCORE,
    FLOW_MIN_RAW_SCORE,
    FLOW_MIN_SCORE,
)
from detectors.flow_core import FlowContext, build_context
from detectors.flow_signal import SubcaseSignal

import detectors.flow_churn as flow_churn
import detectors.flow_fuel as flow_fuel
import detectors.flow_hidden as flow_hidden
import detectors.flow_leverage as flow_leverage
import detectors.flow_spring as flow_spring
import detectors.flow_taker as flow_taker

# Нижняя точка шкалы семейства. Согласована со scoring.py:
# отображение 45..100 → 14..34, ниже 45 даёт отрицательный вклад.
MIN_SCORE = FLOW_MIN_SCORE

# Порог на СЫРОЙ шкале подкейса. Отдельное имя, и это принципиально:
# raw и score живут в разных шкалах, и раньше порог проверялся уже
# после приведения — то есть не проверялся вовсе. Отображение
# монотонно, поэтому даже нулевая фигура давала ровно MIN_SCORE.
#
# Сейчас величины совпадают, но связаны они не по смыслу, а по
# калибровке: сырой порог можно поднять, не трогая шкалу.
MIN_RAW_SCORE = FLOW_MIN_RAW_SCORE

# Реестр подкейсов. Добавление нового модуля — одна строка здесь,
# candidate.py и scoring.py не трогаются. Порядок на исход не
# влияет: победитель выбирается по скору, а не по позиции.
_RUNNERS = (
    flow_hidden,
    flow_spring,
    flow_churn,
    flow_taker,
    flow_fuel,
    flow_leverage,
)

# Подкейсы, которые ходят в сеть сверх дневок. Нужно знать по
# именам, а не по флагу внутри модуля: при отладке сеть выключается
# снаружи, и модуль об этом знать не обязан.
NETWORK_CASES = frozenset({"flow_leverage"})

# Приоритет при близком скоре. Hidden выше всех — единственный
# опережающий подкейс. Spring выше churn: взведённая пружина —
# более зрелая фигура, чем одиночное поглощение, у неё за спиной
# серия попыток, а не одно событие.
CASE_PRIORITY = {
    "flow_hidden": 4,
    "flow_spring": 3,
    "flow_churn": 2,
    "flow_taker": 1,
    "flow_fuel": 1,
    "flow_leverage": 1,
    "none": 0,
}

# Потолки подкейсов. Отражают зрелость модуля, а не силу фигуры:
# сырой скор выше потолка означает, что модуль переоценивает себя.
CASE_CAP = {
    "flow_hidden": CAP_HIDDEN,
    "flow_spring": CAP_SPRING,
    "flow_churn": CAP_CHURN,
    "flow_taker": CAP_TAKER,
    "flow_fuel": CAP_FUEL,
    "flow_leverage": CAP_LEVERAGE,
}

# Разница меньше этого — подкейсы считаются равными, решает зрелость.
TIE_MARGIN = 5

# Совпадение двух независимых фигур на одной монете — отдельный
# факт, а не сумма баллов. Складывать скоры нельзя: подкейсы не
# независимы, они читают одну карту зон. Но и игнорировать нельзя.
CONFIRM_BONUS = 6
CONFIRM_MIN_RAW = 35        # спутник ниже этого подтверждением не считается

_HEADS = {
    "flow_hidden": "Скрытый набор",
    "flow_spring": "Пружина",
    "flow_churn": "Поглощение на уровне",
    "flow_taker": "Смена агрессора",
    "flow_fuel": "Карта предложения",
    "flow_leverage": "Перекос в плече",
}

_TAILS = {
    "flow_hidden": "скрытым набором",
    "flow_spring": "сжатием",
    "flow_churn": "поглощением на уровне",
    "flow_taker": "сменой агрессора",
    "flow_fuel": "снятым предложением сверху",
    "flow_leverage": "перегруженностью шортов",
}


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

    # Исключения подкейсов: имя модуля → текст ошибки. В обычном
    # прогоне пусто. Существует потому, что молчащий подкейс и
    # упавший подкейс выглядят одинаково, а причины разные:
    # первое — свойство рынка, второе — опечатка в коде.
    failures: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.cases is None:
            self.cases = {}

    def to_dict(self) -> dict:
        return asdict(self)


def _strength(score: int) -> str:
    if score >= 85:
        return "экстремальный"
    if score >= 70:
        return "сильный"
    if score >= MIN_SCORE:
        return "умеренный"
    return ""


def _to_family_score(raw: float) -> int:
    """Приводит сырую шкалу подкейса к шкале семейства 45..100.

    Отображается НЕ 0..100, а диапазон, который реально может
    прийти: от MIN_RAW_SCORE до 100. Порог проверяется выше по
    коду, значит меньшие значения сюда не попадают, и растягивать
    от нуля означает выбросить нижнюю половину шкалы семейства.

    Прежняя формула давала минимум 70 при заявленном 45: ярлык
    «умеренный» был недостижим, а весь наблюдаемый разброс
    сырых скоров 45..75 сжимался в 70..86.
    """
    raw = max(MIN_RAW_SCORE, min(100.0, raw))
    span_raw = 100.0 - MIN_RAW_SCORE          # 55
    span_out = FLOW_MAX_SCORE - MIN_SCORE     # 55
    return int(round(
        MIN_SCORE + (raw - MIN_RAW_SCORE) * span_out / span_raw
    ))


def _horizon(ctx: FlowContext) -> dict:
    """Ярлык времени. В пороги и скор не входит."""
    return {
        "wait_days": ctx.horizon_bars,
        "label": ctx.horizon_label,
        "readable": ctx.horizon_scale > 1,
    }


def _verdict(name: str, sig: SubcaseSignal, confirmed_by: str = "") -> str:
    """Собирает вердикт из причин победителя.

    Причины уже отсортированы по порядку применения: сначала
    качество фигуры, затем контекст. Берём первые три — дальше идут
    поправки, они интересны только при разборе ошибок.
    """
    head = _HEADS.get(name, "Поток")

    if not sig.reasons:
        text = f"{head}."
    else:
        text = f"{head}: {'; '.join(sig.reasons[:3])}."

    if confirmed_by:
        tail = _TAILS.get(confirmed_by, "вторым подкейсом")
        text += f" Подтверждено {tail}."

    return text


def detect_flow(
    symbol: str,
    quote_volume_24h: float = 0.0,
    allow_network: bool = True,
) -> FlowSignal:
    """Прогоняет подкейсы по общему контексту и возвращает сильнейший.

    Контекст считается ОДИН раз: дневки берутся из RunCache, агрегаты
    строятся из них, поэтому масштабы бесплатны.

    allow_network выключает подкейсы, которым нужны funding и OI.
    Нужно для быстрой отладки дневного ядра: два лишних запроса на
    монету при двухстах монетах — это минуты, а на выводы о зонах
    и событиях они не влияют.
    """
    ctx = build_context(symbol, quote_volume_24h)
    if not ctx.valid:
        return FlowSignal(symbol=symbol)

    results: list[tuple[str, SubcaseSignal]] = []
    failures: dict[str, str] = {}

    for module in _RUNNERS:
        # __name__ у импортированного модуля полный: "detectors.flow_leverage".
        # Сравнение с NETWORK_CASES по нему всегда ложно, и allow_network
        # молча перестаёт действовать — сеть выключается снаружи, а модуль
        # об этом не узнаёт. Атрибут name объявлен протоколом Subcase, но
        # опираться только на него нельзя: его отсутствие не ошибка импорта,
        # оно ничем себя не проявляет.
        mod_name = getattr(module, "name", module.__name__.rsplit(".", 1)[-1])

        if not allow_network and mod_name in NETWORK_CASES:
            continue

        try:
            sig = module.detect(ctx)
        except Exception as exc:
            # Падение одного подкейса не должно ронять семейство:
            # монет двести, а модулей шесть. Но и терять ошибку
            # молча нельзя — иначе неработающий модуль выглядит
            # как модуль, которому нечего сказать.
            failures[mod_name] = f"{type(exc).__name__}: {exc}"
            continue

        if sig is None:
            continue

        # Потолок зрелости. Применяется здесь, а не в подкейсе:
        # модуль не обязан знать, насколько ему доверяют.
        #
        # Дефолта нет сознательно. Значение по умолчанию 100 снимало
        # бы потолок с модуля, чьё имя не нашлось в таблице, — то есть
        # ровно с того, где ограничение и нужно. Промах по ключу это
        # дефект кода, а не свойство рынка, и он обязан быть виден.
        cap = CASE_CAP.get(sig.subcase)
        if cap is None:
            failures[mod_name] = (
                f"нет потолка для subcase={sig.subcase!r}; "
                f"ожидались {sorted(CASE_CAP)}"
            )
            cap = min(CASE_CAP.values())
        if sig.score > cap:
            sig.score = float(cap)

        results.append((sig.subcase, sig))

    cases = {
        name: {
            "score": round(sig.score, 1),
            "base": round(sig.base_score, 1),
            "cut": round(sig.cut, 2),
            "reasons": sig.reasons[:3],
            "mults": sig.mults,
        }
        for name, sig in results
    }

    if not results:
        return FlowSignal(
            symbol=symbol,
            cases={},
            context=ctx.to_dict(),
            failures=failures,
        )

    # ── Победитель ───────────────────────────────────────────
    # Двухпроходный выбор, и это необходимость, а не стиль.
    # Однопроходный цикл со сравнением «лучше текущего» здесь
    # неприменим: отношение предпочтения не транзитивно. Подкейс A
    # проигрывает B по зрелости, B проигрывает C по скору, но A мог
    # бы обойти C — и исход зависел от того, в каком порядке они
    # встретились, то есть от порядка модулей в _RUNNERS. На рынок
    # эта величина не влияет никак.
    #
    # Сначала берём максимум по скору как опорную точку, затем
    # среди всех, кто отстал не больше чем на TIE_MARGIN, выбираем
    # самого зрелого. Разница в пару баллов между подкейсами ничего
    # не значит, а зрелость фигуры значит.
    top_score = max(s.score for _, s in results)
    contenders = [
        (n, s) for n, s in results
        if s.score >= top_score - TIE_MARGIN
    ]
    best_name, best_sig = max(
        contenders,
        key=lambda x: (CASE_PRIORITY.get(x[0], 0), x[1].score),
    )

    raw = best_sig.score

    # ── Подтверждение вторым подкейсом ───────────────────────
    # Две независимые фигуры на одной монете сильнее одной. Бонус
    # фиксированный и небольшой: подкейсы читают общую карту зон,
    # то есть частично коррелированы, и складывать их скоры было
    # бы двойным счётом.
    confirmed_by = ""
    others = [
        (n, s) for n, s in results
        if n != best_name and s.score >= CONFIRM_MIN_RAW
    ]
    if others:
        confirmed_by = max(others, key=lambda x: x[1].score)[0]
        # Бонус не имеет права пробивать потолок зрелости. Кап
        # выражает доверие к модулю, а подтверждение соседом
        # доверия к модулю не добавляет — оно добавляет веса
        # конкретной фигуре. Иначе fuel при потолке 80 отдавал бы
        # 86, и ограничение работало бы только там, где монета
        # неинтересна.
        cap = CASE_CAP.get(best_name, 100)
        raw = min(float(cap), raw + CONFIRM_BONUS)

    # ── Порог ────────────────────────────────────────────────
    # Проверяется на СЫРОЙ шкале. После приведения проверять
    # бессмысленно: нижняя точка отображения равна порогу.
    if raw < MIN_RAW_SCORE:
        # Фигура собралась, но вклад символический. Разбор
        # отдаём — воронке нужно видеть, насколько не дотянули.
        return FlowSignal(
            symbol=symbol,
            score=int(round(raw)),
            cases=cases,
            context=ctx.to_dict(),
            failures=failures,
        )

    score = _to_family_score(raw)
    hz = _horizon(ctx)
    verdict = _verdict(best_name, best_sig, confirmed_by)

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
        failures=failures,
    )
