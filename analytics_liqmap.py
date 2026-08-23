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
    return out[:MAX_ZONES]


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
