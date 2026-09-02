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

ЧЕСТНОСТЬ (правка 02.09 после первого прогона). Семьдесят восемь монет
при корреляции 0.87 — это ОДНА монета, не семьдесят восемь. Считать
монето-часы значит надувать выборку: ячейка «пятница 14:00 — 26%» на
первом прогоне была ОДНОЙ пятницей (28.08, Джексон-Хоул), когда упало
всё разом. Поэтому мера — ПО НЕДЕЛЯМ: для каждой ячейки (день, час)
берём каждую неделю отдельно и спрашиваем, росло ли в этот час
БОЛЬШИНСТВО монет. Доля таких недель и есть число; n — недели, а не
свечи. При 26 неделях стандартная ошибка ~10%, значит выделять стоит
только разрыв от 20 пунктов и больше.
Вторая мера — ШИРИНА: средняя доля монет, выросших в этот час, по
неделям. Она мягче и показывает не «чаще ли», а «насколько дружно».

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
        if sec.startswith("_") or not isinstance(coins, list):
            continue
        for c in coins:
            out[str(c).upper()] = sec
    return out


def weekly_cells(coins_filter=None):
    """{(dow, hour): [доля выросших монет в этот час, по неделям]}.

    Ключ недели — понедельник по Нью-Йорку. В ячейке столько чисел,
    сколько недель в данных; каждое — ширина роста в этот час той
    недели. Корреляция монет здесь не надувает n.
    """
    acc = defaultdict(lambda: defaultdict(lambda: [0, 0]))   # (dow,h) → week → [up, all]
    ncoins = 0
    for f in sorted(HOURLY.glob("*.json")):
        coin = f.stem.upper()
        if coin == "BTC" or (coins_filter and coin not in coins_filter):
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
            wk = (t.date() - __import__("datetime").timedelta(days=t.weekday())).isoformat()
            cell = acc[(t.weekday(), t.hour)][wk]
            cell[1] += 1
            if c > o:
                cell[0] += 1
    cells = {}
    for key, weeks in acc.items():
        cells[key] = [u / n * 100 for u, n in weeks.values() if n >= 3]
    return cells, ncoins


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


def wk_freq(v):
    """Доля недель, когда в этот час росло большинство монет."""
    return (sum(1 for x in v if x > 50) / len(v) * 100) if v else None


def wk_breadth(v):
    """Средняя ширина роста в этот час по неделям."""
    return (sum(v) / len(v)) if v else None


def heat(cells, ncoins, title):
    """Карта по НЕДЕЛЯМ: в ячейке доля недель, когда в этот час росло
    большинство монет. n — число недель. Выделяем от 20 пунктов."""
    nweeks = max((len(v) for v in cells.values()), default=0)
    print(f"\n{title} · монет {ncoins} · недель {nweeks} · время Нью-Йорка")
    print("доля недель, когда в этот час росло БОЛЬШИНСТВО монет, %")
    print("     " + "".join(f"{h:>4}" for h in range(24)))
    allv = [x for v in cells.values() for x in v]
    base = wk_freq(allv) or 50
    for d in range(7):
        line = f"{DOW[d]:4} "
        for h in range(24):
            v = cells.get((d, h), [])
            s = wk_freq(v)
            if s is None or len(v) < 8:
                line += "   ·"
            else:
                mark = "+" if s - base >= 20 else "-" if base - s >= 20 else " "
                line += f"{s:3.0f}{mark}"
        print(line)
    print(f"     база {base:.0f}% · «+»/«−» от базы на 20 пунктов; "
          f"«·» меньше 8 недель")
    ranked = [((d, h), wk_freq(v), len(v), wk_breadth(v))
              for (d, h), v in cells.items() if len(v) >= 8]
    ranked.sort(key=lambda x: -(x[1] or 0))
    print("\n  чаще всего растёт (день · час NY · недель с ростом · n · средняя ширина):")
    for (d, h), s, n, br in ranked[:6]:
        print(f"    {DOW[d]} {h:02d}:00  {s:4.0f}%  n={n:<3} ширина {br:4.0f}%")
    print("  реже всего:")
    for (d, h), s, n, br in ranked[-6:]:
        print(f"    {DOW[d]} {h:02d}:00  {s:4.0f}%  n={n:<3} ширина {br:4.0f}%")
    desks = {"Азия 20-04": range(20, 24), "Азия 00-04": range(0, 4),
             "Европа 03-08": range(3, 8), "Нью-Йорк 08-12": range(8, 12),
             "Нью-Йорк 12-16": range(12, 16), "Вечер 16-20": range(16, 20)}
    print("\n  по столам (доля недель с ростом большинства · средняя ширина):")
    for name, hrs in desks.items():
        v = [x for (d, h), vv in cells.items() if h in hrs for x in vv]
        if v:
            print(f"    {name:16} {wk_freq(v):4.0f}%   ширина {wk_breadth(v):4.0f}%  "
                  f"n={len(v)}")


def entry_table(coins_filter=None, horizons=(4, 8, 24)):
    """ТОЧКА ВХОДА: что происходит ПОСЛЕ входа в данный час.

    Расхожее правило (владелец, 02.09): лучшие входы — через час после
    открытия Нью-Йорка (10:30) и на открытии Азии (20-21 NY). Проверяем
    не «растёт ли этот час», а «что стало с ценой через 4, 8 и 24 часа
    после входа в этот час». Для каждого часа — медиана хода вперёд по
    всем входам и доля входов в плюсе.
    Корреляция: считаем по дням, а не по монето-часам — каждый день
    даёт одно наблюдение «ширина плюса через N часов» (доля монет в
    плюсе). n — дни, около 180 при полной истории.
    """
    from collections import defaultdict as dd
    series = {}
    for f in sorted(HOURLY.glob("*.json")):
        coin = f.stem.upper()
        if coin == "BTC" or (coins_filter and coin not in coins_filter):
            continue
        try:
            rows = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if rows:
            series[coin] = {r["t"]: r for r in rows if r.get("o")}
    if not series:
        return
    ts = sorted(set().union(*[set(v) for v in series.values()]))
    # per (day, hour): {h: [breadth over coins]}
    per_hour = {h: dd(list) for h in range(24)}
    STEP = 3600 * 1000
    for t in ts:
        ny = datetime.fromtimestamp(t / 1000, tz=timezone.utc).astimezone(NY)
        for H in horizons:
            ups = tot = 0; rets = []
            for coin, m in series.items():
                a, b = m.get(t), m.get(t + H * STEP)
                if not a or not b:
                    continue
                r = (b["c"] / a["o"] - 1) * 100
                rets.append(r); tot += 1
                if r > 0:
                    ups += 1
            if tot >= 3:
                per_hour[ny.hour][H].append((ups / tot * 100, st.median(rets)))
    LON = 5; MSK = 7                              # летний сдвиг
    print(f"\nТОЧКА ВХОДА · монет {len(series)} · вход в начале часа, время Нью-Йорка")
    print("доля дней, когда через N ч БОЛЬШИНСТВО монет в плюсе · медиана хода")
    hdr = f"{'NY':>4}{'Лон':>5}{'Мск':>5}"
    for H in horizons:
        hdr += f"{'+'+str(H)+'ч':>8}{'ход':>7}"
    print(hdr + "    n")
    best = []
    for h in range(24):
        line = f"{h:02d}:00{(h+LON)%24:5d}{(h+MSK)%24:5d}"
        n = 0
        for H in horizons:
            v = per_hour[h][H]
            if not v:
                line += f"{'·':>8}{'':>7}"; continue
            n = len(v)
            frac = sum(1 for b, _ in v if b > 50) / n * 100
            med = st.median(m for _, m in v)
            line += f"{frac:7.0f}%{med:+6.2f}%"
            if H == 24:
                best.append((frac, med, h))
        print(line + f"{n:5d}")
    best.sort(reverse=True)
    print("\n  лучшие входы по 24 часам (доля дней с плюсом · медиана хода · час NY/Лон/Мск):")
    for frac, med, h in best[:5]:
        print(f"    {frac:3.0f}%  {med:+.2f}%   {h:02d}:00 NY · {(h+LON)%24:02d}:00 Лон · {(h+MSK)%24:02d}:00 Мск")
    print("  худшие:")
    for frac, med, h in best[-5:]:
        print(f"    {frac:3.0f}%  {med:+.2f}%   {h:02d}:00 NY · {(h+LON)%24:02d}:00 Лон · {(h+MSK)%24:02d}:00 Мск")
    print("\n  проверка расхожего правила:")
    # Четыре расхожих правила. Закрытие Азии и открытие Лондона —
    # одни и те же часы (03-04 NY): Токио закрывает, Европа открывает.
    # Владелец: «закрытие Азии почти всегда слив» — проверяем ходом
    # ВПЕРЁД от этого часа: если слив, вход туда даст худшие +4 ч.
    for name, hs in (("час после открытия NY (10-11)", (10, 11)),
                     ("открытие Азии (20-21 NY)", (20, 21)),
                     ("закрытие Азии = откр. Лондона (03-04)", (3, 4)),
                     ("закрытие NY (16-17)", (16, 17))):
        for H in (4, 24):
            v = [x for h in hs for x in per_hour[h][H]]
            if v:
                frac = sum(1 for b, _ in v if b > 50) / len(v) * 100
                print(f"    {name:38} +{H:2d} ч: в плюсе {frac:3.0f}% дней, "
                      f"медиана {st.median(m for _, m in v):+.2f}%  n={len(v)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sector", default=None)
    ap.add_argument("--daily", action="store_true")
    ap.add_argument("--entry", action="store_true",
                    help="точка входа: что через 4/8/24 ч после входа в час")
    a = ap.parse_args()
    if a.entry:
        want = None
        if a.sector:
            want = {c for c, s_ in sectors.items() if s_ == a.sector}
        entry_table(want)
        return 0
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
        cells, n = weekly_cells(want)
        heat(cells, n, f"СЕКТОР {a.sector.upper()}")
        return 0

    cells, n = weekly_cells()
    heat(cells, n, "ВСЕ МОНЕТЫ")
    if sectors:
        by = defaultdict(set)
        for c, s in sectors.items():
            by[s].add(c)
        for sec, want in sorted(by.items()):
            if sec.startswith("_"):            # служебные ключи
                continue
            cells, n = weekly_cells(want)
            if n >= 3:
                heat(cells, n, f"СЕКТОР {sec.upper()}")
            else:
                print(f"\nсектор {sec}: монет {n} — мало, пропуск")
    else:
        print("\nsectors.json нет — без разбивки по секторам")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
