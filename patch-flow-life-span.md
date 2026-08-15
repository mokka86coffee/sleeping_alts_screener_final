# Пик жизни по недельным свечам — в контекст и наружу в пейлоад

## файл: `detectors/flow.py`


Вторая половина HEMI-правки: недельки покрывают всю жизнь контракта
и уже лежат в RunCache (их грузили метрики для ATH) — сети ноль.
Величины уходят в пейлоад drop раньше любого гейта: порог для
dormant выбирается по разбросу из пробы, а не придумывается.

### было

```python
    K_TRADES,
    klines_1d,
)
```

### стало

```python
    K_TRADES,
    klines_1d,
    klines_1w,
)
```

### было

```python
# ─────────────────────────────────────────────────────────────
# Горизонт
# ─────────────────────────────────────────────────────────────
def _horizon(ctx: FlowContext) -> dict:
```

### стало

```python
def _life_span(symbol: str) -> tuple[float, float]:
    """Пик всей жизни контракта и минимум до него — по неделькам.

    Зачем: окно DropContext ограничено BOTTOM_LOOKBACK_DAYS, и монета
    с листинговым пиком старше окна выглядит «без цикла» — growth_x ≈ 1
    при том, что цикл был (HEMI). Недельные свечи покрывают всю жизнь
    контракта (LIMIT_1W = 200 недель ≈ 1400 дней), и метрики уже
    загрузили их для ATH: ряд лежит в RunCache, сети здесь ноль.

    Тонкость с пиком на ПЕРВОЙ неделе (листинговый памп): недельный
    low этой недели хронологически чаще стоит ПОСЛЕ пика — взять его
    значило бы мерить падение под видом роста. Точкой «до» для
    пиковой недели служит её открытие; недели до пиковой участвуют
    своими low как обычно.

    (0, 0) — «жизни не видели»: недельки пусты или ряд слишком
    короток. Ноль отличим от измеренной единицы, слой в DropContext
    останется честно пустым.
    """
    kl = klines_1w(symbol)
    if not kl or len(kl) < 2:
        return 0.0, 0.0

    highs: list[float] = []
    lows: list[float] = []
    opens: list[float] = []
    for k in kl:
        try:
            highs.append(float(k[K_HIGH]))
            lows.append(float(k[K_LOW]))
            opens.append(float(k[K_OPEN]))
        except (TypeError, ValueError, IndexError):
            highs.append(0.0)
            lows.append(0.0)
            opens.append(0.0)

    if not highs or max(highs) <= 0:
        return 0.0, 0.0

    peak_idx = max(range(len(highs)), key=lambda i: highs[i])
    cand = [v for v in lows[:peak_idx] if v > 0]
    if opens[peak_idx] > 0:
        cand.append(opens[peak_idx])
    low_before = min(cand, default=0.0)
    return highs[peak_idx], low_before


# ─────────────────────────────────────────────────────────────
# Горизонт
# ─────────────────────────────────────────────────────────────
def _horizon(ctx: FlowContext) -> dict:
```

### было

```python
    ctx = build_context(symbol, bars)
    if ctx is None or not ctx.ready:
```

### стало

```python
    # Слой «жизнь контракта»: почему не расширить окно и откуда
    # недельки — в docstring _life_span. Сетевых запросов ноль.
    life_peak, life_low = _life_span(symbol)
    ctx = build_context(symbol, bars, life_peak=life_peak, life_low=life_low)
    if ctx is None or not ctx.ready:
```

### было

```python
            "growth_x": round(ctx.drop.growth_x, 2),
            "peak_age_days": ctx.drop.peak_age_days,
```

### стало

```python
            "growth_x": round(ctx.drop.growth_x, 2),
            "peak_age_days": ctx.drop.peak_age_days,
            # Слой жизни: кратность до пика ЖИЗНИ и падение от него к
            # текущему дну, в процентах — как drop_pct выше. Наружу —
            # раньше гейта: порог для dormant выбирается по разбросу
            # из пробы, а не придумывается (тот же принцип, что у
            # growth_x строкой выше). Гейт «цикл был» станет
            # «оконный ИЛИ жизненный» отдельным патчем flow_dormant.
            "life_growth_x": round(ctx.drop.life_growth_x, 2),
            "life_drop_pct": round(ctx.drop.life_drop_pct * 100, 1),
```
