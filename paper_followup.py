#!/usr/bin/env python3
"""КУДА ЦЕНА ДОШЛА ПОСЛЕ ВЫХОДА (16.09, владелец: «может цену писать дальше для тех сделок, из которых
вышли, до куда дошла — тогда понятно будет, правы или нет»).

Раз в прогон дочитывает журналы бумажных книг (paper_end / paper_crowd / paper_fast), берёт закрытые
сделки, которым уже хватает возраста, тянет получасовки биржи и дописывает СТРОКУ СЛЕДА — отдельную
запись kind="follow" с тем же ключом (sym + at), чтобы исходные строки не переписывать:

  after_1h / after_6h / after_12h / after_24h — ход ОТ ЦЕНЫ ВЫХОДА в сторону сделки (для шорта знак
      перевёрнут): плюс — вышли рано, ход продолжался; минус — вышли вовремя;
  best_after / worst_after — лучший и худший ход после выхода за FOLLOW_MAX_H часов;
  mfe / mae — что было ВНУТРИ сделки: лучший ход в сторону позиции и худший против неё от входа;
  bars_in — сколько баров держали.
Из этого сразу считается то, чего журнал не знал: цель резала ход или ловила вершину, стоп выбивало
хвостом или он спасал, и сколько стоил выход по сроку.

Хранит, что уже обработано, в output/paper_follow_state.json — второй раз одну сделку не считает.
Запуск из прогона после ботов; руками `python3 paper_followup.py --only paper_end` (печать), `--write`.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
import time
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
try:
    from core_config import FOLLOW_HOURS, FOLLOW_MAX_H
except ImportError:
    FOLLOW_HOURS, FOLLOW_MAX_H = (1, 6, 12, 24), 24

BOOKS = ("paper_end", "paper_crowd", "paper_fast")
STATE = BASE_DIR / "output" / "paper_follow_state.json"


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _rows(stem: str) -> list[dict]:
    p = BASE_DIR / "output" / f"{stem}.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _klines(sym: str, since_ms: int, hours: int) -> list[tuple]:
    """получасовки от момента выхода и на hours вперёд: (t, high, low, close)"""
    import core_binance as cb
    from core_binance import K_HIGH, K_LOW, K_OPEN_TIME, get_klines
    KC = getattr(cb, "K_CLOSE", 4)
    need = hours * 2 + 4
    try:
        ks = get_klines(sym, "30m", limit=min(500, need + 60)) or []
    except Exception:  # noqa: BLE001
        return []
    out = [(int(k[K_OPEN_TIME]), float(k[K_HIGH]), float(k[K_LOW]), float(k[KC])) for k in ks]
    return [b for b in sorted(out) if b[0] >= since_ms]


def _side_of(r: dict) -> int:
    """сторона закрытой сделки: paper_end всегда шорт, у прочих — в записи или в виде выхода"""
    if r.get("side") is not None:
        return int(r["side"])
    if r.get("book") == "paper_end":
        return -1
    if str(r.get("kind")) == "exit_short":
        return -1
    if str(r.get("kind")) == "exit_long":
        return 1
    rule = str(r.get("rule") or "")
    if rule.startswith("провал") or rule.startswith("прокол") or rule.startswith("за толпой"):
        return 1
    return -1


def follow(write: bool, only: str | None = None) -> int:
    done = _read(STATE) or {}
    now_ms = int(time.time() * 1000)
    added = 0
    report = []
    for stem in BOOKS:
        if only and stem != only:
            continue
        rows = _rows(stem)
        exits = [r for r in rows if str(r.get("kind") or "").startswith("exit")]
        for r in exits:
            at = int((r.get("at") or 0) * 1000)
            sym = str(r.get("sym") or "").upper()
            key = f"{stem}|{sym}|{r.get('at')}"
            if not at or not sym or key in done:
                continue
            if now_ms - at < min(FOLLOW_HOURS) * 3600_000:
                continue                       # рано: не набралось даже первого окна
            bars = _klines(sym, at, FOLLOW_MAX_H)
            if len(bars) < 2:
                continue
            side = _side_of(dict(r, book=stem))
            px_out = None
            # цена выхода: закрытие бара, на котором вышли
            px_out = bars[0][3]
            row = {"kind": "follow", "book": stem, "sym": sym, "at": r.get("at"),
                   "rule": r.get("rule"), "why_exit": r.get("why_exit"), "result_pct": r.get("result_pct"),
                   "side": side, "px_out": px_out, "written_at": int(time.time())}
            for h in FOLLOW_HOURS:
                tgt = at + h * 3600_000
                nxt = [b for b in bars if b[0] >= tgt]
                if nxt:
                    row[f"after_{h}h"] = round((nxt[0][3] / px_out - 1) * 100 * side, 2)
            seq = [b for b in bars if b[0] <= at + FOLLOW_MAX_H * 3600_000]
            if len(seq) >= 2:
                moves = [( (b[3] / px_out - 1) * 100 * side) for b in seq]
                row["best_after"] = round(max(moves), 2)
                row["worst_after"] = round(min(moves), 2)
            # что было внутри сделки — по входу, если он есть в журнале
            ent = next((x for x in rows if x.get("kind") == "entry" and str(x.get("sym") or "").upper() == sym
                        and (x.get("at") or 0) <= (r.get("at") or 0)), None)
            if ent and ent.get("px"):
                e = float(ent["px"])
                inside = _klines(sym, int((ent.get("at") or 0) * 1000), FOLLOW_MAX_H)
                inside = [b for b in inside if b[0] <= at]
                if inside:
                    ups = [((b[1] if side > 0 else b[2]) / e - 1) * 100 * side for b in inside]
                    dns = [((b[2] if side > 0 else b[1]) / e - 1) * 100 * side for b in inside]
                    row["mfe"] = round(max(ups), 2)
                    row["mae"] = round(min(dns), 2)
                    row["bars_in"] = len(inside)
                    row["entry_px"] = e
            if write:
                with (BASE_DIR / "output" / f"{stem}.jsonl").open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                done[key] = row["written_at"]
            added += 1
            report.append(row)
    if write:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE)
    # короткая сводка: правы ли были выходы
    if report:
        by = {}
        for x in report:
            w = str(x.get("why_exit") or "")
            k = "цель" if w.startswith("цель") else "стоп" if w.startswith("стоп") else "срок" if w.startswith("срок") else "событие"
            by.setdefault(k, []).append(x)
        print(f"след: дописано {added} сделок")
        for k, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
            a6 = [x["after_6h"] for x in v if x.get("after_6h") is not None]
            if not a6:                      # окно ещё не набралось — берём ближайшее меньшее
                a6 = [x["after_1h"] for x in v if x.get("after_1h") is not None]
            if a6:
                late = 100 * sum(1 for x in a6 if x > 0) / len(a6)
                print(f"  выход «{k}»: n={len(a6)} · после выхода за 6 ч медиана {st.median(a6):+.2f}% · "
                      f"ход продолжился в {late:.0f}% случаев (вышли рано)")
    else:
        print(f"след: новых сделок для дописывания нет" + ("" if write else " (без записи)"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="одна книга: paper_end | paper_crowd | paper_fast")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    return follow(a.write, a.only)


if __name__ == "__main__":
    raise SystemExit(main())
