#!/usr/bin/env python3
"""ЖУРНАЛ ЗАДНИМ ЧИСЛОМ ПО АРХИВУ (16.09, владелец: «а мы можем в журнал добавить сразу сделки по
intraday и вообще по тому, что есть сейчас на компьютере?»).

Правила ботов детерминированы: на тех же барах они дадут те же входы и выходы. Здесь `paper_crowd` и
`paper_end` прогоняются по истории `cq_v2/intraday` бар за баром — сигнал считается ТОЛЬКО по барам до
текущего, заглядывания вперёд нет. Сделки пишутся в ОТДЕЛЬНЫЕ журналы `*_backfill.jsonl`, чтобы не
смешивать с живыми: живые — свидетельство работы бота, эти — реконструкция.

Зачем: архив пишется с 11.09, живого журнала было меньше суток. Так неделя появляется сразу, и
`check_journal` может считать правила не на 70 сделках одного дня, а на нескольких сотнях.

Чего backfill НЕ повторяет и о чём надо помнить при чтении:
  • правило «событие доски» (конец у ≥5 монет разом) — оно зависит от состава прогона, здесь его нет;
  • запрет встречных позиций между книгами — он тоже про живое состояние, здесь книги считаются врозь;
  • биржевые задержки, проскальзывание и то, что бот мог не успеть на бар.
Поэтому backfill годится для сравнения ПРАВИЛ между собой, а не для обещания денег.

`python3 paper_backfill.py` — показать, сколько выйдет; `--write` — записать; `--only ARK` — одна монета;
`--from 2026-09-11` — с какой даты.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

ARCH = BASE_DIR / "cq_v2" / "intraday"


def rows_of(sym: str) -> list[dict]:
    p = ARCH / f"{sym.replace('USDT', '').lower()}.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if not r.get("px"):
            continue
        try:
            r["t"] = int(datetime.strptime(r["candle"], "%Y-%m-%dT%H:%M:%SZ")
                         .replace(tzinfo=timezone.utc).timestamp() * 1000)
        except (KeyError, ValueError):
            continue
        out.append(r)
    out.sort(key=lambda r: r["t"])
    return out


def replay(mod, rows: list[dict], book: str, sym: str) -> list[dict]:
    """бар за баром: сигнал по срезу до текущего бара, выход — по правилам самого бота"""
    trades = []
    i = 0
    n = len(rows)
    while i < n:
        sl = rows[:i + 1]
        try:
            sig = mod.signal(sl)
        except Exception:  # noqa: BLE001
            sig = None
        if not sig:
            i += 1
            continue
        pos = dict(sig)
        j = i + 1
        out = None
        while j < n:
            try:
                ex = mod.check_exit(pos, rows[:j + 1])
            except Exception:  # noqa: BLE001
                ex = None
            if ex:
                res, why = ex
                out = (res, why, rows[j])
                break
            j += 1
        if out is None:
            break                          # позиция дожила до конца архива — в журнал не пишем
        res, why, bar = out
        size = float(pos.get("size") or 1.0)
        trades.append({
            "kind": "exit", "book": book, "sym": sym, "at": int(bar["t"] / 1000),
            "entry_at": int(pos["t"] / 1000), "entry_px": pos.get("px"), "exit_px": bar.get("px"),
            "rule": pos.get("rule"), "why_exit": why, "side": pos.get("side", -1),
            "size": size, "result_pct": round(res * 100, 2), "result_sized_pct": round(res * size * 100, 2),
            "bars_in": j - i, "funding": pos.get("fund") if pos.get("fund") is not None else pos.get("funding"),
            "run_pct": pos.get("run_pct"), "oi_bar_pct": pos.get("oi_bar_pct"), "bg12": pos.get("bg12"),
            "backfill": True,
        })
        i = j + 1                          # следующий вход — не раньше бара выхода
    return trades


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--from", dest="since", help="с какой даты, ГГГГ-ММ-ДД")
    a = ap.parse_args()
    syms = ([x.strip().upper() + ("" if x.strip().upper().endswith("USDT") else "USDT") for x in a.only.split(",")]
            if a.only else sorted(p.stem.upper() + "USDT" for p in ARCH.glob("*.jsonl")))
    cut = 0
    if a.since:
        cut = int(datetime.strptime(a.since, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    import paper_crowd
    import paper_end
    books = (("толпа", paper_crowd, "paper_crowd"), ("конец", paper_end, "paper_end"))
    got = {name: [] for name, _, _ in books}
    for sym in syms:
        rows = rows_of(sym)
        if cut:
            rows = [r for r in rows if r["t"] >= cut]
        if len(rows) < 60:
            continue
        for name, mod, stem in books:
            got[name] += replay(mod, rows, name, sym)
    total = sum(len(v) for v in got.values())
    if not total:
        print("сделок не вышло — мало баров или архив пуст")
        return 0
    print(f"монет {len(syms)} · сделок задним числом {total}\n")
    for name, _, stem in books:
        tr = got[name]
        if not tr:
            continue
        v = [t["result_pct"] for t in tr]
        print(f"{name}: n={len(v)} · попаданий {100 * sum(1 for x in v if x > 0) / len(v):.0f}% · "
              f"медиана {st.median(v):+.2f}% · средняя {st.mean(v):+.2f}%")
        by = {}
        for t in tr:
            by.setdefault(str(t.get("rule") or "—")[:48], []).append(t["result_pct"])
        for k, vv in sorted(by.items(), key=lambda kv: -len(kv[1])):
            if len(vv) >= 5:
                print(f"   {k:<48} n={len(vv):>4} · {100 * sum(1 for x in vv if x > 0) / len(vv):3.0f}% · "
                      f"средняя {st.mean(vv):+.2f}%")
    # деньги по дням: депозит на день делится по весу
    byday = {}
    for tr in got.values():
        for t in tr:
            d = datetime.fromtimestamp(t["at"], timezone.utc).strftime("%Y-%m-%d")     # день — по UTC, как у экрана книги
            byday.setdefault(d, []).append(t)
    print("\nденьги по дням UTC (депозит 10 000 $ на день, доля по весу правила):")
    tot = 0.0
    for d in sorted(byday):
        rs = byday[d]
        w = sum(float(x.get("size") or 1) for x in rs) or 1
        m = sum(10000.0 * float(x.get("size") or 1) / w * float(x["result_pct"]) / 100 for x in rs)
        tot += m
        print(f"  {d}  сделок {len(rs):>4} · итог {m:+8.0f} $ · попаданий "
              f"{100 * sum(1 for x in rs if x['result_pct'] > 0) / len(rs):3.0f}%")
    print(f"  ИТОГО {tot:+.0f} $ за {len(byday)} дн.")
    if a.write:
        for name, _, stem in books:
            if not got[name]:
                continue
            p = BASE_DIR / "output" / f"{stem}_backfill.jsonl"
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("w", encoding="utf-8") as f:
                for t in sorted(got[name], key=lambda x: x["at"]):
                    f.write(json.dumps(t, ensure_ascii=False) + "\n")
            print(f"записано: {p.relative_to(BASE_DIR)} · {len(got[name])} строк")
    else:
        print("\nзапуск с --write, чтобы записать в output/*_backfill.jsonl (живые журналы не трогаются)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
