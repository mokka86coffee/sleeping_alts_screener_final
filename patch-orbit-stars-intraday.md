# Интрадей-величины в звёзды

## файл: `render/orbit.py`

Применять ПОСЛЕ `patch-orbit-stars-cycle.md` и
`patch-metrics-intraday.md`.

Панель и карточка читают только `window.ORB.stars`. Интрадей-блок
считается в метриках и лежит в `raw["intraday"]`, но до звезды не
доходит.

Берём из метрик, а не из пейлоада FLOW, и это принципиально: метрики
считаются для КАЖДОЙ монеты выборки, включая журнальные, а пейлоад
есть только у сработавших. На этом за сессию трижды сели ярусы,
правило выбытия и мерка зала.

### было

```python
            # Вердикт подкейса. Единственное место, где монета
            # объясняет себя словами; крупная карточка его уже
            # рисует, а поля до сих пор не существовало.
            "verdict": str((c.flow or {}).get("verdict") or "")
                       if c is not None else "",
```

### стало

```python
            # Вердикт подкейса. Единственное место, где монета
            # объясняет себя словами; крупная карточка его уже
            # рисует, а поля до сих пор не существовало.
            "verdict": str((c.flow or {}).get("verdict") or "")
                       if c is not None else "",

            # ── Интрадей: горизонт сутки-двое ──
            # Из метрик, а не из пейлоада: метрики считаются для всей
            # выборки, пейлоад — только для сработавших.
            **_star_intraday(raw),
```

### было

```python
def _quiet_days(rec: dict) -> int:
```

### стало

```python
def _star_intraday(raw: dict) -> dict:
    """Интрадей-величины для панели и карточки.

    Плоские ключи, а не вложенный словарь: JS читает звезду в дюжине
    мест, и `s.press` там читается, а `s.intraday.pressure.delta`
    ломается на первом же отсутствующем звене.

    Отсутствующая величина не подменяется нулём. Ноль откупов и
    «не мерили» — разные ответы, и подпись на карточке обязана их
    различать; поэтому ключа просто нет.

    h48 — часовые закрытия за двое суток, те самые, по которым
    считались метки крупных заявок. Позиции в marks отсчитаны от
    начала этого же хвоста, поэтому ряд и метки обязаны ехать вместе.
    """
    intra = (raw or {}).get("intraday") or {}
    if not intra:
        return {}

    out: dict = {}

    closes = [c for c in (raw.get("closes_1h") or []) if c]
    if len(closes) >= 8:
        out["h48"] = [round(float(c), 10) for c in closes[-48:]]

    big = intra.get("big") or {}
    if big:
        out["bigCount"] = int(big.get("count") or 0)
        out["bigBuys"] = int(big.get("buys") or 0)
        out["bigSells"] = int(big.get("sells") or 0)
        out["bigMax"] = float(big.get("max_x") or 0.0)
        marks = big.get("marks") or []
        if marks:
            out["bigMarks"] = [
                {"i": int(m["i"]), "s": str(m["side"]), "x": float(m["x"])}
                for m in marks[:24]
            ]

    pres = intra.get("pressure") or {}
    if pres:
        out["press"] = float(pres.get("delta") or 0.0)
        out["pressShare"] = float(pres.get("share") or 0.0)

    vx = intra.get("vortex") or {}
    if vx:
        out["vxDir"] = str(vx.get("dir") or "")
        out["vxAgo"] = int(vx.get("bars_ago", -1))

    if intra.get("range_pos") is not None:
        out["rangePos"] = float(intra["range_pos"])
    if intra.get("bg") is not None:
        out["volBg"] = float(intra["bg"])

    prom = intra.get("prom") or {}
    if prom.get("q"):
        out["q"] = float(prom["q"])
        out["qScale"] = str(intra.get("scale") or "")

    spd = intra.get("speed") or {}
    if spd.get("v"):
        out["speedV"] = float(spd["v"])
        out["speedAtr"] = float(spd.get("atr_move") or 0.0)

    return out


def _quiet_days(rec: dict) -> int:
```

### было

```python
            "quiet": _quiet_days(rec),
```

### стало

```python
            "quiet": _quiet_days(rec),

            # Плотность попаданий по дням: семь чисел, свежий день
            # последний. Отвечает «жива ли монета в эти сутки», в
            # отличие от hitCount, который отвечает «возвращается ли
            # она изо дня в день». Величины разные, и смешивать их
            # нельзя — иначе обе перестанут значить что-либо.
            "byDay": _hits_by_day(rec),
```

### было

```python
def _star_card(c: Candidate | None) -> dict:
```

### стало

```python
def _hits_by_day(rec: dict, days: int = 7) -> list[int]:
    """Попадания по дням, свежий день последний.

    Читается из карты, которую ведёт журнал. Дни без попаданий —
    честные нули, а не пропуски: провал в середине ряда сам по себе
    информация.

    Пустой список означает, что карты ещё нет: у записей, заведённых
    до появления поля, восстановить её неоткуда.
    """
    import datetime as _dt

    src = rec.get("hits_by_day")
    if not isinstance(src, dict) or not src:
        return []

    today = _dt.datetime.now(_dt.timezone.utc).date()
    out: list[int] = []
    for back in range(days - 1, -1, -1):
        key = (today - _dt.timedelta(days=back)).isoformat()
        try:
            out.append(int(src.get(key) or 0))
        except (TypeError, ValueError):
            out.append(0)
    return out


def _star_card(c: Candidate | None) -> dict:
```
