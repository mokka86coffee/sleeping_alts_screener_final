#!/usr/bin/env python3
"""ДЕНЕЖНЫЙ ПРОГОН КНИГ «ВТОРОЙ ХОД» И «КОНЕЦ» НА ИСТОРИИ 30 ДН (26.09, владелец: «всё, что полдня объяснял про рынок…
теперь просто проверка одного пункта?»). Те же signal() книг (paper_second.signal, paper_end.signal_split), те же
пороги core_config, строки — cq_v2/hist30 (hist30.py). Сначала все сделки по монетам без ограничений, потом
депозит 20000 $ на K слотов в порядке времени (как first3_money.py). Слом лидера для «конца» — таблица
claude/research/leader_break.md (настоящие сломы).
    python3 claude/research/book_replay.py second      # лонги «второй ход»
    python3 claude/research/book_replay.py end         # шорты «конец» (слом лидера / сползание)
"""
from __future__ import annotations
import json, re, sys, datetime as dt, statistics as stt
from pathlib import Path
BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
import paper_second, paper_end                                   # noqa: E402
from core_config import BOOK_DEPOSIT                             # noqa: E402

HIST = BASE / "cq_v2" / "hist30"
FEE = 0.001
BAR = 1_800_000


def breaks():
    out = []
    for line in (BASE / "claude/research/leader_break.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Z0-9]+)\s+[AB] слом (\d\d)\.(\d\d) (\d\d):(\d\d)\s+\+\d+% \|\s+([+-]?\d+\.\d)%", line)
        if m:
            t = dt.datetime(2026, int(m.group(3)), int(m.group(2)), int(m.group(4)), int(m.group(5)), tzinfo=dt.UTC)
            out.append((m.group(1) + "USDT", int(t.timestamp() * 1000), float(m.group(6))))
    out.append(("PHAUSDT", int(dt.datetime(2026, 9, 25, 23, 0, tzinfo=dt.UTC).timestamp() * 1000), 2.3))
    return sorted(out, key=lambda x: x[1])


def lb_at(bks, t):
    cand = [b for b in bks if b[1] <= t and t - b[1] <= 48 * 3600_000]
    return cand[-1] if cand else None


def signal_second2(rows, i):
    """ВТОРОЙ ХОД С ДЛИННОЙ БАЗОЙ (26.09): у ARK база после первой ноги 9 дней (15–23.09), у BLESS 2 дня; окна книги
    (максимум 72 ч, минимум 7 дн, интерес 48 ч) видят только быструю вторую ногу. Здесь: первая нога — максимум за
    LOOK баров ≥ +SECOND_RUN% от минимума 7 дн перед ним; база — цена ≤ max × (1 − SECOND_PULLBACK) и выше минимума после
    максимума (не сползание); фандинг за сутки ≈ 0; интерес сдулся на SECOND_OI_DEFLATE от интереса на максимуме и
    развернулся +SECOND_OI_TURN за 12 баров; спот за 6 баров покупает. Цель — тот максимум."""
    LOOK = 960
    if i < 400:
        return None
    C = [float(r["px"]) for r in rows[:i + 1]]; H = [float(r["h"]) for r in rows[:i + 1]]; L = [float(r["l"]) for r in rows[:i + 1]]
    OI = [float(r["oi"] or 0) for r in rows[:i + 1]]; F = [r["funding"] for r in rows[:i + 1]]
    j0 = max(0, i - LOOK)
    jm = max(range(j0, i + 1), key=lambda j: H[j])
    if i - jm < 48 or jm - 336 < 0:
        return None
    lo_before = min(L[jm - 336:jm])
    run = (H[jm] / lo_before - 1) * 100 if lo_before else 0
    if run < paper_second.SECOND_RUN:
        return None
    if C[i] > H[jm] * (1 - paper_second.SECOND_PULLBACK):
        return None
    lo_after = min(L[jm:i + 1])
    if C[i] < lo_after * 1.03:
        return None
    fm = paper_second._med(F[i - 48:i + 1])
    if fm is None or abs(fm) > paper_second.SECOND_FUND_ZERO:
        return None
    oi_top = max(OI[jm - 6:jm + 7]) if jm >= 6 else OI[jm]
    if not (oi_top and OI[i] and OI[i - 12]):
        return None
    deflated = min(OI[jm:i + 1]) <= oi_top * (1 - paper_second.SECOND_OI_DEFLATE)
    turned = OI[i] / OI[i - 12] - 1 >= paper_second.SECOND_OI_TURN
    spot = sum(float(((r.get("spot") or {}).get("d")) or 0) for r in rows[i - 5:i + 1])
    if deflated and turned and spot > 0:
        return {"t": rows[i]["t"], "px": C[i], "target": round(max(0.05, H[jm] / C[i] - 1), 4), "stop": paper_second.SECOND_STOP,
                "hold": paper_second.SECOND_HOLD, "rule": f"второй ход (база): первая нога +{run:.0f}%, база {(i - jm) / 48:.0f} дн, −{(1 - C[i] / H[jm]) * 100:.0f}% от вершины, фандинг {fm:+.3f}"}
    return None


def trades_second(sym, rows, variant="book"):
    out, i, last_exit = [], 96, -1
    while i < len(rows):
        L = [float(r["l"]) for r in rows[max(0, i - 336):i + 1]]
        run = (rows[i]["px"] / min(L) - 1) * 100 if min(L) else 0
        if variant == "base":
            sig = signal_second2(rows, i)
        else:
            sig = paper_second.signal(rows[:i + 1], {"run_from_low7": run}) if run >= paper_second.SECOND_RUN else None
        if not sig or rows[i]["t"] - last_exit < paper_second.SECOND_PAUSE_H * 3600_000:
            i += 1; continue
        e, tgt, stop, hold = float(sig["px"]), float(sig["target"]), float(sig["stop"]), int(sig["hold"])
        res, why, k = None, None, 0
        for k, r in enumerate(rows[i + 1:], 1):
            if r["l"] <= e * (1 - stop): res, why = -stop, "стоп"; break
            if r["h"] >= e * (1 + tgt): res, why = tgt, "цель"; break
            if k >= hold: res, why = r["px"] / e - 1, "срок"; break
        if res is None:
            res, why = rows[-1]["px"] / e - 1, "висит"
        out.append(dict(sym=sym, side=1, t_in=rows[i]["t"], t_out=rows[min(i + k, len(rows) - 1)]["t"], res=res, why=why, rule=sig["rule"][:60]))
        last_exit = rows[min(i + k, len(rows) - 1)]["t"]
        i += k + 1
    return out


def trades_end(sym, rows, bks):
    out, i, last_exit = [], 150, -1
    while i < len(rows):
        sig = paper_end.signal_split(rows[:i + 1], sym, lb_at(bks, rows[i]["t"]))
        if not sig or rows[i]["t"] - last_exit < 24 * 3600_000:
            i += 1; continue
        e, tgt, hold = float(sig["px"]), float(sig["target"]), int(sig.get("hold") or paper_end.PAPER_END_HOLD)
        res, why, k = None, None, 0
        for k, r in enumerate(rows[i + 1:], 1):
            if e / r["px"] - 1 >= tgt: res, why = tgt, "цель"; break
            if k >= hold: res, why = e / r["px"] - 1, "срок"; break
        if res is None:
            res, why = e / rows[-1]["px"] - 1, "висит"
        out.append(dict(sym=sym, side=-1, t_in=rows[i]["t"], t_out=rows[min(i + k, len(rows) - 1)]["t"], res=res, why=why,
                        rule=sig["rule"].split(":")[0]))
        last_exit = rows[min(i + k, len(rows) - 1)]["t"]
        i += k + 1
    return out


def slots(trades, K):
    size = BOOK_DEPOSIT / K
    tr = sorted(trades, key=lambda x: x["t_in"])
    open_until, taken = [], []
    for x in tr:
        open_until = [u for u in open_until if u > x["t_in"]]
        if len(open_until) >= K:
            continue
        open_until.append(x["t_out"]); taken.append(x)
    return size, taken


def main():
    book = sys.argv[1] if len(sys.argv) > 1 else "second"
    bks = breaks()
    all_tr = []
    for p in sorted(HIST.glob("*.json")):
        rows = json.loads(p.read_text(encoding="utf-8"))
        if len(rows) < 200:
            continue
        sym = p.stem.upper() + "USDT"
        all_tr += (trades_second(sym, rows) if book == "second" else trades_second(sym, rows, "base") if book == "second2"
                   else trades_end(sym, rows, bks))
    name = {"second": "второй ход", "second2": "второй ход (база)"}.get(book, "конец")
    print(f"«{name}»: сигналов без ограничений {len(all_tr)} по {len({x['sym'] for x in all_tr})} монетам")
    for x in sorted(all_tr, key=lambda x: x["t_in"]):
        print(f"  {dt.datetime.fromtimestamp(x['t_in'] / 1000, dt.UTC):%d.%m %H:%M} {x['sym'][:-4]:10} {x['why']:5} {x['res'] * 100:+6.1f}%  {x['rule']}")
    if not all_tr:
        return
    won = [x for x in all_tr if x["res"] > 0]
    print(f"в плюс {len(won)}/{len(all_tr)} · средний {stt.mean(x['res'] for x in all_tr) * 100:+.1f}% · медиана {stt.median(x['res'] for x in all_tr) * 100:+.1f}%")
    by = {}
    for x in all_tr:
        b = by.setdefault(x["rule"], [0, 0, 0.0]); b[0] += 1; b[1] += x["res"] > 0; b[2] += x["res"]
    for r, b in by.items():
        print(f"  {r:26} n={b[0]:3} плюс {b[1]:3} ср {b[2] / b[0] * 100:+.1f}%")
    for K in (2, 4, 8):
        size, taken = slots(all_tr, K)
        money = sum(size * (x["res"] - FEE) for x in taken)
        print(f"депозит {BOOK_DEPOSIT:.0f} $ · K={K} ({size:.0f} $): сделок {len(taken)} · деньги {money:+.0f} $")


if __name__ == "__main__":
    main()
