#!/usr/bin/env python3
"""ЛАБОРАТОРИЯ ОКОН (16.09; владелец: «не надо гнать бота каждые полчаса — найти самые точные окна в рынке:
шорт за час до стыка и час после открытия, воскресенье и понедельник — чаще слив, туда большие суммы; Америка,
Сингапур, Токио — лонговые сетапы через 1.5–2 часа после открытия, среда-четверг, суббота; медиана доски и число
растущих уходят в минус — шортим всё, что росло; уходят в плюс за несколько часов — лонги на то, что чуть пошло»).

Всё считается по получасовкам биржи (core_binance.get_klines, LAB_BARS баров) по монетам сводки — 30 дней.
Три таблицы:
  1. ОКНА ЧАСОВ: день недели × час UTC → медиана хода доски за следующие 1 ч / 2 ч / 4 ч, доля монет вниз, n.
     Отдельно стыки: от «час до открытия» до «час после» и от открытия до +2 ч, по сессиям и по дням недели.
  2. ДИНАМИКА ДОСКИ: на каждом баре — медиана хода всех монет за 6 ч и доля растущих; их изменение за 4 ч.
     Фон «доска разворачивается вниз» (медиана и доля упали за 4 ч и стали < 0) → шорт всех, кто вырос за 12 ч
     больше X; фон «вверх» → лонг тех, кто «чуть пошёл» (+1…+4% за 2 ч) — форвард 2 / 6 / 12 ч.
  3. ЛУЧШИЕ ОКНА: сводная таблица «день · час · правило» с медианой, долей попаданий и n, отсортированная по
     краю против контроля того же часа.
Ничего не пишет. `python3 lab_windows.py --days 30`, `--tz 8` (местные часы в подписях, считается всё в UTC).
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

LAB_BARS = 1500
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
OPENS = {21: "Сидней", 0: "Токио", 7: "Лондон", 13: "Нью-Йорк"}


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def coins() -> list[str]:
    nm = _read(BASE_DIR / "output" / "near_move.json") or {}
    out = [str(s).upper() for s in (nm.get("coins") or {}).keys()]
    return sorted(set(s if s.endswith("USDT") else s + "USDT" for s in out))


def klines(sym: str, limit: int, hourly: bool = False):
    """30м — через биржу; --hourly — из hourly/<монета>.json проекта (часовые свечи с марта, полгода)."""
    if hourly:
        p = BASE_DIR / "hourly" / f"{sym.replace('USDT', '').lower()}.json"
        try:
            arr = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        out = {int(b["t"]): float(b["c"]) for b in arr if isinstance(b, dict) and b.get("t") and b.get("c")}
        if limit and len(out) > limit:
            keys = sorted(out)[-limit:]
            out = {k: out[k] for k in keys}
        return out
    import core_binance as cb
    from core_binance import K_OPEN_TIME, get_klines
    KC = getattr(cb, "K_CLOSE", 4)
    ks = get_klines(sym, "30m", limit=limit) or []
    return {int(k[K_OPEN_TIME]): float(k[KC]) for k in ks}


def med(v):
    return st.median(v) if v else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--tz", type=int, default=8, help="смещение местного времени для подписей")
    ap.add_argument("--only")
    ap.add_argument("--hourly", action="store_true", help="часовые свечи из hourly/*.json (полгода) вместо получасовок биржи")
    a = ap.parse_args()
    if a.hourly:
        syms = [x.strip().upper() + ("" if x.strip().upper().endswith("USDT") else "USDT") for x in a.only.split(",")] if a.only else \
               sorted(p.stem.upper() + "USDT" for p in (BASE_DIR / "hourly").glob("*.json") if p.stem.lower() != "btc")
        bars = a.days * 24 + 60
    else:
        syms = [x.strip().upper() + ("" if x.strip().upper().endswith("USDT") else "USDT") for x in a.only.split(",")] if a.only else coins()
        bars = min(LAB_BARS, a.days * 48 + 60)
    data = {}
    for s in syms:
        try:
            k = klines(s, bars, a.hourly)
        except Exception as ex:  # noqa: BLE001
            print(f"{s}: клайны не получены — {type(ex).__name__}")
            continue
        if len(k) >= 200:
            data[s] = k
    if not data:
        print("нет данных")
        return 0
    times = sorted(set(t for k in data.values() for t in k))
    tset = set(times)
    STEP = 3600000 if a.hourly else 1800000

    def fwd(s, t, h):
        k = data[s]
        t2 = t + h * 3600000
        return (k[t2] / k[t] - 1) * 100 if (t in k and t2 in k) else None

    def back(s, t, h):
        k = data[s]
        t0 = t - h * 3600000
        return (k[t] / k[t0] - 1) * 100 if (t in k and t0 in k) else None

    # ── 1. окна часов: день недели × час UTC
    print(f"монет {len(data)} · баров {len(times)} · {a.days} дн. · подписи часов — UTC (местное = UTC{a.tz:+d})\n")
    cell = defaultdict(list)
    for t in times:
        d = datetime.fromtimestamp(t / 1000, timezone.utc)
        if d.minute != 0:
            continue
        for s in data:
            f1, f2, f4 = fwd(s, t, 1), fwd(s, t, 2), fwd(s, t, 4)
            if f2 is not None:
                cell[(d.weekday(), d.hour)].append((f1, f2, f4))
    ctrl2 = [x[1] for v in cell.values() for x in v]
    c_med = med(ctrl2)
    print(f"── 1. ОКНА: день недели × час UTC → медиана хода доски за 2 ч (контроль по всем часам {c_med:+.2f}%), доля монет вниз")
    print("      " + " ".join(f"{h:>6}" for h in range(0, 24, 2)))
    for wd in range(7):
        row = []
        for h in range(0, 24, 2):
            v = [x[1] for x in cell.get((wd, h), [])]
            row.append(f"{med(v):+5.1f}" if len(v) >= 20 else "    ·")
        print(f"  {WD[wd]}  " + " ".join(f"{x:>6}" for x in row))
    print("\n   самые сильные часы (по 2 ч вперёд, n≥30), край против контроля:")
    ranked = []
    for (wd, h), v in cell.items():
        v2 = [x[1] for x in v]
        if len(v2) >= 30:
            ranked.append((med(v2) - c_med, wd, h, med(v2), 100 * sum(1 for x in v2 if x < 0) / len(v2), len(v2)))
    ranked.sort()
    for edge, wd, h, m, dn, n in ranked[:8]:
        print(f"     ШОРТ  {WD[wd]} {h:02d}:00 UTC ({(h + a.tz) % 24:02d}:00 местн.) · медиана 2 ч {m:+.2f}% · вниз {dn:.0f}% · n={n}")
    for edge, wd, h, m, dn, n in ranked[-8:][::-1]:
        print(f"     ЛОНГ  {WD[wd]} {h:02d}:00 UTC ({(h + a.tz) % 24:02d}:00 местн.) · медиана 2 ч {m:+.2f}% · вниз {dn:.0f}% · n={n}")

    # ── стыки: час до → час после; открытие → +2 ч; по сессиям и по дням недели
    print("\n── СТЫКИ: «шорт за час до открытия, крыть через час после» и «открытие → +2 ч», по сессиям")
    for hour, name in OPENS.items():
        pre_post, post2, by_wd = [], [], defaultdict(list)
        for t in times:
            d = datetime.fromtimestamp(t / 1000, timezone.utc)
            if d.hour != hour or d.minute != 0:
                continue
            for s in data:
                k = data[s]
                a_, b_ = t - 3600000, t + 3600000
                if a_ in k and b_ in k:
                    x = (k[b_] / k[a_] - 1) * 100
                    pre_post.append(x)
                    by_wd[d.weekday()].append(x)
                f2 = fwd(s, t, 2)
                if f2 is not None:
                    post2.append(f2)
        if len(pre_post) < 20:
            continue
        print(f"  {name:<9} час до → час после: медиана {med(pre_post):+.2f}% · вниз {100 * sum(1 for x in pre_post if x < 0) / len(pre_post):.0f}% · n={len(pre_post)}   |   открытие → +2 ч: {med(post2):+.2f}% · вниз {100 * sum(1 for x in post2 if x < 0) / len(post2):.0f}%")
        print("            по дням: " + " · ".join(f"{WD[w]} {med(v):+.2f}% ({100 * sum(1 for x in v if x < 0) / len(v):.0f}%↓, n={len(v)})" for w, v in sorted(by_wd.items()) if len(v) >= 15))

    # ── 2. динамика доски
    print("\n── 2. ДИНАМИКА ДОСКИ: медиана хода за 6 ч и доля растущих; их ход за 4 ч → что делать")
    board = {}
    for t in times:
        v = [back(s, t, 6) for s in data]
        v = [x for x in v if x is not None]
        if len(v) >= max(8, len(data) // 3):
            board[t] = (med(v), 100 * sum(1 for x in v if x > 0) / len(v))
    down_short, up_long, ctrl_dn, ctrl_up = [], [], [], []
    for t in times:
        if t not in board or (t - 4 * 3600000) not in board:
            continue
        m, up = board[t]
        m0, up0 = board[t - 4 * 3600000]
        turning_down = m < 0 and m < m0 and up < up0 and up < 45
        turning_up = m > 0 and m > m0 and up > up0 and up > 55
        for s in data:
            r12 = back(s, t, 12)
            r2 = back(s, t, 2)
            f2, f6, f12 = fwd(s, t, 2), fwd(s, t, 6), fwd(s, t, 12)
            if f6 is None or f2 is None or r12 is None or r2 is None:
                continue
            if r12 >= 5:
                (down_short if turning_down else ctrl_dn).append((-f2, -f6, -(f12 or f6)))
            if 1 <= r2 <= 4:
                (up_long if turning_up else ctrl_up).append((f2, f6, f12 or f6))

    def row(name, v, c):
        if len(v) < 20:
            print(f"  {name:<58} n={len(v)} — мало")
            return
        print(f"  {name:<58} n={len(v):>5} · 2 ч {med([x[0] for x in v]):+.2f}% · 6 ч {med([x[1] for x in v]):+.2f}% · 12 ч {med([x[2] for x in v]):+.2f}% · ≥+3% за 6 ч: {100 * sum(1 for x in v if x[1] >= 3) / len(v):.0f}%"
              + (f"   | контроль 6 ч {med([x[1] for x in c]):+.2f}% (n={len(c)})" if len(c) >= 20 else ""))
    row("доска разворачивается вниз → ШОРТ тех, кто вырос ≥5% за 12 ч", down_short, ctrl_dn)
    row("доска разворачивается вверх → ЛОНГ тех, кто пошёл +1…4% за 2 ч", up_long, ctrl_up)

    # ── 3. лонговые окна после открытий: 1.5–2 ч после Нью-Йорка / Сиднея / Токио, по дням недели
    print("\n── 3. ЛОНГ ЧЕРЕЗ 1.5–2 Ч ПОСЛЕ ОТКРЫТИЯ (вход на +1.5 ч, держим 4 ч), по сессиям и дням недели")
    for hour, name in OPENS.items():
        by_wd = defaultdict(list)
        allv = []
        for t in times:
            d = datetime.fromtimestamp(t / 1000, timezone.utc)
            if d.hour != hour or d.minute != 0:
                continue
            te = t + int(1.5 * 3600000)
            for s in data:
                k = data[s]
                t4 = te + 4 * 3600000
                if te in k and t4 in k:
                    x = (k[t4] / k[te] - 1) * 100
                    by_wd[d.weekday()].append(x)
                    allv.append(x)
        if len(allv) < 20:
            continue
        print(f"  {name:<9} все дни: медиана {med(allv):+.2f}% · ≥+3%: {100 * sum(1 for x in allv if x >= 3) / len(allv):.0f}% · n={len(allv)}   по дням: "
              + " · ".join(f"{WD[w]} {med(v):+.2f}% ({100 * sum(1 for x in v if x >= 3) / len(v):.0f}%≥3, n={len(v)})" for w, v in sorted(by_wd.items()) if len(v) >= 15))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
