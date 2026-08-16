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

from analytics.indicators import median, true_ranges, vortex_phase
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

# ── Заметность и скорость ────────────────────────────────────
# Минимум баров, на которых процентиль ещё является процентилем.
# На мелкой шкале с тремя сделками в баре «медиана размера сделки»
# перестаёт описывать что-либо, и заметность начинает срабатывать на
# случайностях.
PROM_MIN_BARS = 50

# Нижняя граница знаменателя заметности. Совершенно однородная шкала
# дала бы деление на ноль, а по смыслу — бесконечную заметность
# любого всплеска. Ограничиваем и то и другое.
PROM_FLOOR = 0.05
PROM_CAP = 50.0

# Период ATR для скорости хода. Тот же, что у вортекса, — чтобы обе
# величины описывали одно окно наблюдения.
ATR_PERIOD = 14


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


def background(klines: list[list], window: int = 24) -> float | None:
    """Фон суток против недельной нормы, кратностью.

    Отвечает «монета вообще торгуется в эти сутки», в отличие от
    объёма последнего бара, который отвечает «сейчас всплеск». Одно
    число смешивало оба вопроса: у монеты с мёртвой неделей и живым
    последним часом и у монеты с ровным приличным оборотом кратность
    выходила похожей.

    None означает «мерить нечем» — истории не хватило. Отличимо от
    единицы, которая значит «фон ровно как обычно».
    """
    quotes = [q for q in _col(klines, K_QUOTE_VOLUME) if q > 0]
    if len(quotes) < BIG_NORM_BARS // 2:
        return None
    norm = median(quotes[-BIG_NORM_BARS:])
    if norm <= 0:
        return None
    recent = median(quotes[-window:])
    return round(recent / norm, 2)


def prominence(klines: list[list]) -> dict:
    """Насколько крупная заявка ЗАМЕТНА именно на этой шкале.

    Механика, из которой растёт величина. Заявка размером X на баре с
    оборотом V поднимает средний размер сделки примерно в (1 + X/V)
    раз. Значит заметность одной и той же заявки — это её доля в
    обороте бара, и чем мельче шкала, тем меньше V и тем крупнее
    след. Часовой бар вбирает вшестеро больший оборот, чем
    десятиминутный, и та же заявка в нём тонет. Поэтому у PROM памп
    12 августа читался на десятиминутке и не читался на часе.

    Мельче — заметнее, но лишь до предела: норма считается медианой,
    а медиана по трём сделкам на баре медианой не является. Оптимум
    там, где след заявки уже виден, а норма ещё устойчива, и находится
    он замером, а не рассуждением.

    Отсюда формула. Кратность самого крупного бара сравнивается не с
    назначенным порогом, а с СОБСТВЕННЫМ разбросом шкалы:

        q = (max_x − 1) / (p90_x − 1)

    Единица вычитается, потому что x = 1 означает «ровно норма», то
    есть отсутствие события; мерить надо превышение над нормой, а не
    саму кратность. Если самый крупный бар даёт ×5 при девяностом
    процентиле ×2.5 — событие для этой шкалы заурядно, q около трёх.
    Те же ×5 при процентиле ×1.2 — q двадцать, событие торчит.

    Величина безразмерная, поэтому «×5 на десяти минутах» и «×20 на
    шести часах» назначать не нужно: оба порога выводятся из данных
    сами, а сравнивать шкалы можно напрямую.
    """
    quotes = _col(klines, K_QUOTE_VOLUME)
    trades = _col(klines, K_TRADES)
    sizes = [
        (q / t) if t > 0 and q > 0 else 0.0
        for q, t in zip(quotes, trades)
    ]
    norm_src = [s for s in sizes[-BIG_NORM_BARS:] if s > 0]
    if len(norm_src) < PROM_MIN_BARS:
        return {}
    norm = median(norm_src)
    if norm <= 0:
        return {}

    xs = sorted(s / norm for s in norm_src)
    p90 = xs[min(len(xs) - 1, int(len(xs) * 0.9))]

    tail = [s for s in sizes[-BIG_TAIL_BARS:] if s > 0]
    if not tail:
        return {}
    max_x = max(tail) / norm

    if max_x <= 1.0:
        return {"q": 0.0, "max_x": round(max_x, 2), "p90_x": round(p90, 2)}

    denom = max(p90 - 1.0, PROM_FLOOR)
    return {
        "q": round(min((max_x - 1.0) / denom, PROM_CAP), 2),
        "max_x": round(max_x, 2),
        "p90_x": round(p90, 2),
        "trades_med": round(median([t for t in trades[-BIG_NORM_BARS:] if t > 0] or [0]), 1),
    }


def move_speed(klines: list[list], bars: int = BIG_TAIL_BARS) -> dict:
    """Скорость крупнейшего хода: сколько ATR набирается за бар.

    Памп за два часа и рост за сутки отличаются не амплитудой, а
    амплитудой на единицу времени. Причём мерить её в процентах
    нельзя: десять процентов у спокойной монеты и у волатильной —
    разные события. Нормируем на собственный ATR шкалы:

        v = (вершина − дно) / (ATR × баров между ними)

    Двадцать ATR за двенадцать баров — событие. Те же двадцать ATR за
    двести баров — тренд. Величина безразмерная и сравнима между
    шкалами так же, как заметность.

    Ход ищется как крупнейший подъём: минимум окна и максимум ПОСЛЕ
    него. Ход до минимума к этому минимуму отношения не имеет.
    """
    highs = _col(klines, K_HIGH)[-bars:]
    lows = _col(klines, K_LOW)[-bars:]
    closes = _col(klines, K_CLOSE)[-bars:]
    if len(closes) < ATR_PERIOD + 2:
        return {}

    trs = true_ranges(highs, lows, closes)
    if len(trs) < ATR_PERIOD:
        return {}
    atr = sum(trs[-ATR_PERIOD:]) / ATR_PERIOD
    if atr <= 0:
        return {}

    valid = [(i, v) for i, v in enumerate(lows) if v > 0]
    if not valid:
        return {}
    low_i, low_v = min(valid, key=lambda p: p[1])
    after = [(i, v) for i, v in enumerate(highs[low_i:], low_i) if v > 0]
    if not after:
        return {}
    hi_i, hi_v = max(after, key=lambda p: p[1])

    span = max(1, hi_i - low_i)
    amp = hi_v - low_v
    if amp <= 0:
        return {"atr_move": 0.0, "bars": span, "v": 0.0}

    return {
        "atr_move": round(amp / atr, 1),
        "bars": span,
        "v": round(amp / atr / span, 3),
    }


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
    bg = background(klines)
    if bg is not None:
        out["bg"] = bg
    prom = prominence(klines)
    if prom:
        out["prom"] = prom
    spd = move_speed(klines)
    if spd:
        out["speed"] = spd
    return out


def pick_scale(scans: list[dict]) -> dict:
    """На какой шкале смотреть эту монету.

    Два независимых ответа, и это не избыточность. Заметность
    отвечает «где виден крупный участник», скорость — «где виден сам
    ход». Совпали — подтверждение. Разошлись — на монете идут два
    разных события, и смотреть надо оба места; молча выбрать одно
    значило бы половину потерять.
    """
    by_prom = max(
        (s for s in scans if (s.get("prom") or {}).get("q")),
        key=lambda s: s["prom"]["q"], default=None,
    )
    by_speed = max(
        (s for s in scans if (s.get("speed") or {}).get("v")),
        key=lambda s: s["speed"]["v"], default=None,
    )
    out: dict = {}
    if by_prom:
        out["by_prom"] = {"scale": by_prom["scale"], "q": by_prom["prom"]["q"]}
    if by_speed:
        out["by_speed"] = {"scale": by_speed["scale"], "v": by_speed["speed"]["v"]}
    if by_prom and by_speed:
        out["agree"] = by_prom["scale"] == by_speed["scale"]
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
