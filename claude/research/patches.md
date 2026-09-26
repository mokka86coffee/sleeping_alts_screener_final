# Патчи (26.09). A и B ВНЕСЕНЫ 12:10 по «да», C ВНЕСЕН 12:50 по «делай» — все ждут перезапуска прогона. Каждый — одна правка одного файла + строка в core_config.

## A. «Картина»: лонг только при медиане доски за 6 ч выше нуля (R27, leader_break_sight.py)
Откуда число: ноль — знак, не порог; в часы 6–24 после слома лидера лонги при доске6 ≤ 0 дают 43% / −0.83% (222 сделки), при доске6 > 0 — 62% / +0.55%;
в обычные дни с доской24 > +1% сделок при доске6 ≤ 0 всего 73 из 808 (71% в плюс). Суточная медиана после слома отстаёт и пропускает лонги.

core_config.py, рядом с SIGHT_BOARD_GATE:
```python
# ДОСКА ЗА 6 Ч (26.09, R27/leader_break_sight.py): после слома лидера суточная медиана ещё > +1%, а доска уже села — лонги «картины»
# в часы 6–24 после слома при медиане за 6 ч ≤ 0 дают 43% / −0.83% (222 сделки) против 62% / +0.55%. Ноль — знак, не выведенная мерка.
# Лонг только при медиане доски за 6 ч > SIGHT_BOARD6_GATE (вдобавок к суточной). None — выключено.
SIGHT_BOARD6_GATE = 0.0
```
paper_sight.py, импорт рядом с SIGHT_BOARD_GATE (строки 72–75):
```python
try:
    from core_config import SIGHT_BOARD_GATE, SIGHT_BOARD6_GATE
except ImportError:
    SIGHT_BOARD_GATE, SIGHT_BOARD6_GATE = None, None
```
paper_sight.py, в `_main` после `bg = background()` (строка 459):
```python
    # медиана доски за 6 ч — по архиву получасовок тех же монет (12 баров назад); суточная — из market_bg
    _ch6 = []
    for _s in syms:
        _r = rows_of(_s)
        if len(_r) >= 13 and _r[-1].get("px") and _r[-13].get("px"):
            _ch6.append((float(_r[-1]["px"]) / float(_r[-13]["px"]) - 1) * 100)
    bg["median6"] = (sorted(_ch6)[len(_ch6) // 2] if _ch6 else None)
```
paper_sight.py, блок «СТОРОНА ПО ФОНУ ДОСКИ» (строки 506–512) — добавить вторые ворота сразу после первых:
```python
        if s > 0 and SIGHT_BOARD6_GATE is not None and bg.get("median6") is not None and t > int(state["last_sig"].get(sym) or 0):
            if float(bg["median6"]) <= SIGHT_BOARD6_GATE:
                state["last_sig"][sym] = t
                _why = f"доска {float(bg['median6']):+.2f}% за 6 ч — лонг только выше {SIGHT_BOARD6_GATE:+.1f}% (R27)"
                events.append({"kind": "skip", "book": BOOK_LABEL, "sym": sym, "side": s, "t": t, "px": float(rows[-1]["px"]),
                               "at": now, "why_skip": _why, "score": sum(v.values()), "votes": v})
                s = 0
```
Проверка перед установкой: `.venv/bin/python paper_sight.py --only ARK` (без --write). Вступает в силу после перезапуска прогона владельцем.

## B. Журнал очереди: честная медиана доски за 24 ч (сейчас поле `board_med_24h` — ход с 00:00 UTC)
near_move.py, `_today_bars` (строка ~246): хранить все 80 строк, а не только сегодняшние, и посчитать ход за 24 ч:
```python
    rows, all_rows = [], []
    for line in p.read_text(encoding="utf-8").splitlines()[-80:]:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        all_rows.append(r)
        if str(r.get("candle", ""))[:10] == today:
            rows.append(r)
    # ход за 24 ч — 48 получасовок назад (или самая ранняя из последних 49), для медианы доски в журнале
    _pxs = [r.get("px") for r in all_rows[-49:] if r.get("px")]
    px_chg_24h = (_pxs[-1] / _pxs[0] - 1) if len(_pxs) >= 25 else None
```
near_move.py, возвращаемый словарь (строка ~644), рядом с `"px_chg_pct"`:
```python
            "px_chg_24h_pct": round(px_chg_24h * 100, 1) if px_chg_24h is not None else None,
```
near_move.py, блок `_BG` (строки 1455–1462): суточная медиана — из нового поля, прежняя — под честным именем:
```python
    _chg_day = [float((vv.get("today") or {}).get("px_chg_pct")) for vv in (res.get("coins") or {}).values() if (vv.get("today") or {}).get("px_chg_pct") is not None]
    _chg = [float((vv.get("today") or {}).get("px_chg_24h_pct")) for vv in (res.get("coins") or {}).values() if (vv.get("today") or {}).get("px_chg_24h_pct") is not None]
    _chg.sort(); _chg_day.sort()
    _board_med = round(_chg[len(_chg) // 2], 2) if _chg else None
    _board_up = round(100 * sum(1 for x in _chg if x > 0) / len(_chg)) if _chg else None
    _board_day = round(_chg_day[len(_chg_day) // 2], 2) if _chg_day else None
    rows.append({..., "board_med_24h": _board_med, "board_up_pct": _board_up, "board_med_day": _board_day, "board_n": len(_chg), ...})
```
и в строке монеты (1487) `"board_med_24h": _board_med` остаётся, добавить `"board_med_day": _board_day`.
После установки: пересчитать state_probs.py / exclusion по честной доске (записи до патча — с 00:00 UTC, пометить).

## C. Полоса «скоро» по R34 — ВНЕСЕНО 26.09 12:50
core_config: `STAR_OI_JUMP_3H = 15.0` (с комментарием-источником). near_move `_today_bars`: `oi_jump_3h_pct` = интерес последнего бара к 6 барам назад (all_rows).
render_intro `collect_items`: после блока «В ТОПЕ ПОДРЯД» — для всех монет из near_move.json с `today.oi_jump_3h_pct ≥ STAR_OI_JUMP_3H` метка
«интерес +N% за 3 ч» + вероятности («спит: +10% за 48 ч у 52%, +40% у 15%» / «в ходу: 73% / 44%») и группа 0 (скоро); подпись группы «скоро» дополнена.
Не вход, а повод смотреть: у спящих 61% сигналов не дают и +10%.

