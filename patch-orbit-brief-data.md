# Данные для сводки: поля журнала в звёздах, спячка и итог журнала

## файл: `render/orbit.py`


Четыре строки брифа (`В работе`, `У уровня`, ряды отбора, хвост
журнала) читают поля, которые сюда никогда не писались. Патч
прокидывает их из журнала и текущего прогона, ничего не пересчитывая.

### было

```python
        # up_from_low / days_from_low — те же поля, что читает
        # _numbers() во flow_report. Для монет, которых нет в текущем
        # прогоне, роста не будет: raw есть только у кандидатов.
        raw = (getattr(c, "raw", None) or {}) if c is not None else {}
```

### стало

```python
        # up_from_low / days_from_low — те же поля, что читает
        # _numbers() во flow_report. Для монет, которых нет в текущем
        # прогоне, роста не будет: raw есть только у кандидатов.
        raw = (getattr(c, "raw", None) or {}) if c is not None else {}
        # Вложенный drop текущего прогона: отсюда берётся first_run —
        # «первый разгон после ЭТОГО падения». Признак живёт в окне
        # DropContext (240 дней) и в журнале не хранится, поэтому
        # источник — только текущий прогон; для монеты вне прогона
        # его честно нет.
        fdrop = ((c.flow or {}).get("drop") or {}) if c is not None else {}
```

### было

```python
            "up": round(float(raw.get("up_from_low") or 0)),
            "updays": int(raw.get("days_from_low") or 0),
```

### стало

```python
            "up": round(float(raw.get("up_from_low") or 0)),
            "updays": int(raw.get("days_from_low") or 0),
            # ── Поля журнала: их читает сводка при входе ──
            # px/stop оживляют строку «у уровня», streak — «в работе»,
            # hits/runsSeen — справку персистентности в рядах отбора,
            # chg — ход от входа в журнал. До этого сводка читала
            # px, stop, streak, firstRun — и ни одно поле сюда не
            # писалось: четыре её строки были мертвы с заведения.
            "px": float(rec.get("price") or 0.0),
            "stop": float(rec.get("stop_hint") or 0.0),
            "streak": int(rec.get("streak") or 0),
            "hits": int(rec.get("hits") or 0),
            "runsSeen": int(rec.get("runs_seen") or 0),
            "chg": round(float(rec.get("change_pct") or 0.0), 1),
            "firstRun": bool(fdrop.get("first_run")),
```

### было

```python
def _orbit_market(candidates: list[Candidate], snapshot: RunSnapshot,
                  slices: list[dict]) -> dict:
```

### стало

```python
def _orbit_dormant(candidates: list[Candidate],
                   leader: Candidate | None) -> list[dict]:
    """Монеты в спячке — для строки «Спят» в сводке.

    Единственное состояние ДО движения, и источник у него — кандидаты
    текущего прогона, а не журнал: в журнал попадают лидеры, а спячка
    по определению случается раньше лидерства. Лидер прогона
    исключается — если он сам dormant, его блок выше уже сообщил
    и имя, и фигуру, вторая строка сказала бы то же самое дважды.
    """
    from render.dashboard import _tick

    lead_sym = leader.symbol if leader is not None else ""
    out = []
    for c in candidates:
        f = c.flow or {}
        if (f.get("case") or "") != "flow_dormant" or c.symbol == lead_sym:
            continue
        out.append({
            "t": _tick(c),
            "cap": _cap(_data(c)["cap"]),
            "score": int(getattr(c, "score", 0) or 0),
        })
    out.sort(key=lambda d: -d["score"])
    return out[:3]


def _orbit_journal() -> dict:
    """Итог журнала лидеров — для хвоста сводки.

    Считается при чтении, потому что это агрегат по всему файлу, а не
    поле записи: лучший и худший ход имеют смысл только на фоне
    остальных. «Новые» — записи, заведённые текущим прогоном:
    since_run записи совпадает со счётчиком прогонов в _meta.
    Это честная замена мёртвой строке «новые в топ-3» — поле newTop3
    никто никогда не писал, а since_run пишется каждым прогоном.
    """
    from render.dashboard import _read_json, LEADERS_PATH

    j = _read_json(LEADERS_PATH)
    meta = j.get("_meta") or {}
    run_no = int(meta.get("runs") or 0)

    recs = {k: v for k, v in j.items()
            if not k.startswith("_") and isinstance(v, dict)}
    if not recs:
        return {}

    def _lbl(sym: str) -> str:
        return sym[:-4] if sym.endswith("USDT") else sym

    fresh = [_lbl(s) for s, r in recs.items()
             if run_no > 0 and int(r.get("since_run") or 0) == run_no]

    by_chg = sorted(recs.items(),
                    key=lambda kv: float(kv[1].get("change_pct") or 0.0))
    worst_sym, worst = by_chg[0]
    best_sym, best = by_chg[-1]

    return {
        "n": len(recs),
        "fresh": fresh[:3],
        "best": {"t": _lbl(best_sym),
                 "chg": round(float(best.get("change_pct") or 0.0), 1)},
        "worst": {"t": _lbl(worst_sym),
                  "chg": round(float(worst.get("change_pct") or 0.0), 1)},
    }


def _orbit_market(candidates: list[Candidate], snapshot: RunSnapshot,
                  slices: list[dict]) -> dict:
```

### было

```python
        "topVol": top3("surge"),
        "hourly": {"n": len(hourly_items), "list": top3("hourly")},
        "flowVol": _orbit_flow_bigvol(candidates),
    }
```

### стало

```python
        "topVol": top3("surge"),
        "hourly": {"n": len(hourly_items), "list": top3("hourly")},
        "flowVol": _orbit_flow_bigvol(candidates),
        # Спячка и итог журнала — читает только сводка при входе.
        # Спячка идёт из кандидатов (до лидерства журнала не бывает),
        # итог журнала — агрегат по файлу, не поле записи.
        "dormant": _orbit_dormant(candidates, leader),
        "journal": _orbit_journal(),
    }
```
