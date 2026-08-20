# Патч: определение состояния монеты — из render_orbit.py в analytics

Предыдущий патч подвала положил `_star_oi()`/`_star_late()` прямо в
`render_orbit.py` — рабочий путь данных, но не то место: как только
эти поля понадобятся залу или отчёту, придётся либо звать
render-модуль из другого render-модуля (лишняя связь), либо заводить
вторую копию (тот же способ разъехаться, что уже был у volume_ratio).
Логика переезжает в `analytics_momentum.star_oi()`/`star_late()`,
`render_orbit.py` их только зовёт.

Второе: подвал карточки раньше сам решал, «горячо» ли плечо
(`oiRise >= 2 && oiHeld >= 70` — порог, придуманный в JS на ходу).
Теперь решение — `oi_state()` в analytics_momentum, и подвал просто
показывает готовую метку (`held` / `repeat` / `cleared`) словом, а не
пересчитывает условие заново.

Применять после `analytics_momentum.py` (обновлён — см. отдельно) и
после `patch-card-footer-oi-momentum.md` (этот патч правит то, что
тот уже положил).

## файл: `render_orbit.py`

### было
```python
from core_binance import get_btc_context
from core_config import (
    FROZEN_MAX_CHANGE_PCT, FROZEN_TAIL_MIN, FROZEN_TAIL_PCT, ORBIT_BG_SRC,
)
from core_models import Candidate, RunSnapshot
from render_theme import esc
from render_flow_report import case_key, CASE_RU, _cap, _data, flow_order
from analytics_indicators import median
```

### стало
```python
from core_binance import get_btc_context
from core_config import (
    FROZEN_MAX_CHANGE_PCT, FROZEN_TAIL_MIN, FROZEN_TAIL_PCT, ORBIT_BG_SRC,
)
from core_models import Candidate, RunSnapshot
from render_theme import esc
from render_flow_report import case_key, CASE_RU, _cap, _data, flow_order
from analytics_indicators import median
from analytics_momentum import star_oi, star_late
```

### было
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

### стало
```python
def _star_intraday(raw: dict) -> dict:
```

### было
```python
            **_star_intraday(raw),
            **_star_unlocks(raw),
            **_star_oi(c),
            **_star_late(c),
```

### стало
```python
            **_star_intraday(raw),
            **_star_unlocks(raw),
            **star_oi(c),
            **star_late(c),
```

## файл: `render_cardscene.py`

### было
```
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

### стало
```
    /* Состояние плеча — готовая метка из analytics_momentum.oi_state(),
       а не свой порог. Раньше «горячо» решалось прямо здесь
       (rise>=2 && held>=70) — то же самое, независимо от кода, уже
       решает сервер, и держать два места принятия одного решения
       значит однажды их развести, как разошлись две реализации
       volume_ratio. held — самое настороженное: цикл ещё ни разу не
       закрывался (GPS перед обвалом стоял именно здесь). repeat —
       тот же подъём уже сдувался в этом окне хотя бы раз (BLESS).
       cleared — плечо разгружено, мешать некому. */
    if (c.oiState) {
      var oiWord = c.oiState === 'cleared' ? 'разгружено'
        : c.oiState === 'repeat' ? 'цикл ' + ((c.oiCycles || 0) + 1)
        : 'не проверено';
      var oiTone = c.oiState === 'held' ? 'hot'
        : c.oiState === 'repeat' ? 'warm' : '';
      foot.push(['плечо',
        '×' + xf(c.oiRise) + ' · держит ' + Math.round(c.oiHeld) + '% · ' + oiWord,
        oiTone]);
    }
```
