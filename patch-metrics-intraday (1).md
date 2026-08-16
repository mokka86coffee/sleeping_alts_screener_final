# Интрадей-блок в метрики

## файл: `analytics/metrics.py`

Требует нового модуля `analytics/intraday.py` — он идёт отдельным
файлом, патчем не создаётся.

Считается здесь, а не в семействе, по трём причинам. Часовые свечи
на этом шаге уже загружены и лежат в `RunCache` — сети ноль. Метрики
считаются для КАЖДОЙ монеты выборки, включая журнальные, которые
возвращает `tracked_symbols`, — значит величины будут у всех звёзд, а
не только у сработавших; на этом за сессию трижды сели и ярусы, и
правило выбытия. И FLOW остаётся дневным: он про тренд, а это про
ближайшие сутки-двое.

Ничего не ломает: новый ключ в `raw`, читателей у него пока нет.
Первая задача блока — попасть в пробу, чтобы по разбросу выбрать
пороги (`techdebt-intraday.md`).

### было

```python
from analytics.indicators import (
    atr_pct, bb_width_pct, bb_width_rank, drawdown_from_high,
    obv_slope_pct, pct_change, rvol, stoch_rsi, vortex_phase,
    median, volume_ratio,
)
```

### стало

```python
from analytics.indicators import (
    atr_pct, bb_width_pct, bb_width_rank, drawdown_from_high,
    obv_slope_pct, pct_change, rvol, stoch_rsi, vortex_phase,
    median, volume_ratio,
)
from analytics.intraday import scan as intraday_scan
```

### было

```python
    vp_4h = vortex_phase(highs_4h, lows_4h, closes_4h, 14) if closes_4h else {}
```

### стало

```python
    vp_4h = vortex_phase(highs_4h, lows_4h, closes_4h, 14) if closes_4h else {}

    # ── Интрадей: что происходит прямо сейчас ──
    # Отдельная шкала и отдельный горизонт — сутки-двое против недель
    # у остального в этом словаре. Считается по тем же часовым
    # свечам, что загружены выше, дополнительной сети ноль.
    #
    # Получасовки сюда пока не приходят: их нет в кэше, а запрос на
    # всю выборку стоит веса. Модуль шкалы не знает и примет любую —
    # добавление второй шкалы см. techdebt-intraday.md, пункт П-3.
    intraday = intraday_scan(kl_1h, "1h") if kl_1h else {}
```

### было

```python
        "history_days": len(closes_1d),
```

### стало

```python
        "history_days": len(closes_1d),
        "intraday": intraday,
```
