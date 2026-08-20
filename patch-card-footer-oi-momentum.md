# Патч: подвал карточки — OI-момент и флаг «поздно»

Перед применением: `analytics_momentum.py` — новый файл, его нужно
положить в корень репозитория ДО прогона `apply_patch.py` (патчер
работает только по уже существующим файлам).

Порядок применения не важен: блоки независимы по файлам, атомарность
внутри файла держит сам скрипт.

## файл: `detectors_flow.py`

### было
```python
from detectors_flow_core import Bar, FlowContext, build_context
from detectors_flow_signal import SubcaseSignal
```

### стало
```python
from detectors_flow_core import Bar, FlowContext, build_context
from detectors_flow_signal import SubcaseSignal
from analytics_momentum import oi_cycle
```

### было
```python
def _oi_stats(symbol: str) -> dict:
    """Ряд открытого интереса за окно Binance (И-1).

    Различитель «сквиз или набор», которого нет у ценового следа:
    вынос, ПОСТРОИВШИЙ интерес и удержавший его (плато), и вынос,
    схлопнувшийся вместе с движением, по свечам неотличимы. Binance
    отдаёт максимум 30 дневных точек, поэтому подъём и удержание
    меряются по пику окна OI, без выравнивания с вершинами ценовых
    разгонов; выравнивание — следующим шагом, когда у величин
    появится потребитель (техдолг И-1).

    x — текущий OI к медиане окна без последней точки; rise_x — во
    сколько раз пик окна выше минимума до него (набор); held_pct —
    сколько процентов пика дожило до сегодня (плато против сброса);
    peak_age_days — давность пика. Знака направления у OI нет
    намеренно: плато не говорит, кто в позиции, — направление
    добавляет фандинг, по отдельности обе величины немые.

    Пустой словарь — точек меньше восьми, мерить нечего.
    """
    hist = get_oi_history(symbol, period="1d", limit=30)
    vals: list[float] = []
    for r in hist or []:
        try:
            v = float(r.get("sumOpenInterest", 0))
        except (TypeError, ValueError, AttributeError):
            continue
        if v > 0:
            vals.append(v)
    if len(vals) < 8:
        return {}

    cur = vals[-1]
    med = median(vals[:-1])
    if med <= 0:
        return {}

    peak_idx = max(range(len(vals)), key=lambda i: vals[i])
    peak = vals[peak_idx]
    low_before = min(vals[:peak_idx + 1])
    rise = (peak / low_before) if low_before > 0 else 0.0
    held = (cur / peak * 100) if peak > 0 else 0.0

    return {
        "x": round(cur / med, 2),
        "rise_x": round(rise, 2),
        "held_pct": round(held, 1),
        "peak_age_days": len(vals) - 1 - peak_idx,
    }
```

### стало
```python
def _oi_stats(symbol: str) -> dict:
    """Ряд открытого интереса за окно Binance (И-1).

    Различитель «сквиз или набор», которого нет у ценового следа:
    вынос, ПОСТРОИВШИЙ интерес и удержавший его (плато), и вынос,
    схлопнувшийся вместе с движением, по свечам неотличимы. Binance
    отдаёт максимум 30 дневных точек, поэтому подъём и удержание
    меряются по пику окна OI, без выравнивания с вершинами ценовых
    разгонов; выравнивание — следующим шагом, когда у величин
    появится потребитель (техдолг И-1).

    rise_x/held_pct/peak_age_days/cycles считает analytics_momentum
    .oi_cycle() — общая формула для карточки, зала, орбиты и отчёта.
    Раньше та же идея жила ещё в analytics_metrics.oi_profile() и
    в detectors_flow_leverage._oi_state() с другими окнами и другой
    формулой held_pct — три источника расходились между собой (см.
    Ч-1 тех.долга). x остаётся здесь отдельно: он читает медиану
    ряда, а не его профиль подъёма.

    Пустой словарь — точек меньше восьми, мерить нечего.
    """
    hist = get_oi_history(symbol, period="1d", limit=30)
    vals: list[float] = []
    for r in hist or []:
        try:
            v = float(r.get("sumOpenInterest", 0))
        except (TypeError, ValueError, AttributeError):
            continue
        if v > 0:
            vals.append(v)
    if len(vals) < 8:
        return {}

    profile = oi_cycle(vals)
    if not profile:
        return {}

    cur = vals[-1]
    med = median(vals[:-1])
    out = dict(profile)
    out["peak_age_days"] = out.pop("peak_age")
    out["x"] = round(cur / med, 2) if med > 0 else 0.0
    return out
```

### было
```python
    cases = {
        name: {
            "score": round(sig.score, 1),
            "base": round(sig.base_score, 1),
            "cut": round(sig.cut, 2),
            "reasons": sig.reasons[:3],
            "mults": sig.mults,
        }
        for name, sig in results
    }
```

### стало
```python
    cases = {
        name: {
            "score": round(sig.score, 1),
            "base": round(sig.base_score, 1),
            "cut": round(sig.cut, 2),
            "reasons": sig.reasons[:3],
            "mults": sig.mults,
            # Признак прежде оседал только внутри диспетчера (влиял
            # на выбор победителя) и никуда не долетал дальше. Ч-4
            # тех.долга: фигура fuel помечает себя late на свежем
            # росте (growth_load), но экран об этом молчал.
            "late": bool(getattr(sig, "late", False)),
        }
        for name, sig in results
    }
```

## файл: `analytics_pulse.py`

### было
```python
DELTA_KEYS = (
    "price", "vol_1h", "vol_4h", "vol_1d", "rvol_1h", "atr_pct",
    "up_low", "buy_share", "oi_x", "oi_usd", "vx_strength", "rel_vol",
    "score",
)
```

### стало
```python
# vol_1h/vol_4h/rvol_1h убраны: они мерят возраст текущего бара, а не
# рынок, и дельта по ним отвечает не на тот вопрос (см. Ч-2 тех.долга).
# funding и oi_held добавлены — их снимок уже пишет, дельты не было.
DELTA_KEYS = (
    "price", "vol_1d", "atr_pct", "funding",
    "up_low", "buy_share", "oi_x", "oi_held", "oi_usd", "vx_strength",
    "rel_vol", "score",
)
```

### было
```python
        ("oi_held", oi.get("held_pct")),
        ("rel_vol", ctx.get("rel_vol")),
```

### стало
```python
        ("oi_held", oi.get("held_pct")),
        ("oi_cycles", oi.get("cycles")),
        ("rel_vol", ctx.get("rel_vol")),
```

## файл: `render_orbit.py`

### было
```python
def _star_intraday(raw: dict) -> dict:
```

### стало
```python
def _star_oi(c: Candidate | None) -> dict:
    """Профиль открытого интереса в звезду: рост, удержание, циклы.

    Источник — context.oi_hist, единственная формула на проект
    (analytics_momentum.oi_cycle, см. Ч-1 тех.долга). Пусто, если
    семейство не отработало или ряда OI не было: ноль здесь соврал
    бы — «плечо не набрано» и «не мерили» разные ответы.
    """
    if c is None or not c.flow:
        return {}
    oi = ((c.flow.get("context") or {}).get("oi_hist")) or {}
    if not oi:
        return {}
    out: dict = {}
    if oi.get("rise_x") is not None:
        out["oiRise"] = float(oi["rise_x"])
    if oi.get("held_pct") is not None:
        out["oiHeld"] = float(oi["held_pct"])
    if oi.get("cycles") is not None:
        out["oiCycles"] = int(oi["cycles"])
    return out


def _star_late(c: Candidate | None) -> dict:
    """Победивший подкейс помечен late — фигура уже отыграна (Ч-4).

    Диспетчер кладёт признак внутрь cases[имя_кейса] и раньше нигде
    не читал его дальше себя самого. Здесь — первое место, где он
    долетает до экрана.
    """
    if c is None or not c.flow:
        return {}
    case = str(c.flow.get("case") or "")
    info = (c.flow.get("cases") or {}).get(case) or {}
    return {"late": True} if info.get("late") else {}


def _star_intraday(raw: dict) -> dict:
```

### было
```python
            **_star_intraday(raw),
            **_star_unlocks(raw),
```

### стало
```python
            **_star_intraday(raw),
            **_star_unlocks(raw),
            **_star_oi(c),
            **_star_late(c),
```

## файл: `render_cardscene.py`

### было
```
    if (c.speedV) foot.push(['скорость хода', c.speedV + ' ATR/бар', '']);
```

### стало
```
    if (c.speedV) foot.push(['скорость хода', c.speedV + ' ATR/бар', '']);

    /* Момент OI: во сколько раз набрали и какая доля удержана, плюс
       цикличность. Разбор GPS/PORTAL/ONG/BLESS показал, что один
       снимок «рост+удержание» не различает балласт и топливо — нужен
       ещё счётчик: сколько раз этот же подъём уже сдувался. cycles=0
       при заметном росте — не «спокойно», а «ещё не проверено»
       временем: ровно случай GPS перед обвалом (rise_x=2.98,
       held_pct=100, cycles=0). ONG в это же время держит третий
       подряд подъём без единого отката. */
    if (num(c.oiRise) !== null && num(c.oiHeld) !== null) {
      var oiHot = c.oiRise >= 2 && c.oiHeld >= 70;
      foot.push(['плечо',
        '×' + xf(c.oiRise) + ' · держит ' + Math.round(c.oiHeld) + '%' +
        (num(c.oiCycles) !== null ? ' · цикл ' + (c.oiCycles + 1) : ''),
        oiHot ? 'hot' : '']);
    }
```

### было
```
    if (num(c.volBg) !== null) foot.push(['фон суток', '×' + xf(c.volBg), 'warm']);
```

### стало
```
    if (num(c.volBg) !== null) foot.push(['фон суток', '×' + xf(c.volBg), 'warm']);
    /* Ч-4: fuel помечает себя late на свежем росте (growth_load) —
       диспетчер это уже знает при выборе победителя, экран молчал. */
    if (c.late) foot.push(['осторожно', 'фигура уже отыграна', 'hot']);
```
