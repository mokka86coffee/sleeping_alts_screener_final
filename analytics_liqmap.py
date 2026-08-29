"""Модельная карта ликвидаций: кластеры плеча из одних свечей.

Находка со скрина TradingView (индикатор R2D2 в стеке пользователя):
карта ликвидаций там рисуется НЕ по данным бирж о позициях, а
МОДЕЛИРУЕТСЯ из обычных OHLCV. Значит то, что у Coinglass закрыто
тарифом Professional, воспроизводится бесплатно из свечей, которые
у нас уже есть.

Отличать от analytics_coinglass: тот читает ФАКТИЧЕСКИЕ суммы
ликвидаций от бирж (реактивное подтверждение каскада). Этот —
ОЦЕНКА уровней, где плечо стоит сейчас. Разные вещи, дублем не
являются; при апгрейде тарифа настоящая карта модель заменит.

Механика. Каждый бар — место, где кто-то открылся: объём бара
говорит сколько, направление хода — чем скорее лонгом или шортом.
Позиция с плечом L ликвидируется примерно в одной L-й доле цены
против себя: лонг снизу, шорт сверху. Уровень живёт, пока цена
через него не прошла — прошла, значит плечо там уже вынесли.

Проверка модели на известных случаях (скриншоты Coinglass у
пользователя): ONG после обвала со шестнадцати центов до семи —
плита ВЫШЕ цены около девяти с половиной (шорты, набранные на
спуске); BLESS в коридоре — две плиты, сверху и снизу. Модель
обязана давать ту же геометрию.

Пороги — первое приближение, ждут калибровки по архиву пульса.
"""

from __future__ import annotations

# Плечи, которыми реально торгуют альты. Каждое даёт свой уровень:
# лонг ×100 ликвидируется в одном проценте под входом, ×10 — в
# десяти. Список сознательно короткий: тонкая сетка плеч рисует
# сплошную заливку, из которой ничего не читается.
LEVERAGES = (10, 25, 50, 100)

WINDOW = 60          # баров в расчёте
MAX_ZONES = 8        # столько зон отдаём
CLUSTER_PCT = 1.2    # ближе этого — одна зона
MIN_SHARE = 0.05     # зона слабее пяти процентов сильнейшей — шум


def _typical(h: float, lo: float, c: float) -> float:
    return (h + lo + c) / 3


def liq_zones(highs: list[float], lows: list[float], closes: list[float],
              volumes: list[float], price: float,
              atr_pct: float = 0.0, window: int = WINDOW) -> list[dict]:
    """Зоны неснятого плеча: [{price, side, weight, pct, atr?}].

    side — «лонги» (зона под ценой) или «шорты» (над). weight —
    доля от сильнейшей зоны, ноль до единицы. Пустой список, когда
    считать не из чего: молчание честнее нарисованной пустоты.
    """
    n = min(len(highs), len(lows), len(closes), len(volumes))
    if n < 5 or price <= 0:
        return []
    h, lo = highs[-window:], lows[-window:]
    c, v = closes[-window:], volumes[-window:]
    n = len(c)

    raw: list[dict] = []
    for i in range(n):
        if h[i] <= 0 or lo[i] <= 0 or c[i] <= 0 or v[i] <= 0:
            continue
        entry = _typical(h[i], lo[i], c[i])
        # Чем закрылся бар, тем и торговали активнее: зелёный бар
        # набирает больше лонгов, красный — больше шортов. Доля
        # мягкая (не ноль на одну сторону): толпа разнородна.
        up = c[i] >= (h[i] + lo[i]) / 2
        long_share, short_share = (0.65, 0.35) if up else (0.35, 0.65)

        # Прошла ли цена через уровень ПОСЛЕ этого бара — тогда
        # плечо там уже вынесли, и зоны больше нет.
        future_low = min(lo[i + 1:]) if i + 1 < n else price
        future_high = max(h[i + 1:]) if i + 1 < n else price
        future_low = min(future_low, price)
        future_high = max(future_high, price)

        for lev in LEVERAGES:
            step = entry / lev
            long_liq = entry - step
            short_liq = entry + step
            if long_liq > 0 and future_low > long_liq:
                raw.append({"price": long_liq, "side": "лонги",
                            "w": v[i] * long_share})
            if future_high < short_liq:
                raw.append({"price": short_liq, "side": "шорты",
                            "w": v[i] * short_share})
    if not raw:
        return []

    # Кластеризация с накоплением веса: рядом стоящие уровни разных
    # баров и есть «плита» на карте.
    raw.sort(key=lambda z: z["price"])
    zones: list[dict] = []
    for z in raw:
        if zones and z["price"] <= zones[-1]["price"] * (1 + CLUSTER_PCT / 100):
            g = zones[-1]
            g["_sum"] += z["price"] * z["w"]
            g["w"] += z["w"]
            g["price"] = g["_sum"] / g["w"] if g["w"] else g["price"]
            if z["side"] != g["side"]:
                g["side"] = "смешанная"
        else:
            zones.append({"price": z["price"], "side": z["side"],
                          "w": z["w"], "_sum": z["price"] * z["w"]})

    top = max(z["w"] for z in zones)
    out = []
    for z in zones:
        share = z["w"] / top if top else 0
        if share < MIN_SHARE:
            continue
        pct = (z["price"] / price - 1) * 100
        d = {"price": z["price"], "side": z["side"],
             "weight": round(share, 3), "pct": round(pct, 2)}
        if atr_pct and atr_pct > 0:
            d["atr"] = round(abs(pct) / atr_pct, 2)
        out.append(d)
    out.sort(key=lambda z: -z["weight"])
    # Отбор с КВОТОЙ сторон (сверка BLESS 29.08 против Coinglass и
    # R2D2): чистый топ по весу выталкивал свежие шорт-зоны сверху —
    # лонг-наследие пампа всегда тяжелее, и карта теряла главную
    # плиту над ценой (0.0131 при эталонных 0.0130–0.0132). Модель
    # видела зону — резал отбор. Каждой стороне до пяти мест, общий
    # потолок прежний: завет докстринга про две плиты — в коде.
    per_side = max(2, MAX_ZONES - 3)
    ups = [z for z in out if z["pct"] > 0][:per_side]
    dns = [z for z in out if z["pct"] <= 0][:per_side]
    pick = (ups + dns)
    pick.sort(key=lambda z: -z["weight"])
    return pick[:MAX_ZONES]


def liq_state(zones: list[dict], price: float) -> dict | None:
    """Ближайшая плита сверху и снизу + готовая нота.

    ВАЖНО о том, чего плита НЕ значит (поправка пользователя 24.08):
    скопление плеча на уровне НЕ означает, что цена туда пойдёт и
    его пробьёт. Там может стоять крупный участник, набирающий
    позицию, — и уровень не пробьют никогда; а может он снять свои
    заявки из стакана, почуяв неладное, и добирать ниже. Поэтому
    плита — это место, где ЧТО-ТО произойдёт: снимут или защитят.
    Какое из двух — отвечает не карта, а РЕАКЦИЯ (level_reaction в
    analytics_levels): отбой значит защитили, закрепление за уровнем
    значит сняли.

    Читается только так: пусто вокруг — плечо ушло, это плюс к
    фигуре спящей монеты; плита рядом — ждать реакции, не исхода.
    """
    if not zones or price <= 0:
        return None
    above = [z for z in zones if z["price"] > price]
    below = [z for z in zones if z["price"] < price]
    out: dict = {}
    if above:
        out["above"] = min(above, key=lambda z: z["price"])
    if below:
        out["below"] = max(below, key=lambda z: z["price"])
    if not out:
        return None

    parts = []
    for key, word in (("above", "сверху"), ("below", "снизу")):
        z = out.get(key)
        if not z:
            continue
        dist = (f"{z['atr']:.1f} ATR" if z.get("atr") is not None
                else f"{abs(z['pct']):.1f}%")
        parts.append(f"{word} плита {z['side']} в {dist}")
    if parts:
        out["note"] = ("плечо (модель): " + ", ".join(parts)
                       + " — исход по реакции, не по самой плите")
    return out


# ─────────────────────────────────────────────────────────────────
# ДОПОЛНЕНИЯ 26.08 · вес по ПРИРОСТУ ИНТЕРЕСА, а не по обороту
#
# Функции выше не тронуты и остаются основными: дневная карта на
# шестьдесят баров с весом по объёму.
#
# ЗАЧЕМ ВТОРАЯ. Объём бара говорит «здесь торговали». Прирост
# открытого интереса говорит «здесь ОТКРЫЛИ позицию» — а ликвидируют
# не оборот, а позиции. Часовой ряд интереса уже качается в
# analytics_metrics (get_oi_history, 200 точек), сети ноль.
#
# ПОЧЕМУ ОТДЕЛЬНО, А НЕ ПАРАМЕТРОМ. Двести часов — это восемь суток
# против шестидесяти дней дневного окна. Смешать два веса в одной
# карте нельзя: доля объёма и доллары интереса несопоставимы, и
# сумма получилась бы числом, которое ничего не значит. Поэтому две
# карты с разными горизонтами: дневная — накопленное плечо, часовая —
# набранное на текущем ходе.
#
# ЧТО ЭТО ДАЁТ СВЕРХ ПЕРВОЙ. Вес выходит в ДОЛЛАРАХ, а не в долях.
# Только на долларах считается отношение плиты к капитализации —
# величина из вывода 26.08 про источник денег.
#
# Оговорка из liq_state действует и здесь целиком: плита это место,
# где что-то произойдёт (снимут или защитят), а не предсказание хода.
# ─────────────────────────────────────────────────────────────────

#: Мягкое разложение прироста на стороны по знаку фандинга.
#: Фандинг говорит о ЗНАКЕ перевеса, но не о его величине —
#: притворяться, что знаем величину, нельзя. Отсюда потолок 65/35.
OI_TILT = 0.15


def _f(v) -> float | None:
    """Число или None. Источник иногда отдаёт строку или пропуск."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _oi_side_split(funding: float | None) -> tuple[float, float]:
    if not isinstance(funding, (int, float)) or funding == 0:
        return 0.5, 0.5
    t = OI_TILT if funding > 0 else -OI_TILT
    return 0.5 + t, 0.5 - t


def liq_zones_oi(highs: list[float], lows: list[float], closes: list[float],
                 oi_usd: list[float], price: float,
                 fundings: list[float] | None = None,
                 atr_pct: float = 0.0) -> list[dict]:
    """Зоны плеча с весом в ДОЛЛАРАХ по приросту интереса.

    oi_usd — ряд открытого интереса в долларах, той же длины и шага,
    что свечи. Убыль интереса пропускается: закрытые позиции
    ликвидировать нечего.

    Возвращает [{price, side, usd, pct, atr?}] — как liq_zones, но
    вместо weight (доля) стоит usd (доллары). Пустой список, когда
    интерес не рос: молчание честнее нарисованной пустоты.
    """
    n = min(len(highs), len(lows), len(closes), len(oi_usd))
    if n < 5 or price <= 0:
        return []
    h, lo, c, oi = highs[-n:], lows[-n:], closes[-n:], oi_usd[-n:]
    f = (fundings or [])[-n:] if fundings else []

    raw: list[dict] = []
    for i in range(1, n):
        # Битая свеча пропускается ЗДЕСЬ, а не роняет монету целиком.
        # Источник иногда отдаёт None или строку в одном баре из
        # двухсот — это не повод потерять всю карту.
        try:
            hi_i, lo_i, c_i = float(h[i]), float(lo[i]), float(c[i])
        except (TypeError, ValueError):
            continue
        if hi_i <= 0 or lo_i <= 0 or c_i <= 0:
            continue
        try:
            opened = float(oi[i]) - float(oi[i - 1])
        except (TypeError, ValueError):
            continue
        if opened <= 0:
            continue
        entry = _typical(hi_i, lo_i, c_i)
        wl, ws = _oi_side_split(f[i] if i < len(f) else None)

        # То же и для будущего хода: битые бары просто не участвуют
        # в проверке «прошла ли цена сквозь уровень».
        fut_lo = [x for x in (_f(v) for v in lo[i + 1:]) if x is not None]
        fut_hi = [x for x in (_f(v) for v in h[i + 1:]) if x is not None]
        future_low = min(fut_lo) if fut_lo else price
        future_high = max(fut_hi) if fut_hi else price
        future_low = min(future_low, price)
        future_high = max(future_high, price)

        for lev in LEVERAGES:
            step = entry / lev
            long_liq, short_liq = entry - step, entry + step
            # Плечо ×L несёт свою долю прироста. Доли равные:
            # распределения по ступеням мы не знаем, и придумывать
            # его значило бы выдать допущение за измерение.
            part = opened / len(LEVERAGES)
            if long_liq > 0 and future_low > long_liq:
                raw.append({"price": long_liq, "side": "лонги",
                            "usd": part * wl})
            if future_high < short_liq:
                raw.append({"price": short_liq, "side": "шорты",
                            "usd": part * ws})
    if not raw:
        return []

    raw.sort(key=lambda z: z["price"])
    zones: list[dict] = []
    for z in raw:
        if zones and z["price"] <= zones[-1]["price"] * (1 + CLUSTER_PCT / 100):
            g = zones[-1]
            g["_sum"] += z["price"] * z["usd"]
            g["usd"] += z["usd"]
            g["price"] = g["_sum"] / g["usd"] if g["usd"] else g["price"]
            if z["side"] != g["side"]:
                g["side"] = "смешанная"
        else:
            zones.append({"price": z["price"], "side": z["side"],
                          "usd": z["usd"], "_sum": z["price"] * z["usd"]})

    top = max(z["usd"] for z in zones)
    out = []
    for z in zones:
        if top and z["usd"] / top < MIN_SHARE:
            continue
        pct = (z["price"] / price - 1) * 100
        d = {"price": z["price"], "side": z["side"],
             "usd": round(z["usd"], 2), "pct": round(pct, 2)}
        if atr_pct and atr_pct > 0:
            d["atr"] = round(abs(pct) / atr_pct, 2)
        out.append(d)
    out.sort(key=lambda z: -z["usd"])
    return out[:MAX_ZONES]


def fuel_to_cap(zones: list[dict] | None, price: float,
                mcap_usd: float | None) -> dict | None:
    """Плечо под ценой и над ней — в долях КАПИТАЛИЗАЦИИ.

    По выводу 26.08: рынок без спотовых денег двигают чужим плечом,
    и значимо не сколько его в долларах, а сколько относительно
    размера самой монеты. Разбор четырёх монет дал разброс в 255 раз
    при сопоставимых ходах — ни одна другая величина так не делила.

    Работает только с долларовыми зонами (liq_zones_oi). Долевые веса
    liq_zones сюда не годятся: доля не переводится в капитализацию.
    """
    if not zones or not mcap_usd or mcap_usd <= 0 or price <= 0:
        return None
    below = sum(z.get("usd") or 0 for z in zones if z.get("price", 0) < price)
    above = sum(z.get("usd") or 0 for z in zones if z.get("price", 0) > price)
    if below <= 0 and above <= 0:
        return None
    return {"below": round(below / mcap_usd, 4),
            "above": round(above / mcap_usd, 4),
            "below_usd": round(below, 2), "above_usd": round(above, 2)}


def stop_vs_zones(stop_price: float | None, zones: list[dict] | None,
                  price: float, atr_pct: float = 0.0,
                  guard_atr: float = 0.35) -> dict | None:
    """Не стоит ли наш стоп ровно в плите (Т-5).

    Правило из разбора прибыльных: стоп внутри скопления снимут виком,
    не двигая рынок против позиции. Правило записано давно, а проверить
    его до сих пор было нечем.

    Возвращает {hit: зона, dist_atr} когда стоп внутри защитной полосы,
    иначе None. Это ПОДСКАЗКА, а не запрет: карта модельная, и
    ошибиться она может в обе стороны.
    """
    if not zones or not isinstance(stop_price, (int, float)) or price <= 0:
        return None
    if stop_price <= 0 or not atr_pct or atr_pct <= 0:
        return None
    guard_pct = atr_pct * guard_atr
    best = None
    for z in zones:
        zp = z.get("price") or 0
        if zp <= 0:
            continue
        d = abs(zp / stop_price - 1) * 100
        if d <= guard_pct and (best is None or d < best[0]):
            best = (d, z)
    if not best:
        return None
    d, z = best
    return {"hit": {k: z.get(k) for k in ("price", "side", "usd", "weight")},
            "dist_atr": round(d / atr_pct, 2),
            "note": ("стоп стоит в плите %s (модель) — такие снимают виком, "
                     "не двигая рынок против позиции" % z.get("side"))}
