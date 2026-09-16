#!/usr/bin/env python3
"""ОДНА-ДВЕ СДЕЛКИ В ДЕНЬ (16.09; владелец: «ты не вычленяешь 1–2 сделки в день — например, на Америке в четверг в
лонг, а в субботу в шорт, — и пытаешься заработать всё время»). Не правило на все часы, а календарь окон.

Окно = день недели × сессия (Сидней 21, Токио 0, Лондон 7, Нью-Йорк 13 UTC) × смещение от открытия (0 / +1.5 ч) ×
сторона. В каждом окне из ВСЕЙ доски берётся ОДНА монета по правилу отбора:
  лонг  — та, что сильнее всех просела за 6 ч к моменту входа (но не больше −25%: не ловим ножи);
  шорт  — та, что сильнее всех выросла за 6 ч (но не больше +40%: не шортим ракету);
держится HOLD часов, без стопа, потолок убытка CAP по закрытию, комиссия 0.1%. Размер — SLOT% капитала.
Считает за период по каждому окну: сделок (≈ число недель), попаданий, медиана, средняя, сумма, худшая.
Печатает календарь-таблицу и десять лучших окон; `--pick 2` собирает портфель: не больше двух лучших окон в день
(выбранных по первой половине периода, проверенных на второй — чтобы не подгонять), и даёт P&L по неделям.
Источник — hourly/*.json (полгода часовиков). `python3 lab_daily.py --days 180 --hold 4 --pick 2`.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

FEE = 0.001
CAP = 0.25
SLOT = 10.0
OPENS = {21: "Сидней", 0: "Токио", 7: "Лондон", 13: "Нью-Йорк"}
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
OFFS = [0, 2]        # часовики: смещение только целыми часами


def load_hourly(days: int) -> dict:
    data = {}
    for p in (BASE_DIR / "hourly").glob("*.json"):
        if p.stem.lower() == "btc":
            continue
        try:
            arr = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        d = {int(b["t"]): float(b["c"]) for b in arr if isinstance(b, dict) and b.get("t") and b.get("c")}
        if len(d) < 200:
            continue
        keys = sorted(d)[-(days * 24 + 48):]
        data[p.stem.upper() + "USDT"] = {k: d[k] for k in keys}
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--hold", type=float, default=4.0)
    ap.add_argument("--pick", type=int, default=2, help="сколько лучших окон в день брать в портфель")
    ap.add_argument("--cap", type=float, default=CAP)
    ap.add_argument("--board-filter", type=float, default=None, help="пропускать окно, если медиана доски за сутки ДО входа против стороны сильнее этого процента (например 1.5)")
    ap.add_argument("--confirm", type=int, default=None, help="вход не в начале окна, а через K часов — и только если доска за эти K часов пошла в сторону сделки (подтверждение внутри окна)")
    ap.add_argument("--regime", default=None, help="брать окно только в этом режиме ДОСКИ: флэт | рост | слив (режим — трое суток, эффективность хода)")
    a = ap.parse_args()
    data = load_hourly(a.days)
    if not data:
        print("hourly/*.json пусто")
        return 0
    times = sorted(set(t for d in data.values() for t in d))
    H = 3600000

    def board_regime(t):
        """режим доски на момент t: трое суток, |ход| / путь по медиане доски (без заглядывания вперёд)"""
        seq = []
        for h in range(72, -1, -6):
            tt = t - h * H
            mv = [(d[tt] / d[tt - 24 * H] - 1) for d in data.values() if tt in d and (tt - 24 * H) in d]
            if len(mv) >= 8:
                seq.append(st.median(mv))
        if len(seq) < 8:
            return None
        net = seq[-1] - seq[0]
        path = sum(abs(seq[q] - seq[q - 1]) for q in range(1, len(seq))) or 1e-9
        return "флэт" if abs(net) / path < 0.25 else ("рост" if net > 0 else "слив")
    t_mid = times[len(times) // 2]

    def ret(sym, t0, t1):
        d = data[sym]
        return (d[t1] / d[t0] - 1) if (t0 in d and t1 in d) else None

    # ── все окна: по каждому часу открытия сессии в каждом дне
    trades = defaultdict(list)     # (wd, sess, off, side) → [(t, sym, res)]
    for t in times:
        d = datetime.fromtimestamp(t / 1000, timezone.utc)
        if d.minute != 0 or d.hour not in OPENS:
            continue
        sess = OPENS[d.hour]
        wd = d.weekday()
        if a.regime and board_regime(t) != a.regime:
            continue
        for off in OFFS:
            te = t + int(off * H)
            tx = te + int(a.hold * H)
            # кандидаты: ход за 6 ч к входу
            cands = []
            for sym in data:
                r6 = ret(sym, te - 6 * H, te)
                if r6 is None or ret(sym, te, tx) is None:
                    continue
                cands.append((sym, r6))
            if len(cands) < 10:
                continue
            board_pre = None
            if a.board_filter is not None:
                mv = [ret(sym, te - 24 * H, te) for sym in data]
                mv = [x for x in mv if x is not None]
                board_pre = st.median(mv) * 100 if len(mv) >= 8 else None
            board_in = None
            if a.confirm:
                mv = [ret(sym, te, te + a.confirm * H) for sym in data]
                mv = [x for x in mv if x is not None]
                board_in = st.median(mv) * 100 if len(mv) >= 8 else None
            for side in (1, -1):
                if board_pre is not None and side * board_pre <= -a.board_filter:
                    continue                       # доска за сутки до входа против стороны — окно пропускаем
                if a.confirm:
                    if board_in is None or side * board_in <= 0:
                        continue                   # доска в первые K часов окна пошла против — не входим
                pool = [c for c in cands if (-0.25 <= c[1] < 0 if side > 0 else 0 < c[1] <= 0.40)]
                if not pool:
                    continue
                sym, r6 = (min(pool, key=lambda c: c[1]) if side > 0 else max(pool, key=lambda c: c[1]))
                # ход сделки с потолком по закрытию; при подтверждении вход через K часов после начала окна
                dsym = data[sym]
                te_ = te + (a.confirm * H if a.confirm else 0)
                if te_ not in dsym:
                    continue
                e = dsym[te_]
                res = None
                for k in range(1, int(a.hold) + 1):
                    tk = te_ + k * H
                    if tk not in dsym:
                        break
                    cur = side * (dsym[tk] / e - 1)
                    if cur <= -a.cap:
                        res = cur
                        break
                if res is None:
                    rr = ret(sym, te_, te_ + int(a.hold * H))
                    if rr is None:
                        continue
                    res = side * rr
                trades[(wd, sess, off, side)].append((te, sym, res - FEE, r6))
    if not trades:
        print("окон нет")
        return 0

    def stat(v):
        r = [x[2] for x in v]
        tot = sum(r)
        return len(r), 100 * sum(1 for x in r if x > 0) / len(r), st.median(r) * 100, st.mean(r) * 100, tot * 100, min(r) * 100

    print(f"монет {len(data)} · дней {a.days} · удержание {a.hold:g} ч · потолок {a.cap * 100:.0f}% · одна монета на окно (лонг — сильнее всех просела за 6 ч, шорт — сильнее всех выросла)"
          + (f" · подтверждение: вход через {a.confirm} ч, только если доска за эти часы пошла в сторону сделки" if a.confirm else "")
          + (f" · фильтр доски до входа {a.board_filter}%" if a.board_filter else "") + (f" · только режим доски «{a.regime}»" if a.regime else "") + "\n")
    print("── КАЛЕНДАРЬ: сумма за период, % на сделку размера 1 (n ≈ недель); + лонг / − шорт; смещение 0 и +1.5 ч")
    hdr = "        " + "  ".join(f"{s:>16}" for s in OPENS.values())
    print(hdr)
    for wd in range(7):
        cells = []
        for sess in OPENS.values():
            parts = []
            for off in OFFS:
                l = trades.get((wd, sess, off, 1), [])
                s_ = trades.get((wd, sess, off, -1), [])
                sl = sum(x[2] for x in l) * 100 if l else 0
                ss = sum(x[2] for x in s_) * 100 if s_ else 0
                parts.append(f"{sl:+4.0f}/{ss:+4.0f}")
            cells.append("  ".join(parts))
        print(f"  {WD[wd]}    " + "  ".join(f"{c:>16}" for c in cells))
    print("   (в клетке: лонг/шорт на открытии · лонг/шорт через 2 ч после открытия — сумма % за все недели)\n")

    rows = []
    for key, v in trades.items():
        n, hit, med, mean, tot, worst = stat(v)
        if n < 8:
            continue
        h1 = [x[2] for x in v if x[0] < t_mid]
        h2 = [x[2] for x in v if x[0] >= t_mid]
        rows.append((tot, key, n, hit, med, mean, worst, (sum(h1) * 100 if h1 else 0), (sum(h2) * 100 if h2 else 0)))
    rows.sort(reverse=True)
    print("── ЛУЧШИЕ ОКНА (по сумме за период; половины — сумма в первой и второй половине периода):")
    for tot, (wd, sess, off, side), n, hit, med, mean, worst, s1, s2 in rows[:12]:
        print(f"  {WD[wd]} · {sess:<9} {'+2 ч' if off else 'открытие':<9} {'ЛОНГ ' if side > 0 else 'ШОРТ '} n={n:>2} · попаданий {hit:3.0f}% · медиана {med:+5.2f}% · средняя {mean:+5.2f}% · сумма {tot:+6.1f}% · худшая {worst:+5.1f}% · половины {s1:+5.1f} / {s2:+5.1f}")
    print("\n── ХУДШИЕ ОКНА (их не брать):")
    for tot, (wd, sess, off, side), n, hit, med, mean, worst, s1, s2 in rows[-6:]:
        print(f"  {WD[wd]} · {sess:<9} {'+2 ч' if off else 'открытие':<9} {'ЛОНГ ' if side > 0 else 'ШОРТ '} n={n:>2} · попаданий {hit:3.0f}% · сумма {tot:+6.1f}% · половины {s1:+5.1f} / {s2:+5.1f}")

    # ── портфель: окна выбраны по первой половине, проверены на второй
    print(f"\n── ПОРТФЕЛЬ: не больше {a.pick} окон в день, выбранных по ПЕРВОЙ половине периода, результат — на ВТОРОЙ (честная проверка)")
    first = defaultdict(list)
    for key, v in trades.items():
        h1 = [x[2] for x in v if x[0] < t_mid]
        if len(h1) >= 5:
            first[key[0]].append((sum(h1), key))
    chosen = []
    for wd in range(7):
        best = sorted(first.get(wd, []), reverse=True)[:a.pick]
        chosen += [k for s_, k in best if s_ > 0]
    if not chosen:
        print("   ни одно окно не прошло")
        return 0
    for k in chosen:
        print(f"   взято: {WD[k[0]]} · {k[1]} · {'+2 ч' if k[2] else 'открытие'} · {'ЛОНГ' if k[3] > 0 else 'ШОРТ'}")
    byweek = defaultdict(float)
    allv = []
    for k in chosen:
        for te, sym, res, r6 in trades[k]:
            if te >= t_mid:
                y, w, _ = datetime.fromtimestamp(te / 1000, timezone.utc).isocalendar()
                byweek[f"{y}-нед{w:02d}"] += res * SLOT
                allv.append(res)
    if allv:
        print(f"   вторая половина: сделок {len(allv)} · попаданий {100 * sum(1 for x in allv if x > 0) / len(allv):.0f}% · средняя {100 * st.mean(allv):+.2f}% · итог {100 * sum(allv) * SLOT / 100:+.1f}% при сделке {SLOT:.0f}% капитала")
        for w, p in sorted(byweek.items()):
            print(f"     {w}  {p:+6.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
