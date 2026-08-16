# Величины цикла и живости — в звёзды

## файл: `render/orbit.py`

Панель зала и крупная карточка читают только `window.ORB.stars`.
Всё, что появилось в ядре за последние правки — кратность от дна
цикла, глубина от пика жизни, удержавшие отскоки, вердикт, — до
звёзд не доходило.

Применять ПОСЛЕ `patch-orbit-brief-data.md`.

### было

```python
        fdrop = ((c.flow or {}).get("drop") or {}) if c is not None else {}
```

### стало

```python
        # Вложенный контекст текущего прогона. drop лежит внутри
        # context — путь длинный, но читается один раз здесь, а не в
        # пяти местах JS.
        fctx = ((c.flow or {}).get("context") or {}) if c is not None else {}
        fdrop = fctx.get("drop") or {}
```

### было

```python
            "chg": round(float(rec.get("change_pct") or 0.0), 1),
            "firstRun": bool(fdrop.get("first_run")),
```

### стало

```python
            "chg": round(float(rec.get("change_pct") or 0.0), 1),
            "firstRun": bool(fdrop.get("first_run")),

            # ── Положение в цикле ──
            # Кратность от дна ЦИКЛА (окно 240 дней), а не от
            # локального минимума: up выше считается по окну в 60
            # дней, и у монеты, которая уже поехала, оно уползает
            # вверх следом за ценой. Две величины расходятся в разы,
            # и правило завершения считает именно по этой. Из
            # прогона, а при его отсутствии — из журнала, куда её
            # пишет update_leaders.
            "upX": round(float(fdrop.get("up_x")
                               or rec.get("up_x") or 0.0), 2),
            # Глубина от пика ЖИЗНИ контракта. Без неё кратность от
            # дна читается одинаково у ранней монеты и у отработавшей:
            # ×2 при −94% от пика и ×2 при −30% — разные монеты.
            "lifeDrop": round(float(fdrop.get("life_drop_pct") or 0.0), 1),
            "trendDone": bool(rec.get("trend_done")),

            # ── Живость ──
            # Отскоки, вернувшиеся на дно и не пробившие его, против
            # всех отработанных. Прямое выражение правила «первый
            # разгон — сквиз»: монета с тремя удержанными отскоками
            # уже показала спрос трижды.
            "rallies": int(fdrop.get("rallies") or 0),
            "heldRallies": int(fdrop.get("held_rallies") or 0),

            # Молчание в днях: сколько прошло с последнего события
            # (срабатывание FLOW либо аномальный объём). Возраст
            # записи больше ничего не значит — запись живёт, пока
            # события есть, поэтому на экран идёт тишина, а не срок.
            "quiet": _quiet_days(rec),

            # Вердикт подкейса. Единственное место, где монета
            # объясняет себя словами; крупная карточка его уже
            # рисует, а поля до сих пор не существовало.
            "verdict": str((c.flow or {}).get("verdict") or "")
                       if c is not None else "",
```

### было

```python
def _star_card(c: Candidate | None) -> dict:
```

### стало

```python
def _quiet_days(rec: dict) -> int:
    """Сколько дней прошло с последнего события по записи журнала.

    Событие — срабатывание FLOW либо обновление аномального объёма;
    его момент пишет update_leaders в last_hit. У записей, заведённых
    до появления поля, берётся first_seen: судить по величине,
    которой не собирали, не о чем, и ноль здесь соврал бы сильнее.
    """
    import datetime as _dt

    raw = rec.get("last_hit") or rec.get("first_seen")
    if not raw:
        return 0
    try:
        when = _dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return 0
    if when.tzinfo is None:
        when = when.replace(tzinfo=_dt.timezone.utc)
    delta = _dt.datetime.now(_dt.timezone.utc) - when
    return max(0, int(delta.total_seconds() // 86400))


def _star_card(c: Candidate | None) -> dict:
```
