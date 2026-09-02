#!/usr/bin/env python3
"""КОГДА РАСТЁТ: доля растущих монет по дню недели и часу (02.09).

Крипта круглосуточная и всемирная, но деньги приходят по расписанию
столов: Азия, Европа, Америка. Сводка отвечает, в какие часы больше
монет журнала идёт вверх — в целом и по секторам.

ВХОД. hourly/<coin>.json от coinglass_hourly.py (часовые свечи, 180
дней). Без них — дневки cq_v2 (тогда только дни недели).
Сектора — sectors.json: {"defi": ["ENA","CVX",…], "meme": […], …}.
Нет файла — считаем без секторов.

ВРЕМЯ — Нью-Йорк, как просил владелец. Свечи Coinglass в UTC;
переводим с учётом летнего времени.

МЕРА. Для каждой ячейки (день, час): сколько свечей закрылось выше
открытия, из скольких. Это ДОЛЯ растущих, а не размер хода: маленькая
монета на +30% и на +0.3% — одна растущая свеча. Размер отдельно, как
медиана хода в ячейке.

ЧЕСТНОСТЬ. Показываем n в каждой ячейке. При 70 монетах × 26 недель
в ячейке около 1800 свечей — стандартная ошибка доли ~1.2%. Разница
меньше 3% — шум, не печатаем как находку.

    python3 when_grows.py                 # общая карта + сектора
    python3 when_grows.py --sector defi   # одна
    python3 when_grows.py --daily         # только дни недели, по cq_v2
"""
import argparse
import json
import statistics as st
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
DOW = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
HOURLY = Path("hourly")
DAILY = Path("cq_v2")


def load_sectors() -> dict[str, str]:
    p = Path("sectors.json")
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    out = {}
    for sec, coins in (d or {}).items():
        for c in coins or []:
            out[str(c).upper()] = sec
    return out


def hourly_cells(coins_filter=None):
    """{(dow, hour): [ходы в %]} по часовым свечам, время Нью-Йорка."""
    cells = defaultdict(list)
    ncoins = 0
    for f in sorted(HOURLY.glob("*.json")):
        coin = f.stem.upper()
        if coins_filter and coin not in coins_filter:
            continue
        try:
            rows = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if not rows:
            continue
        ncoins += 1
        for r in rows:
            o, c = r.get("o"), r.get("c")
            if not o or not c:
                continue
            t = datetime.fromtimestamp(r["t"] / 1000, tz=timezone.utc).astimezone(NY)
            cells[(t.weekday(), t.hour)].append((c / o - 1) * 100)
    return cells, ncoins


def daily_cells(coins_filter=None):
    cells = defaultdict(list)
    ncoins = 0
    for f in sorted(DAILY.glob("*.json")):
        coin = f.stem.upper()
        if coin.startswith("_") or (coins_filter and coin not in coins_filter):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        oh = d.get("ohlcv") or []
        if not oh:
            continue
        ncoins += 1
        for r in oh:
            o, c = r.get("open"), r.get("close")
            if not o or not c:
                continue
            day = datetime.fromisoformat(r["datetime"][:10]).weekday()
            cells[day].append((c / o - 1) * 100)
    return cells, ncoins


def share(v):
    return (sum(1 for x in v if x > 0) / len(v) * 100) if v else None


def heat(cells, ncoins, title):
    print(f"\n{title} · монет {ncoins} · время Нью-Йорка · доля растущих часов, %")
    print("     " + "".join(f"{h:>4}" for h in range(24)))
    allv = [x for v in cells.values() for x in v]
    base = share(allv) or 50
    for d in range(7):
        line = f"{DOW[d]:4} "
        for h in range(24):
            v = cells.get((d, h), [])
            s = share(v)
            if s is None or len(v) < 30:
                line += "   ·"
            else:
                mark = "+" if s - base >= 3 else "-" if base - s >= 3 else " "
                line += f"{s:3.0f}{mark}"
        print(line)
    print(f"     база {base:.0f}% · «+» выше базы на 3 и больше, «−» ниже; "
          f"«·» меньше 30 свечей")
    # лучшие и худшие ячейки
    ranked = [((d, h), share(v), len(v), st.median(v))
              for (d, h), v in cells.items() if len(v) >= 30]
    ranked.sort(key=lambda x: -(x[1] or 0))
    print("\n  сильнее всего растут (день · час NY · доля · n · медиана хода):")
    for (d, h), s, n, med in ranked[:6]:
        print(f"    {DOW[d]} {h:02d}:00  {s:4.0f}%  n={n:<5} {med:+.2f}%")
    print("  слабее всего:")
    for (d, h), s, n, med in ranked[-6:]:
        print(f"    {DOW[d]} {h:02d}:00  {s:4.0f}%  n={n:<5} {med:+.2f}%")
    # по столам
    desks = {"Азия 20-04": range(20, 24), "Азия 00-04": range(0, 4),
             "Европа 03-08": range(3, 8), "Нью-Йорк 08-12": range(8, 12),
             "Нью-Йорк 12-16": range(12, 16), "Вечер 16-20": range(16, 20)}
    print("\n  по столам (доля растущих часов):")
    for name, hrs in desks.items():
        v = [x for (d, h), vv in cells.items() if h in hrs for x in vv]
        if v:
            print(f"    {name:16} {share(v):4.0f}%  n={len(v)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sector", default=None)
    ap.add_argument("--daily", action="store_true")
    a = ap.parse_args()
    sectors = load_sectors()

    if a.daily or not any(HOURLY.glob("*.json")):
        cells, n = daily_cells()
        if not cells:
            print("нет ни hourly/, ни cq_v2/ — считать не из чего")
            return 1
        print(f"ДНИ НЕДЕЛИ · монет {n} · свеча UTC · доля растущих дней")
        for d in range(7):
            v = cells.get(d, [])
            if v:
                print(f"  {DOW[d]}  {share(v):4.0f}%  n={len(v):<5} "
                      f"медиана {st.median(v):+.1f}%")
        if not any(HOURLY.glob("*.json")):
            print("\nчасов нет: сначала python3 coinglass_hourly.py")
        return 0

    if a.sector:
        want = {c for c, s in sectors.items() if s == a.sector}
        cells, n = hourly_cells(want)
        heat(cells, n, f"СЕКТОР {a.sector.upper()}")
        return 0

    cells, n = hourly_cells()
    heat(cells, n, "ВСЕ МОНЕТЫ")
    if sectors:
        by = defaultdict(set)
        for c, s in sectors.items():
            by[s].add(c)
        for sec, want in sorted(by.items()):
            cells, n = hourly_cells(want)
            if n >= 3:
                heat(cells, n, f"СЕКТОР {sec.upper()}")
            else:
                print(f"\nсектор {sec}: монет {n} — мало, пропуск")
    else:
        print("\nsectors.json нет — без разбивки по секторам")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
