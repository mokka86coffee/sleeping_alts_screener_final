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
        if coins_filter:
            if coin not in coins_filter:
                continue
        elif coin == "BTC":                  # в общей карте альты без BTC
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
    # ГРУППЫ ДНЕЙ (владелец, 02.09): объединять выходные, понедельник и
    # пятницу с серединой недели нельзя — это разные рынки. Понедельник
    # открывает неделю, пятница закрывает, выходные без столов.
    # Семь дней ОТДЕЛЬНО, у каждого свои 24 часа (владелец, 02.09):
    # середину недели объединять нельзя — среда и четверг это разные
    # дни, как показал биткоин.
    NAMES = ("ПОНЕДЕЛЬНИК", "ВТОРНИК", "СРЕДА", "ЧЕТВЕРГ", "ПЯТНИЦА",
             "СУББОТА", "ВОСКРЕСЕНЬЕ")
    GROUPS = tuple((NAMES[d], (d,)) for d in range(7))
    # per (group, hour): {H: [(ширина, медиана)] по дням}
    per_hour = {g: {h: dd(list) for h in range(24)} for g, _ in GROUPS}
    gof = {d: g for g, days in GROUPS for d in days}
    # и то же по КАЖДОМУ дню недели — для итога по дням
    per_dow = {dw: {h: dd(list) for h in range(24)} for dw in range(7)}
    # дневные свечи по Нью-Йорку: (дата) → {монета: (open 00:00, close 23:00)}
    day_oc = dd(dict)
    STEP = 3600 * 1000
    for t in ts:
        ny = datetime.fromtimestamp(t / 1000, tz=timezone.utc).astimezone(NY)
        g = gof[ny.weekday()]
        if ny.hour == 0:
            for coin, m in series.items():
                a_ = m.get(t); b_ = m.get(t + 23 * STEP)
                if a_ and b_:
                    day_oc[ny.date()][coin] = (a_["o"], b_["c"])
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
            need = 1 if (coins_filter and len(coins_filter) < 3) else 3
            if tot >= need:
                rec = (ups / tot * 100, st.median(rets))
                per_hour[g][ny.hour][H].append(rec)
                per_dow[ny.weekday()][ny.hour][H].append(rec)
    LON = 5; MSK = 7                              # летний сдвиг
    print(f"\nТОЧКА ВХОДА · монет {len(series)} · вход в начале часа · время Нью-Йорка")
    print("в ячейке: доля дней, когда через N ч БОЛЬШИНСТВО монет в плюсе · медиана хода")
    RULES = (("час после откр. NY (10-11)", (10, 11)),
             ("открытие Азии (20-21)", (20, 21)),
             ("закрытие Азии = откр. Лондона (03-04)", (3, 4)),
             ("закрытие NY (16-17)", (16, 17)))
    for gname, _days in GROUPS:
        ph = per_hour[gname]
        n_any = max((len(ph[h][24]) for h in range(24)), default=0)
        print(f"\n── {gname} · дней {n_any} ──")
        print(f"{'NY':>5}{'Лон':>4}{'Мск':>4}{'+4ч':>7}{'ход':>7}{'+24ч':>7}{'ход':>7}")
        best = []
        for h in range(24):
            line = f"{h:02d}:00{(h+LON)%24:4d}{(h+MSK)%24:4d}"
            for H in (4, 24):
                v = ph[h][H]
                if not v:
                    line += f"{'·':>7}{'':>7}"; continue
                frac = sum(1 for b_, _ in v if b_ > 50) / len(v) * 100
                med = st.median(m for _, m in v)
                line += f"{frac:6.0f}%{med:+6.2f}"
                if H == 24:
                    best.append((frac, med, h))
            print(line)
        if best:
            best.sort(reverse=True)
            print("   лучшие на сутки: " + " · ".join(
                f"{h:02d}:00 NY {f_:.0f}% {m:+.2f}" for f_, m, h in best[:3]))
            print("   худшие на сутки: " + " · ".join(
                f"{h:02d}:00 NY {f_:.0f}% {m:+.2f}" for f_, m, h in best[-3:]))

    # ── ИТОГ ПО ДНЯМ НЕДЕЛИ (владелец, 02.09) ──
    # Дневная свеча по Нью-Йорку: открытие 00:00, закрытие 23:00. По
    # каждой дате — ширина (доля монет в плюсе за день). Дальше по дню
    # недели: сколько дней, в скольких росло большинство, средняя
    # ширина, медиана хода. И лучший/худший час входа этого дня на
    # суточном горизонте.
    by_dow = dd(list)
    for date, oc in day_oc.items():
        need = 1 if (coins_filter and len(coins_filter) < 3) else 3
        if len(oc) < need:
            continue
        rets = [(c / o - 1) * 100 for o, c in oc.values() if o]
        up = sum(1 for r in rets if r > 0) / len(rets) * 100
        by_dow[date.weekday()].append((up, st.median(rets)))
    print(f"\n══ ИТОГ ПО ДНЯМ НЕДЕЛИ · день по Нью-Йорку 00:00→23:00 ══")
    print(f"{'день':5}{'дней':>6}{'рост у большинства':>20}{'ширина':>9}"
          f"{'медиана':>9}   лучший вход (сутки)   худший вход")
    for dw in range(7):
        v = by_dow.get(dw, [])
        if not v:
            print(f"{DOW[dw]:5}{'—':>6}"); continue
        frac = sum(1 for u, _ in v if u > 50) / len(v) * 100
        width = sum(u for u, _ in v) / len(v)
        med = st.median(m for _, m in v)
        hrs = []
        for h in range(24):
            vv = per_dow[dw][h][24]
            if len(vv) >= 4:
                f_ = sum(1 for b_, _ in vv if b_ > 50) / len(vv) * 100
                hrs.append((f_, st.median(m for _, m in vv), h))
        if hrs:
            hrs.sort(reverse=True)
            bf, bm, bh = hrs[0]; wf, wm, wh = hrs[-1]
            tail = (f"   {bh:02d}:00 {bf:.0f}% {bm:+.2f}      "
                    f"{wh:02d}:00 {wf:.0f}% {wm:+.2f}")
        else:
            tail = ""
        print(f"{DOW[dw]:5}{len(v):>6}{frac:>19.0f}%{width:>8.0f}%{med:>+8.2f}%{tail}")
    print("  «рост у большинства» — доля дней, когда больше половины монет закрылись выше открытия")
    print("  «ширина» — средняя доля монет в плюсе за день")


def btc_regime(hours: int = 12, thr: float = 1.0) -> dict:
    """{t: 'up'|'down'|'flat'} по ходу биткоина за прошлые `hours` часов.

    Владелец, 02.09: статистику по альтам вести отдельно на флэте
    биткоина и отдельно на его росте и спаде — расписание альтов может
    зависеть от того, что делает биткоин. Порог thr в процентах.
    """
    f = HOURLY / "btc.json"
    if not f.exists():
        return {}
    try:
        rows = json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    m = {r["t"]: r["c"] for r in rows if r.get("c")}
    STEP = 3600 * 1000
    out = {}
    for t, c in m.items():
        p = m.get(t - hours * STEP)
        if not p:
            continue
        ch = (c / p - 1) * 100
        out[t] = "up" if ch > thr else "down" if ch < -thr else "flat"
    return out


REG_NAME = {"flat": "БИТКОИН ВО ФЛЭТЕ", "up": "БИТКОИН РАСТЁТ",
            "down": "БИТКОИН ПАДАЕТ"}


def turns_table(coins_filter=None, by_regime=False):
    """ГДЕ ДЕНЬ РАЗВОРАЧИВАЕТСЯ (владелец, 02.09): в какой час всё
    начинает расти и в какой начинает падать.

    Мера прямая: по каждой монете и каждому дню (Нью-Йорк 00:00→23:00)
    берём час, где цена была НИЖЕ всего — с него начинается рост, — и
    час, где ВЫШЕ всего — с него начинается падение. Дальше по каждому
    дню недели: в какой час минимумы и максимумы попадают чаще всего.
    Число в ячейке — доля дней, когда у большинства монет минимум (или
    максимум) пришёлся на этот час. Равномерно было бы ~4% на час.
    """
    from collections import defaultdict as dd
    series = {}
    for f in sorted(HOURLY.glob("*.json")):
        coin = f.stem.upper()
        if coins_filter:
            if coin not in coins_filter:
                continue
        elif coin == "BTC":
            continue
        try:
            rows = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if rows:
            series[coin] = {r["t"]: r for r in rows if r.get("l") and r.get("h")}
    if not series:
        print("нет часов в hourly/"); return
    # ЛОКАЛЬНЫЕ РАЗВОРОТЫ, а не минимум дня (правка 02.09 по первому
    # прогону). Резать по полуночи Нью-Йорка нельзя: ход, идущий через
    # границу, оставляет минимум на краю, и полночь набирала 9% —
    # ложно. Теперь час считается ДНОМ, если его low ниже всех в окне
    # ±W часов, и ПИКОМ, если high выше всех. Границ суток нет, день
    # недели — по часу самого разворота.
    W = 6
    STEP = 3600 * 1000
    reg = btc_regime() if by_regime else {}
    turns = []           # (weekday, hour, kind, regime)
    for coin, m in series.items():
        ts_c = sorted(m)
        lows = [m[t]["l"] for t in ts_c]
        highs = [m[t]["h"] for t in ts_c]
        for i_, t in enumerate(ts_c):
            if i_ < W or i_ + W >= len(ts_c):
                continue
            # окно должно быть непрерывным по времени
            if ts_c[i_ + W] - ts_c[i_ - W] != 2 * W * STEP:
                continue
            ny = datetime.fromtimestamp(t / 1000, tz=timezone.utc).astimezone(NY)
            win_l = lows[i_ - W:i_ + W + 1]
            win_h = highs[i_ - W:i_ + W + 1]
            # при ничьей разворот — первый из равных, иначе соседние
            # свечи с общим краем гасят друг друга
            rg = reg.get(t, "all") if by_regime else "all"
            if lows[i_] == min(win_l) and win_l.index(lows[i_]) == W:
                turns.append((ny.weekday(), ny.hour, "lo", rg))
            if highs[i_] == max(win_h) and win_h.index(highs[i_]) == W:
                turns.append((ny.weekday(), ny.hour, "hi", rg))
    # по дню недели: распределение часов разворотов
    NAMES = ("ПОНЕДЕЛЬНИК", "ВТОРНИК", "СРЕДА", "ЧЕТВЕРГ", "ПЯТНИЦА",
             "СУББОТА", "ВОСКРЕСЕНЬЕ")
    LON = 5; MSK = 7
    print(f"\nГДЕ ХОД РАЗВОРАЧИВАЕТСЯ · монет {len(series)} · окно ±{W} ч · время Нью-Йорка")
    print("«дно» — доля разворотов вверх в этот час: с него начинается рост")
    print("«пик» — доля разворотов вниз. ровно было бы 4% на час")

    def block(title, sel):
        lo = dd(int); hi = dd(int)
        for dw, h, k, _rg in sel:
            (lo if k == "lo" else hi)[h] += 1
        nlo, nhi = sum(lo.values()), sum(hi.values())
        if not nlo or not nhi:
            return
        print(f"\n── {title} · разворотов вверх {nlo}, вниз {nhi} ──")
        print("час NY " + "".join(f"{h:>4}" for h in range(24)))
        print("дно  % " + "".join(f"{lo[h]/nlo*100:4.0f}" for h in range(24)))
        print("пик  % " + "".join(f"{hi[h]/nhi*100:4.0f}" for h in range(24)))
        top_lo = sorted(range(24), key=lambda h: -lo[h])[:3]
        top_hi = sorted(range(24), key=lambda h: -hi[h])[:3]
        print("   рост начинается чаще всего: " + " · ".join(
            f"{h:02d} NY ({(h+LON)%24:02d} Лон, {(h+MSK)%24:02d} Мск) {lo[h]/nlo*100:.0f}%"
            for h in top_lo))
        print("   падение начинается чаще:    " + " · ".join(
            f"{h:02d} NY ({(h+LON)%24:02d} Лон, {(h+MSK)%24:02d} Мск) {hi[h]/nhi*100:.0f}%"
            for h in top_hi))

    if by_regime:
        # три среза по режиму биткоина; внутри каждого — вся неделя,
        # по дням недели уже слишком тонко
        for rg in ("flat", "up", "down"):
            sel = [x for x in turns if x[3] == rg]
            block(REG_NAME[rg] + " · вся неделя", sel)
        print("\n  режим: ход биткоина за прошлые 12 ч, порог ±1%")
        return
    for dw in range(7):
        block(NAMES[dw], [x for x in turns if x[0] == dw])
    block("ВСЯ НЕДЕЛЯ", turns)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sector", default=None)
    ap.add_argument("--daily", action="store_true")
    ap.add_argument("--entry", action="store_true",
                    help="точка входа: что через 4/8/24 ч после входа в час")
    ap.add_argument("--only", nargs="*", default=None,
                    help="только эти монеты — проверить быстро, не ждать всех")
    ap.add_argument("--turns", action="store_true",
                    help="в какой час день делает дно (рост) и пик (падение)")
    ap.add_argument("--regime", action="store_true",
                    help="разбить по режиму биткоина: флэт / рост / спад")
    a = ap.parse_args()
    if a.turns:
        want = {c.upper() for c in a.only} if a.only else None
        turns_table(want, by_regime=a.regime)
        return 0
    if a.entry:
        want = None
        if a.only:
            want = {c.upper() for c in a.only}
        elif a.sector:
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
