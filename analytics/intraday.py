"""Интрадей-слой: что происходит с монетой прямо сейчас.

Отвечает на вопрос горизонта в один-два дня, а не на вопрос тренда.
Семейство FLOW остаётся дневным и об этом модуле не знает; всё, что
здесь считается, идёт в карточку монеты — приборную панель, задача
которой избавить от открывания графика по каждой монете.

Шкала не выбирается заранее. Один и тот же момент на разных шкалах
даёт противоположный ответ: у PROM 16 августа на получасовке перекрест
вортекса уже состоялся (VI+ 1.12 против VI− 0.86) и крупные покупки
стояли на минимуме, а на часовике перекреста не было вовсе (0.87
против 1.18), и пузыри схлопнулись внутрь часовых баров. Поэтому
каждая величина считается на той шкале, которую передали, а решение
«где раньше» принимает вызывающий, сравнивая результаты.

Все функции чистые и сетевых вызовов не делают: свечи передаются
готовыми. Часовые уже лежат в RunCache после metrics, получасовые
требуют отдельного запроса — см. techdebt-intraday.md.
"""

from __future__ import annotations

from analytics.indicators import median, vortex_phase
from core.binance import (
    K_CLOSE, K_HIGH, K_LOW, K_QUOTE_VOLUME, K_TAKER_BUY_QUOTE, K_TRADES,
)

# ── Крупные заявки ───────────────────────────────────────────
# Норма среднего размера сделки берётся за неделю. Короче — норма
# начинает подстраиваться под сам всплеск, длиннее — перестаёт
# описывать текущий режим монеты.
BIG_NORM_BARS = 168

# Во сколько раз средний размер сделки должен превысить норму.
#
# Начальное значение, а не выверенный порог. У dormant на дневках
# стоит 2.5, но там речь о монете с мёртвым оборотом у дна; внутри
# суток средний размер прыгает сильнее, поэтому здесь взято выше.
# Проверять по разбросу — techdebt-intraday.md, пункт П-1.
BIG_TRADE_X = 3.0

# Сколько последних баров отдаём с позициями — столько же, сколько
# рисует карточка.
BIG_TAIL_BARS = 48

# Нейтральная полоса по стороне. Бар с долей покупок 50.1% не
# является покупкой: у такой разметки сторона определялась бы шумом.
SIDE_BUY_MIN = 0.55
SIDE_SELL_MAX = 0.45

# ── Наклон сторон ────────────────────────────────────────────
# Половины окна сравниваются между собой, а не с длинной нормой:
# вопрос «усиливается ли сторона сейчас», а не «сильна ли она
# вообще».
PRESSURE_WINDOW = 12

# ── Вортекс ──────────────────────────────────────────────────
VORTEX_PERIOD = 14
# Докуда искать перекрест. Дальше давность перестаёт быть новостью:
# разворот трёхдневной свежести на часах — это уже состоявшееся
# движение, а не момент входа.
CROSS_LOOKBACK = 72

# ── Диапазон ─────────────────────────────────────────────────
RANGE_BARS = 168


def _col(klines: list[list], idx: int) -> list[float]:
    out: list[float] = []
    for k in klines:
        try:
            out.append(float(k[idx]))
        except (TypeError, ValueError, IndexError):
            out.append(0.0)
    return out


def _side(buy_quote: float, quote: float) -> str:
    """Сторона бара по доле тейкер-покупок.

    Нейтраль — не отсутствие данных, а честный ответ «стороны нет».
    """
    if quote <= 0:
        return "none"
    share = buy_quote / quote
    if share >= SIDE_BUY_MIN:
        return "buy"
    if share <= SIDE_SELL_MAX:
        return "sell"
    return "none"


def big_trades(klines: list[list]) -> dict:
    """Бары, набранные немногими крупными сделками, со стороной.

    Средний размер сделки — оборот бара делить на число сделок. Бар,
    где он подскочил над собственной нормой монеты, набран крупным
    участником, а не толпой мелких. Норма — медиана за BIG_NORM_BARS,
    то есть за неделю на часах.

    Честная разница с настоящим пузырём: сторона берётся из доли
    тейкер-покупок ВСЕГО бара, то есть в среднем за час, а не по
    конкретной заявке. Внутри бара крупная покупка и крупная продажа
    гасят друг друга, и такой бар уйдёт в нейтраль.

    Позиции отдаются относительно ХВОСТА в BIG_TAIL_BARS баров — в
    том же виде, в каком их ждёт карточка, чтобы не пересчитывать
    индексы на стороне отрисовки.
    """
    quotes = _col(klines, K_QUOTE_VOLUME)
    trades = _col(klines, K_TRADES)
    buys = _col(klines, K_TAKER_BUY_QUOTE)

    sizes = [
        (q / t) if t > 0 and q > 0 else 0.0
        for q, t in zip(quotes, trades)
    ]
    norm_src = [s for s in sizes[-BIG_NORM_BARS:] if s > 0]
    if len(norm_src) < 20:
        return {}
    norm = median(norm_src)
    if norm <= 0:
        return {}

    tail_from = max(0, len(sizes) - BIG_TAIL_BARS)
    marks: list[dict] = []
    for i in range(tail_from, len(sizes)):
        if sizes[i] <= 0:
            continue
        x = sizes[i] / norm
        if x < BIG_TRADE_X:
            continue
        marks.append({
            "i": i - tail_from,
            "side": _side(buys[i], quotes[i]),
            "x": round(x, 1),
        })

    if not marks:
        return {"count": 0, "max_x": round(max(sizes[-BIG_TAIL_BARS:] or [0]) / norm, 1)}

    return {
        "count": len(marks),
        "buys": sum(1 for m in marks if m["side"] == "buy"),
        "sells": sum(1 for m in marks if m["side"] == "sell"),
        "max_x": max(m["x"] for m in marks),
        "marks": marks,
    }


def pressure(klines: list[list], window: int = PRESSURE_WINDOW) -> dict:
    """Усиливается покупатель или продавец.

    Медиана доли тейкер-покупок за последнее окно против такого же
    предыдущего. Медиана, а не среднее: один толстый бар не должен
    решать за все остальные.

    Наружу — разница в процентных пунктах. Плюс означает, что
    покупатель прибавил, минус — что продавец.
    """
    quotes = _col(klines, K_QUOTE_VOLUME)
    buys = _col(klines, K_TAKER_BUY_QUOTE)
    shares = [
        (b / q) for b, q in zip(buys, quotes) if q > 0
    ]
    if len(shares) < window * 2:
        return {}

    new = median(shares[-window:])
    old = median(shares[-window * 2:-window])
    return {
        "share": round(new * 100, 1),
        "delta": round((new - old) * 100, 1),
        "window": window,
    }


def vortex_cross(klines: list[list]) -> dict:
    """Сторона по вортексу и сколько баров назад она сменилась.

    Давность перекреста — главное здесь, а не сам факт. У PROM на
    получасовке 16 августа перекрест был, на часовике его не было:
    сравнивая давность между шкалами, видно, на какой развернулось
    раньше. Само значение «направление» без давности этого не
    показывает.

    −1 в bars_ago означает, что в пределах CROSS_LOOKBACK смены не
    было: сторона держится дольше, чем мы смотрим.
    """
    highs = _col(klines, K_HIGH)
    lows = _col(klines, K_LOW)
    closes = _col(klines, K_CLOSE)
    if len(closes) < VORTEX_PERIOD + 2:
        return {}

    now = vortex_phase(highs, lows, closes, VORTEX_PERIOD)
    if not now or now.get("label") == "no data":
        return {}

    up_now = now["vi_plus"] > now["vi_minus"]

    # Идём назад по одному бару и ищем, где знак разницы был другим.
    # Считается по тем же рядам, обрезанным справа: индикатор не
    # знает будущего, и обрезка честно воспроизводит его прошлое
    # значение.
    bars_ago = -1
    limit = min(CROSS_LOOKBACK, len(closes) - VORTEX_PERIOD - 1)
    for back in range(1, limit + 1):
        cut = len(closes) - back
        past = vortex_phase(highs[:cut], lows[:cut], closes[:cut], VORTEX_PERIOD)
        if not past or past.get("label") == "no data":
            break
        if (past["vi_plus"] > past["vi_minus"]) != up_now:
            bars_ago = back
            break

    return {
        "dir": "up" if up_now else "down",
        "vi_plus": now["vi_plus"],
        "vi_minus": now["vi_minus"],
        "spread": round(now["vi_plus"] - now["vi_minus"], 4),
        "bars_ago": bars_ago,
    }


def range_pos(klines: list[list], bars: int = RANGE_BARS) -> float | None:
    """Где цена внутри диапазона окна, в процентах.

    Ноль — на минимуме окна, сто — на максимуме. Отвечает «у низа
    или у верха» без графика. None означает вырожденный диапазон,
    а не середину: у монеты, стоявшей неделю в одной точке,
    положения внутри диапазона нет.
    """
    highs = [h for h in _col(klines, K_HIGH)[-bars:] if h > 0]
    lows = [l for l in _col(klines, K_LOW)[-bars:] if l > 0]
    closes = [c for c in _col(klines, K_CLOSE)[-bars:] if c > 0]
    if not highs or not lows or not closes:
        return None
    hi, lo = max(highs), min(lows)
    if hi <= lo:
        return None
    return round((closes[-1] - lo) / (hi - lo) * 100, 1)


def scan(klines: list[list], scale: str) -> dict:
    """Все интрадей-величины одной шкалы одним словарём.

    scale — только подпись: модуль не знает и не должен знать, часы
    это или получасовки. Сравнением шкал между собой занимается
    вызывающий.

    Пустой словарь означает «на этой шкале мерить нечего» — истории
    не хватило. Отличимо от нулей, и это важно: ноль крупных заявок
    и отсутствие замера — разные ответы.
    """
    if not klines or len(klines) < VORTEX_PERIOD + 2:
        return {}

    out: dict = {"scale": scale, "bars": len(klines)}
    big = big_trades(klines)
    if big:
        out["big"] = big
    pres = pressure(klines)
    if pres:
        out["pressure"] = pres
    vx = vortex_cross(klines)
    if vx:
        out["vortex"] = vx
    pos = range_pos(klines)
    if pos is not None:
        out["range_pos"] = pos
    return out


def earliest_turn(scans: list[dict]) -> dict:
    """На какой шкале разворот вверх случился раньше.

    Сравнивает давность перекреста между шкалами. Смысл в том, что
    мелкая шкала видит разворот раньше крупной, и разница в часах —
    это фора, которую даёт наблюдение за ней.

    Сравниваются БАРЫ, приведённые к минутам, иначе «10 баров назад»
    на получасовке и на часах означали бы разное время.
    """
    best: dict = {}
    for s in scans:
        vx = s.get("vortex") or {}
        if vx.get("dir") != "up" or vx.get("bars_ago", -1) < 0:
            continue
        minutes = _scale_minutes(s.get("scale", ""))
        if minutes <= 0:
            continue
        ago = vx["bars_ago"] * minutes
        if not best or ago > best["minutes_ago"]:
            best = {
                "scale": s["scale"],
                "bars_ago": vx["bars_ago"],
                "minutes_ago": ago,
            }
    return best


def _scale_minutes(scale: str) -> int:
    """Минут в баре по подписи шкалы. Ноль — подпись не разобрана."""
    table = {"15m": 15, "30m": 30, "1h": 60, "2h": 120, "4h": 240}
    return table.get(scale, 0)
