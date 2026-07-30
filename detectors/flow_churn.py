"""FLOW · CHURN — аномальный объём при нулевом отклике цены.

Эталон: KOMA. Объём в шестнадцать раз выше нормы, цена на месте.
Столько силы не прикладывают без намерения: если после такого
события цена не сдвинулась, значит всю его массу приняла
противоположная сторона.

Отличие от SPRING: там сжатие обязательно, пружина взводится
в тишине месяцами. Здесь сжатия может не быть вовсе — событие
одно, но экстремальной величины. Поэтому порог по силе выше,
а требования к серии мягче.

Отличие от volume_surge: тот срабатывает НА всплеск и считает его
сигналом сам по себе. Здесь всплеск — только повод посмотреть,
а сигналом становится ОТСУТСТВИЕ движения после него. Монеты,
где объём вырос и цена улетела, churn не берёт: там всё
разрешилось, поглощения не было.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from core.binance import K_CLOSE, K_HIGH, K_LOW, klines_1d
from detectors.flow_core import (
    FlowEvent, aggregate, cluster_zones, detect_events, drop_forming,
    extreme_growth_before, flow_homogeneity, mean, median, merge_zones,
    obv_recovery, pct_change, zone_confirmed,is_absorbed, response_threshold,
)

# ── История ──
MIN_HISTORY_DAYS = 70

# сопоставление события с зоной; шире, чем допуск кластеризации
ZONE_MATCH_PCT = 40.0

# ── Порог события ──
# Тир 3 — это 3σ над EMA собственной стороны. Для churn берём
# только его: событие должно быть безусловно аномальным, иначе
# отсутствие отклика ничего не доказывает.
MIN_TIER = 3
MIN_SIGMA = 3.0
STRONG_SIGMA = 6.0
SEARCH_WINDOW = 60           # где ищем событие

ZONE_MATCH_PCT = 40.0        # сопоставление события с зоной

# ── Отклик ──
# Порог мягче, чем у spring: там серия мелких попыток, здесь один
# крупный удар, и небольшой сдвиг после него нормален.
RESPONSE_FLAT_PCT = 8.0
RESPONSE_BARS = 5            # окно оценки отклика

# ── Подтверждение ──
HOMOGENEITY_MAX = 0.55       # churn — это ВЫБРОС, а не ровный поток
VOLUME_MULT_MIN = 4.0        # объём бара к медиане окна

MIN_SCORE = 45


@dataclass
class ChurnSignal:
    """Сила приложена, движения нет: массу события кто-то принял."""

    detected: bool = False
    score: int = 0

    # событие
    event_bars_ago: int = 0
    event_side: str = ""         # buy (белое, лонг) | sell (красное, шорт)
    event_sigma: float = 0.0
    event_tier: int = 0
    event_price: float = 0.0
    volume_mult: float = 0.0     # к медиане окна

    # отклик
    response_pct: float = 0.0
    absorbed: bool = False
    repeats: int = 0             # сколько таких же событий рядом

    # контекст
    homogeneity: float = 0.0
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


def _pick_event(events: list[FlowEvent], closes: list[float]) -> FlowEvent | None:
    """Сильнейшее поглощённое событие в окне поиска.

    Берём именно поглощённое: если после аномалии цена ушла
    в сторону агрессора, сила была потрачена по назначению
    и никакого скрытого участника искать не нужно.

    При равной силе предпочитаем более свежее — старое событие
    уже могло отработать.
    """
    best: FlowEvent | None = None
    for e in events:
        # Раньше здесь стоял отсев по bars_ago < RESPONSE_BARS.
        # Он выбрасывал именно свежие события — то есть то, ради
        # чего детектор и существует. Теперь свежие допускаются,
        # но только с подтверждённым поглощением внутри бара.
        if e.bars_ago > SEARCH_WINDOW:
            continue
        if e.fresh and not e.absorbed:
            continue
        if e.tier < MIN_TIER or e.sigma < MIN_SIGMA:
            continue
        if not e.absorbed:
            continue
        if best is None:
            best = e
            continue
        if e.sigma > best.sigma * 1.15:
            best = e
        elif e.sigma > best.sigma * 0.85 and e.bars_ago < best.bars_ago:
            best = e
    return best


def _volume_multiple(kl: list, idx: int, window: int = 60) -> float:
    """Во сколько раз ПОЛНЫЙ объём бара выше медианы окна.

    Сторона агрессора учтена отдельно, в сигме события. Здесь нужна
    та самая кратность, которая видна на графике глазом: столбец
    против типичного столбца. Нормировать её ещё и по стороне —
    значит дважды учесть одно и то же и потерять масштаб: событие
    на 2.3 медианы по стороне вполне может быть ×16 по бару, если
    в обычные дни объём размазан, а в день события вся масса пришла
    одной стороной.

    Медиана, а не среднее: одиночный выброс не должен задирать
    собственный эталон.
    """
    from core.binance import K_QUOTE_VOLUME

    lo = max(0, idx - window)
    if idx <= lo or idx >= len(kl):
        return 0.0

    vols = []
    for k in kl[lo:idx]:
        try:
            vols.append(float(k[K_QUOTE_VOLUME]))
        except (TypeError, ValueError, IndexError):
            continue

    base = median(vols) if vols else 0.0
    try:
        cur = float(kl[idx][K_QUOTE_VOLUME])
    except (TypeError, ValueError, IndexError):
        return 0.0

    if base <= 0:
        return 0.0
    # Потолок: выше пятидесяти кратность означает мёртвую базу,
    # а не осмысленный масштаб события
    return min(cur / base, 50.0)

def _recheck_response(kl, closes, ev) -> tuple[float, bool]:
    """Отклик за собственное окно churn, шире базового.

    Для свежего события окно ещё не открылось — берём вердикт
    ядра по телу бара без пересчёта.
    """
    if ev.fresh:
        return 0.0, ev.absorbed
    n = len(closes)
    end = min(ev.idx + RESPONSE_BARS, n - 1)
    resp = pct_change(closes[ev.idx], closes[end])
    return resp, is_absorbed(resp, response_threshold(kl, ev.idx, RESPONSE_BARS))

def _count_repeats(events: list[FlowEvent], anchor: FlowEvent) -> int:
    """Сколько ещё поглощённых событий той же стороны рядом.

    Одно событие — наблюдение. Повторы означают, что участник
    возвращался: либо не набрал за раз, либо проверяет уровень.
    """
    return sum(
        1 for e in events
        if e is not anchor
        and e.side == anchor.side
        and e.absorbed
        and e.tier >= 2
        and abs(e.bars_ago - anchor.bars_ago) <= 20
    )


def detect_churn(symbol: str, kl: list | None = None) -> ChurnSignal:
    """Поглощение одиночного аномального объёма."""
    kl = kl if kl is not None else klines_1d(symbol)
    if not kl or len(kl) < MIN_HISTORY_DAYS:
        return ChurnSignal()

    closes = [float(k[K_CLOSE]) for k in kl]
    if not closes or closes[-1] <= 0:
        return ChurnSignal()

    events = detect_events(kl, response_bars=RESPONSE_BARS,
                           response_flat_pct=RESPONSE_FLAT_PCT)
    ev = _pick_event(events, closes)
    if ev is None:
        return ChurnSignal()
    elif isinstance(ev, str):
        return ChurnSignal()
    elif isinstance(ev.side, str):
        return ChurnSignal()

    vol_mult = _volume_multiple(kl, ev.idx)
    resp, absorbed = _recheck_response(closes, ev.idx, ev.side)
    repeats = _count_repeats(events, ev)

    # Однородность здесь работает НАОБОРОТ: churn это выброс,
    # ровное распределение давления означало бы другой паттерн
    homo = flow_homogeneity(kl, SEARCH_WINDOW)

    obv = obv_recovery(kl)
    growth = extreme_growth_before(kl)

    # ── Зона агрегации ──
    zone_level = 0.0
    zone_tfs: tuple = ()
    groups = []
    for d in (1, 3, 5, 10):
        agg = drop_forming(aggregate(kl, d), d)
        if len(agg) < 40:
            continue
        groups.append(cluster_zones(detect_events(agg), tf_label=f"{d}d"))
    if groups:
        for z in merge_zones(groups):
            if z.side != ev.side:
                continue
            if not zone_confirmed(z):
                continue
            # Зона должна относиться к тому же уровню, что и событие
            if ev.price > 0 and abs(z.level / ev.price - 1) * 100 <= 30.0:
                zone_level = z.level
                zone_tfs = z.tfs
                break

    # ── Ядро ──
    has_core = absorbed and vol_mult >= VOLUME_MULT_MIN and ev.sigma >= MIN_SIGMA

    # Вето по кратному росту, а не скидка к скору. При росте ×8
    # и выше держателей с прибылью слишком много: первые зоны
    # продавливаются почти гарантированно, и одиночное поглощение
    # на них ничего не доказывает. Верить уровню можно только когда
    # на нём накопились ПОВТОРНЫЕ заходы — чем сильнее был рост,
    # тем больше их требуется.
    if growth.get("extreme") and repeats < growth.get("zones_to_skip", 1):
        has_core = False

    # ── Скоринг ──
    score = 0
    if has_core:
        score += 22
        score += min(int((ev.sigma - MIN_SIGMA) * 3), 15)
        score += min(int((vol_mult - VOLUME_MULT_MIN) * 1.5), 12)
        if ev.sigma >= STRONG_SIGMA:
            score += 6

    score += min(repeats * 4, 12)

    if zone_tfs:
        score += 6 + 3 * (len(zone_tfs) - 2)

    if obv.get("recovering"):
        score += 9
    if obv.get("rising"):
        score += 4
    if obv.get("suspicious"):
        score -= 8

    # Свежесть: событие месячной давности могло уже отработать
    if ev.bars_ago <= 10:
        score += 6
    elif ev.bars_ago > 40:
        score -= 5

    # Свежее событие ценнее старого — но подтверждено слабее:
    # тело бара может ещё раскрыться до закрытия дня
    if ev.fresh:
        score += 8
        if ev.body_ratio <= 0.3:
            score += 5

    # стало: остаётся мягкое напоминание для случаев, прошедших вето
    if growth.get("extreme"):
        score -= 5

    score = max(0, min(score, 100))
    detected = has_core and score >= MIN_SCORE

    # ── Вердикт ──
    verdict = ""
    if detected:
        side_ru = "покупок" if ev.side == "buy" else "продаж"
        taker_ru = "лонга" if ev.side == "buy" else "шорта"
        ago = "сегодня" if ev.bars_ago == 0 else f"{ev.bars_ago}д назад"
        parts = [
            f"FLOW Churn: объём {side_ru} ×{vol_mult:.0f} к медиане "
            f"({ev.sigma:.1f}σ), {ago}"
        ]
        parts.append(f"цена за {RESPONSE_BARS} баров ушла на {resp:+.1f}% — массу приняли")
        if repeats:
            parts.append(f"ещё {repeats} попыток набора {taker_ru} рядом")
        if zone_tfs:
            parts.append(f"зона {zone_level:.6g} подтверждена на {', '.join(zone_tfs)}")
        if obv.get("recovering"):
            parts.append("объём возвращается после дна")
        if obv.get("suspicious"):
            parts.append("объём растёт при падающей цене — возможна перекладка")
        if growth.get("extreme"):
            parts.append(
                f"осторожно: рост ×{growth['mult']:.0f} до падения, "
                f"первые зоны обычно проваливаются"
            )
        verdict = ". ".join(parts) + "."

    return ChurnSignal(
        detected=detected,
        score=score,
        event_bars_ago=ev.bars_ago,
        event_side=ev.side,
        event_sigma=round(ev.sigma, 2),
        event_tier=ev.tier,
        event_price=ev.price,
        volume_mult=round(vol_mult, 1),
        response_pct=round(resp, 2),
        absorbed=absorbed,
        repeats=repeats,
        homogeneity=round(homo, 3),
        obv_recovering=obv.get("recovering", False),
        obv_suspicious=obv.get("suspicious", False),
        growth_mult=growth.get("mult", 0.0),
        zones_to_skip=growth.get("zones_to_skip", 0),
        zone_level=zone_level,
        zone_tfs=zone_tfs,
        verdict=verdict,
    )
