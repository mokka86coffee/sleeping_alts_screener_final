"""Скрытое накопление.

Цена не растёт, поток растёт. Набор идёт в стакан, свеча его не
показывает — потому и «скрытое». Подкейс не предсказывает выход
наверх, он лишь фиксирует, что накопление состоялось, и отдаёт
это дальше с горизонтом ожидания.

Контракт: возврат SubcaseSignal либо None. Отказ — это None,
а не объект с флагом: диспетчер третьего состояния не знает и
пустышку положил бы в results наравне с закрытой фигурой.
"""

from __future__ import annotations

from detectors.flow_config import (
    HIDDEN_BUY_SHARE_MIN,
    HIDDEN_DELTA_SLOPE_MIN,
    HIDDEN_HOMOGENEITY_MIN,
    HIDDEN_HORIZON_BARS,
    HIDDEN_MIN_BARS,
    HIDDEN_MIN_QUOTE_24H,
    HIDDEN_MULT_NO_ZONE,
    HIDDEN_MULT_RECOVERY,
    HIDDEN_MULT_ZONE,
    HIDDEN_PRICE_SLOPE_MAX,
    HIDDEN_SCORE_BASE,
    HIDDEN_VOLUME_RECOVERY_MIN,
    HIDDEN_VORTEX_WEIGHT,
    HIDDEN_WINDOW,
    VOLUME_RECOVERY_GOOD,
)
from detectors.flow_core import FlowContext, _clip, _slope
from detectors.flow_signal import SubcaseSignal, veto_bullish

# Имя совпадает с ключом в CASE_CAP и CASE_PRIORITY диспетчера.
# Расхождение оставляло подкейс без потолка и роняло приоритет.
NAME = "flow_hidden"
name = NAME


def detect(ctx: FlowContext) -> SubcaseSignal | None:
    """Расхождение цены и потока на окне наблюдения.

    Порядок проверок не произволен: сначала то, что делает замер
    бессмысленным целиком, затем сама фигура, затем уточнения.
    Обвал дельты стоит до расхождения намеренно — на панике дельта
    растёт по модулю, и без этой отсечки подкейс читал бы слив
    как набор.
    """
    # Зоны необязательны: набор бывает и вне размеченного уровня,
    # уровень здесь усиливает фигуру, а не создаёт её.
    if veto_bullish(ctx, require_zones=False):
        return None

    bars = ctx.base
    if len(bars) < HIDDEN_MIN_BARS:
        return None

    # Ликвидность. На тонкой монете дельта — это две сделки,
    # и любая форма на ней случайна.
    if ctx.quote_volume_24h < HIDDEN_MIN_QUOTE_24H:
        return None

    flow = ctx.flow

    # Само расхождение — два условия, и оба обязательны.
    window = min(HIDDEN_WINDOW, len(bars))
    price_slope = _slope([b.close for b in bars[-window:]])
    if price_slope > HIDDEN_PRICE_SLOPE_MAX:
        return None
    if flow.delta_slope < HIDDEN_DELTA_SLOPE_MIN:
        return None

    # Набор, собранный одним баром, — разовый вход, а не накопление.
    if flow.homogeneity < HIDDEN_HOMOGENEITY_MIN:
        return None

    # Растущая дельта при паритете сторон — артефакт разметки.
    if flow.buy_share < HIDDEN_BUY_SHARE_MIN:
        return None

    # Ноль от ядра означает «мерить нечего», а не «объём мёртв»:
    # порогом проверяется только измеренная величина.
    if 0 < ctx.volume_recovery < HIDDEN_VOLUME_RECOVERY_MIN:
        return None

    # ── Фигура закрыта ─────────────────────────────────────
    # Опора под набором: протестированный уровень с наибольшей
    # массой тиров — там уже доказано, что предложение снимают.
    zone = ctx.pick_zone_below(key=lambda z: (z.tests, z.tier_sum))

    sig = SubcaseSignal(
        subcase=NAME,
        score=HIDDEN_SCORE_BASE,
        base_score=HIDDEN_SCORE_BASE,
        horizon_bars=HIDDEN_HORIZON_BARS,
        zone_price=(zone.price if zone is not None else 0.0),
    )

    sig.add(
        "цена стоит, поток растёт",
        price_slope=price_slope,
        delta_slope=flow.delta_slope,
        buy_share=flow.buy_share,
    )
    sig.add("набор размазан по окну", homogeneity=flow.homogeneity)

    # Превышение порога наклона. Ограничено удвоением: дальше
    # величина говорит уже об импульсе, а не о скрытом наборе.
    excess = _clip(flow.delta_slope / HIDDEN_DELTA_SLOPE_MIN - 1.0, 0.0, 1.0)
    sig.apply("наклон", 1.0 + excess)

    # Однородность работает штрафом: на самом пороге режет вдвое.
    sig.apply("однородность", 0.5 + 0.5 * flow.homogeneity)

    # Форма вортекса с весом подкейса. Доверие к замеру входит
    # внутрь mult(), поэтому вне коридора множитель слабее.
    sig.apply("вортекс", ctx.vortex.mult(HIDDEN_VORTEX_WEIGHT))

    if zone is not None:
        sig.apply("уровень", HIDDEN_MULT_ZONE)
        sig.add(
            "набор стоит на уровне",
            zone_price=zone.price,
            zone_tests=zone.tests,
            zone_strength=zone.strength,
        )
    else:
        sig.apply("без уровня", HIDDEN_MULT_NO_ZONE)

    if ctx.volume_recovery >= VOLUME_RECOVERY_GOOD:
        sig.apply("объём вернулся", HIDDEN_MULT_RECOVERY)
        sig.add("интерес после дна восстановлен", recovery=ctx.volume_recovery)

    return sig
