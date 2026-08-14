"""Спячка · монета отспала своё и стоит.

Состояние ДО движения, а не во время и не после. Остальные пять
подкейсов описывают то, что уже происходит: накопление, разряд,
поглощение, агрессию, снятое предложение. Спячка — единственное, что
предшествует всему этому, и её в семействе не было.

Почему её не ловил никто: каждый подкейс требует свидетельств, а
спячка определяется их ОТСУТСТВИЕМ. Событий нет, всплесков нет,
диапазон не сужается — он просто стоит. Hidden хочет растущий поток,
spring — сжимающийся клин, churn — шум. Ничего этого здесь нет по
определению.

И главное, ради чего подкейс вообще имеет смысл при нашем темпе:
СПЯЧКА ДЛИТСЯ. Сжатие и разряд умещаются в один-два дневных бара, и
прогон раз в три часа приходит уже после. Спячка идёт неделями —
застать её можно сотню раз подряд.

Замер, а не сигнал. Подкейс отвечает «здесь может начаться», а не
«начинается»; момента он не знает и знать не может. Место ему в
наблюдении у предполагаемого дна.

Пороги проставлены наугад и подлежат калибровке первым же прогоном:
все пять величин уходят в факты сигнала, чтобы разброс был виден.
"""

from __future__ import annotations

from detectors.flow_config import (
    DORMANT_TAIL_BARS,
    DORMANT_WAKE_X,
    DORMANT_MULT_WAKE,
    DORMANT_BIG_TRADE_X,
    DORMANT_BASE_MIN,
    DORMANT_BIG_NEAR_BARS,
    DORMANT_DROP_MIN,
    DORMANT_BACK_MAX,
    DORMANT_BOUNCE_MAX,
    DORMANT_BOUNCE_MIN,
    DORMANT_INVALID_PCT,
    DORMANT_GROWTH_MIN,
    DORMANT_MIN_BARS,
    DORMANT_MIN_QUOTE_24H,
    DORMANT_MULT_BIG_BUY,
    DORMANT_MULT_BIG_EXIT,
    DORMANT_MULT_BIG_MANY,
    DORMANT_MULT_FLOW,
    DORMANT_QUIET_MAX,
    DORMANT_MULT_QUIET,
    DORMANT_RANGE_MAX,
    DORMANT_SCORE_BASE,
    DORMANT_WINDOW,
)
from detectors.flow_core import FlowContext, _clip, _median
from detectors.flow_signal import SubcaseSignal, veto_bullish

NAME = "flow_dormant"
name = NAME


def _base_shape(ctx: FlowContext) -> dict[str, float]:
    """Форма базы: насколько узок и тих участок после дна.

    Диапазон меряется к СОБСТВЕННОМУ падению монеты, а не в абсолютных
    процентах: десять процентов хода для монеты, упавшей на 90%, —
    это стояние, а для упавшей на 30% — уже движение. Абсолютный порог
    сравнивал бы разные вещи.
    """
    bars = ctx.base[-DORMANT_WINDOW:]
    if len(bars) < DORMANT_MIN_BARS:
        return {}

    lows = [b.low for b in bars if b.low > 0]
    highs = [b.high for b in bars if b.high > 0]
    if not lows or not highs:
        return {}

    lo, hi = min(lows), max(highs)
    if lo <= 0:
        return {}

    span = (hi - lo) / lo * 100.0

    # ── Отскок и возврат ──
    # Это не «пролив», как я закодировал сначала, а полный цикл:
    # флэт, попытка ухода вверх, возврат на дно. Попытка важна сама
    # по себе — она показывает, что спрос есть; возврат показывает,
    # что его пока не хватило.
    #
    # Три точки: дно ДО отскока, вершина отскока, дно ПОСЛЕ. Считать
    # только просадку от вершины мало — она одинакова и у отскока с
    # возвратом, и у обычного сползания без всякой попытки.
    low_idx = min(range(len(bars)), key=lambda i: bars[i].low if bars[i].low > 0 else 1e18)
    head = bars[: low_idx + 1]
    peak = max((b.high for b in head if b.high > 0), default=0.0)
    peak_idx = max(range(len(head)), key=lambda i: head[i].high) if head else 0

    pre = [b.low for b in bars[: peak_idx + 1] if b.low > 0]
    pre_low = min(pre) if pre else lo

    bounce = ((peak - pre_low) / pre_low * 100.0) if pre_low > 0 else 0.0
    # Насколько новое дно выше старого. Около нуля — вернулась туда
    # же, откуда пошла; много — это уже растущая структура, а не
    # возврат в спячку.
    back = ((lo - pre_low) / pre_low * 100.0) if pre_low > 0 else 0.0
    flush = ((peak - lo) / peak * 100.0) if peak > 0 else 0.0

    # Доля падения, которую занимает база. Чем меньше — тем плотнее
    # стоит, тем больше сжатой пружины.
    #
    # Падение приводится к ТОМУ ЖЕ знаменателю, что и span: span
    # считается от низа базы, а drop_pct — от пика, и делить их
    # напрямую нельзя. Падение на 74.8% от пика означает, что пик
    # стоит на 297% выше низа; первая редакция делила 146 на 74.8 и
    # получала 1.96 при пороге 0.55, то есть отвергала медианную
    # монету арифметикой, а не рынком.
    dp = min(0.99, max(0.0, ctx.drop.drop_pct))
    drop = max(1.0, dp / (1.0 - dp) * 100.0)

    # ── Тишина базы, а не текущего бара ──
    # Медианный оборот базы против оборота во время падения. Обе
    # величины собственные, монета сравнивается сама с собой.
    #
    # Хвост исключён: последние бары — это уже возможное
    # пробуждение, и включать их в замер тишины значит требовать,
    # чтобы монета продолжала спать в тот момент, когда она
    # интересна. Ровно на этом spring отвергает всю выборку.
    tail_cut = max(0, len(bars) - DORMANT_TAIL_BARS)
    body = [b.volume for b in bars[:tail_cut] if b.volume > 0]

    # Окно падения берётся из DropContext, а не фиксированным
    # отступом от конца ряда.
    #
    # Первая редакция брала base[-180:-60] и у монет с короткой
    # историей попадала В СЕРЕДИНУ ТОЙ ЖЕ БАЗЫ: AKE сравнивался сам
    # с собой и давал отношение 14.19 при пороге 0.95. Падение у
    # каждой монеты в своём месте, и ядро это место знает.
    #
    # Границы: от пика до начала базы. Пересечения с базой нет по
    # построению, поэтому отношение отвечает на заданный вопрос —
    # тише ли монета сейчас, чем когда падала.
    full = ctx.base
    base_start = max(0, len(full) - DORMANT_WINDOW)
    peak_i = max(0, len(full) - int(ctx.drop.peak_age_days or 0))
    fall = [b.volume for b in full[peak_i:base_start] if b.volume > 0]
    if len(fall) < 5:
        # Пик внутри базы либо истории мало: берём всё, что раньше
        # базы. Хуже по точности, но честнее, чем молча вернуть
        # единицу и притвориться, что замер состоялся.
        fall = [b.volume for b in full[:base_start] if b.volume > 0]

    quiet = (_median(body) / _median(fall)) if body and fall and _median(fall) > 0 else 1.0

    return {
        "quiet": quiet,
        "fall_bars": float(len(fall)),
        "span_pct": span,
        "span_of_drop": span / drop,
        "bars": float(len(bars)),
        "flush_pct": flush,
        "bounce_pct": bounce,
        "back_pct": back,
        "pre_low": pre_low,
        "low": lo,
        "low_idx": float(low_idx),
        "bars_after_low": float(len(bars) - 1 - low_idx),
    }


def _big_trades(ctx: FlowContext, low_idx: float) -> dict[str, float]:
    """След крупных заявок на базе — наш аналог «пузырей».

    Настоящий пузырь у рыночных индикаторов — одна крупная заявка с
    известной стороной и временем внутри дня. На дневках отдельных
    заявок не видно, но СРЕДНИЙ РАЗМЕР СДЕЛКИ считается: оборот бара
    делить на число сделок. Бар, где он подскочил над собственной
    нормой монеты, набран немногими крупными сделками, а не толпой
    мелких — это и есть след крупного участника.

    Поле trades приходит из K_TRADES свечи. Константа в binance.py
    была объявлена и не использовалась нигде.

    Честная разница с настоящим пузырём: сторону берём из доли
    покупок того же бара, то есть знаем её приблизительно и в
    среднем по дню, а не по конкретной заявке.
    """
    window = ctx.base[-DORMANT_WINDOW:]
    bars = [b for b in window if b.trades > 0 and b.volume > 0]
    if len(bars) < DORMANT_MIN_BARS:
        return {}

    sizes = [b.volume / b.trades for b in bars]
    norm = _median(sizes)
    if norm <= 0:
        return {}

    # Норма по всей базе, а поиск — только РЯДОМ С ДНОМ.
    #
    # Крупная заявка в середине флэта и крупная заявка на проливе —
    # разные события. Первая ничего не говорит: кто-то просто прошёл
    # мимо. Вторая означает, что на слив вышел объём и цена его
    # выдержала. Считать их вместе значит смешивать шум с признаком.
    near_from = max(0, int(low_idx) - DORMANT_BIG_NEAR_BARS)
    near_to = min(len(bars), int(low_idx) + DORMANT_BIG_NEAR_BARS + 1)

    # Стороны считаются РАЗДЕЛЬНО, а не усредняются.
    #
    # У дна встречается и то, и другое: крупные продажи — продавец
    # доводит капитуляцию, крупные покупки — кто-то её принимает.
    # Средняя доля покупок по всем крупным барам смешивала бы эти
    # два события в одно бессмысленное число около половины, тогда
    # как интересно именно их сочетание.
    buys, sells, shares = 0, 0, []
    for i, (b, size) in enumerate(zip(bars, sizes)):
        if not (near_from <= i < near_to):
            continue
        if size < norm * DORMANT_BIG_TRADE_X:
            continue
        share = b.buy_volume / b.volume if b.volume > 0 else 0.5
        shares.append(share)
        if share >= 0.5:
            buys += 1
        else:
            sells += 1

    if not shares:
        return {"big_count": 0.0, "big_max_x": max(sizes) / norm}

    return {
        "big_count": float(len(shares)),
        "big_buys": float(buys),
        "big_sells": float(sells),
        "big_max_x": max(sizes) / norm,
        "big_buy_share": sum(shares) / len(shares),
    }


def detect(ctx: FlowContext) -> SubcaseSignal | None:
    """Собирает фигуру спячки либо возвращает None."""
    stop = veto_bullish(ctx, require_zones=False)
    if stop:
        return ctx.reject(NAME, stop)

    bars = ctx.base
    if len(bars) < DORMANT_MIN_BARS:
        return ctx.reject(NAME, f"баров {len(bars)} < {DORMANT_MIN_BARS}")

    if ctx.quote_volume_24h < DORMANT_MIN_QUOTE_24H:
        return ctx.reject(
            NAME,
            f"оборот {ctx.quote_volume_24h:,.0f} < {DORMANT_MIN_QUOTE_24H:,.0f}",
        )

    drop = ctx.drop

    # ── Монета жила ──────────────────────────────────────────
    # Без этого условия подкейс соберёт все мёртвые альты, которых
    # на бирже сотни и которые мертвы всегда. Спячка интересна
    # только там, где был настоящий цикл: есть кому возвращаться.
    if drop.growth_x < DORMANT_GROWTH_MIN:
        return ctx.reject(
            NAME,
            f"цикла не было: рост до пика x{drop.growth_x:.2f} "
            f"< x{DORMANT_GROWTH_MIN}",
        )

    # ── Монета упала ─────────────────────────────────────────
    if drop.drop_pct * 100.0 < DORMANT_DROP_MIN:
        return ctx.reject(
            NAME,
            f"падение {drop.drop_pct * 100:.1f}% < {DORMANT_DROP_MIN}%",
        )

    # ── База была тихой ──────────────────────────────────────
    shape = _base_shape(ctx)
    if not shape:
        return ctx.reject(NAME, "база не измеряется")

    # Тишина базы гейтом БОЛЬШЕ НЕ РЕЖЕТ — стала множителем ниже.
    #
    # Причина не в рынке, а в том, что величину нечем измерить
    # надёжно. Окно падения выводится из peak_age_days, и у
    # половины монет оно вырождается: замер уходит в запасной путь
    # и сравнивает базу со всей историей до неё. В прогоне 14
    # августа это дало отношение с медианой 3.41 при пороге 0.95 и
    # девятнадцать отказов — числа, которым я не могу доверять.
    #
    # Правило простое: величина, которую нельзя посчитать надёжно,
    # не имеет права отвергать монету. Показывать её можно, влиять
    # на порядок внутри подкейса — можно, вычёркивать — нет.

    # ── Отскок был ───────────────────────────────────────────
    # Без попытки ухода вверх это просто мёртвая монета. Отскок —
    # доказательство, что спрос на неё существует; без него спячка
    # неотличима от делистинга в рассрочку.
    if shape["bounce_pct"] < DORMANT_BOUNCE_MIN:
        return ctx.reject(
            NAME,
            f"отскока не было: {shape['bounce_pct']:.1f}% "
            f"< {DORMANT_BOUNCE_MIN}%",
        )
    if shape["bounce_pct"] > DORMANT_BOUNCE_MAX:
        return ctx.reject(
            NAME,
            f"это уже движение: отскок {shape['bounce_pct']:.1f}% "
            f"> {DORMANT_BOUNCE_MAX}%",
        )

    # ── И вернулась на дно ───────────────────────────────────
    # Верхняя граница отделяет возврат от растущей структуры: если
    # новое дно заметно выше старого, монета уже идёт, и это другая
    # фигура, для которой в семействе есть свои подкейсы.
    if shape["back_pct"] > DORMANT_BACK_MAX:
        return ctx.reject(
            NAME,
            f"на дно не вернулась: новое дно на {shape['back_pct']:.1f}% "
            f"выше старого > {DORMANT_BACK_MAX}%",
        )

    if shape["span_of_drop"] > DORMANT_RANGE_MAX:
        return ctx.reject(
            NAME,
            f"база широка: {shape['span_pct']:.1f}% при падении "
            f"{drop.drop_pct * 100:.1f}% — доля {shape['span_of_drop']:.2f} "
            f"> {DORMANT_RANGE_MAX}",
        )

    # ── Фигура закрыта ───────────────────────────────────────
    sig = SubcaseSignal(
        subcase=NAME,
        score=DORMANT_SCORE_BASE,
        base_score=DORMANT_SCORE_BASE,
        horizon_bars=ctx.horizon_bars,
        # Уровень фигуры — дно базы, а не зона из карты уровней.
        #
        # У спячки опорной зоны может не быть вовсе: монета упала
        # ниже всей своей карты, и зон под ценой нет по построению —
        # именно на этом spring отказывает трети выборки. Дно базы
        # существует всегда и является настоящей точкой отсчёта:
        # ниже него фигура перестаёт быть собой.
        zone_price=shape["low"],
    )

    # Уровень недействительности. Не рекомендация и не стоп: просто
    # цена, ниже которой утверждение «монета отспала и стоит»
    # перестаёт быть верным, потому что она снова падает.
    invalid = shape["low"] * (1.0 - DORMANT_INVALID_PCT)

    sig.add(
        f"спит {int(shape['bars'])} баров после падения "
        f"{drop.drop_pct * 100:.0f}% от роста x{drop.growth_x:.1f}, "
        f"отскок {shape['bounce_pct']:.0f}% и возврат на дно "
        f"{shape['low']:.6g}",
        flush_pct=shape["flush_pct"],
        bounce_pct=shape["bounce_pct"],
        back_pct=shape["back_pct"],
        base_low=shape["low"],
        bars_after_low=shape["bars_after_low"],
        invalid_below=invalid,
        drop_pct=drop.drop_pct * 100.0,
        growth_x=drop.growth_x,
        bars_since_bottom=float(drop.bars_since_bottom),
        rel_vol=ctx.rel_vol,
        atr_share=ctx.atr_share,
        span_pct=shape["span_pct"],
        span_of_drop=shape["span_of_drop"],
    )

    # Чем дольше и плотнее спячка, тем выше скор. Обе величины
    # непрерывные, порогов внутри нет — только растяжка.
    length = _clip(drop.bars_since_bottom / (DORMANT_BASE_MIN * 4.0), 0.0, 1.0)
    tight = _clip(1.0 - shape["span_of_drop"] / DORMANT_RANGE_MAX, 0.0, 1.0)
    sig.apply("длительность", 1.0 + length * 0.35)
    sig.apply("плотность", 1.0 + tight * 0.35)

    # ── Крупные заявки на базе ───────────────────────────────
    # То, ради чего подкейс вообще стоит смотреть: сама по себе
    # спячка — это лишь место, а крупная сделка на дне — признак,
    # что место кому-то интересно.
    big = _big_trades(ctx, shape['low_idx'])
    if big:
        sig.add(
            f"крупных сделок на базе: {int(big.get('big_count', 0))}, "
            f"максимум x{big.get('big_max_x', 0):.1f} к норме",
            **{k: float(v) for k, v in big.items()},
        )
        buys = big.get("big_buys", 0.0)
        sells = big.get("big_sells", 0.0)

        # Крупные покупки у дна — то самое «кто-то подхватывает».
        # Главный множитель подкейса.
        if buys >= 3:
            sig.apply("крупные покупки у дна", DORMANT_MULT_BIG_MANY)
        elif buys >= 1:
            sig.apply("крупная покупка у дна", DORMANT_MULT_BIG_BUY)

        # Крупные продажи у дна сами по себе не против: это
        # капитуляция, и её кто-то принимает. Плохо, только когда
        # покупок рядом нет вовсе — тогда продавец вышел, а принять
        # было некому.
        if sells >= 1 and buys == 0:
            sig.apply("крупный выходил", DORMANT_MULT_BIG_EXIT)
            sig.add(
                f"крупных продаж у дна {int(sells)}, покупок нет — "
                f"принять было некому",
                big_sells=sells,
            )
        elif sells >= 1 and buys >= 1:
            sig.add(
                f"у дна и крупные продажи ({int(sells)}), и крупные "
                f"покупки ({int(buys)}) — капитуляцию принимают",
                big_sells=sells, big_buys=buys,
            )

    # ── Поток поверх спячки ──────────────────────────────────
    # Если вдобавок виден растущий поток при стоящей цене — это
    # hidden поверх спячки, и такая пара сильнее каждой части.
    if ctx.flow.delta_slope > 0 and ctx.flow.buy_share > 0.5:
        sig.apply("поток растёт", DORMANT_MULT_FLOW)
        sig.add(
            "поверх спячки виден набор",
            delta_slope=ctx.flow.delta_slope,
            buy_share=ctx.flow.buy_share,
        )

    # ── Тишина базы ──────────────────────────────────────────
    # Множитель, а не гейт: см. выше. Ниже единицы — база была тише
    # падения, то есть монета действительно затихала.
    quiet = shape["quiet"]
    if quiet <= DORMANT_QUIET_MAX:
        sig.apply("база тихая", DORMANT_MULT_QUIET)
    sig.add(
        f"оборот базы {quiet:.2f} к падению "
        f"({int(shape['fall_bars'])} баров замера)",
        quiet=quiet,
        fall_bars=shape["fall_bars"],
    )

    # ── Пробуждение ──────────────────────────────────────────
    # Свойство ТЕКУЩЕГО бара, а не истории, и потому отдельная
    # величина рядом со спячкой, а не гейт над ней.
    #
    # Спячка отвечает «здесь может начаться», пробуждение — «похоже,
    # началось». Первое без второго — наблюдение, второе без
    # первого — обычный всплеск объёма, каких десятки в день.
    # Ценность у их СОЧЕТАНИЯ, и выразить его можно только держа обе
    # величины одновременно.
    waking = ctx.rel_vol
    if waking >= DORMANT_WAKE_X:
        sig.apply("просыпается", DORMANT_MULT_WAKE)
        sig.add(
            f"объём последнего бара x{waking:.1f} к норме — спячка "
            f"нарушена",
            wake_x=waking,
        )
    else:
        sig.add("спит: объём у нормы", wake_x=waking)

    sig.apply("вортекс", ctx.vortex.mult(0.6))

    if sig.weak:
        return ctx.reject(
            NAME,
            f"фигура собралась, но скор {sig.score:.1f} < 20 после множителей",
        )
    return sig
