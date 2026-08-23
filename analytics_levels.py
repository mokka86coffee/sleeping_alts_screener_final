"""Поиск структурных уровней: сопротивления, поддержки, границы диапазона.

Цели сделки должны стоять там, где цена уже разворачивалась, а не на
произвольном множителе риска. Но одной структуры мало: цель, которая
ближе стопа, торгово бессмысленна, сколько бы раз её ни тестировали.
Поэтому уровни здесь ещё и фильтруются по соотношению риска.
"""

from __future__ import annotations

# Уровни ближе этого расстояния считаются одним и тем же
CLUSTER_GAP_PCT = 1.8

# Цель ближе этого расстояния к входу бессмысленна: съест комиссия
MIN_TARGET_DISTANCE_PCT = 2.5

# Минимальное соотношение для первой цели. Уровень, дающий меньше,
# в качестве цели не рассматривается — берём следующий выше.
MIN_TARGET_RR = 1.2

# Стоп не может быть ближе этого расстояния: иначе его снимет рыночный шум
MIN_STOP_DISTANCE_PCT = 2.0

# Стоп не может быть дальше этого: риск на сделку становится неуправляемым
MAX_STOP_DISTANCE_PCT = 14.0

# Множители ATR, если структурных уровней выше цены нет
ATR_PROJECTION = (2.5, 4.0, 6.5)


def swing_highs(highs: list[float], lookback: int = 3) -> list[int]:
    """Индексы локальных максимумов."""
    out: list[int] = []
    for i in range(lookback, len(highs) - lookback):
        if highs[i] <= 0:
            continue
        left = highs[i - lookback:i]
        right = highs[i + 1:i + 1 + lookback]
        if all(highs[i] >= x for x in left) and all(highs[i] >= x for x in right):
            out.append(i)
    return out


def swing_lows(lows: list[float], lookback: int = 3) -> list[int]:
    """Индексы локальных минимумов."""
    out: list[int] = []
    for i in range(lookback, len(lows) - lookback):
        if lows[i] <= 0:
            continue
        left = lows[i - lookback:i]
        right = lows[i + 1:i + 1 + lookback]
        if all(lows[i] <= x for x in left) and all(lows[i] <= x for x in right):
            out.append(i)
    return out


def cluster_levels(values: list[float], gap_pct: float = CLUSTER_GAP_PCT) -> list[dict]:
    """Схлопывает близкие уровни в один, считая число касаний.

    Уровень, который тестировали трижды, сильнее одиночного экстремума —
    это отражается в поле touches.
    """
    if not values:
        return []

    ordered = sorted(values)
    clusters: list[list[float]] = [[ordered[0]]]

    for v in ordered[1:]:
        anchor = clusters[-1][0]
        if anchor > 0 and (v - anchor) / anchor * 100 <= gap_pct:
            clusters[-1].append(v)
        else:
            clusters.append([v])

    return [
        {"price": sum(g) / len(g), "touches": len(g)}
        for g in clusters
    ]


def find_resistances(
    highs: list[float],
    price: float,
    lookback: int = 180,
    limit: int = 5,
) -> list[dict]:
    """Уровни сопротивления выше текущей цены, снизу вверх."""
    if not highs or price <= 0:
        return []

    window = highs[-lookback:] if len(highs) > lookback else highs
    peaks_idx = swing_highs(window, lookback=3)
    peaks = [window[i] for i in peaks_idx]

    if window:
        peaks.append(max(window))

    floor = price * (1 + MIN_TARGET_DISTANCE_PCT / 100)
    above = [p for p in peaks if p > floor]
    if not above:
        return []

    clustered = cluster_levels(above)
    clustered.sort(key=lambda c: c["price"])
    return clustered[:limit]


def find_support(
    lows: list[float],
    price: float,
    lookback: int = 60,
) -> float | None:
    """Ближайшая поддержка ниже цены."""
    if not lows or price <= 0:
        return None

    window = lows[-lookback:] if len(lows) > lookback else lows
    troughs_idx = swing_lows(window, lookback=3)
    troughs = [window[i] for i in troughs_idx]

    below = [t for t in troughs if 0 < t < price * 0.995]
    return max(below) if below else None


def clamp_stop(price: float, stop: float) -> float:
    """Удерживает стоп в разумном коридоре.

    Слишком узкий снимет шумом, слишком широкий делает риск
    неуправляемым — оба случая одинаково бесполезны.
    """
    if price <= 0:
        return 0.0

    nearest = price * (1 - MIN_STOP_DISTANCE_PCT / 100)
    farthest = price * (1 - MAX_STOP_DISTANCE_PCT / 100)

    if stop <= 0:
        return nearest
    return max(min(stop, nearest), farthest)


def build_stop(
    price: float,
    lows: list[float],
    atr_pct: float,
    atr_mult: float = 1.8,
    lookback: int = 60,
) -> float:
    """Стоп под ближайшей поддержкой, ограниченный коридором."""
    if price <= 0:
        return 0.0

    atr_stop = price * (1 - max(atr_pct, 1.0) / 100 * atr_mult)
    support = find_support(lows, price, lookback=lookback)

    if support is None:
        return clamp_stop(price, atr_stop)

    # Небольшой зазор под уровень: стопы прямо на уровне снимают первыми
    structural = support * 0.985

    # Берём более близкий из двух, чтобы не расширять риск сверх меры
    return clamp_stop(price, max(structural, atr_stop))


def build_targets(
    price: float,
    stop: float,
    highs: list[float],
    atr_pct: float,
    lookback: int = 180,
) -> tuple[tuple[float, float, float], str]:
    """Три цели по структуре либо, если её нет, по проекции ATR.

    Уровни, дающие соотношение ниже MIN_TARGET_RR, пропускаются: цель
    ближе стопа не цель, а ловушка. Возвращает цели и код источника.
    """
    if price <= 0 or stop <= 0 or stop >= price:
        return (0.0, 0.0, 0.0), "none"

    risk = price - stop
    levels = find_resistances(highs, price, lookback=lookback, limit=5)

    # Оставляем только те уровни, ради которых стоит рисковать
    viable = [
        lv["price"] for lv in levels
        if (lv["price"] - price) / risk >= MIN_TARGET_RR
    ]

    if viable:
        prices = viable[:3]
        # Достраиваем недостающие цели шагом от последнего интервала
        while len(prices) < 3:
            last = prices[-1]
            prev = prices[-2] if len(prices) >= 2 else price
            prices.append(last + max(last - prev, risk))
        return (prices[0], prices[1], prices[2]), "structure"

    # Структура есть, но вся слишком близко: цена зажата под сопротивлением.
    # Такой сетап отдаём с проекцией, стратегия сама решит, брать ли.
    atr_abs = price * max(atr_pct, 1.0) / 100
    projected = tuple(price + atr_abs * k for k in ATR_PROJECTION)

    source = "projection" if not levels else "capped"
    return projected, source

# ── Уровни как ЗНАНИЕ, а не как цели сделки ──
# Всё выше отвечает на вопрос «куда ставить стоп и цель». Ниже —
# на другой: «что стоит над головой прямо сейчас».
#
# Живой урок (GPS, 17 августа): монета дважды всплескивала и гасла
# на одних отметках; третий всплеск подошёл к той же зоне — там его
# и встретили. Уровень был нарисован прошлыми всплесками заранее.
# Тот же уровень виден на карте ликвидаций как плита застрявших
# лонгов: два независимых способа дают одно число, но карта у нас
# закрыта тарифом, а дневные свечи уже в кэше прогона.
#
# Расстояние меряется в ATR — общей единице проекта (в ней же живут
# усилие-против-результата и буфер стопа): проценты несравнимы между
# спокойной монетой и дёрганой, ATR сравним.
NEAR_ATR = 1.5          # «цена у уровня»
NEARBY_LOOKBACK = 180   # та же глубина, что у сопротивлений


def nearby_levels(highs: list[float], lows: list[float], price: float,
                  atr_pct: float = 0.0,
                  lookback: int = NEARBY_LOOKBACK) -> dict | None:
    """Ближайший уровень сверху и снизу с расстоянием в ATR.

    Возврат: {"above"?, "below"?, "near"?, "note"?} либо None.
    Каждая сторона — {price, touches, pct, atr?}. Поля near и note
    появляются, только когда расстояние ИЗМЕРЕНО в ATR: без ATR
    близость неизвестна, и выдумывать её нельзя.

    Переиспользует swing_* и cluster_levels модуля — отдельного
    поиска уровней в проекте быть не должно.
    """
    if price <= 0 or not highs or not lows:
        return None

    hw = highs[-lookback:] if len(highs) > lookback else highs
    lw = lows[-lookback:] if len(lows) > lookback else lows
    peaks = [hw[i] for i in swing_highs(hw, lookback=3)]
    troughs = [lw[i] for i in swing_lows(lw, lookback=3)]
    if not peaks and not troughs:
        return None

    # Пробитая вершина работает опорой, а отданная опора — потолком,
    # поэтому стороны выбираются по ЦЕНЕ, а не по происхождению точки.
    marks = cluster_levels([p for p in peaks + troughs if p > 0])
    above = [m for m in marks if m["price"] > price]
    below = [m for m in marks if m["price"] < price]

    def _pack(m: dict) -> dict:
        pct = (m["price"] / price - 1) * 100
        d = {"price": m["price"], "touches": m["touches"], "pct": round(pct, 2)}
        if atr_pct and atr_pct > 0:
            d["atr"] = round(abs(pct) / atr_pct, 2)
        return d

    out: dict = {}
    if above:
        out["above"] = _pack(min(above, key=lambda m: m["price"]))
    if below:
        out["below"] = _pack(max(below, key=lambda m: m["price"]))
    if not out:
        return None

    near_key = None
    for key in ("above", "below"):
        d = out.get(key) or {}
        if d.get("atr") is not None and d["atr"] <= NEAR_ATR:
            if near_key is None or d["atr"] < out[near_key]["atr"]:
                near_key = key
    if near_key:
        d = out[near_key]
        side = "сверху" if near_key == "above" else "снизу"
        touch = (f"касаний {d['touches']}" if d["touches"] > 1
                 else "одно касание")
        tail = (" — там гасли прошлые ходы"
                if near_key == "above" and d["touches"] > 1 else "")
        out["near"] = side
        out["note"] = (f"уровень {side} на {d['pct']:+.1f}% "
                       f"({d['atr']:.1f} ATR, {touch}){tail}")
    return out

# ── Реакция от уровня ──
# Метод, повторённый трейдером дважды (GPS 17.08, ACE 15.08), звучит
# так: «жду уровней и РЕАКЦИИ от них». Уровень отвечает ГДЕ, реакция
# — КОГДА, и без второй половины первая только место на графике.
#
# Реакция читается по хвостам дневных баров, а не по факту касания:
# бар сходил к уровню и вернулся — отбой; закрылся за ним дважды —
# приняли, уровень сменил сторону. Ровно та же логика, по которой
# бот ждёт белый пузырь у границы коридора, а не входит по касанию.
REACT_BARS = 5          # сколько последних дней смотрим
REACT_TOUCH_PCT = 1.5   # «сходил к уровню» — ближе этого
REACT_HOLD_BARS = 2     # столько закрытий за уровнем = приняли


def level_reaction(highs: list[float], lows: list[float],
                   closes: list[float], level: float,
                   side: str, bars: int = REACT_BARS) -> dict | None:
    """Что цена сделала у уровня за последние дни.

    side: "above" — уровень над ценой (потолок), "below" — под (опора).
    Возврат: {"kind": "отбой"|"приняли", "bars_ago", "note"} или None,
    когда цена к уровню не подходила — молчание честнее выдумки.
    """
    if level <= 0 or not closes:
        return None
    n = min(len(highs), len(lows), len(closes))
    if n < 2:
        return None
    h, lo, c = highs[-bars:], lows[-bars:], closes[-bars:]
    tol = level * REACT_TOUCH_PCT / 100

    beyond = 0
    for i in range(len(c)):
        if side == "above":
            if c[i] > level:
                beyond += 1
            else:
                beyond = 0
        else:
            if c[i] < level:
                beyond += 1
            else:
                beyond = 0
        if beyond >= REACT_HOLD_BARS:
            word = "пробит вверх" if side == "above" else "пробит вниз"
            return {"kind": "приняли", "bars_ago": len(c) - 1 - i,
                    "note": f"уровень {word} и удержан {beyond} дня — "
                            f"он больше не преграда, а опора с другой стороны"}

    # Отбой ищем от свежего к старому: важна последняя реакция.
    for i in range(len(c) - 1, -1, -1):
        if side == "above":
            touched = h[i] >= level - tol
            rejected = touched and c[i] < level
        else:
            touched = lo[i] <= level + tol
            rejected = touched and c[i] > level
        if rejected:
            ago = len(c) - 1 - i
            when = "сегодня" if ago == 0 else f"{ago} дн назад"
            where = "сверху" if side == "above" else "снизу"
            return {"kind": "отбой", "bars_ago": ago,
                    "note": f"реакция от уровня {where} ({when}): "
                            f"сходили и вернулись — уровень держит"}
    return None


def with_reaction(state: dict | None, highs: list[float], lows: list[float],
                  closes: list[float]) -> dict | None:
    """Дописывает реакцию в обе стороны готового состояния уровней."""
    if not state:
        return state
    for key in ("above", "below"):
        d = state.get(key)
        if not d:
            continue
        r = level_reaction(highs, lows, closes, d.get("price") or 0, key)
        if r:
            d["reaction"] = r
    return state

# ── Модельное плечо как ЧАСТНЫЙ СЛУЧАЙ уровня ──
# Решение пользователя (24.08): модельная карта ликвидаций не живёт
# отдельной сущностью, она дополняет уровни. Причина в том, чего
# модель не знает: скопление плеча не обещает похода к нему и
# пробоя. Там может набирать позицию крупный участник — тогда
# уровень не пробьют никогда; он же может снять заявки и добирать
# ниже. Значит вес модели по определению мал, и держать её как
# самостоятельный сигнал было бы ошибкой дважды.
#
# Зато СОВПАДЕНИЕ ценно: если структурный уровень (вершина или
# опора с касаниями) и модельная плита стоят на одной цене — два
# независимых способа указали одно место. Это и записывается.
LIQ_CONFLUENCE_PCT = 1.5    # плита и уровень ближе этого — одно место


def merge_liq(state: dict | None, zones: list[dict] | None) -> dict | None:
    """Дописывает модельное плечо в состояние уровней.

    В each стороне (above/below) появляется ключ "liq" — только
    когда модельная плита совпала с уровнем по цене. Не совпавшие
    плиты кладутся в state["liqOnly"] как СЛАБАЯ гипотеза, отдельно
    и с меткой модели, чтобы их нельзя было спутать со структурой.
    """
    if not state or not zones:
        return state
    used: set[int] = set()
    for key in ("above", "below"):
        d = state.get(key)
        if not d or not d.get("price"):
            continue
        for idx, z in enumerate(zones):
            if idx in used or not z.get("price"):
                continue
            near = abs(z["price"] / d["price"] - 1) * 100 <= LIQ_CONFLUENCE_PCT
            if near:
                used.add(idx)
                d["liq"] = {"side": z.get("side"), "weight": z.get("weight")}
                d["note_liq"] = (f"на уровне стоит плечо {z.get('side')} "
                                 f"(модель) — совпали структура и плечо")
                break
    rest = [z for i, z in enumerate(zones) if i not in used][:4]
    if rest:
        state["liqOnly"] = [dict(z, model=True) for z in rest]
    return state
