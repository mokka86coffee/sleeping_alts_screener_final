# Правила входа и выхода в условном портфеле

## файл: `analytics/leaders.py`

Применять ПОСЛЕ `patch-leaders-portfolio.md`.

Портфель считал механический вход во всё подряд. Теперь у него есть
правила, и считается он в двух вариантах сразу: как было и как стало.
Разница между ними и есть цена правил — иначе неизвестно, помогают
они или мешают.

## Что решено

**Позиция берётся от первого появления в прогоне** — как и было.
Существующие записи остаются входами: правила применяются с этого
момента вперёд, задним числом не переигрываются. Восстановить, каким
был `first_run` девять дней назад, нечем, а подставлять догадку в
метрику, которой потом верить, нельзя.

**Пропускаем первый разгон.** Самое подтверждённое правило проекта:
первый памп после затяжного падения — сквиз. `first_run` приходит из
пейлоада семейства и записывается в момент заведения.

**Пропускаем выходные,** кроме одного случая: плоское длительное дно
при росте от дна не выше 50%. Плоское длительное дно — это dormant:
его гейты ровно это и проверяют, отдельного условия городить незачем.
Замер по журналу 16 августа: входы в будни дают +7.1%, входы на
выходных −6.9%, и трое из четырёх худших (MMT, 1000CAT, SAGA) зашли в
субботу-воскресенье с максимумом ровно 0.0% — то есть после входа не
поднялись над ним ни разу.

**Выходим по крупной продаже на дневном баре,** если монета выше
входа. Красный пузырь на пампе — сигнал, что разгон встретил
предложение. Цена выхода — цена того прогона, где метку увидели.

**Отдельно собираются глубокие просадки** — минус тридцать процентов и
хуже, с датой входа и фигурой. Их разбирают руками и по ним правят
стратегию.

### было

```python
def _new_record(
    now: datetime,
    price: float,
    ratios: dict[str, float],
    run_no: int = 0,
) -> dict:
    return {
```

### стало

```python
# ── Правила входа ────────────────────────────────────────────
# Рост от дна, выше которого вход на выходных не делается даже на
# плоском дне. Пятьдесят процентов — граница из описания стратегии:
# отскок от базы, а не уже состоявшийся разгон.
SKIP_WEEKEND_UP_MAX = 50.0

# Просадка, начиная с которой монета попадает в отдельный список на
# ручной разбор.
DEEP_LOSS_PCT = -30.0


def _entry_rules(now: datetime, raw: dict, flow: dict) -> dict:
    """Взяли бы позицию по правилам или пропустили, и почему.

    Записывается в момент заведения, а не считается потом: `first_run`
    и рост от дна к следующему прогону уже другие, и восстановить их
    задним числом нечем.

    Пропуск не мешает вести запись. Монета остаётся в журнале и
    наблюдается как обычно — правило влияет только на условный
    портфель, то есть на оценку, а не на само наблюдение.
    """
    drop = (flow.get("context") or {}).get("drop") or {}
    case = str(flow.get("case") or "")

    if drop.get("first_run"):
        return {"skip": "первый разгон"}

    # Пятница считается будним днём: суббота и воскресенье — 5 и 6.
    if now.weekday() >= 5:
        try:
            up = float(raw.get("up_from_low") or 0.0)
        except (TypeError, ValueError):
            up = 0.0
        flat_base = case.endswith("dormant")
        if not (flat_base and up <= SKIP_WEEKEND_UP_MAX):
            return {"skip": "выходные"}

    return {}


def _new_record(
    now: datetime,
    price: float,
    ratios: dict[str, float],
    run_no: int = 0,
    rules: dict | None = None,
) -> dict:
    base = dict(rules or {})
    return {
        **base,
```

### было

```python
                flow_store[leader.symbol] = moved or _new_record(
                    now, price, {}, run_no,
                )
```

### стало

```python
                flow_store[leader.symbol] = moved or _new_record(
                    now, price, {}, run_no,
                    _entry_rules(now, leader.raw or {}, leader.flow or {}),
                )
```

### было

```python
def _touch_portfolio(rec: dict, price: float, now: datetime,
                     run_no: int) -> None:
```

### стало

```python
def _touch_exit(rec: dict, raw: dict, price: float, now: datetime) -> None:
    """Выход по крупной продаже на дневном баре.

    Красный пузырь на пампе означает, что разгон встретил предложение.
    Проверяются два последних дневных бара: метка появляется на баре, а
    прогон идёт каждый час, и требовать попадания ровно в текущий бар
    значило бы ловить событие в одном прогоне из двадцати четырёх.

    Условие «монета выше входа» обязательно: продажа на падающей
    монете ничего не завершает, там и завершать нечего.

    Выход один и окончательный. Позиция закрыта — дальнейшие движения
    цены её не касаются, иначе метрика перестала бы отвечать на
    вопрос «сколько бы взяли по правилам».
    """
    if rec.get("exit_price") or rec.get("skip"):
        return
    if price <= 0:
        return
    try:
        if float(rec.get("change_pct") or 0.0) <= 0:
            return
    except (TypeError, ValueError):
        return

    big = (raw or {}).get("daily_big") or {}
    marks = big.get("marks") or []
    if not marks:
        return

    tail = int(big.get("tail") or 48)
    for m in marks:
        try:
            fresh = int(m.get("i", -1)) >= tail - 2
        except (TypeError, ValueError):
            continue
        if fresh and m.get("side") == "sell":
            rec["exit_price"] = price
            rec["exit_at"] = now.isoformat()
            rec["exit_why"] = "крупная продажа на пампе"
            return


def _touch_portfolio(rec: dict, price: float, now: datetime,
                     run_no: int) -> None:
```

### было

```python
                _touch_price(rec, price, now)
                # Строго после _touch_price: добор читает свежие
                # change_pct и min_change_pct, которые тот и пишет.
                _touch_portfolio(rec, price, now, run_no)
```

### стало

```python
                _touch_price(rec, price, now)
                # Строго после _touch_price: добор и выход читают
                # свежие change_pct и min_change_pct, которые тот и
                # пишет.
                _touch_portfolio(rec, price, now, run_no)
                _touch_exit(rec, c.raw or {}, price, now)
```

### было

```python
    invested = value = peak = 0.0
    adds = 0

    for symbol, rec in store.items():
        if symbol.startswith("_") or not isinstance(rec, dict):
            continue
        try:
            entry = float(rec.get("entry_price") or 0.0)
            price = float(rec.get("price") or 0.0)
            chg = float(rec.get("change_pct") or 0.0)
            mx = float(rec.get("max_change_pct") or 0.0)
        except (TypeError, ValueError):
            continue
        if entry <= 0 or price <= 0:
            continue

        invested += PORT_STAKE
        value += PORT_STAKE * (1.0 + chg / 100.0)
        peak += PORT_STAKE * (1.0 + mx / 100.0)
```

### стало

```python
    invested = value = peak = 0.0
    r_invested = r_value = 0.0
    adds = skipped = exits = 0
    losers: list[dict] = []

    for symbol, rec in store.items():
        if symbol.startswith("_") or not isinstance(rec, dict):
            continue
        try:
            entry = float(rec.get("entry_price") or 0.0)
            price = float(rec.get("price") or 0.0)
            chg = float(rec.get("change_pct") or 0.0)
            mx = float(rec.get("max_change_pct") or 0.0)
        except (TypeError, ValueError):
            continue
        if entry <= 0 or price <= 0:
            continue

        if chg <= DEEP_LOSS_PCT:
            losers.append({
                "t": symbol[:-4] if symbol.endswith("USDT") else symbol,
                "chg": round(chg, 1),
                "case": str(rec.get("entry_case") or "").replace("flow_", ""),
                "at": str(rec.get("first_seen") or "")[:10],
                "entry": entry,
            })

        # ── Портфель по правилам ──
        # Пропущенные не участвуют вовсе, вышедшие зафиксированы по
        # цене выхода. Считается рядом с механическим, а не вместо:
        # без пары чисел неизвестно, помогают правила или мешают.
        if rec.get("skip"):
            skipped += 1
        else:
            r_invested += PORT_STAKE
            try:
                exit_at = float(rec.get("exit_price") or 0.0)
            except (TypeError, ValueError):
                exit_at = 0.0
            if exit_at > 0:
                exits += 1
                r_value += PORT_STAKE * (exit_at / entry)
            else:
                r_value += PORT_STAKE * (1.0 + chg / 100.0)

        invested += PORT_STAKE
        value += PORT_STAKE * (1.0 + chg / 100.0)
        peak += PORT_STAKE * (1.0 + mx / 100.0)
```

### было

```python
    if invested <= 0:
        return {}

    return {
        "invested": round(invested, 0),
        "value": round(value, 0),
        "pnl_pct": round((value / invested - 1.0) * 100.0, 1),
        "peak_pct": round((peak / invested - 1.0) * 100.0, 1),
        "adds": adds,
    }
```

### стало

```python
    if invested <= 0:
        return {}

    losers.sort(key=lambda d: d["chg"])

    out = {
        "invested": round(invested, 0),
        "value": round(value, 0),
        "pnl_pct": round((value / invested - 1.0) * 100.0, 1),
        "peak_pct": round((peak / invested - 1.0) * 100.0, 1),
        "adds": adds,
        "skipped": skipped,
        "exits": exits,
        "losers": losers[:6],
        "losers_all": len(losers),
    }
    if r_invested > 0:
        out["rules_pnl_pct"] = round((r_value / r_invested - 1.0) * 100.0, 1)
        out["rules_value"] = round(r_value, 0)
    return out
```
