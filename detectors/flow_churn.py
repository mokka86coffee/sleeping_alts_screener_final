"""FLOW · подкейс churn — поглощение на уровне.

Фигура: аномальный объём приходит на уровень, цена не отвечает.
Кто-то принимает поток лимитом, не давая рынку сдвинуться.

Ключевое отличие от volume_surge: там объём с откликом, здесь —
объём без отклика. Разграничение проходит по response, поэтому
задвоения между семействами нет по построению: один и тот же бар
не может быть одновременно absorbed и не absorbed.

Одиночное поглощение фигурой не является. Оно говорит «здесь
столкнулись», но не говорит, кто победил. Победителя определяет
то, что происходит потом: осталась цена над уровнем или нет.
"""

from __future__ import annotations

from detectors.flow_config import (
    CHURN_MIN_TIER,
    CHURN_NOISE_MIN_VOL,
    HOMOGENEITY_MIN,
    ZONE_NEAR_PCT,
    ZONE_SINGLE_SCALE_WEIGHT,
)
from detectors.flow_core import FlowContext, Zone
from detectors.flow_signal import FlowSignal, veto_bullish

name = "flow_churn"


# ─────────────────────────────────────────────────────────────
# Выбор зоны
# ─────────────────────────────────────────────────────────────

def _pick_zone(ctx: FlowContext) -> Zone | None:
    """Зона, на которой строится фигура.

    Берётся ближайшая к цене снизу — она работает опорой. Зоны
    сверху описывают завал, а не поглощение, и разбираются в
    flow_fuel.
    """
    below = [
        z
        for z in ctx.zones
        if z.price <= ctx.price and z.absorbed_events(CHURN_MIN_TIER)
    ]
    if not below:
        return None

    near = [
        z
        for z in below
        if (ctx.price - z.price) / ctx.price <= ZONE_NEAR_PCT
    ]
    pool = near or below
    return max(pool, key=lambda z: (z.tests, -abs(ctx.price - z.price)))


# ─────────────────────────────────────────────────────────────
# Базовый скор
# ─────────────────────────────────────────────────────────────

def _base_score(zone: Zone) -> tuple[float, dict[str, float]]:
    """Скор от качества самого поглощения.

    Складывается из тира событий, их количества и того, насколько
    плотно цена стояла при аномальном потоке.
    """
    events = zone.absorbed_events(CHURN_MIN_TIER)
    top_tier = max(e.tier for e in events)
    sigma = max(e.sigma for e in events)

    # Тир даёт основу, сигма сверх порога — надбавку.
    score = {2: 38.0, 3: 55.0}.get(top_tier, 30.0)
    score += min(15.0, (sigma - 4.0) * 2.5) if sigma > 4.0 else 0.0

    # Повторное поглощение на одном уровне сильнее одиночного.
    if len(events) >= 3:
        score += 12.0
    elif len(events) == 2:
        score += 7.0

    facts = {
        "tier": float(top_tier),
        "sigma": sigma,
        "events": float(len(events)),
        "zone_price": zone.price,
    }
    return score, facts


# ─────────────────────────────────────────────────────────────
# Детект
# ─────────────────────────────────────────────────────────────

def detect(ctx: FlowContext) -> FlowSignal | None:
    """Собирает фигуру churn либо возвращает None."""

    if veto_bullish(ctx):
        return None

    zone = _pick_zone(ctx)
    if zone is None:
        return None

    # Фон обязан быть шумным. Поглощение в тишине — это не
    # поглощение, а отсутствие торговли: принимать нечего.
    if ctx.flow.rel_volume < CHURN_NOISE_MIN_VOL:
        return None

    score, facts = _base_score(zone)
    sig = FlowSignal(
        subcase=name,
        score=score,
        horizon_bars=ctx.horizon_bars,
        zone_price=zone.price,
    )
    sig.add(
        f"поглощение на {zone.price:.6g}: тир {int(facts['tier'])}, "
        f"событий {int(facts['events'])}",
        **facts,
    )

    # ── Плато: главный множитель фигуры ──────────────────────
    # Без выдержанного диапазона над зоной вклад режется более чем
    # вдвое. Именно плато отличает отработавшую фигуру от заготовки.
    sig.apply("plateau", zone.plateau_mult)
    if zone.plateau_bars > 0:
        sig.add(
            f"плато над зоной {zone.plateau_bars} дней",
            plateau_bars=float(zone.plateau_bars),
        )

    # ── Подтверждение масштабами ─────────────────────────────
    if len(zone.scales) < 2:
        sig.apply("single_scale", ZONE_SINGLE_SCALE_WEIGHT)
        sig.add("подтверждено одним масштабом", scales=1.0)
    else:
        sig.add(
            f"подтверждено масштабами {sorted(zone.scales)}",
            scales=float(len(zone.scales)),
        )

    # ── Тесты уровня ─────────────────────────────────────────
    # Каждый успешный тест — свидетельство, что принимавший
    # остался на месте. Возраст события при этом роли не играет.
    if zone.tests >= 2:
        sig.apply("tested", 1.15)
        sig.add(
            f"уровень выдержал {zone.tests} теста",
            tests=float(zone.tests),
            last_test_age=float(zone.last_test_age),
        )
    elif zone.tests == 0:
        sig.apply("untested", 0.8)
        sig.add("уровень ещё не тестировался", tests=0.0)

    # ── Однородность потока ──────────────────────────────────
    # Вклад, сделанный одним баром, не описывает намерение:
    # это может быть разовая выгрузка, а не работа на уровне.
    if ctx.flow.homogeneity < HOMOGENEITY_MIN:
        sig.apply("lumpy", 0.75)
        sig.add(
            "поток неоднороден",
            homogeneity=ctx.flow.homogeneity,
        )

    # ── Восстановление объёма ────────────────────────────────
    if ctx.volume_recovery >= 1.0:
        sig.apply("recovery", 1.1)
        sig.add(
            f"объём восстановился (x{ctx.volume_recovery:.2f})",
            volume_recovery=ctx.volume_recovery,
        )

    # ── Недоверие за рост ────────────────────────────────────
    # Чем сильнее был рост перед падением, тем больше зон обязано
    # провалиться прежде, чем нижней можно верить.
    need = ctx.distrust_zones
    if need and zone.zones_below < need:
        sig.apply("distrust", 0.7)
        sig.add(
            f"под зоной ещё {need - zone.zones_below} несработавших уровня",
            zones_below=float(zone.zones_below),
        )

    return sig if not sig.weak else None
