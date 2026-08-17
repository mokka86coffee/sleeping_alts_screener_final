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

import math

from analytics.indicators import median, true_ranges, vortex_phase
from core.binance import (
    K_CLOSE, K_HIGH, K_LOW, K_OPEN, K_QUOTE_VOLUME, K_TAKER_BUY_QUOTE,
    K_TRADES, K_VOLUME,
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

# ── Импакт: цена за единицу давления ─────────────────────────
# Минимальная глубина ноги, при которой она считается ногой, а не
# колебанием. Заглушка: на часах шесть процентов ловят и настоящие
# проливы, и крупную рябь. Калибровать по разбросу — П-10.
IMPACT_LEG_PCT = 6.0

# Дельта приводится к миллионам: в сырых долларах импакт получается
# числом с шестью нулями после запятой и глазом не читается.
IMPACT_UNIT = 1_000_000.0

# Сколько ног отдаём наружу. Три — минимум, на котором видно
# направление: одна ничего не сравнивает, две дают знак, три
# показывают, устойчив ли он.
IMPACT_LEGS = 3


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


# ── Лестница шкал ────────────────────────────────────────────
# Всплеск имеет собственную длительность, и фиксированная шкала его
# либо режет, либо размазывает. Ступени складываются из часовых
# свечей агрегацией — сети на это не нужно, часовые уже в кэше.
#
# Вниз от часа агрегацией не спуститься: получасовки требуют запроса
# и берутся только для монет, попадающих на карточку (П-3).
LADDER_SCALES = (1, 2, 3, 6, 12)

# ── Связка с открытым интересом ───────────────────────────────
# Иерархия подделываемости, по которой выстроены приоритеты: цена и
# всё производное от неё рисуется дешевле всего, объём накручивается
# самоторговлей, размер сделки и дельта — тоже, только дороже. А
# открытый интерес требует настоящей маржи с двух сторон, и нарисовать
# его, не заплатив, нельзя. Поэтому там, где OI спорит с остальными
# величинами, прав он.
#
# Цена считается стоящей на месте, если ушла меньше чем на столько.
STANCE_FLAT_PCT = 3.0

# Изменение открытого интереса, ниже которого считаем его плоским.
STANCE_OI_PCT = 2.0


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


def fold(klines: list[list], n: int) -> list[list]:
    """Складывает свечи по n штук, свежий край всегда полный.

    Остаток обрезается со СТАРОЙ стороны. Иначе при длине, не кратной
    n, самая свежая группа окажется короче остальных, и её объём
    выйдет заниженным не рынком, а арифметикой — та же ловушка, что в
    metrics.aggregate_quote_fill.

    Поля складываются по своей природе: обороты и число сделок
    суммируются, максимум берётся максимумом, минимум минимумом,
    открытие от первой свечи, закрытие от последней.
    """
    if n <= 1:
        return list(klines)
    if len(klines) < n:
        return []

    trimmed = klines[len(klines) % n:]
    out: list[list] = []
    for i in range(0, len(trimmed), n):
        chunk = trimmed[i:i + n]
        if len(chunk) < n:
            break
        row = [0.0] * 11
        try:
            row[K_OPEN] = float(chunk[0][K_OPEN])
            row[K_CLOSE] = float(chunk[-1][K_CLOSE])
            row[K_HIGH] = max(float(k[K_HIGH]) for k in chunk)
            row[K_LOW] = min(float(k[K_LOW]) for k in chunk)
            row[K_VOLUME] = sum(float(k[K_VOLUME]) for k in chunk)
            row[K_QUOTE_VOLUME] = sum(float(k[K_QUOTE_VOLUME]) for k in chunk)
            row[K_TRADES] = sum(float(k[K_TRADES]) for k in chunk)
            row[K_TAKER_BUY_QUOTE] = sum(
                float(k[K_TAKER_BUY_QUOTE]) for k in chunk)
        except (TypeError, ValueError, IndexError):
            continue
        out.append(row)
    return out


def ladder(klines: list[list], scales: tuple = LADDER_SCALES) -> dict:
    """Заметность заявки на каждой ступени и шкала, где она видна лучше.

    Одна и та же заявка на шкале с меньшим оборотом бара оставляет
    больший след: часовой бар вбирает вшестеро больше десятиминутного,
    и заявка в нём тонет. Поэтому шкала наблюдения не назначается, а
    выбирается — той, где заметность максимальна.

    Ступени только вверх от часа: агрегация складывает свечи, но не
    делит их. Мельче часа — отдельный запрос, см. П-3.
    """
    steps: list[dict] = []
    for n in scales:
        folded = fold(klines, n)
        if len(folded) < PROM_MIN_BARS:
            continue
        prom = prominence(folded)
        if not prom or not prom.get("q"):
            continue
        steps.append({
            "scale": f"{n}h",
            "q": prom["q"],
            "max_x": prom["max_x"],
            "bars": len(folded),
        })
    if not steps:
        return {}
    best = max(steps, key=lambda s: s["q"])
    return {"steps": steps, "best": {"scale": best["scale"], "q": best["q"]}}


def _oi_change_pct(oi: list[float]) -> float | None:
    """Изменение открытого интереса за ряд, в процентах.

    Ряд приходит от вызывающего: intraday в сеть не ходит. Крайние
    точки берутся ненулевыми — в истории OI попадаются пропуски, и
    ноль на краю дал бы изменение в тысячи процентов.
    """
    vals = [v for v in oi or [] if v and v > 0]
    if len(vals) < 4:
        return None
    return (vals[-1] / vals[0] - 1.0) * 100.0


def stance(klines: list[list], oi: list[float] | None = None) -> dict:
    """Что происходит: накопление, выход толпы или набор шорта.

    Три величины вместе, и ни одна по отдельности этого не говорит.
    Дельта показывает, кто агрессивен. Цена — приняли ли агрессию.
    Открытый интерес — открывались позиции или закрывались.

    Именно OI разделяет случаи, которые без него выглядят одинаково.
    BLESS: белые пузыри на четырёх днищах подряд, дельта в плюс,
    цена стоит — картина накопления. Но OI падал через каждое дно,
    минус пятьдесят пять процентов за две недели: покупали
    ЗАКРЫВАЮЩИЕ, а не новые. BEAT в тот же день: цена на минимуме
    всей истории, дельта в плюс, и OI впервые разворачивается вверх —
    вот это набор.

    Чего величина не говорит: у открытого интереса нет знака. Рост на
    минимуме означает и набор лонга, и набор шорта. Различает
    фандинг, которого здесь нет; поэтому «набор шорта» называется
    только там, где на него указывает отрицательная дельта.

    Пустой словарь, когда OI не передали: без него остаются две
    величины из трёх, а на двух все интересные случаи неотличимы.
    """
    closes = [c for c in _col(klines, K_CLOSE) if c > 0]
    if len(closes) < 12:
        return {}
    oi_pct = _oi_change_pct(oi or [])
    if oi_pct is None:
        return {}

    deltas = _delta_series(klines)
    quotes = _col(klines, K_QUOTE_VOLUME)
    net = sum(deltas)
    turn = sum(quotes)
    share = abs(net) / turn if turn > 0 else 0.0
    price_pct = (closes[-1] / closes[0] - 1.0) * 100.0

    flat = abs(price_pct) <= STANCE_FLAT_PCT
    down = price_pct < -STANCE_FLAT_PCT
    oi_up = oi_pct >= STANCE_OI_PCT
    oi_down = oi_pct <= -STANCE_OI_PCT
    buying = net > 0 and share >= BALANCE_MIN_SHARE
    selling = net < 0 and share >= BALANCE_MIN_SHARE

    verdict = ""
    if buying and oi_up and (flat or down):
        verdict = "накопление"
    elif buying and oi_down:
        # Покупают закрывающие: шорты фиксируют или лонги усредняются
        # и тут же выносятся. Позиций в сумме становится меньше.
        verdict = "выход толпы"
    elif selling and oi_up:
        verdict = "набор шорта"
    elif selling and oi_down:
        verdict = "делеверидж"

    out = {
        "price_pct": round(price_pct, 1),
        "delta_m": round(net / IMPACT_UNIT, 1),
        "share": round(share, 3),
        "oi_pct": round(oi_pct, 1),
    }
    if verdict:
        out["verdict"] = verdict
    return out


def big_levels(klines: list[list]) -> dict:
    """Средняя цена крупных покупок против текущей: поддержка или навес.

    Крупная покупка ниже текущей цены — участник в плюсе, ему торопиться
    некуда. Выше — он в минусе и ждёт безубытка, то есть представляет
    будущее предложение. Одни и те же метки означают поддержку или
    навес в зависимости от того, с какой стороны они остались.

    Средняя взвешена по кратности: заявка ×5 к норме весит впятеро
    против заявки ×1. Без веса одна мелкая метка сдвигала бы среднюю
    так же, как настоящая плита.

    Пустой словарь, если крупных покупок в окне не было: ноль меток и
    «метки под ценой» — разные ответы.
    """
    big = big_trades(klines)
    marks = (big or {}).get("marks") or []
    buys = [m for m in marks if m.get("side") == "buy"]
    if not buys:
        return {}

    closes = _col(klines, K_CLOSE)
    tail_from = max(0, len(closes) - BIG_TAIL_BARS)
    num = den = 0.0
    for m in buys:
        idx = tail_from + int(m.get("i", 0))
        if idx < 0 or idx >= len(closes) or closes[idx] <= 0:
            continue
        w = float(m.get("x") or 1.0)
        num += closes[idx] * w
        den += w
    last = next((c for c in reversed(closes) if c > 0), 0.0)
    if den <= 0 or last <= 0:
        return {}

    avg = num / den
    return {
        "avg": round(avg, 10),
        "n": len(buys),
        "vs_price_pct": round((last / avg - 1.0) * 100.0, 1),
        "kind": "поддержка" if avg < last else "навес",
    }


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


def _delta_series(klines: list[list]) -> list[float]:
    """Чистая дельта тейкеров по барам, в валюте котировки.

    Покупки тейкером приходят полем, продажи считаются как остаток:
    оборот минус покупки. Отсюда дельта = 2 × покупки − оборот. По
    знаку закрытия дельту не восстанавливают — бар может закрыться
    вверх на чистых продажах и наоборот.
    """
    quotes = _col(klines, K_QUOTE_VOLUME)
    buys = _col(klines, K_TAKER_BUY_QUOTE)
    return [2.0 * b - q for b, q in zip(buys, quotes)]


def _pivots(closes: list[float], pct: float) -> list[tuple[int, float]]:
    """Точки разворота ряда: зигзаг с порогом в процентах.

    Нужен, чтобы разбить ряд на ноги. Порог в процентах, а не в ATR,
    сознательно: ATR сам меняется вместе с волатильностью, и на
    затухающем рынке ноги начали бы дробиться, а на разгоне —
    слипаться. Постоянный порог даёт ноги, сравнимые между собой во
    времени, а это и есть цель.
    """
    if len(closes) < 3:
        return []
    thr = pct / 100.0
    vals = [(i, v) for i, v in enumerate(closes) if v > 0]
    if len(vals) < 3:
        return []

    out: list[tuple[int, float]] = []
    # Пока направление не определено, следим за обоими краями: первым
    # пробитый порог и задаёт сторону, а вершиной ноги становится тот
    # край, от которого пробили. Слежение за одним краем сразу после
    # старта давало бы ложную первую ногу на любом ряду, начавшемся
    # с движения против будущего тренда.
    hi_i, hi_v = vals[0]
    lo_i, lo_v = vals[0]
    direction = 0
    ext_i, ext_v = vals[0]

    for i, v in vals[1:]:
        if direction == 0:
            if v > hi_v:
                hi_i, hi_v = i, v
            if v < lo_v:
                lo_i, lo_v = i, v
            if hi_v > 0 and (hi_v - v) / hi_v >= thr:
                out.append((hi_i, hi_v))
                direction, ext_i, ext_v = -1, i, v
            elif lo_v > 0 and (v - lo_v) / lo_v >= thr:
                out.append((lo_i, lo_v))
                direction, ext_i, ext_v = 1, i, v
            continue

        if direction > 0:
            if v > ext_v:
                ext_i, ext_v = i, v
            elif ext_v > 0 and (ext_v - v) / ext_v >= thr:
                out.append((ext_i, ext_v))
                direction, ext_i, ext_v = -1, i, v
        else:
            if v < ext_v:
                ext_i, ext_v = i, v
            elif ext_v > 0 and (v - ext_v) / ext_v >= thr:
                out.append((ext_i, ext_v))
                direction, ext_i, ext_v = 1, i, v

    out.append((ext_i, ext_v))
    return out


def impact(klines: list[list], pct: float = IMPACT_LEG_PCT) -> dict:
    """Сколько цены съедает миллион чистых продаж — по нисходящим ногам.

    Цена движется не от объёма, а от того, сколько пассивной
    ликвидности стоит против агрессии. Значит отношение «сдвиг цены к
    чистой дельте» — прямая мера глубины стакана: те же продажи,
    сдвинувшие цену вдвое слабее, означают вдвое больше покупателей
    на этих уровнях.

    BLESS 12-14 августа: два пролива по 400 миллионов чистых продаж
    уронили цену на 43% и на 25%. Второй при этом был крупнее в
    ШТУКАХ — доллары те же, а цена ниже, — то есть разрыв ещё больше,
    чем в процентах.

    Три вещи, из-за которых величина считается именно так.

    Сдвиг берётся логарифмом, а не процентом: −43% и −25% в процентах
    несравнимы между собой, в логарифмах −0.55 и −0.29 складываются и
    делятся честно.

    Дельта суммируется по ноге целиком, включая положительные бары:
    вопрос в ЧИСТОМ давлении, а откуп внутри пролива это давление и
    уменьшает.

    Рядом отдаётся скорость подачи — дельта на бар. Без неё каскад
    ликвидаций и спокойная раздача сливаются в одно число: импакт
    зависит не только от суммы, но и от того, за сколько времени её
    подали. Первый пролив BLESS был вертикальной свечой, второй
    растянут — и часть разницы объясняется этим, а не глубиной
    стакана.
    """
    closes = _col(klines, K_CLOSE)
    if len(closes) < 20:
        return {}
    piv = _pivots(closes, pct)
    if len(piv) < 2:
        return {}

    deltas = _delta_series(klines)
    legs: list[dict] = []
    for (i0, v0), (i1, v1) in zip(piv, piv[1:]):
        if v1 >= v0 or v0 <= 0 or v1 <= 0 or i1 <= i0:
            continue
        drop = math.log(v1 / v0)                       # отрицательный
        net = sum(deltas[i0:i1 + 1])
        bars = i1 - i0
        leg = {
            "drop_pct": round((v1 / v0 - 1) * 100, 1),
            "bars": bars,
            "delta_m": round(net / IMPACT_UNIT, 1),
        }
        if net < 0:
            press = -net / IMPACT_UNIT
            leg["impact"] = round(abs(drop) / press, 4)
            leg["rate_m"] = round(press / max(1, bars), 2)
        legs.append(leg)

    if not legs:
        return {}
    legs = legs[-IMPACT_LEGS:]

    out: dict = {"legs": legs}
    scored = [l for l in legs if "impact" in l]
    if len(scored) >= 2:
        last, prev = scored[-1]["impact"], scored[-2]["impact"]
        out["last"] = last
        out["prev"] = prev
        if prev > 0:
            # Меньше единицы — та же продажа двигает цену слабее, чем
            # в прошлый раз. Это утверждение о ПРОШЛОЙ упругости, а не
            # предсказание: новый продавец может прийти любого размера.
            out["ratio"] = round(last / prev, 2)
    elif scored:
        out["last"] = scored[-1]["impact"]
    return out


# Ниже этой доли чистый перевес считается шумом: на любом отрезке
# покупки и продажи не сходятся ровно, и пара процентов расхождения
# ничего не означают.
BALANCE_MIN_SHARE = 0.03


def flow_balance(klines: list[list], pct: float = IMPACT_LEG_PCT) -> dict:
    """Кто кого принял: агрессия против пассивной стороны.

    Цена движется не от агрессии, а от того, приняли её или нет.
    Тейкер бьёт по рынку и оставляет след в дельте; мейкер стоит
    лимитами и в дельте не виден вовсе — виден только по тому, что
    агрессия не сдвинула цену.

    Отсюда четыре случая, и информация живёт в двух из них:

        цена вниз, дельта минус  — слив, знаки сошлись
        цена вниз, дельта ПЛЮС   — РАЗДАЧА: покупали агрессивно,
                                   а приняли лимитными продажами
        цена вверх, дельта плюс  — разгон, знаки сошлись
        цена вверх, дельта МИНУС — ПОГЛОЩЕНИЕ: продавали агрессивно,
                                   а приняли лимитными покупками

    Совпадение знаков означает, что рынок просто ехал. Расхождение
    означает, что против толпы кто-то стоял, и это единственный
    способ его увидеть: пассивная сторона в потоке не отражается.

    BLESS за наблюдаемый период: чистая агрессия положительная —
    выносы дали +5.2 и +6.28 млрд покупок против примерно двенадцати
    млрд продаж, — а цена ниже, чем была до первого выноса. Значит
    всю эту массу выбрали лимитные продавцы.

    Оговорка, которая меняет смысл слова «раздача». Это фьючерс:
    тейкер-покупка открывает лонг против мейкера, встающего в шорт.
    Пассивная сторона не сбрасывала актив, а НАБИРАЛА короткую
    позицию. Различает открытый интерес: рос вместе с выносом —
    строили шорт, падал — закрывались лонги, и это уже капитуляция.
    Здесь OI не читается, поэтому величина называет расхождение, а не
    трактует его.

    Перевес нормируется на оборот той же ноги: в долларах монеты
    несравнимы между собой, в долях оборота — вполне.
    """
    closes = _col(klines, K_CLOSE)
    if len(closes) < 20:
        return {}
    piv = _pivots(closes, pct)
    if len(piv) < 2:
        return {}

    deltas = _delta_series(klines)
    quotes = _col(klines, K_QUOTE_VOLUME)

    legs: list[dict] = []
    distrib = absorb = 0.0
    for (i0, v0), (i1, v1) in zip(piv, piv[1:]):
        if i1 <= i0 or v0 <= 0 or v1 <= 0:
            continue
        net = sum(deltas[i0:i1 + 1])
        turn = sum(quotes[i0:i1 + 1])
        if turn <= 0:
            continue
        share = abs(net) / turn
        down = v1 < v0
        if down and net > 0:
            kind = "раздача"
        elif not down and net < 0:
            kind = "поглощение"
        else:
            kind = "слив" if down else "разгон"

        if share >= BALANCE_MIN_SHARE:
            if kind == "раздача":
                distrib += abs(net)
            elif kind == "поглощение":
                absorb += abs(net)

        legs.append({
            "dir": "down" if down else "up",
            "move_pct": round((v1 / v0 - 1) * 100, 1),
            "delta_m": round(net / IMPACT_UNIT, 1),
            "share": round(share, 3),
            "kind": kind,
            "bars": i1 - i0,
        })

    if not legs:
        return {}

    # Окно целиком. Самое сильное утверждение получается не по ногам,
    # а по всему отрезку: чистая агрессия одного знака при цене,
    # ушедшей в другую сторону, означает, что всю её приняли.
    first = next((c for c in closes if c > 0), 0.0)
    last = next((c for c in reversed(closes) if c > 0), 0.0)
    net_all = sum(deltas)
    turn_all = sum(quotes)
    out: dict = {
        "legs": legs[-IMPACT_LEGS:],
        "net_m": round(net_all / IMPACT_UNIT, 1),
        "distrib_m": round(distrib / IMPACT_UNIT, 1),
        "absorb_m": round(absorb / IMPACT_UNIT, 1),
    }
    if first > 0 and last > 0:
        out["price_pct"] = round((last / first - 1) * 100, 1)
        share_all = abs(net_all) / turn_all if turn_all > 0 else 0.0
        if share_all >= BALANCE_MIN_SHARE:
            if net_all > 0 and last < first:
                out["window"] = "раздача"
            elif net_all < 0 and last > first:
                out["window"] = "поглощение"
            else:
                out["window"] = "согласие"
            out["share"] = round(share_all, 3)
    return out


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


def scan(klines: list[list], scale: str,
         oi: list[float] | None = None) -> dict:
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
    imp = impact(klines)
    if imp:
        out["impact"] = imp
    bal = flow_balance(klines)
    if bal:
        out["balance"] = bal
    lad = ladder(klines)
    if lad:
        out["ladder"] = lad
    lv = big_levels(klines)
    if lv:
        out["big_levels"] = lv
    if oi:
        st = stance(klines, oi)
        if st:
            out["stance"] = st
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
