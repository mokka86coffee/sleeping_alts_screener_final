# Патч · спячка и след крупных заявок

Новый файл `detectors/flow_dormant.py` кладётся целиком (в отдельной
выдаче). Здесь пять патчей: число сделок в баре, константы, реестр,
имя подкейса.

**Аналог пузырей.** `K_TRADES = 8` в `binance.py` объявлена и не
используется нигде. Средний размер сделки — оборот бара делить на
число сделок — говорит, немногими крупными сделками набран объём или
толпой мелких. Это след крупного участника, и данные для него уже
приходят в каждой свече.

---

# 1 · `detectors/flow_core.py` — поле в баре

### было

```python
    # доля фактически набранного времени бара: 1.0 — полный,
    # меньше — головной бар агрегата либо обрезанный край ряда
    fill: float = 1.0
```

### стало

```python
    # Число сделок в баре (K_TRADES свечи).
    #
    # Нужно ровно для одной величины — среднего размера сделки,
    # volume / trades. Она отвечает на вопрос, который иначе не
    # задать по дневкам: объём пришёл немногими крупными заявками
    # или толпой мелких. Первое — след крупного участника, наш
    # аналог «пузырей» рыночных индикаторов.
    #
    # Ноль означает «не измерено» и обрабатывается как отсутствие,
    # а не как «сделок не было»: старые дампы поля не содержат.
    trades: float = 0.0
    # доля фактически набранного времени бара: 1.0 — полный,
    # меньше — головной бар агрегата либо обрезанный край ряда
    fill: float = 1.0
```

### было

```python
                volume=sum(b.volume for b in chunk),
                buy_volume=sum(b.buy_volume for b in chunk),
                sell_volume=sum(b.sell_volume for b in chunk),
                fill=_clip(filled / float(scale), 0.0, 1.0),
```

### стало

```python
                volume=sum(b.volume for b in chunk),
                buy_volume=sum(b.buy_volume for b in chunk),
                sell_volume=sum(b.sell_volume for b in chunk),
                # Складывается, а не усредняется: и оборот, и число
                # сделок аддитивны, поэтому средний размер сделки у
                # склеенного бара считается верно сам собой.
                trades=sum(b.trades for b in chunk),
                fill=_clip(filled / float(scale), 0.0, 1.0),
```

---

# 2 · `detectors/flow.py` — число сделок из свечи

### было

```python
            quote = float(k[K_QUOTE_VOLUME])
            buy = float(k[K_TAKER_BUY_QUOTE])
```

### стало

```python
            quote = float(k[K_QUOTE_VOLUME])
            buy = float(k[K_TAKER_BUY_QUOTE])
            trades = float(k[K_TRADES])
```

### было

```python
                volume=quote,
                buy_volume=buy,
                sell_volume=max(0.0, quote - buy),
                fill=fill,
```

### стало

```python
                volume=quote,
                buy_volume=buy,
                sell_volume=max(0.0, quote - buy),
                trades=trades,
                fill=fill,
```

### было

```python
from core.binance import (
    K_CLOSE,
    K_CLOSE_TIME,
    K_HIGH,
    K_LOW,
    K_OPEN,
    K_OPEN_TIME,
    K_QUOTE_VOLUME,
    K_TAKER_BUY_QUOTE,
    klines_1d,
)
```

### стало

```python
from core.binance import (
    K_CLOSE,
    K_CLOSE_TIME,
    K_HIGH,
    K_LOW,
    K_OPEN,
    K_OPEN_TIME,
    K_QUOTE_VOLUME,
    K_TAKER_BUY_QUOTE,
    K_TRADES,
    klines_1d,
)
```

---

# 3 · `detectors/flow.py` — реестр

### было

```python
import detectors.flow_taker as flow_taker
import detectors.flow_leverage as flow_leverage
```

### стало

```python
import detectors.flow_taker as flow_taker
import detectors.flow_leverage as flow_leverage
import detectors.flow_dormant as flow_dormant
```

### было

```python
    flow_taker,
    flow_leverage,
)
```

### стало

```python
    flow_taker,
    flow_leverage,
    flow_dormant,
)
```

### было

```python
CASE_PRIORITY = {
    "flow_hidden": 4,
    "flow_spring": 3,
    "flow_churn": 2,
```

### стало

```python
CASE_PRIORITY = {
    # Спячка выше всех: она единственная описывает состояние ДО
    # движения, а вся шкала приоритетов ради этого и заведена.
    # Если на монете видно и спячку, и что-то ещё — «ещё» это уже
    # начавшееся движение, и представлять монету должно не оно.
    "flow_dormant": 5,
    "flow_hidden": 4,
    "flow_spring": 3,
    "flow_churn": 2,
```

### было

```python
CASE_CAP = {
    "flow_hidden": CAP_HIDDEN,
```

### стало

```python
CASE_CAP = {
    "flow_dormant": CAP_DORMANT,
    "flow_hidden": CAP_HIDDEN,
```

### было

```python
_HEADS = {
    "flow_hidden": "Скрытый набор",
```

### стало

```python
_HEADS = {
    "flow_dormant": "Спячка",
    "flow_hidden": "Скрытый набор",
```

---

# 4 · `detectors/flow_config.py` — константы

Дописать в конец файла.

### было

```python
FUEL_ROOM_MIN_PCT = 0.06
```

### стало

```python
FUEL_ROOM_MIN_PCT = 0.06


# ─────────────────────────────────────────────────────────────
# flow_dormant
# ─────────────────────────────────────────────────────────────
# ВНИМАНИЕ: пороги проставлены наугад. Наблюдённого разброса нет —
# подкейс новый, и величины, по которым он режет, наружу раньше не
# отдавались. Все пять уходят в факты сигнала, чтобы первый прогон
# показал распределение; после него и затягиваем.
#
# Числа ниже взяты по пяти монетам, на которых фигура видна глазами:
# AKE, ACU, APR, TUT, BICO. Пять точек — не выборка, а ориентир.

CAP_DORMANT = 92

# Окно базы и минимум истории.
DORMANT_WINDOW = 60
DORMANT_MIN_BARS = 20

# Ликвидность: на тонкой монете и средний размер сделки, и объём —
# случайные величины.
DORMANT_MIN_QUOTE_24H = 2_000_000.0

# Монета жила: был реальный цикл роста до пика. Без этого условия
# подкейс соберёт мёртвые навсегда альты, которых на бирже сотни.
# У наблюдаемых: AKE x39.9, TUT x42.6, APR x10.1, BICO x8.1,
# ACU x3.6 — последний уже на грани, отсюда порог.
DORMANT_GROWTH_MIN = 3.0

# Монета упала. У наблюдаемых 57…84%.
DORMANT_DROP_MIN = 45.0

# Дно держится, а не рисуется прямо сейчас. Свежее дно — это ещё
# падение, а не спячка.
DORMANT_BASE_MIN = 10

# Сейчас тихо. Обе величины коин-относительные: rel_vol — объём
# последнего бара к собственной норме, atr_share — размах к цене.
DORMANT_QUIET_MAX = 0.95
DORMANT_ATR_MAX = 0.12

# Ширина базы как ДОЛЯ падения, а не в процентах.
# Десять процентов хода для монеты, упавшей на 90%, — стояние; для
# упавшей на 30% — уже движение. Абсолютный порог сравнивал бы
# разные вещи.
DORMANT_RANGE_MAX = 0.55

# ── След крупных заявок ──
# Во сколько раз средний размер сделки бара должен превысить медиану
# по базе, чтобы считать бар следом крупного участника.
DORMANT_BIG_TRADE_X = 2.5

DORMANT_SCORE_BASE = 44.0
DORMANT_MULT_BIG_BUY = 1.12
DORMANT_MULT_BIG_MANY = 1.25
DORMANT_MULT_FLOW = 1.18
```

---

# 5 · `render/flow_report.py` — имя подкейса

Единственное место, где живут человеческие имена: их читает и чип
карточки, и легенда орбиты.

### было

```python
    "fuel": "путь свободен",
```

### стало

```python
    "fuel": "путь свободен",
    "dormant": "спячка",
```
