"""FLOW · SPRING — сжатие диапазона плюс поглощение в тишине.

Эталон: AKE. Диапазон сжат до минимума, объём невелик, но серия
попыток набора идёт одна за другой и цена не двигается. Каждая
проваливающаяся попытка съедает встречную ликвидность; когда она
кончается, следующая попытка той же силы проходит без сопротивления —
отсюда вертикаль.

Ключевое отличие от volume_surge: там сигналом служит сам всплеск
объёма, здесь — ОТСУТСТВИЕ отклика на приложенную силу. Пружина
взводится в тишине, а не в шуме.

Абсолютный порог сжатия обязателен. Отношение ATR30/ATR180 после
краша врёт: знаменатель раздут обвалом, и монета с восьмипроцентным
дневным ходом формально выглядит «успокоившейся». HOLO отсекается
именно этим, AKE проходит с запасом.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from core.binance import K_CLOSE, K_HIGH, K_LOW, klines_1d
from detectors.flow_core import (
    FlowEvent,
    aggregate,
    cluster_zones,
    detect_events,
    drop_forming,
    extreme_growth_before,
    flow_homogeneity,
    mean,
    median,
    merge_zones,
    obv_recovery,
    pct_change,
    slope,
    zone_confirmed,
)

# ── История ──
MIN_HISTORY_DAYS = 90

# ── Сжатие ──
ATR_FAST = 30
ATR_SLOW = 180
DORMANCY_MAX = 0.62          # относительное сжатие
DORMANT_ABS_MAX = 0.055      # абсолютный потолок: средний дневной ход к цене
RANGE_WINDOW = 30            # окно замера коридора
RANGE_MAX_PCT = 70.0         # реалистичный «тихий» коридор для альта

# ── Поглощение ──
PRESSURE_WINDOW = 40         # где ищем серию попыток
MIN_ATTEMPTS = 3             # одиночное событие пружину не взводит
ABSORBED_SHARE_MIN = 0.7     # доля провалившихся попыток в серии
HOMOGENEITY_MIN = 0.45       # ровное давление против одиночного сброса

# ── Расхождение силы и отклика ──
DECOUPLING_MIN = 2.0

MIN_SCORE = 45


@dataclass
class SpringSignal:
    """Взведённая пружина: сила прикладывается, цена не отвечает."""

    detected: bool = False
    score: int = 0

    # сжатие
    dormancy: float = 0.0            # ATR30 / ATR180
    atr_abs: float = 0.0             # средний ход как доля цены
    range_pct: float = 0.0           # ширина коридора
    compressed: bool = False

    # поглощение
    attempts: int = 0
    absorbed: int = 0
    absorbed_share: float = 0.0
    dominant_side: str = ""          # buy (белое, лонг) | sell (красное, шорт)
    homogeneity: float = 0.0
    decoupling: float = 0.0          # сила на единицу отклика

    # контекст
    obv_recovering: bool = False
    obv_suspicious: bool = False
    growth_mult: float = 0.0
    zones_to_skip: int = 0
    zone_level: float = 0.0
    zone_tfs: tuple = ()

    verdict: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["zone_tfs"] = list(self.zone_tfs)
        return d


def _atr(highs, lows, closes, period: int) -> float:
    """Средний истинный диапазон за период, в абсолютных единицах."""
    n = len(closes)
    if n < period + 1:
        return 0.0
    trs = []
    for i in range(n - period, n):
        if i < 1:
            continue
        trs.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    return mean(trs)


def _compression(highs, lows, closes) -> tuple[float, float, float, bool]:
    """Сжат ли диапазон — по трём независимым мерам.

    Абсолютная мера (atr_abs) — ОБЯЗАТЕЛЬНА. Она отсекает монеты,
    которые «успокоились» до восьми процентов в день.

    Коридор проверяет, что цена стоит, а не медленно сползает.

    Относительная (dormancy) — достаточна, но НЕ необходима.
    После краша она врёт: знаменатель раздут обвалом, и монета
    с восьмипроцентным ходом формально выглядит успокоившейся.
    Обратный случай тоже реален: монета может ровно стоять весь год
    и не иметь никакого затухания относительно самой себя. Поэтому
    её заменяет более строгий абсолютный порог.
    """
    price = closes[-1] if closes else 0.0
    if price <= 0:
        return 0.0, 0.0, 0.0, False

    atr_fast = _atr(highs, lows, closes, ATR_FAST)
    atr_slow = _atr(highs, lows, closes, ATR_SLOW) or atr_fast

    dormancy = atr_fast / atr_slow if atr_slow > 0 else 1.0
    atr_abs = atr_fast / price

    seg_h = highs[-RANGE_WINDOW:]
    seg_l = lows[-RANGE_WINDOW:]
    lo = min(seg_l) if seg_l else 0.0
    hi = max(seg_h) if seg_h else 0.0
    range_pct = pct_change(lo, hi) if lo > 0 else 999.0

    quiet_abs = atr_abs <= DORMANT_ABS_MAX
    very_quiet = atr_abs <= DORMANT_ABS_MAX * 0.75
    compressed = (
        quiet_abs
        and range_pct <= RANGE_MAX_PCT
        and (dormancy <= DORMANCY_MAX or very_quiet)
    )
    return dormancy, atr_abs, range_pct, compressed


def _absorption(events: list[FlowEvent], kl: list) -> dict:
    """Серия попыток, которые не сдвинули цену.

    Считаем не отдельное событие, а серию: одиночный провал
    ничего не значит — шорт набирают и под смену тренда, и под
    локальный сквиз. Решает совокупность.

    Сторона серии задаёт направление будущего выхода. Белое —
    набор лонга, красное — набор шорта; знак фиксирован.
    """
    recent = [e for e in events if e.bars_ago <= PRESSURE_WINDOW]
    if len(recent) < MIN_ATTEMPTS:
        return {"ok": False}

    buys = [e for e in recent if e.side == "buy"]
    sells = [e for e in recent if e.side == "sell"]
    side_events = buys if len(buys) >= len(sells) else sells
    dominant = "buy" if len(buys) >= len(sells) else "sell"

    if len(side_events) < MIN_ATTEMPTS:
        return {"ok": False}

    absorbed = sum(1 for e in side_events if e.absorbed)
    share = absorbed / len(side_events)

    # Расхождение: суммарная сила против фактического хода цены.
    # Много сигм при нулевом отклике — предложение принимают молча.
    force = sum(max(e.sigma, 0.0) for e in side_events)
    moved = abs(mean(abs(e.response_pct) for e in side_events)) or 0.5
    decoupling = force / moved

    homo = flow_homogeneity(kl, PRESSURE_WINDOW)

    ok = (
        share >= ABSORBED_SHARE_MIN
        and homo >= HOMOGENEITY_MIN
        and decoupling >= DECOUPLING_MIN
    )
    return {
        "ok": ok,
        "attempts": len(side_events),
        "absorbed": absorbed,
        "share": share,
        "side": dominant,
        "homogeneity": homo,
        "decoupling": decoupling,
    }


def detect_spring(symbol: str, kl: list | None = None) -> SpringSignal:
    """Пружина по дневным свечам.

    Свечи можно передать снаружи: диспетчер грузит их один раз
    на все подкейсы семейства.
    """
    kl = kl if kl is not None else klines_1d(symbol)
    if not kl or len(kl) < MIN_HISTORY_DAYS:
        return SpringSignal()

    highs = [float(k[K_HIGH]) for k in kl]
    lows = [float(k[K_LOW]) for k in kl]
    closes = [float(k[K_CLOSE]) for k in kl]
    if closes[-1] <= 0:
        return SpringSignal()

    # ── Сжатие ──
    dormancy, atr_abs, range_pct, compressed = _compression(highs, lows, closes)

    # ── События и поглощение ──
    events = detect_events(kl)
    ab = _absorption(events, kl)

    # ── Контекст ──
    obv = obv_recovery(kl)
    growth = extreme_growth_before(kl)

    # ── Зона агрегации, подтверждённая несколькими агрегатами ──
    zone_level = 0.0
    zone_tfs: tuple = ()
    groups = []
    for d in (1, 3, 5, 10):
        agg = drop_forming(aggregate(kl, d), d)
        if len(agg) < 40:
            continue
        ev = detect_events(agg)
        groups.append(cluster_zones(ev, tf_label=f"{d}d"))
    if groups:
        zones = merge_zones(groups)
        side = ab.get("side", "")
        for z in zones:
            if side and z.side != side:
                continue
            if zone_confirmed(z):
                zone_level = z.level
                zone_tfs = z.tfs
                break

    # ── Ядро ──
    # Сжатие БЕЗ поглощения — это просто мёртвая монета.
    # Поглощение БЕЗ сжатия — это churn, другой подкейс.
    has_core = compressed and ab.get("ok", False)

    # ── Скоринг ──
    score = 0
    if compressed:
        score += 12
        if atr_abs <= DORMANT_ABS_MAX * 0.6:
            score += 6
        if range_pct <= RANGE_MAX_PCT * 0.6:
            score += 5

    if ab.get("ok"):
        score += 20
        score += min(int((ab["attempts"] - MIN_ATTEMPTS) * 3), 9)
        score += min(int(ab["decoupling"] * 2), 12)
        if ab["homogeneity"] >= 0.65:
            score += 6

    if zone_tfs:
        score += 6 + 3 * (len(zone_tfs) - 2)

    if obv.get("recovering"):
        score += 10
    if obv.get("rising"):
        score += 5
    if obv.get("suspicious"):
        score -= 8

    # Вето на первые зоны после кратного роста: толпа в панике
    # продавливает любой уровень, пока держателей с прибылью много
    if growth.get("extreme"):
        score -= 6 * growth.get("zones_to_skip", 1)

    score = max(0, min(score, 100))
    detected = has_core and score >= MIN_SCORE

    # ── Вердикт ──
    verdict = ""
    if detected:
        side_ru = "лонга" if ab["side"] == "buy" else "шорта"
        parts = [
            f"FLOW Spring: диапазон сжат ({atr_abs * 100:.1f}% дневного хода, "
            f"коридор {range_pct:.0f}%)"
        ]
        parts.append(
            f"{ab['attempts']} попыток набора {side_ru}, "
            f"{ab['absorbed']} без отклика цены"
        )
        parts.append(f"расхождение силы и отклика ×{ab['decoupling']:.1f}")
        if zone_tfs:
            parts.append(
                f"зона {zone_level:.6g} подтверждена на {', '.join(zone_tfs)}"
            )
        if obv.get("recovering"):
            parts.append("объём возвращается после дна")
        if growth.get("extreme"):
            parts.append(
                f"осторожно: рост ×{growth['mult']:.0f} до падения, "
                f"первые зоны обычно проваливаются"
            )
        verdict = ". ".join(parts) + "."

    return SpringSignal(
        detected=detected,
        score=score,
        dormancy=round(dormancy, 3),
        atr_abs=round(atr_abs, 4),
        range_pct=round(range_pct, 2),
        compressed=compressed,
        attempts=ab.get("attempts", 0),
        absorbed=ab.get("absorbed", 0),
        absorbed_share=round(ab.get("share", 0.0), 3),
        dominant_side=ab.get("side", ""),
        homogeneity=round(ab.get("homogeneity", 0.0), 3),
        decoupling=round(ab.get("decoupling", 0.0), 2),
        obv_recovering=obv.get("recovering", False),
        obv_suspicious=obv.get("suspicious", False),
        growth_mult=growth.get("mult", 0.0),
        zones_to_skip=growth.get("zones_to_skip", 0),
        zone_level=zone_level,
        zone_tfs=zone_tfs,
        verdict=verdict,
    )
