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
Поэтому плато здесь обязательно — в отличие от spring, где фигурой
является само сжатие.
"""

from __future__ import annotations

import math

from detectors.flow_config import (
    CHURN_DIST_PENALTY,
    CHURN_MIN_TIER,
    CHURN_NOISE_MIN_VOL,
    CHURN_TEST_WEIGHT,
    HOMOGENEITY_MIN,
    TIER_3_SIGMA,
    VORTEX_MULT_MAX,
    ZONE_SINGLE_SCALE_WEIGHT,
)
from detectors.flow_core import FlowContext, Zone
from detectors.flow_signal import SubcaseSignal, veto_bullish

name = "flow_churn"


# ─────────────────────────────────────────────────────────────
# Выбор зоны
# ─────────────────────────────────────────────────────────────

def _zone_quality(zone: Zone, price: float) -> float:
    """Пригодность зоны как основы фигуры churn.

    Прежний вариант сравнивал кортеж (tests, plateau_bars, -dist).
    Лексикографический порядок означает диктатуру первого поля: зона
    с тремя тестами побеждала зону с одним при любых остальных
    показателях. На MMT это дало выбор уровня с двумя событиями и
    tier_sum 4 вместо соседнего с шестью событиями, tier_sum 16 и
    поглощением 0.83 — сильнее по всем осям сразу, но с одним
    тестом вместо трёх. Скор упал до 44.3, монета не добрала порог.

    Здесь считается произведение двух сомножителей.

    МАССА отвечает на вопрос, было ли столкновение существенным:
    сколько поглощённых событий и какого тира легло на уровень.
    ЗРЕЛОСТЬ отвечает на вопрос, кто победил: плато и тесты — это
    поведение цены ПОСЛЕ столкновения, а именно оно и определяет
    исход. Сильное событие без истории — заготовка; скромное
    событие с плато в полтора месяца — состоявшийся уровень.

    Произведение, а не сумма: обнуление любого сомножителя должно
    обнулять пригодность. Уровень без поглощений не churn, уровень
    без истории тоже не churn.
    """
    events = zone.absorbed_events(CHURN_MIN_TIER)
    if not events:
        return 0.0

    # Масса: сумма тиров поглощённых событий, приглушённая корнем.
    # Линейный рост дал бы диктатуру количества — двадцать слабых
    # событий перевесили бы три сильных, хотя описывают они разное.
    mass = sum(e.tier for e in events) ** 0.5

    # Зрелость: плато в днях плюс вклад тестов. Тест весомее одного
    # дня стояния — это активная проверка уровня, а не пассивное
    # удержание, поэтому идёт с множителем.
    maturity = zone.plateau_bars + zone.tests * CHURN_TEST_WEIGHT
    if maturity <= 0:
        # Уровень свежий: история ещё не написана. Не отбрасываем
        # совсем — фигура может быть в стадии формирования, — но
        # ставим в конец очереди.
        maturity = 0.5

    # Близость к цене — удобство входа, а не аргумент за уровень.
    # Входит слабым множителем, чтобы при прочих равных выбирался
    # ближний, но не перебивал разницу в качестве.
    dist = abs(price - zone.price) / price if price > 0 else 1.0
    proximity = 1.0 / (1.0 + dist * CHURN_DIST_PENALTY)

    return mass * maturity * proximity


def _pick_zone(ctx: FlowContext) -> Zone | None:
    """Зона, на которой строится фигура.

    Берутся уровни под ценой: они работают опорой. Зоны сверху
    описывают завал, а не поглощение, и разбираются в flow_fuel.

    Фильтр близости снят. Прежнее `pool = near or below` отбрасывало
    весь остальной список, стоило хоть одной зоне попасть в
    ZONE_NEAR_PCT: на KAITO это отсекло уровень с плато 46 дней и
    четырьмя тестами в пользу соседнего с плато 3 бара. Расстояние
    теперь учитывается внутри скора как слабый множитель — ближний
    выигрывает при прочих равных, но не перебивает разницу в
    качестве уровня.
    """
    below = [
        z for z in ctx.zones
        if z.price <= ctx.price and z.absorbed_events(CHURN_MIN_TIER)
    ]
    if not below:
        return None

    best = max(below, key=lambda z: _zone_quality(z, ctx.price))
    return best if _zone_quality(best, ctx.price) > 0 else None


# ─────────────────────────────────────────────────────────────
# Базовый скор
# ─────────────────────────────────────────────────────────────

def _base_score(zone: Zone) -> tuple[float, dict[str, float]]:
    """Скор от качества самого поглощения.

    Складывается из тира событий, их силы в сигмах и количества
    поглощений на уровне.
    """
    events = zone.absorbed_events(CHURN_MIN_TIER)
    top_tier = max(e.tier for e in events)
    sigma = max(e.sigma for e in events)

    # Тир даёт основу. Ветки ниже второго тира нет намеренно:
    # CHURN_MIN_TIER = 2 гарантирует, что такие события в выборку
    # не попадают, и третье значение в словаре было бы мёртвым.
    score = 55.0 if top_tier >= 3 else 38.0

    # Сила сверх порога тира — надбавка по ЛОГАРИФМИЧЕСКОЙ шкале.
    #
    # Прежняя линейная формула min(15, (sigma - 4) * 2.5) упиралась
    # в потолок при sigma = 10 и выдавала ровно 15 практически
    # всем: в прогоне UNI дала 15.7, ON — 33.5, MMT — 80.8.
    # Слагаемое перестало различать фигуры, то есть выродилось
    # в константу.
    #
    # Большие значения не дефект ядра: robust_sigma делит на MAD,
    # и на плотной выборке отношение вырастает до десятков.
    # Величина честная, но её распределение имеет длинный хвост,
    # и линейная шкала на нём неработоспособна по построению.
    #
    # log2 от порога тира: sigma 8 → 4 балла, 16 → 8, 32 → 12,
    # потолок при 64. Различение восстановлено на всём
    # наблюдаемом диапазоне.
    if sigma > TIER_3_SIGMA:
        score += min(15.0, math.log2(sigma / TIER_3_SIGMA) * 4.0)

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

def detect(ctx: FlowContext) -> SubcaseSignal | None:
    """Собирает фигуру churn либо возвращает None."""
    if veto_bullish(ctx):
        return None

    zone = _pick_zone(ctx)
    if zone is None:
        return None

    # Фон обязан быть шумным. Поглощение в тишине — это не
    # поглощение, а отсутствие торговли: принимать нечего.
    # rel_volume жил в FlowState прежней редакции; в новом ядре
    # относительный объём правого края лежит в самом контексте.
    if ctx.rel_vol < CHURN_NOISE_MIN_VOL:
        return None

    score, facts = _base_score(zone)

    sig = SubcaseSignal(
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
    # Без выдержанного диапазона над зоной вклад режется: именно
    # плато отличает отработавшую фигуру от заготовки. Мягкий
    # вариант множителя здесь НЕ применяется — он для spring.
    sig.apply("plateau", zone.plateau_mult())
    if zone.plateau_bars > 0:
        sig.add(
            f"плато над зоной {zone.plateau_bars} дней",
            plateau_bars=float(zone.plateau_bars),
        )
    else:
        sig.add("плато над зоной не набралось", plateau_bars=0.0)

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

# ── Вортекс: кто победил в столкновении ──────────────────
    # Снижающиеся пики продаж означают, что предложение слабеет.
    # Для churn это ответ на главный вопрос фигуры: столкновение
    # состоялось, исход определяет то, что происходит дальше.
    vx = ctx.vortex
    if vx.direction == "up":
        sig.apply("vortex_up", min(VORTEX_MULT_MAX, vx.mult(0.4)))
        sig.add(
            f"вортекс на масштабе {vx.scale}D: предложение слабеет "
            f"(выраженность {vx.strength:.2f}, согласие {vx.confidence:.1f})",
            vortex_scale=float(vx.scale),
            vortex_strength=vx.strength,
            vortex_confidence=vx.confidence,
        )
    elif vx.direction == "down":
        sig.apply("vortex_down", 0.8)
        sig.add(
            f"вортекс на масштабе {vx.scale}D: пики продаж растут",
            vortex_scale=float(vx.scale),
            vortex_strength=vx.strength,
        )

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
