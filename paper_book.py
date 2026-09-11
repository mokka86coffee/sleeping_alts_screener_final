"""
paper_book.py — БУМАЖНАЯ КНИГА ПО ПЕРВЫМ ОЧЕРЕДИ (11.09, владелец).

Зачем: очередь сегодня даёт четыре хода из пятидесяти первых. Вместо споров — журнал: берём
каждую монету, которая была в первых трёх не меньше трёх прогонов за сутки, и «продаём, как
только она по какому-то сигналу завершается». Сигнал — не один: на одной и той же позиции
считаются ЧЕТЫРЕ выхода независимо (событие конца, хедж вихря, сила вниз, выпадение из первых),
у каждого своя цена и результат. Через неделю видно, какой из них чего стоит — на лестницах и
параболах отдельно.

Правила владельца, дословно:
- вход — третье попадание в первые три за 24 часа, размер один;
- стоп в точку входа, как только цена от входа +10%;
- добор ×2 один раз: выходов не было, монета всё ещё в первых, цена ниже +50% от входа;
  после добора ждём +10% от цены добора и переставляем стоп в неё; иначе стоп прежний;
- позиция закрывается целиком: стоп, все четыре выхода сработали, трое суток.

Читает только output/queue_log.jsonl — ничего не считает заново. Пишет output/paper_book.json
(открытые и закрытые) и возвращает текст блока для сообщения прогона.

Запуск: из run.py после очереди — `paper_book.update()`; вручную — `python3 paper_book.py`
(пересобрать с нуля по всему журналу: `--rebuild`, сводка: `--report`).
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from core_config import (BASE_DIR, PAPER_ADD_AFTER_BE, PAPER_ADD_MAX_PCT, PAPER_BE_PCT, PAPER_DROP_RUNS,
                             PAPER_FORCE_FRESH_BARS, PAPER_HITS, PAPER_MAX_DAYS, PAPER_WINDOW_H)
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
    PAPER_HITS, PAPER_WINDOW_H, PAPER_MAX_DAYS, PAPER_BE_PCT, PAPER_ADD_MAX_PCT, PAPER_FORCE_FRESH_BARS = 3, 24.0, 3, 10.0, 50.0, 1
    PAPER_DROP_RUNS, PAPER_ADD_AFTER_BE = 3, True

OUT_DIR = BASE_DIR / "output"
LOG = OUT_DIR / "queue_log.jsonl"
BOOK = OUT_DIR / "paper_book.json"
EXITS = ("конец", "хедж", "сила", "выпадение")


def _t(s: str) -> datetime:
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def _read_log() -> list[dict]:
    rows = []
    if not LOG.exists():
        return rows
    for line in LOG.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("at") and r.get("sym") and r.get("px"):
            rows.append(r)
    rows.sort(key=lambda r: (r["at"], r.get("place") or 99))
    return rows


_ARCH: dict = {}


def _arch(sym: str) -> list[dict]:
    """Получасовки архива монеты: [{t, px, oi, d, end, force_dn}] — end и сила теми же формулами,
    что в near_move / render_coin. Кэш на прогон."""
    if sym in _ARCH:
        return _ARCH[sym]
    p = BASE_DIR / "cq_v2" / "intraday" / f"{sym.replace('USDT', '').lower()}.jsonl"
    rows = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("px") and (r.get("fut") or {}).get("tk") is not None and r.get("candle"):
                rows.append({"t": _t(r["candle"]), "px": float(r["px"]), "oi": r.get("oi"), "d": (r.get("fut") or {}).get("d") or 0.0})
    rows.sort(key=lambda x: x["t"])
    def ema(xs, n):
        k = 2 / (n + 1); out = []; e = None
        for x in xs:
            e = x if e is None else x * k + e * (1 - k); out.append(e)
        return out
    d = [r["d"] for r in rows]
    kv = [a - b for a, b in zip(ema(d, 12), ema(d, 26))] if rows else []
    sg = ema(kv, 9) if rows else []
    prev = None
    for i, r in enumerate(rows):
        ch = (r["oi"] / prev - 1) * 100 if (prev and r["oi"]) else None
        r["end"] = bool(ch is not None and ch <= -2.0 and r["d"] < 0)
        r["force_dn"] = bool(i > 0 and kv[i] < sg[i] and kv[i - 1] >= sg[i - 1])
        if r["oi"]:
            prev = r["oi"]
    _ARCH[sym] = rows
    return rows


def _bar_at(sym: str, when: datetime) -> dict | None:
    """Последний закрытый бар архива не позже when (свеча закрывается через 30 мин после открытия)."""
    rows = _arch(sym)
    best = None
    for r in rows:
        if r["t"] + timedelta(minutes=30) <= when:
            best = r
        else:
            break
    return best


def _load_book() -> dict:
    if BOOK.exists():
        try:
            return json.loads(BOOK.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"open": {}, "closed": [], "watch": [], "last_at": None}


def _save_book(book: dict) -> None:
    try:
        from sources_storage import write_atomic
        write_atomic(BOOK, json.dumps(book, ensure_ascii=False, indent=1))
    except ImportError:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        BOOK.write_text(json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")


def _pct(a: float, b: float) -> float:
    return round((b / a - 1) * 100, 2)


def _avg_entry(pos: dict) -> float:
    """средняя входа по размеру: вход размером 1, добор размером 1 (позиция ×2)"""
    if pos.get("add_px"):
        return (pos["entry_px"] + pos["add_px"]) / 2
    return pos["entry_px"]


VARIANT: dict = {"hours": None, "no_reentry_after_end": False, "bg_filter": False}
_BG: list | None = None


def _bg_median_at(when: datetime):
    """Медиана доски из ленты фона на момент when (ближайшая строка не позже, не дальше 3 ч)."""
    global _BG
    if _BG is None:
        _BG = []
        p = OUT_DIR / "market_bg.jsonl"
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                try:
                    _BG.append((_t(r["at"]), (r.get("risk_on") or {}).get("median_pct"), r.get("breadth") or {}))
                except (KeyError, TypeError, ValueError):
                    continue
        _BG.sort(key=lambda x: x[0])
    best = None
    for t, med, br in _BG:
        if t <= when:
            best = (t, med, br)
        else:
            break
    if not best or when - best[0] > timedelta(hours=3):
        return None
    return best[1]


def _apply_run(book: dict, at: str, run_rows: dict, hist: list[dict]) -> list[str]:
    """Один прогон: at — время, run_rows — sym → строка журнала этого прогона, hist — все строки
    журнала до него включительно (для счёта попаданий за окно). Возвращает строки событий."""
    events: list[str] = []
    now = _t(at)
    since = now - timedelta(hours=PAPER_WINDOW_H)
    # попадания в первые три за окно
    hits: dict[str, int] = {}
    for r in hist:
        if _t(r["at"]) < since:
            continue
        if (r.get("place") or 99) <= 3:
            hits[r["sym"]] = hits.get(r["sym"], 0) + 1
    # ── открытые: выходы, стоп, добор, закрытие
    for sym, pos in list(book["open"].items()):
        row = run_rows.get(sym)
        bar = _bar_at(sym, now)
        # ЦЕНА И СИГНАЛЫ — ИЗ АРХИВА (11.09): строка очереди есть только пока монета в очереди;
        # после выпадения у неё не было бы ни цены, ни «конца», ни силы — а именно там позиции и живут
        px = bar["px"] if bar else (row["px"] if row else pos["last_px"])
        place = (row.get("place") or 99) if row else 99
        pos["last_px"], pos["last_at"] = px, at
        pos["max_px"] = max(pos["max_px"], px)
        pos["min_px"] = min(pos["min_px"], px)
        fired_any_before = any(pos["exits"][k] for k in EXITS)
        pos["out_runs"] = (pos.get("out_runs", 0) + 1) if place > 3 else 0
        new_bar = bool(bar and bar["t"].isoformat() != pos.get("last_bar"))
        pos["last_bar"] = bar["t"].isoformat() if bar else pos.get("last_bar")
        # четыре выхода — независимо, каждый один раз
        sig = {
            "конец": bool(new_bar and bar["end"]) or bool(row and "конец" in str(row.get("today") or "")),
            "хедж": bool(row and row.get("vortex_hedge")),
            "сила": bool(new_bar and bar["force_dn"]) or bool(row and row.get("force_turn_ago") is not None and row["force_turn_ago"] <= PAPER_FORCE_FRESH_BARS),
            "выпадение": pos["out_runs"] >= PAPER_DROP_RUNS,
        }
        for k in EXITS:
            if sig[k] and not pos["exits"][k]:
                pos["exits"][k] = {"at": at, "px": px, "res_pct": _pct(_avg_entry(pos), px)}
                events.append(f"{sym.replace('USDT', '')}: выход «{k}» {px:g} · {pos['exits'][k]['res_pct']:+.1f}%")
        # стоп в точку входа после +BE от входа; после добора — в цену добора после +BE от неё
        if pos.get("add_px"):
            if pos["stop"] != pos["add_px"] and px >= pos["add_px"] * (1 + PAPER_BE_PCT / 100):
                pos["stop"] = pos["add_px"]
                events.append(f"{sym.replace('USDT', '')}: стоп переставлен в цену добора {pos['stop']:g}")
        elif pos["stop"] is None and px >= pos["entry_px"] * (1 + PAPER_BE_PCT / 100):
            pos["stop"] = pos["entry_px"]
            events.append(f"{sym.replace('USDT', '')}: +{PAPER_BE_PCT:.0f}% — стоп в точку входа {pos['stop']:g}")
        # добор ×2 один раз: выходов не было, всё ещё в первых, ниже +ADD_MAX от входа
        if (not pos.get("add_px") and not fired_any_before and not any(pos["exits"][k] for k in EXITS)
                and place <= 3 and px < pos["entry_px"] * (1 + PAPER_ADD_MAX_PCT / 100)
                and at != pos["entry_at"]
                and (not PAPER_ADD_AFTER_BE or pos["stop"] is not None)):
            pos["add_px"], pos["add_at"], pos["size"] = px, at, 2
            events.append(f"{sym.replace('USDT', '')}: добор ×2 по {px:g} (от входа {_pct(pos['entry_px'], px):+.1f}%)")
        # ЗАКРЫТИЕ — НА ПЕРВОМ ЖЕ ВЫХОДЕ (владелец: «продаём, как только по какому-то сигналу
        # завершается»), либо стоп, либо срок. Остальные выходы дописываются виртуально — см. watch.
        reason = None
        first = [k for k in EXITS if sig[k] and pos["exits"][k] and pos["exits"][k]["at"] == at]
        if pos["stop"] is not None and px <= pos["stop"]:
            reason = "стоп"
        elif first:
            reason = "выход: " + first[0]
        elif now - _t(pos["entry_at"]) >= timedelta(days=PAPER_MAX_DAYS):
            reason = "срок"
        if reason:
            pos["closed_at"], pos["closed_px"], pos["closed_reason"] = at, px, reason
            pos["res_pct"] = _pct(_avg_entry(pos), px)
            pos["mfe_pct"], pos["mae_pct"] = _pct(pos["entry_px"], pos["max_px"]), _pct(pos["entry_px"], pos["min_px"])
            book["closed"].append(pos)
            del book["open"][sym]
            if not all(pos["exits"][k] for k in EXITS):
                book.setdefault("watch", []).append(pos)   # досчитать остальные выходы виртуально
            events.append(f"{sym.replace('USDT', '')}: закрыта ({reason}) {px:g} · {pos['res_pct']:+.1f}% · макс {pos['mfe_pct']:+.1f}% · мин {pos['mae_pct']:+.1f}%")
    # ── виртуальное дописывание выходов у закрытых (для сравнения четырёх правил)
    for pos in list(book.get("watch", [])):
        sym = pos["sym"]; row = run_rows.get(sym)
        if now - _t(pos["entry_at"]) >= timedelta(days=PAPER_MAX_DAYS) or all(pos["exits"][k] for k in EXITS):
            book["watch"].remove(pos); continue
        bar = _bar_at(sym, now)
        px = bar["px"] if bar else (row["px"] if row else pos["last_px"]); place = (row.get("place") or 99) if row else 99
        pos["out_runs"] = (pos.get("out_runs", 0) + 1) if place > 3 else 0
        new_bar = bool(bar and bar["t"].isoformat() != pos.get("last_bar")); pos["last_bar"] = bar["t"].isoformat() if bar else pos.get("last_bar")
        vsig = {"конец": bool(new_bar and bar["end"]) or bool(row and "конец" in str(row.get("today") or "")), "хедж": bool(row and row.get("vortex_hedge")),
                "сила": bool(new_bar and bar["force_dn"]) or bool(row and row.get("force_turn_ago") is not None and row["force_turn_ago"] <= PAPER_FORCE_FRESH_BARS), "выпадение": pos["out_runs"] >= PAPER_DROP_RUNS}
        for k in EXITS:
            if vsig[k] and not pos["exits"][k]:
                pos["exits"][k] = {"at": at, "px": px, "res_pct": _pct(_avg_entry(pos), px), "virtual": True}
    # ── новые входы: третье попадание в этом прогоне
    for sym, row in run_rows.items():
        if sym in book["open"] or (row.get("place") or 99) > 3:
            continue
        if hits.get(sym, 0) < PAPER_HITS:
            continue
        # не открываем повторно ту, что закрыли в этом окне, пока попадания не набрались заново после закрытия
        last_closed = next((c for c in reversed(book["closed"]) if c["sym"] == sym), None)
        if last_closed and _t(last_closed["closed_at"]) >= since:
            after = sum(1 for r in hist if r["sym"] == sym and (r.get("place") or 99) <= 3 and _t(r["at"]) > _t(last_closed["closed_at"]))
            if after < PAPER_HITS:
                continue
        hh = _t(at).hour
        session = "Токио" if hh < 7 else "Лондон" if hh < 13 else "Нью-Йорк" if hh < 22 else "Сидней"
        # ── варианты правил входа (проверяются на журнале, см. --variants)
        if VARIANT.get("hours") is not None and hh not in VARIANT["hours"]:
            continue
        if VARIANT.get("no_reentry_after_end"):
            day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
            ended = any(b["end"] for b in _arch(sym) if day0 <= b["t"] <= now)
            if ended:
                continue
        if VARIANT.get("bg_filter"):
            med = _bg_median_at(now)
            if med is not None and med < 0:
                continue
        bar0 = _bar_at(sym, now)
        entry_px = bar0["px"] if bar0 else row["px"]
        book["open"][sym] = {
            "sym": sym, "entry_at": at, "entry_px": entry_px, "size": 1, "stop": None, "last_bar": bar0["t"].isoformat() if bar0 else None,
            "add_px": None, "add_at": None, "last_px": entry_px, "last_at": at,
            "max_px": entry_px, "min_px": entry_px, "hits_at_entry": hits[sym],
            "mode": row.get("mode"), "session": session, "place": row.get("place"),
            "exits": {k: None for k in EXITS},
        }
        events.append(f"{sym.replace('USDT', '')}: ВХОД по {entry_px:g} · {hits[sym]} попаданий за {PAPER_WINDOW_H:.0f} ч · {row.get('mode') or '—'} · {session}")
    book["last_at"] = at
    return events


def update() -> str:
    """Один шаг по последнему прогону журнала. Возвращает текст блока для сообщения."""
    rows = _read_log()
    if not rows:
        return ""
    book = _load_book()
    runs = sorted({r["at"] for r in rows})
    todo = [a for a in runs if not book["last_at"] or a > book["last_at"]]
    events: list[str] = []
    for a in todo:
        run_rows = {r["sym"]: r for r in rows if r["at"] == a}
        hist = [r for r in rows if r["at"] <= a]
        events = _apply_run(book, a, run_rows, hist)   # события последнего прогона
    _save_book(book)
    return block(book, events)


def rebuild(save: bool = True) -> dict:
    """Пересобрать книгу с нуля по всему журналу (проверка правил на истории)."""
    rows = _read_log()
    book = {"open": {}, "closed": [], "watch": [], "last_at": None}
    for a in sorted({r["at"] for r in rows}):
        run_rows = {r["sym"]: r for r in rows if r["at"] == a}
        hist = [r for r in rows if r["at"] <= a]
        _apply_run(book, a, run_rows, hist)
    if save:
        _save_book(book)
    return book


def variants() -> str:
    """Сравнение правил входа на одном журнале: часы, запрет после «конца», фильтр по фону."""
    global VARIANT
    hours_us = set(range(13, 22)); hours_asia = set(range(0, 9))
    grid = [("как есть", {}),
            ("без входа после «конца» в те же сутки", {"no_reentry_after_end": True}),
            ("только Америка 13–22", {"hours": hours_us}),
            ("только Азия 0–9", {"hours": hours_asia}),
            ("Америка + без «конца»", {"hours": hours_us, "no_reentry_after_end": True}),
            ("Азия + без «конца»", {"hours": hours_asia, "no_reentry_after_end": True}),
            ("как есть + фон (медиана ≥ 0)", {"bg_filter": True}),
            ("без «конца» + фон", {"no_reentry_after_end": True, "bg_filter": True}),
            ("Америка + без «конца» + фон", {"hours": hours_us, "no_reentry_after_end": True, "bg_filter": True}),
            ("Азия + без «конца» + фон", {"hours": hours_asia, "no_reentry_after_end": True, "bg_filter": True})]
    out = [f"{'вариант':<38} {'поз.':>4} {'в плюс':>6} {'медиана':>8} {'сумма':>8} {'≥+20%':>5} {'≤-10%':>5}"]
    for name, v in grid:
        VARIANT = {"hours": None, "no_reentry_after_end": False, "bg_filter": False, **v}
        b = rebuild(save=False)
        res = [c["res_pct"] for c in b["closed"]] + [_pct(_avg_entry(p), p["last_px"]) for p in b["open"].values()]
        if not res:
            out.append(f"{name:<38} {0:>4}"); continue
        out.append(f"{name:<38} {len(res):>4} {sum(1 for r in res if r > 0):>6} {st.median(res):>+7.1f}% {sum(res):>+7.1f}% {sum(1 for r in res if r >= 20):>5} {sum(1 for r in res if r <= -10):>5}")
    VARIANT = {"hours": None, "no_reentry_after_end": False, "bg_filter": False}
    return "\n".join(out)


def block(book: dict, events: list[str] | None = None) -> str:
    lines = ["БУМАЖНАЯ КНИГА — первые три ≥3 прогонов за сутки, четыре выхода на позиции:"]
    for sym, p in book["open"].items():
        fired = [k for k in EXITS if p["exits"][k]]
        lines.append(f"  · {sym.replace('USDT', '')} вход {p['entry_px']:g} ({p['entry_at'][5:16]}) · сейчас {p['last_px']:g} ({_pct(_avg_entry(p), p['last_px']):+.1f}%)"
                     f" · стоп {p['stop'] if p['stop'] is not None else '—'}" + (f" · добор {p['add_px']:g}" if p.get('add_px') else "")
                     + (f" · выходы: {', '.join(fired)}" if fired else " · выходов нет"))
    if not book["open"]:
        lines.append("  · открытых нет")
    for e in events or []:
        lines.append("  → " + e)
    return "\n".join(lines)


def report(book: dict | None = None) -> str:
    book = book or _load_book()
    cl = book["closed"]
    if not cl:
        return "закрытых позиций нет"
    out = [f"закрыто {len(cl)} · открыто {len(book['open'])}"]
    res = [c["res_pct"] for c in cl]
    out.append(f"итог по закрытию: в плюс {sum(1 for r in res if r > 0)} из {len(res)} · медиана {st.median(res):+.1f}% · сумма {sum(res):+.1f}%")
    for k in EXITS:
        v = [c["exits"][k]["res_pct"] for c in cl if c["exits"].get(k)]
        if v:
            out.append(f"  выход «{k}»: сработал у {len(v)} · в плюс {sum(1 for r in v if r > 0)} · медиана {st.median(v):+.1f}%")
    by = {}
    for c in cl:
        by.setdefault(c.get("closed_reason"), []).append(c["res_pct"])
    for k, v in by.items():
        out.append(f"  закрытие «{k}»: {len(v)} · медиана {st.median(v):+.1f}%")
    for m in ("лестница", "парабола", "неясно"):
        v = [c["res_pct"] for c in cl if (c.get("mode") or "неясно") == m]
        if v:
            out.append(f"  форма «{m}»: {len(v)} · в плюс {sum(1 for r in v if r > 0)} · медиана {st.median(v):+.1f}%")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="бумажная книга по первым очереди")
    ap.add_argument("--rebuild", action="store_true", help="пересобрать с нуля по всему журналу")
    ap.add_argument("--report", action="store_true", help="сводка по закрытым")
    ap.add_argument("--variants", action="store_true", help="сравнить правила входа на журнале")
    a = ap.parse_args()
    if a.rebuild:
        b = rebuild()
        print(block(b))
        print(report(b))
        for c in b["closed"]:
            ex = " · ".join(f"{k} {c['exits'][k]['res_pct']:+.1f}%" if c["exits"][k] else f"{k} —" for k in EXITS)
            print(f"  {c['sym'].replace('USDT', ''):<9} {c['entry_at'][5:16]} вход {c['entry_px']:<10g} → {c['closed_at'][5:16]} {c['closed_reason']:<12} {c['res_pct']:+6.1f}% · макс {c['mfe_pct']:+.1f}% мин {c['mae_pct']:+.1f}% · {ex}" + (f" · добор {c['add_px']:g}" if c.get('add_px') else ""))
        return
    if a.report:
        print(report())
        return
    if a.variants:
        print(variants())
        return
    print(update())


if __name__ == "__main__":
    main()
