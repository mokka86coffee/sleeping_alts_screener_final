#!/usr/bin/env python3
"""СВОДКА МИКРОКАПОВ: когда все разом сливают и когда все разом растут.

Задача владельца (02.09): за два года торговли замечено, что сливает в
одно время, покупает в другое; биткоин чаще растёт в понедельник-среду
и всё идёт за ним; к закрытию Нью-Йорка слив почти всегда; в пятницу к
закрытию рост, перед субботой слив; вся альта привязана к биткоину.
Нужна своя сводка по МИКРОКАПАМ (BLESS, ONG, PLAY и подобные — не
NEAR/SOL/ETH), а потом связать её с биткоином.

МЕРА — ШИРИНА: доля микрокапов, выросших за этот час. Не ход одной
монеты, а сколько монет из всех пошли вверх. Это и есть «все разом».
Ячейка (день недели, час) — средняя ширина по всем неделям; при 26
неделях стандартная ошибка около 3-4 пунктов, выделяем от 10.

БИТКОИН отдельно: его часовой ход и связь с шириной альтов —
корреляция и доля часов, где направление совпало.

    python3 alts_schedule.py                # сводка + проверка наблюдений
    python3 alts_schedule.py --majors ETH SOL NEAR ARB   # кого исключить
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
MAJORS = {"BTC", "ETH", "SOL", "NEAR", "ARB", "HYPE", "WLD", "SUI", "APT",
          "BNB", "XRP", "ADA", "DOGE", "TRX", "AVAX", "LINK", "TON", "DOT"}
STEP = 3600 * 1000


def load(coin):
    f = HOURLY / f"{coin.lower()}.json"
    if not f.exists():
        return {}
    try:
        rows = json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return {r["t"]: r for r in rows if r.get("o") and r.get("c")}


def btc_regime(btc: dict, hours: int, thr: float) -> dict:
    """{t: 'flat'|'up'|'down'} по ходу биткоина за прошлые `hours` часов.

    ДВЕ СВОДКИ (владелец, 02.09): альты на флэте биткоина и альты на его
    движении. На флэте виден ИХ СОБСТВЕННЫЙ ритм — биткоин не мешает.
    На движении видно, как они ходят за ним. Флэт — ход биткоина за
    окно в пределах ±thr процентов.
    """
    out = {}
    for t, r in btc.items():
        p = btc.get(t - hours * STEP)
        if not p:
            continue
        ch = (r["c"] / p["c"] - 1) * 100
        out[t] = "up" if ch > thr else "down" if ch < -thr else "flat"
    return out


REG = (("flat", "БИТКОИН ВО ФЛЭТЕ — СВОЙ РИТМ АЛЬТОВ"),
       ("up", "БИТКОИН РАСТЁТ"),
       ("down", "БИТКОИН ПАДАЕТ"))


def heat(cells, base, title, min_n=8):
    nweeks = max((len(v) for v in cells.values()), default=0)
    print(f"\n{'═' * 70}\n{title} · ячеек с данными до {nweeks} недель")
    print("     " + "".join(f"{h:>4}" for h in range(24)))
    for d in range(7):
        line = f"{DOW[d]:4} "
        for h in range(24):
            v = cells.get((d, h), [])
            if len(v) < min_n:
                line += "   ·"; continue
            mean = st.mean(v)
            mk = "▲" if mean - base >= 10 else "▼" if base - mean >= 10 else " "
            line += f"{mean:3.0f}{mk}"
        print(line)
    ranked = sorted(((st.mean(v), d, h, len(v)) for (d, h), v in cells.items()
                     if len(v) >= min_n), key=lambda x: x[0])
    if not ranked:
        print("  мало данных"); return
    print("  СЛИВАЮТ РАЗОМ:")
    for mean, d, h, n in ranked[:6]:
        print(f"    {DOW[d]} {h:02d}:00 NY · {(h+5)%24:02d} Лон · {(h+7)%24:02d} Мск"
              f"   ширина {mean:.0f}%  недель {n}")
    print("  РАСТУТ РАЗОМ:")
    for mean, d, h, n in ranked[-6:][::-1]:
        print(f"    {DOW[d]} {h:02d}:00 NY · {(h+5)%24:02d} Лон · {(h+7)%24:02d} Мск"
              f"   ширина {mean:.0f}%  недель {n}")
    desks = (("Азия ночь 20-00", range(20, 24)), ("Азия утро 00-04", range(0, 4)),
             ("Лондон 03-08", range(3, 8)), ("NY утро 08-12", range(8, 12)),
             ("NY день 12-16", range(12, 16)), ("NY закрытие 15-17", range(15, 18)),
             ("вечер 17-20", range(17, 20)))
    print("  ПО СТОЛАМ · будни / выходные:")
    for name, hrs in desks:
        wd = [x for (d, h), v in cells.items() if h in hrs and d < 5 for x in v]
        we = [x for (d, h), v in cells.items() if h in hrs and d >= 5 for x in v]
        if wd and we:
            print(f"    {name:20} будни {st.mean(wd):4.0f}%   выходные {st.mean(we):4.0f}%")


def runs_table(alts, btc, reg, min_pct, w, by_regime,
               state="all", state_days=7, state_pct=10.0):
    """ПРОБЕГИ (владелец, 02.09, BLESS 30.08): ход с 17:00 до 21:45 +13%
    за пять часов — вот что ловить. Не свеча, не фиксированное окно, а
    весь пробег от локального дна до локальной вершины.

    Дно — час, чей low ниже ±w соседних; вершина — high выше ±w. Пробег
    вверх = дно → ближайшая вершина после него, вниз = вершина → дно.
    Берём пробеги от min_pct процентов. У каждого — час старта, размер,
    длительность. Сводка: когда стартуют, какого размера.
    """
    NAMES = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
    ups, downs = [], []       # (dow, hour, pct, dur_h, regime)
    for coin, m in alts.items():
        ts_c = sorted(m)
        lows = [m[t]["l"] for t in ts_c]; highs = [m[t]["h"] for t in ts_c]
        ext = []              # (i, 'lo'|'hi')
        for i in range(w, len(ts_c) - w):
            if ts_c[i + w] - ts_c[i - w] != 2 * w * STEP:
                continue
            wl = lows[i - w:i + w + 1]; wh = highs[i - w:i + w + 1]
            if lows[i] == min(wl) and wl.index(lows[i]) == w:
                ext.append((i, "lo"))
            if highs[i] == max(wh) and wh.index(highs[i]) == w:
                ext.append((i, "hi"))
        ext.sort()
        closes = {t: m[t]["c"] for t in ts_c}
        for (i0, k0), (i1, k1) in zip(ext, ext[1:]):
            if k0 == k1:
                continue
            t0 = ts_c[i0]
            # СОСТОЯНИЕ МОНЕТЫ в момент старта (владелец, 02.09): в
            # семидесяти пяти монетах половина полгода стекала, и их
            # пробеги — шум умирающих. Считаем только тех, кто в ходу:
            # где монета была за state_days дней до старта.
            if state != "all":
                prev = closes.get(t0 - state_days * 24 * STEP)
                if not prev:
                    continue
                ch = (closes[t0] / prev - 1) * 100
                st_ = "up" if ch >= state_pct else "down" if ch <= -state_pct else "flat"
                if st_ != state:
                    continue
            ny = datetime.fromtimestamp(t0 / 1000, tz=timezone.utc).astimezone(NY)
            rg = reg.get(t0, "?") if by_regime else "all"
            dur = (ts_c[i1] - t0) / STEP
            if k0 == "lo":
                pct = (highs[i1] / lows[i0] - 1) * 100
                if pct >= min_pct:
                    ups.append((ny.weekday(), ny.hour, pct, dur, rg))
            else:
                pct = (1 - lows[i1] / highs[i0]) * 100
                if pct >= min_pct:
                    downs.append((ny.weekday(), ny.hour, pct, dur, rg))

    def block(title, U, D):
        if not U or not D:
            print(f"\n{title}: мало пробегов"); return
        print(f"\n{'═' * 70}\n{title} · пробегов вверх {len(U)}, вниз {len(D)} "
              f"· медиана размера ↑{st.median(x[2] for x in U):.1f}% "
              f"↓{st.median(x[2] for x in D):.1f}% · длительность ↑{st.median(x[3] for x in U):.0f}ч "
              f"↓{st.median(x[3] for x in D):.0f}ч")
        # карта стартов: доля всех пробегов, стартовавших в (день, час)
        for kind, R in (("СТАРТЫ ВВЕРХ", U), ("СТАРТЫ ВНИЗ", D)):
            n = len(R)
            grid = defaultdict(int)
            for dw, h, *_ in R:
                grid[(dw, h)] += 1
            flat = n / 168 * 100 / n * 100 if n else 0   # доля при равномерности
            print(f"  {kind} · % от всех, ровно было бы {100/168:.1f} на ячейку")
            print("     " + "".join(f"{h:>4}" for h in range(24)))
            for dw in range(7):
                line = f"{NAMES[dw]:4} "
                for h in range(24):
                    v = grid[(dw, h)] / n * 100
                    mk = "▲" if v >= 1.6 else " "
                    line += f"{v:3.0f}{mk}" if v else "   ·"
                print(line)
            top = sorted(grid.items(), key=lambda x: -x[1])[:6]
            print("   чаще всего: " + " · ".join(
                f"{NAMES[dw]} {h:02d} NY ({(h+5)%24:02d} Лон, {(h+7)%24:02d} Мск) {c/n*100:.1f}%"
                for (dw, h), c in top))
        # по часу суток без дня — плотнее
        for kind, R in (("↑ по часу суток", U), ("↓ по часу суток", D)):
            n = len(R); hh = defaultdict(int)
            for _, h, *_ in R:
                hh[h] += 1
            print(f"  {kind}: " + " ".join(f"{h:02d}:{hh[h]/n*100:2.0f}" for h in range(24)))

    if by_regime:
        for key, title in REG:
            block(title, [x for x in ups if x[4] == key], [x for x in downs if x[4] == key])
    else:
        block("ВСЯ ВЫБОРКА", ups, downs)


def sync_table(alts, btc, reg, min_pct, w, by_regime, need_up, need_dn, tol):
    """СИНХРОННЫЕ СТАРТЫ (владелец, 02.09). Событие роста — не меньше
    need_up монет стартовали пробег вверх в один час, ±tol ч. Событие
    падения — не меньше need_dn монет стартовали вниз. Одно событие —
    одна отметка, сколько бы монет в него ни вошло.

    Это снимает обе болезни разом: одиночная монета не считается вовсе,
    а семьдесят коррелированных монет в один час дают ОДНО событие, а
    не семьдесят. Порог на падение выше, потому что падают дружнее.
    """
    NAMES = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
    starts_up = defaultdict(set); starts_dn = defaultdict(set)   # t → {монеты}
    size_up = defaultdict(list); size_dn = defaultdict(list)
    for coin, m in alts.items():
        ts_c = sorted(m)
        lows = [m[t]["l"] for t in ts_c]; highs = [m[t]["h"] for t in ts_c]
        ext = []
        for i in range(w, len(ts_c) - w):
            if ts_c[i + w] - ts_c[i - w] != 2 * w * STEP:
                continue
            wl = lows[i - w:i + w + 1]; wh = highs[i - w:i + w + 1]
            if lows[i] == min(wl) and wl.index(lows[i]) == w:
                ext.append((i, "lo"))
            if highs[i] == max(wh) and wh.index(highs[i]) == w:
                ext.append((i, "hi"))
        ext.sort()
        for (i0, k0), (i1, k1) in zip(ext, ext[1:]):
            if k0 == k1:
                continue
            t0 = ts_c[i0]
            if k0 == "lo":
                pct = (highs[i1] / lows[i0] - 1) * 100
                if pct >= min_pct:
                    starts_up[t0].add(coin); size_up[t0].append(pct)
            else:
                pct = (1 - lows[i1] / highs[i0]) * 100
                if pct >= min_pct:
                    starts_dn[t0].add(coin); size_dn[t0].append(pct)

    def events(starts, sizes, need):
        """Часы, где в окне ±tol набралось need монет. Соседние часы,
        прошедшие порог, склеиваем в одно событие — берём час с
        максимумом монет."""
        ts_all = sorted(set(starts))
        cand = []
        for t in ts_all:
            coins = set()
            for k in range(-tol, tol + 1):
                coins |= starts.get(t + k * STEP, set())
            if len(coins) >= need:
                cand.append((t, len(coins)))
        out = []
        i = 0
        while i < len(cand):
            j = i
            while j + 1 < len(cand) and cand[j + 1][0] - cand[j][0] <= STEP:
                j += 1
            best = max(cand[i:j + 1], key=lambda x: x[1])
            med = st.median(sizes.get(best[0]) or [0])
            out.append((best[0], best[1], med))
            i = j + 1
        return out

    ev_up = events(starts_up, size_up, need_up)
    ev_dn = events(starts_dn, size_dn, need_dn)

    def block(title, U, D):
        print(f"\n{'═' * 70}\n{title} · событий роста {len(U)}, падения {len(D)}")
        if U:
            print(f"   рост: медиана монет в событии {st.median(n for _, n, _ in U):.0f}, "
                  f"медиана размера пробега {st.median(m for _, _, m in U):.1f}%")
        if D:
            print(f"   падение: медиана монет {st.median(n for _, n, _ in D):.0f}, "
                  f"размера {st.median(m for _, _, m in D):.1f}%")
        for kind, E in (("СОБЫТИЯ РОСТА", U), ("СОБЫТИЯ ПАДЕНИЯ", D)):
            if not E:
                continue
            grid = defaultdict(int); hh = defaultdict(int); dd_ = defaultdict(int)
            for t, n, _ in E:
                ny = datetime.fromtimestamp(t / 1000, tz=timezone.utc).astimezone(NY)
                grid[(ny.weekday(), ny.hour)] += 1
                hh[ny.hour] += 1; dd_[ny.weekday()] += 1
            print(f"  {kind} · число событий в ячейке")
            print("     " + "".join(f"{h:>4}" for h in range(24)) + "   всего")
            for dw in range(7):
                line = f"{NAMES[dw]:4} "
                for h in range(24):
                    v = grid[(dw, h)]
                    line += f"{v:4d}" if v else "   ·"
                print(line + f"{dd_[dw]:7d}")
            print("   по часу суток: " + " ".join(f"{h:02d}:{hh[h]:2d}" for h in range(24)))
            top = sorted(grid.items(), key=lambda x: -x[1])[:6]
            print("   чаще всего: " + " · ".join(
                f"{NAMES[dw]} {h:02d} NY ({(h+5)%24:02d} Лон, {(h+7)%24:02d} Мск) ×{c}"
                for (dw, h), c in top))

    if by_regime:
        for key, title in REG:
            U = [e for e in ev_up if reg.get(e[0]) == key]
            D = [e for e in ev_dn if reg.get(e[0]) == key]
            block(title, U, D)
    else:
        block("ВСЯ ВЫБОРКА", ev_up, ev_dn)
    return ev_up, ev_dn


def schedule_json(ev_up, ev_dn, reg, ncoins, path):
    """Сводка для схемы (02.09): часы пампов и сливов на флэте
    биткоина, лучшие дни, счётчики по режимам. Схема читает
    output/schedule.json и рисует панель; нет файла — нет панели."""
    from collections import Counter
    def hours_days(E):
        hh = Counter(); dd_ = Counter()
        for t, _, _ in E:
            ny = datetime.fromtimestamp(t / 1000, tz=timezone.utc).astimezone(NY)
            hh[ny.hour] += 1; dd_[ny.weekday()] += 1
        return hh, dd_
    flat_up = [e for e in ev_up if reg.get(e[0], "flat") == "flat"]
    flat_dn = [e for e in ev_dn if reg.get(e[0], "flat") == "flat"]
    hu, du = hours_days(flat_up); hd, ddn = hours_days(flat_dn)
    mean_u = (sum(hu.values()) / 24) if hu else 1
    mean_d = (sum(hd.values()) / 24) if hd else 1

    def clusters(hs):
        """соседние часы — в отрезки"""
        hs = sorted(hs); out = []
        for h in hs:
            if out and h == out[-1][1] + 1:
                out[-1][1] = h
            else:
                out.append([h, h])
        return out
    pump_h = {h for h in range(24) if hu[h] >= mean_u * 1.35}
    dump_h = {h for h in range(24) if hd[h] >= mean_d * 1.8}
    # СПОРНЫЙ ЧАС (03.09): 21 NY был и в пампах, и в сливе, и виджет
    # показывал «рост ещё 2 ч» за час до слива. Час отдаём тому, у кого
    # он аномальнее относительно СВОЕЙ нормы: слив 16 при норме 5 бьёт
    # памп 18 при норме 13.
    for h in pump_h & dump_h:
        if hd[h] / mean_d >= hu[h] / mean_u:
            pump_h.discard(h)
        else:
            dump_h.discard(h)
    pump = clusters(sorted(pump_h))
    dead = clusters([h for h in range(24) if hu[h] <= mean_u * 0.6 and h not in dump_h])
    dump = clusters(sorted(dump_h))
    reg_cnt = {}
    for key in ("flat", "up", "down"):
        reg_cnt[key] = [sum(1 for e in ev_up if reg.get(e[0], "flat") == key),
                        sum(1 for e in ev_dn if reg.get(e[0], "flat") == key)]
    # старт отскоков на падении биткоина — самый частый час
    dn_up = [e for e in ev_up if reg.get(e[0]) == "down"]
    hdu, _ = hours_days(dn_up)
    bounce_h = max(hdu, key=hdu.get) if hdu else None
    days_rank = [d for d, _ in du.most_common()]
    out = {"at": datetime.now().strftime("%Y-%m-%d"), "coins": ncoins,
           "pump": pump, "pump_main": (max(hu, key=hu.get) if hu else None),
           "pump_main_n": (max(hu.values()) if hu else 0),
           "dead": dead, "dump": dump,
           "dump_main": (max(hd, key=hd.get) if hd else None),
           "dump_main_n": (max(hd.values()) if hd else 0),
           "dump_main_ratio": round(max(hd.values()) / sorted(hd.values())[-2], 1)
                              if len(hd) > 1 else None,
           "days_best": days_rank[:2], "days_up": {str(d): du[d] for d in range(7)},
           "days_dn": {str(d): ddn[d] for d in range(7)},
           "regime": reg_cnt, "bounce_hour": bounce_h}
    Path(path).parent.mkdir(exist_ok=True)
    Path(path).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"\nсводка записана: {path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--majors", nargs="*", default=None,
                    help="кого исключить из микрокапов")
    ap.add_argument("--regime", action="store_true",
                    help="две сводки: альты на флэте BTC и на его движении")
    ap.add_argument("--hours", type=int, default=12,
                    help="окно режима BTC в часах (по умолчанию 12)")
    ap.add_argument("--thr", type=float, default=1.0,
                    help="порог флэта в процентах (по умолчанию ±1)")
    ap.add_argument("--win", type=int, default=3,
                    help="окно хода в часах от начала часа (по умолчанию 3)")
    ap.add_argument("--runs", action="store_true",
                    help="пробеги: от дна до вершины, когда стартуют и какого размера")
    ap.add_argument("--min-pct", type=float, default=5.0,
                    help="минимальный размер пробега, %% (по умолчанию 5)")
    ap.add_argument("--extw", type=int, default=3,
                    help="окно локального экстремума ±ч (по умолчанию 3)")
    ap.add_argument("--state", choices=("all", "up", "down", "flat"), default="all",
                    help="состояние МОНЕТЫ на старте: up — росла за неделю до")
    ap.add_argument("--state-days", type=int, default=7,
                    help="за сколько дней смотреть состояние монеты")
    ap.add_argument("--state-pct", type=float, default=10.0,
                    help="порог состояния, %% (по умолчанию ±10)")
    ap.add_argument("--sync", action="store_true",
                    help="синхронные старты: ≥N монет в один час = событие")
    ap.add_argument("--sync-up", type=int, default=6,
                    help="монет для события роста (по умолчанию 6)")
    ap.add_argument("--sync-down", type=int, default=10,
                    help="монет для события падения (по умолчанию 10)")
    ap.add_argument("--tol", type=int, default=1,
                    help="допуск по часу, ± (по умолчанию 1)")
    ap.add_argument("--json", nargs="?", const="output/schedule.json", default=None,
                    help="записать сводку для схемы (по умолчанию output/schedule.json)")
    a = ap.parse_args()
    WIN = max(1, a.win)
    majors = set(m.upper() for m in a.majors) if a.majors else MAJORS

    alts = {}
    for f in sorted(HOURLY.glob("*.json")):
        c = f.stem.upper()
        if c in majors:
            continue
        m = load(c)
        if len(m) >= 24 * 30:                     # хотя бы месяц
            alts[c] = m
    btc = load("BTC")
    if not alts:
        print("нет микрокапов в hourly/ — сначала backfill_binance.py")
        return 1
    if a.sync:
        reg = btc_regime(btc, a.hours, a.thr) if (a.regime and btc) else {}
        print(f"СИНХРОННЫЕ СТАРТЫ · монет {len(alts)} · пробег от {a.min_pct:.0f}% · "
              f"рост ≥{a.sync_up} монет, падение ≥{a.sync_down} монет, ±{a.tol} ч · "
              f"время Нью-Йорка")
        ev_up, ev_dn = sync_table(alts, btc, reg, a.min_pct, a.extw,
                                  bool(a.regime and btc), a.sync_up, a.sync_down, a.tol)
        if a.json:
            if not reg:
                reg = btc_regime(btc, a.hours, a.thr) if btc else {}
            schedule_json(ev_up, ev_dn, reg, len(alts), a.json)
        return 0
    if a.runs:
        reg = btc_regime(btc, a.hours, a.thr) if (a.regime and btc) else {}
        st_txt = {"all": "все монеты", "up": f"только РАСТУЩИЕ (+{a.state_pct:.0f}% за {a.state_days} дн до старта)",
                  "down": f"только падающие (−{a.state_pct:.0f}% за {a.state_days} дн)",
                  "flat": "только стоящие"}[a.state]
        print(f"ПРОБЕГИ · монет {len(alts)} · порог {a.min_pct:.0f}% · "
              f"экстремум ±{a.extw} ч · {st_txt} · время Нью-Йорка")
        runs_table(alts, btc, reg, a.min_pct, a.extw, bool(a.regime and btc),
                   a.state, a.state_days, a.state_pct)
        return 0

    # ── ширина по ОКНАМ (владелец, 02.09): за час микрокап колеблется в
    # обе стороны, и «выросла или нет» по часу не читается. Берём ход от
    # открытия часа t до закрытия часа t+WIN−1: три часа — уже движение,
    # а не дрожь. Ячейка — час, В КОТОРЫЙ движение началось.
    ts = sorted(set().union(*[set(m) for m in alts.values()]))
    breadth = {}                                   # t → (доля вверх, n)
    for t in ts:
        up = n = 0
        for m in alts.values():
            r = m.get(t); r2 = m.get(t + (WIN - 1) * STEP)
            if not r or not r2:
                continue
            n += 1
            if r2["c"] > r["o"]:
                up += 1
        if n >= max(3, len(alts) // 5):           # хотя бы пятая часть монет
            breadth[t] = (up / n * 100, n)

    if not breadth:
        print(f"монет прошло фильтр: {len(alts)}, но ни в одном часе нет "
              f"минимума монет — проверь, что в hourly/ у альтов есть данные")
        return 1
    cells = defaultdict(list)                      # (dow, h) → [ширина по неделям]
    for t, (b, _) in breadth.items():
        ny = datetime.fromtimestamp(t / 1000, tz=timezone.utc).astimezone(NY)
        cells[(ny.weekday(), ny.hour)].append(b)
    base = st.mean(x for v in cells.values() for x in v)
    span = (max(breadth) - min(breadth)) / 86400000
    print(f"монет {len(alts)} · часов с шириной {len(breadth)} · охват {span:.0f} дней")
    nweeks = max(len(v) for v in cells.values())

    print(f"СВОДКА МИКРОКАПОВ · монет {len(alts)} · недель {nweeks} · "
          f"время Нью-Йорка · окно {WIN} ч")
    print(f"в ячейке — средняя ШИРИНА: доля монет, выросших за {WIN} ч от "
          f"начала этого часа. база {base:.0f}%")
    print("▲ ширина выше базы на 10 и больше (растут разом) · "
          "▼ ниже на 10 (сливают разом)\n")
    print("     " + "".join(f"{h:>4}" for h in range(24)))
    for d in range(7):
        line = f"{DOW[d]:4} "
        for h in range(24):
            v = cells.get((d, h), [])
            if len(v) < 8:
                line += "   ·"; continue
            mean = st.mean(v)
            mk = "▲" if mean - base >= 10 else "▼" if base - mean >= 10 else " "
            line += f"{mean:3.0f}{mk}"
        print(line)

    ranked = sorted(((st.mean(v), d, h, len(v)) for (d, h), v in cells.items()
                     if len(v) >= 8), key=lambda x: x[0])
    print("\n  СЛИВАЮТ РАЗОМ (самая узкая ширина):")
    for mean, d, h, n in ranked[:8]:
        print(f"    {DOW[d]} {h:02d}:00 NY · {(h+5)%24:02d} Лон · {(h+7)%24:02d} Мск"
              f"   ширина {mean:.0f}%  n={n}")
    print("  РАСТУТ РАЗОМ (самая широкая):")
    for mean, d, h, n in ranked[-8:][::-1]:
        print(f"    {DOW[d]} {h:02d}:00 NY · {(h+5)%24:02d} Лон · {(h+7)%24:02d} Мск"
              f"   ширина {mean:.0f}%  n={n}")

    if a.regime and btc:
        reg = btc_regime(btc, a.hours, a.thr)
        cnt = defaultdict(int)
        for t in breadth:
            cnt[reg.get(t, "?")] += 1
        print(f"\nрежим биткоина: ход за {a.hours} ч, флэт в пределах ±{a.thr}% · "
              f"часов: флэт {cnt['flat']}, рост {cnt['up']}, спад {cnt['down']}")
        for key, title in REG:
            rc = defaultdict(list)
            for t, (b, _) in breadth.items():
                if reg.get(t) != key:
                    continue
                ny = datetime.fromtimestamp(t / 1000, tz=timezone.utc).astimezone(NY)
                rc[(ny.weekday(), ny.hour)].append(b)
            allv = [x for v in rc.values() for x in v]
            if not allv:
                continue
            heat(rc, st.mean(allv), f"{title} · база {st.mean(allv):.0f}%", min_n=5)
        print("\n  ЧТЕНИЕ: если на флэте есть свои ▲ и ▼ — это ритм самих альтов;"
              "\n  если ▲▼ появляются только на движении — альты просто идут за BTC.")
        return 0

    # ── по столам ──
    desks = (("Азия ночь 20-00", range(20, 24)), ("Азия утро 00-04", range(0, 4)),
             ("Лондон 03-08", range(3, 8)), ("NY утро 08-12", range(8, 12)),
             ("NY день 12-16", range(12, 16)), ("NY закрытие 15-17", range(15, 18)),
             ("вечер 17-20", range(17, 20)))
    print("\n  ПО СТОЛАМ · средняя ширина, будни / выходные:")
    for name, hrs in desks:
        wd = [x for (d, h), v in cells.items() if h in hrs and d < 5 for x in v]
        we = [x for (d, h), v in cells.items() if h in hrs and d >= 5 for x in v]
        print(f"    {name:20} будни {st.mean(wd):4.0f}%   выходные {st.mean(we):4.0f}%")

    # ── НАБЛЮДЕНИЯ ВЛАДЕЛЬЦА, числом ──
    print("\n══ ПРОВЕРКА НАБЛЮДЕНИЙ ══")

    # 1. биткоин чаще растёт пн-ср, альты за ним
    if btc:
        by_day_btc = defaultdict(list); by_day_alt = defaultdict(list)
        days = defaultdict(list)
        for t, (b, _) in breadth.items():
            ny = datetime.fromtimestamp(t / 1000, tz=timezone.utc).astimezone(NY)
            days[ny.date()].append((ny.hour, t, b))
        for date, hrs in days.items():
            hrs.sort()
            if len(hrs) < 20:
                continue
            t0, t1 = hrs[0][1], hrs[-1][1]
            if t0 in btc and t1 in btc:
                by_day_btc[date.weekday()].append((btc[t1]["c"] / btc[t0]["o"] - 1) * 100)
            by_day_alt[date.weekday()].append(st.mean(b for _, _, b in hrs))
        print("\n1. «Биткоин растёт пн-ср, альты за ним»")
        print(f"   {'день':5}{'BTC дней в плюсе':>18}{'BTC медиана':>13}{'ширина альтов':>15}")
        for d in range(7):
            vb = by_day_btc.get(d, []); va = by_day_alt.get(d, [])
            if vb and va:
                up = sum(1 for x in vb if x > 0) / len(vb) * 100
                print(f"   {DOW[d]:5}{up:>17.0f}%{st.median(vb):>+12.2f}%{st.mean(va):>14.0f}%")

    # 2. слив к закрытию NY
    print("\n2. «К закрытию Нью-Йорка слив почти всегда» · ширина в 15-17 NY:")
    for d in range(7):
        v = [x for h in (15, 16, 17) for x in cells.get((d, h), [])]
        if v:
            wk = defaultdict(list)
            print(f"   {DOW[d]}  ширина {st.mean(v):3.0f}%  "
                  f"(база {base:.0f}) · "
                  f"{'слив' if base - st.mean(v) >= 6 else 'рост' if st.mean(v) - base >= 6 else 'ровно'}")

    # 3. пятница к закрытию рост, перед субботой слив
    print("\n3. «Пятница к закрытию рост, перед субботой слив»")
    for name, d, hrs in (("пт 13-16 NY", 4, (13, 14, 15, 16)),
                         ("пт 17-20 NY", 4, (17, 18, 19, 20)),
                         ("пт 21-23 NY", 4, (21, 22, 23)),
                         ("сб 00-04 NY", 5, (0, 1, 2, 3, 4))):
        v = [x for h in hrs for x in cells.get((d, h), [])]
        if v:
            print(f"   {name:12} ширина {st.mean(v):3.0f}%  "
                  f"({st.mean(v) - base:+.0f} к базе)")

    # 4. альты привязаны к биткоину
    if btc:
        pairs = []
        for t, (b, _) in breadth.items():
            r = btc.get(t); r2 = btc.get(t + (WIN - 1) * STEP)
            if r and r2:
                pairs.append((b - 50, (r2["c"] / r["o"] - 1) * 100))
        if len(pairs) > 100:
            xs = [p[0] for p in pairs]; ys = [p[1] for p in pairs]
            mx, my = st.mean(xs), st.mean(ys)
            cov = sum((x - mx) * (y - my) for x, y in pairs)
            sx = sum((x - mx) ** 2 for x in xs) ** .5
            sy = sum((y - my) ** 2 for y in ys) ** .5
            r_ = cov / (sx * sy) if sx and sy else 0
            same = sum(1 for x, y in pairs if (x > 0) == (y > 0)) / len(pairs) * 100
            # альты вверх при биткоине вниз — «свой ход»
            own = sum(1 for x, y in pairs if x > 10 and y < -0.2)
            print(f"\n4. «Альта привязана к биткоину»")
            print(f"   корреляция ширины альтов с ходом BTC за {WIN} ч: r={r_:+.2f}  "
                  f"(часов {len(pairs)})")
            print(f"   направление совпало в {same:.0f}% часов")
            print(f"   альты широко вверх (>60%) при BTC вниз (<−0.2%): "
                  f"{own} часов из {len(pairs)} — {own/len(pairs)*100:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
