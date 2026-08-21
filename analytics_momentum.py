"""Момента-величины FLOW, общие для карточки, зала, орбиты и отчёта.

Единственное место, где считается «во сколько раз вырос открытый
интерес и держится ли он», и — впервые — сколько раз этот же подъём
уже сдувался. Прежде идея «набрали и держат» была посчитана трижды
(analytics_metrics.oi_profile, detectors_flow._oi_stats,
detectors_flow_leverage._oi_state) тремя разными окнами и без сверки
между собой — на GPS и PORTAL в один и тот же момент они дали бы
разные числа. Здесь одна формула, её и зовут все потребители экрана.
Внутренний гейт flow_leverage не трогаем: у него свой дневной ряд и
свой смысл (перекос шортов, а не карточка), это отдельная задача.

Второе: одного снимка «рост + удержание» недостаточно, чтобы отличить
топливо от балласта. Разбор ONG/GPS/PORTAL/BLESS показал разницу:
ONG держит третий подряд подъём OI без единого отката — предыдущие
сдувались (видно на TradingView, не в 30-дневном окне Binance).
BLESS дважды за полгода набирала и сдувала, и это же видно и по OI,
и по heatmap ликвидаций — те же вертикали, тот же откат. cycles
считает, сколько раз в пределах доступного окна ряд OI уже поднимался
заметно выше опоры и возвращался к ней — тем же автоматом, что
_count_rallies в detectors_flow_core.py, только на ряду OI, а не цены;
переносить дословно нельзя — там опора «дно после падения», здесь
опора это просто минимум ряда до сих пор, падения как понятия нет.

Пороги ниже не откалиброваны — как и всё, что вводится впервые в
проекте (см. flow_dormant, flow_leverage на момент заведения): взяты
по порядку величины, требуют правки после первого прогона на разбросе.
"""

from __future__ import annotations

from analytics_pulse import for_symbol as _pulse_for_symbol

# Доля отката от локального пика ряда OI, ниже которой цикл считается
# сдувшимся, а не просто просевшим. Ряд шумит сам по себе, порог
# отделяет шум от настоящего выхода позиций.
CYCLE_FADE_FRAC = 0.5

# Минимальный подъём от опоры до локального пика, чтобы засчитать
# движение циклом, а не дрожанием ряда.
CYCLE_MIN_RISE = 1.15

# Меньше этого точек в ряду — цикличность не измеряется вовсе:
# на коротком ряде счётчик циклов был бы шумом, выдаваемым за факт.
MIN_POINTS = 8


def oi_cycle(values: list[float]) -> dict:
    """Профиль ряда открытого интереса: рост, удержание, циклы.

    values — ряд OI по возрастанию времени, последняя точка текущая.
    Источник (часовой или дневной) может быть любым, лишь бы один и
    тот же на весь проект — расхождение источников уже стоило путаницы
    на GPS/PORTAL.

    rise_x — во сколько раз текущее значение выше минимума ряда.
    held_pct — какая доля набранного (от минимума до максимума ряда)
    удержана сейчас: 100 — стоим на пике, 0 — всё вышло.
    peak_age — давность пика ряда, в шагах ряда от конца (часы либо
    дни — как передан values).

    cycles — сколько ЗАВЕРШЁННЫХ циклов «поднялись и сдулись» видно в
    ряду ДО текущего движения. Завершённый цикл: подъём не меньше
    CYCLE_MIN_RISE от опоры, откат от его вершины не меньше
    CYCLE_FADE_FRAC пройденного хода. Текущее, ещё не закрывшееся
    движение в счёт не идёт — оно и есть то, что описывают rise_x и
    held_pct. Ноль циклов при заметном текущем росте — не «спокойно»,
    а «ещё не проверено»: ровно случай GPS перед обвалом (rise_x=2.98,
    held_pct=100, cycles=0), где решить успело только время, а не счёт.

    Пустой словарь — короче MIN_POINTS точек, мерить нечего.
    """
    row = [v for v in values if v is not None and v > 0]
    if len(row) < MIN_POINTS:
        return {}

    now = row[-1]
    lo, hi = min(row), max(row)
    if lo <= 0 or hi <= lo:
        return {}

    peak_idx = max(range(len(row)), key=lambda i: row[i])

    base = row[0]
    top = base
    in_cycle = False
    cycles = 0
    for v in row[:-1]:      # последняя точка — текущее движение, не цикл
        if not in_cycle:
            if v < base:
                base = v
            if base > 0 and v / base >= CYCLE_MIN_RISE:
                in_cycle = True
                top = v
            continue
        if v > top:
            top = v
            continue
        span = top - base
        if span <= 0:
            in_cycle = False
            continue
        if (top - v) / span >= CYCLE_FADE_FRAC:
            cycles += 1
            base = v
            top = base
            in_cycle = False

    return {
        "rise_x": round(now / lo, 2),
        "held_pct": round((now - lo) / (hi - lo) * 100, 1),
        "peak_age": len(row) - 1 - peak_idx,
        "cycles": cycles,
    }


# ─────────────────────────────────────────────────────────────
# Определение состояния плеча
# ─────────────────────────────────────────────────────────────
# Ниже этого роста плечо не набрано заметно: профиль не выдаёт
# состояния вовсе, а не подставляет неверную метку на шуме ряда.
STATE_RISE_MIN = 1.3

# Ниже этой доли удержания позиции считаются вышедшими: плечо
# разгружено, идти вверх мешать некому через ликвидации.
STATE_CLEARED_MAX = 40.0


def oi_state(profile: dict) -> dict:
    """Единая словесная метка состояния плеча по профилю oi_cycle().

    Не пересчёт — свод уже посчитанных чисел в одну из трёх меток,
    чтобы карточка, зал, орбита и отчёт называли одно и то же
    состояние монеты одинаково, а не как «путь свободен» и «топливо
    сверху» про один и тот же случай (эта путаница уже была в
    проекте между fuel и growth_load, см. Ч-4 тех.долга).

      held    — плечо набрано и держится, ЭТОТ подъём ещё ни разу не
                 закрывался (cycles == 0) в пределах видимого окна.
                 Самое настороженное состояние: GPS перед обвалом стоял
                 именно здесь — rise_x=2.98, held_pct=100, cycles=0.
                 Читается как «не проверено», а не как «спокойно».
      repeat  — то же самое, но такой подъём в этом же окне уже был
                 и сдулся хотя бы раз (cycles >= 1). Не безопаснее
                 held, но есть с чем сравнивать: BLESS стоял здесь
                 дважды за полгода, и оба раза сдувался.
      cleared — held_pct низкий: плечо разгружено, продавать сверху
                 особо некому.

    Пустой словарь — рост ниже STATE_RISE_MIN либо профиля нет
    вовсе: состояние не определено, а не «спокойно».

    Пороги не откалиброваны, как и в oi_cycle() — та же оговорка:
    взяты по порядку величины, требуют правки после первого прогона.
    """
    if not profile:
        return {}
    rise = float(profile.get("rise_x") or 0.0)
    held = float(profile.get("held_pct") or 0.0)
    cycles = int(profile.get("cycles") or 0)

    if rise < STATE_RISE_MIN:
        return {}

    if held < STATE_CLEARED_MAX:
        label = "cleared"
    elif cycles > 0:
        label = "repeat"
    else:
        label = "held"

    return {"label": label, "rise_x": rise, "held_pct": held, "cycles": cycles}


# ─────────────────────────────────────────────────────────────
# Поля для звезды / карточки монеты
# ─────────────────────────────────────────────────────────────
# Читают Candidate целиком, а не сырой context: источник один на весь
# путь данных — context.oi_hist уже посчитан detectors_flow._oi_stats()
# через oi_cycle() выше. Раньше эта сборка жила прямо в render_orbit.py;
# перенесена сюда, чтобы зал, отчёт и орбита звали ОДНУ функцию, а не
# держали рядом свою копию — ровно так разошлись когда-то две реализации
# volume_ratio (см. analytics_indicators.volume_ratio).

def star_oi(candidate) -> dict:
    """Профиль и состояние плеча в плоские поля звезды/карточки.

    Пусто, если семейство не отработало или ряда OI не было: ноль
    здесь соврал бы — «плечо не набрано» и «не мерили» разные ответы.
    """
    flow = getattr(candidate, "flow", None) if candidate is not None else None
    if not flow:
        return {}
    oi = (flow.get("context") or {}).get("oi_hist") or {}
    if not oi:
        return {}

    out: dict = {}
    if oi.get("rise_x") is not None:
        out["oiRise"] = float(oi["rise_x"])
    if oi.get("held_pct") is not None:
        out["oiHeld"] = float(oi["held_pct"])
    if oi.get("cycles") is not None:
        out["oiCycles"] = int(oi["cycles"])

    state = oi_state(oi)
    if state:
        out["oiState"] = state["label"]
    return out


def star_late(candidate) -> dict:
    """Победивший подкейс помечен late — фигура уже отыграна.

    Диспетчер кладёт признак внутрь cases[имя_кейса] (см. Ч-4
    тех.долга) и раньше нигде не читал его дальше себя самого.
    """
    flow = getattr(candidate, "flow", None) if candidate is not None else None
    if not flow:
        return {}
    case = str(flow.get("case") or "")
    info = (flow.get("cases") or {}).get(case) or {}
    return {"late": True} if info.get("late") else {}


# ─────────────────────────────────────────────────────────────
# Этап 2: что изменилось за последние часы
# ─────────────────────────────────────────────────────────────
# Этаж 1 (столбы сцены, oi_state выше) отвечает «готова ли монета
# сейчас». Этаж 2 — единственный вопрос, ради которого заведён
# analytics_pulse.py: что произошло с прошлого прогона, за шесть
# часов, за сутки. Материал уже копится в pulse.json (record()
# вызывается из run.py), для_symbol() уже умеет доставать дельты —
# не хватало только выбора ОДНОГО наблюдения на экран из нескольких
# горизонтов и полей сразу.

# Вес горизонта: свежее решает больше, но не единолично — сдвиг за
# сутки всё равно может перевесить, если он заметно крупнее.
_HORIZON_WEIGHT = {"prev": 1.0, "h6": 0.85, "h24": 0.6}

# Пороги отсечки шума по каждому полю — ниже них дельта не
# отличима от дрожания замера и не годится в наблюдение.
_NOISE = {
    "score": 5.0,        # баллов
    "oi_x": 0.3,         # кратности
    "buy_share": 0.01,   # долей единицы
    "price_pct": 3.0,    # процентов цены
    # Спред часового вортекса карточки (intraday.vortex, то же поле,
    # что рисует «вортекс … едва/уверенно»). Порог не откалиброван —
    # взят по порядку величины того же рода признаков (buy_share);
    # первый прогон покажет разброс spread по рынку.
    "ivx_spread": 0.03,
}


def pulse_note(symbol: str) -> dict:
    """Самое значимое изменение по pulse.json за час/шесть/сутки.

    Тот же приём взвешивания, что podium.notes() уже применяет к
    интрадей-полям: вес относительно СОБСТВЕННОГО порога поля, чтобы
    разные оси (score, плечо, перевес сторон, цена) были сравнимы
    между собой, а не просто отсортированы по абсолютной величине.

    Разворот вортекса (vx_flip) идёт отдельной строкой с фиксированным
    высоким весом: это качественная смена, а не количественный сдвиг,
    сравнивать её в тех же единицах не с чем.

    Пустой словарь — истории меньше двух точек (for_symbol сам это
    возвращает пустым) либо ни одна дельта не прошла порог шума.
    """
    hist = _pulse_for_symbol(symbol)
    if not hist:
        return {}

    scored: list[tuple[float, str, dict]] = []

    for span in ("prev", "h6", "h24"):
        d = hist.get(span)
        if not d:
            continue
        w = _HORIZON_WEIGHT.get(span, 0.5)

        for key, unit in (("score", 10.0), ("oi_x", 1.0),
                          ("buy_share", 0.01), ("price_pct", 5.0),
                          ("ivx_spread", 0.1)):
            v = d.get(key)
            if v is None or abs(v) < _NOISE[key]:
                continue
            scored.append((abs(v) / unit * w, span, {"kind": key, "delta": v}))

    flip = hist.get("vx_flip")
    if flip:
        scored.append((3.0, "prev", {
            "kind": "vx_flip", "from": flip.get("from"), "to": flip.get("to"),
        }))

    # Флип часового вортекса карточки — тот же приём, что vx_flip
    # выше, но для intraday.vortex (ivx_*), а не для дневного
    # FLOW-вортекса. Разные источники держатся раздельно: смешать их
    # значило бы потерять, какой именно вортекс развернулся.
    iflip = hist.get("ivx_flip")
    if iflip:
        scored.append((3.0, "prev", {
            "kind": "ivx_flip", "from": iflip.get("from"), "to": iflip.get("to"),
        }))

    if not scored:
        return {}

    scored.sort(key=lambda t: -t[0])
    _, span, info = scored[0]
    info["span"] = span
    return info


def star_pulse(symbol: str) -> dict:
    """Плоские поля для звезды: что изменилось за ближайший горизонт.

    Одно наблюдение, не весь pulse_note() целиком — экран показывает
    одну строку, а не таблицу; выбор уже сделан внутри pulse_note().
    """
    note = pulse_note(symbol)
    if not note:
        return {}
    out = {"pulseKind": note["kind"], "pulseSpan": note["span"]}
    if "delta" in note:
        out["pulseDelta"] = note["delta"]
    if "from" in note:
        out["pulseFrom"] = note["from"]
        out["pulseTo"] = note["to"]
    return out


# ─────────────────────────────────────────────────────────────
# Состояние цикла: отдан ли ход
# ─────────────────────────────────────────────────────────────
# Не то же самое, что cycle_done() в detectors_flow_config.py: тот
# решает судьбу ЗАПИСИ ЖУРНАЛА (выбытие) и намеренно консервативен —
# там ошибка в одну сторону стоит дороже (потерянная монета хуже
# лишней), поэтому он смотрит только на ход с вершины не ниже
# CYCLE_TREND_DONE_X (10.0). Здесь другой вопрос — что показать на
# карточке ПРЯМО СЕЙЧАС, и здесь обе ошибки стоят примерно поровну.
#
# BLESS показал разрыв между этими двумя вопросами: вершина хода
# ×7.74, ниже порога cycle_done — журнал его не выбросит, и вдобавок
# запись помечена added_manually, что глушит даже эту проверку. Но
# 76% отданного хода — уже не «обычные колебания базы», это тот же
# смысл, который CYCLE_GIVEBACK_MAX проверяет выше десяти, просто
# порог здесь мягче и живёт отдельно от решения о выбытии.
CYCLE_GIVEBACK_WARN = 0.60


def cycle_state(peak_x: float | None, now_x: float | None) -> dict:
    """Отдан ли ход, независимо от гейта выбытия из журнала.

    peak_x — вершина хода от дна цикла, now_x — текущее положение от
    того же дна. Пустой словарь — вершины нет либо ход ещё не отдан
    заметно: молчание здесь означает «нечего показывать», а не
    «ход не отдан» — величина попросту не смотрит настолько глубоко.
    """
    peak = float(peak_x or 0.0)
    now = float(now_x or 0.0)
    if peak <= 1.0 or now <= 0:
        return {}
    given = 1.0 - now / peak
    if given < CYCLE_GIVEBACK_WARN:
        return {}
    return {"peak_x": round(peak, 2), "given_pct": round(given * 100, 1)}


def star_cycle(peak_x, now_x) -> dict:
    """Плоские поля звезды: отдан ли ход, для предупреждения на карточке."""
    state = cycle_state(peak_x, now_x)
    if not state:
        return {}
    return {"cyclePeakX": state["peak_x"], "cycleGivenPct": state["given_pct"]}


# ─────────────────────────────────────────────────────────────
# Дивергенция цены и потока
# ─────────────────────────────────────────────────────────────
# Не новый индикатор — разбор уже посчитанного. BLESS показал
# классику на Klinger Oscillator (в проекте не считается): второй
# пик цены на августовском проливе стоял примерно там же, где
# первый, а осциллятор дал заметно более низкий второй пик — поток
# слабеет при том же уровне цены. OBV в analytics_indicators уже
# считает ту же идею (приток со знаком движения цены), просто
# никогда не сравнивался с ценой по двум вершинам. Вопрос тот же,
# только на уже имеющемся инструменте вместо нового.
from analytics_indicators import obv_series as _obv_series

# Доля окна, в которой ищется второй (более свежий) пик — остальное
# уходит под поиск первого. Треть — ориентир, не калибровка.
DIVERGENCE_TAIL_FRAC = 3

# Насколько второй пик может быть НИЖЕ первого и всё ещё считаться
# тем же уровнем, а не обычным спадом.
DIVERGENCE_PRICE_TOL = 0.03

# Минимальный зазор между пиками в барах — иначе один и тот же
# локальный максимум ловится дважды через шум соседних дней.
DIVERGENCE_MIN_GAP = 3

# Насколько OBV на втором пике должен быть ниже первого (в долях
# размаха ряда), чтобы это не было шумом. Не откалибровано.
DIVERGENCE_OBV_WEAK = 0.05


def momentum_divergence(closes: list[float], volumes: list[float]) -> dict:
    """Слабеет ли поток на втором пике цены при том же уровне цены.

    closes/volumes — один и тот же дневной хвост (например
    spark_1d/spark_vol кандидата), одинаковой длины и без сдвига
    индексов между собой.

    Ищутся два последних заметных пика цены: второй — максимум
    последней трети ряда, первый — максимум всего, что было раньше
    него. OBV сравнивается в тех же двух точках. Пустой словарь —
    пиков не нашлось, зазор между ними меньше DIVERGENCE_MIN_GAP,
    второй пик заметно ниже первого (это уже не дивергенция, а
    обычный спад), либо OBV не ослаб настолько, чтобы отличаться от
    шума ряда.
    """
    n = len(closes)
    if n < 10 or n != len(volumes):
        return {}

    third = max(3, n // DIVERGENCE_TAIL_FRAC)
    tail = closes[-third:]
    i2 = n - third + max(range(len(tail)), key=lambda i: tail[i])
    if i2 < DIVERGENCE_MIN_GAP + 2:
        return {}

    head = closes[:i2]
    i1 = max(range(len(head)), key=lambda i: head[i])
    if i2 - i1 < DIVERGENCE_MIN_GAP:
        return {}

    p1, p2 = closes[i1], closes[i2]
    if p1 <= 0 or p2 <= 0:
        return {}
    if p2 < p1 * (1.0 - DIVERGENCE_PRICE_TOL):
        return {}

    obv = _obv_series(closes, volumes)
    span = max((abs(v) for v in obv), default=0.0) or 1.0
    drop_share = (obv[i1] - obv[i2]) / span
    if drop_share < DIVERGENCE_OBV_WEAK:
        return {}

    return {
        "price_pct": round((p2 / p1 - 1.0) * 100.0, 1),
        "obv_drop_share": round(drop_share, 3),
        "bars_between": i2 - i1,
    }


def star_divergence(candidate) -> dict:
    """Плоские поля звезды: дивергенция по дневному хвосту (24 точки).

    Источник — spark_1d/spark_vol, уже посчитанные метриками и
    оставленные в срезе кандидата (KEEP_SERIES в analytics_metrics.py).
    Дополнительных данных и запросов не требуется.
    """
    raw = getattr(candidate, "raw", None) if candidate is not None else None
    if not raw:
        return {}
    s1 = raw.get("spark_1d") or []
    sv = raw.get("spark_vol") or []
    n = min(len(s1), len(sv))
    closes: list[float] = []
    vols: list[float] = []
    for i in range(n):
        try:
            closes.append(float(s1[i]))
            vols.append(float(sv[i]))
        except (TypeError, ValueError):
            return {}

    d = momentum_divergence(closes, vols)
    if not d:
        return {}
    return {"divPricePct": d["price_pct"], "divShare": d["obv_drop_share"]}
