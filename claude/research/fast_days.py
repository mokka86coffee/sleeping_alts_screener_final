#!/usr/bin/env python3
"""БЫСТРЫЕ КНИГИ ПО ДНЯМ И СЕССИЯМ — ПРОВЕРКА R40–R42 НА ЖИВЫХ СДЕЛКАХ (27.09, владелец: «правило про дни будет корректироваться, как только
перестанет работать — впишем новые дни»). Раз в сутки из чата.

1. Живые сделки «всплеск/вынос» и «пробуждение» с включения ворот сессий (27.09 17:26): по дню недели и сессии входа — сделок, в плюс, $ при 500.
2. Отсечённые воротами всплески (строки «… всплеск пропущен: …» в output/fast_tier.log): что дали бы при тех же выходах — цель +5 / стоп −5 /
   до часа выхода сессии (FAST3_SES_EXIT_H), по трёхминуткам Binance. Разрез по причине (первый час, поздно, день) и дню.
   Если отсечённый день/час в плюсе, а разрешённые в минусе — правило пора менять (приносить владельцу со счётом).
3. Сводка разборов выходов (fast_review.py --summary).

    .venv/bin/python claude/research/fast_days.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core_http import get_json  # noqa: E402
from core_config import FAST3_SES_EXIT_H  # noqa: E402

L = timezone(timedelta(hours=3))
GATE_FROM = datetime(2026, 9, 27, 17, 26, tzinfo=L).timestamp()
WIN = (("Сидней", 0, 3), ("Токио", 3, 10), ("Лондон", 10, 16), ("Нью-Йорк", 16, 24))
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
TP = SL = 0.05
FEE = 0.001


def ses(t: float) -> str:
    h = datetime.fromtimestamp(t, L).hour
    return next(n for n, a, b in WIN if a <= h < b)


def exit_ts(t: float) -> float:
    d = datetime.fromtimestamp(t, L)
    n = ses(t)
    return (d.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=FAST3_SES_EXIT_H.get(n, 24))).timestamp()


def cell(g: list[float]) -> str:
    if not g:
        return "—"
    return f"{len(g)} · {round(sum(x > 0 for x in g) / len(g) * 100)}% · {sum(g) * 5:+.0f}$"


def live() -> list[dict]:
    out = []
    for book, f in (("всплеск/вынос", "paper_fast3.jsonl"), ("пробуждение", "paper_wake.jsonl")):
        for ln in (ROOT / "output" / f).open(encoding="utf-8"):
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if str(r.get("kind", "")).startswith("exit") and (r.get("opened_at") or 0) >= GATE_FROM and r.get("result_pct") is not None:
                t = float(r["opened_at"])
                out.append(dict(book=book, sym=r.get("sym"), side=int(r.get("side") or 1), t=t, res=float(r["result_pct"]),
                                wd=WD[datetime.fromtimestamp(t, L).weekday()], ses=ses(t)))
    return out


def skipped() -> list[dict]:
    """строки «HH:MM:SS <книга>: <МОНЕТА> всплеск пропущен: <причина>» — дата идёт от времени изменения лога назад"""
    p = ROOT / "output" / "fast_tier.log"
    lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    day = datetime.fromtimestamp(os.path.getmtime(p), L).date()
    prev, out = None, []
    rx = re.compile(r"^(\d\d):(\d\d):(\d\d) (.+?): (\S+) всплеск пропущен: (.+)$")
    tm = re.compile(r"^(\d\d):(\d\d):(\d\d) ")
    for ln in reversed(lines):
        m0 = tm.match(ln)
        if not m0:
            continue
        hms = tuple(int(x) for x in m0.groups())
        if prev is not None and hms > prev:
            day -= timedelta(days=1)
        prev = hms
        m = rx.match(ln)
        if m:
            t = datetime(day.year, day.month, day.day, hms[0], hms[1], hms[2], tzinfo=L).timestamp()
            if t >= GATE_FROM:
                why = m.group(6)
                kind = "первый час" if "первый час" in why else "поздно" if "поздно" in why else "день" if "день" in why else why
                out.append(dict(book=m.group(4), sym=m.group(5) + "USDT", t=t, kind=kind))
    return out


def simulate(s: dict):
    """лонг по закрытию бара всплеска: +5 / −5 / до часа выхода сессии, в которой всплеск был"""
    t0 = int(s["t"] * 1000) // 180_000 * 180_000 - 180_000
    end = exit_ts(s["t"])
    k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": s["sym"], "interval": "3m", "startTime": t0, "endTime": int(end * 1000), "limit": 500},
                 quiet_400=True, weight=2) or []
    k = [x for x in k if int(x[0]) + 180_000 <= time.time() * 1000]
    if len(k) < 2 or time.time() < end:
        return None                                              # срок ещё не вышел — исход не известен
    e = float(k[0][4])
    for x in k[1:]:
        if float(x[3]) <= e * (1 - SL):
            return -SL * 100 - FEE * 100
        if float(x[2]) >= e * (1 + TP):
            return TP * 100 - FEE * 100
    return (float(k[-1][4]) / e - 1) * 100 - FEE * 100


def own_mm() -> set:
    try:
        return set(json.loads((ROOT / "output" / "own_mm.json").read_text()).get("coins", {}).keys())
    except (OSError, ValueError):
        return set()


def main() -> int:
    print(f"БЫСТРЫЕ ПО ДНЯМ ({datetime.now(L):%d.%m %H:%M}; с включения ворот сессий 27.09 17:26; клетка: сделок · в плюс · $ при 500)")
    om = own_mm()
    lv_all = live()
    lv = [r for r in lv_all if r.get("sym") not in om]            # 27.09: монеты своего ММ в счёт правил не идут
    ex_ = [r for r in lv_all if r.get("sym") in om]
    if ex_:
        print(f"(монеты своего ММ вне счёта: {cell([r['res'] for r in ex_])})")
    by = defaultdict(list)
    for r in lv:
        by[(r["book"], r["wd"], r["ses"])].append(r["res"])
    for book in ("всплеск/вынос", "пробуждение"):
        g = [r for r in lv if r["book"] == book]
        print(f"\n{book}: всего {cell([r['res'] for r in g])}")
        for wd in WD:
            row = [cell(by[(book, wd, n)]) for n, _, _ in WIN]
            if any(c != "—" for c in row):
                print(f"  {wd}: " + " | ".join(f"{n} {c}" for (n, _, _), c in zip(WIN, row)))
    sk = skipped()
    res = []
    for s in sk:
        r = simulate(s)
        if r is not None:
            res.append(dict(s, res=r, wd=WD[datetime.fromtimestamp(s["t"], L).weekday()]))
    print(f"\nОТСЕЧЕНО ВОРОТАМИ: {len(sk)} всплесков, с известным исходом {len(res)} (что дали бы при тех же выходах)")
    agg = defaultdict(list)
    for r in res:
        agg[r["kind"]].append(r["res"]); agg[r["kind"] + " · " + r["wd"]].append(r["res"])
    for k in sorted(agg):
        print(f"  {k}: {cell(agg[k])}")
    try:
        sys.path.insert(0, str(ROOT))
        import fast_review
        print("\nРАЗБОРЫ ВЫХОДОВ: " + fast_review.summary())
    except Exception as e:  # noqa: BLE001
        print(f"\nразборы: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
