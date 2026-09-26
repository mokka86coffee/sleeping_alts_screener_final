#!/usr/bin/env python3
"""ПЕРЕВОРОТ В ПЛОХИЕ ЧАСЫ (26.09, владелец: «во время, когда стратегия не работает, брать позиции в обратную сторону»).
Для каждого правила: часы, где сумма результата < 0 → сторона наоборот с теми же целью/стопом/сроком (зеркально).
Два счёта: in-sample (часы и сделки — одни и те же 14 дн) и честный (плохие часы по первой неделе, переворот на второй).
Часы: по часу суток (24 ячейки) и по дню недели × час (168).
    python3 claude/research/rules_flip.py    # → claude/research/rules_flip.json + печать
"""
from __future__ import annotations
import json, statistics as st, datetime as dt
from pathlib import Path
from collections import defaultdict
BASE = Path(__file__).resolve().parents[2]
import sys; sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules_by_time as rb
H = BASE / "cq_v2" / "hist3m"; B = 20; L = dt.timezone(dt.timedelta(hours=3))
WD = rb.WD


_SIG = {}


def simulate_side(sym, rows, rule, side_fn):
    """как rb.simulate, но сторона входа = side_fn(t_local) (±1); выходы зеркальные; сигналы считаются один раз на монету"""
    if sym not in _SIG:
        _SIG[sym] = rb.signals(rows)
    sig = _SIG[sym]; cfg = rb.RULES[rule]; n = len(rows); trades = []; pos = None; last_exit = -10**9
    for i in range(n):
        if pos:
            e, sd = pos["e"], pos["sd"]; h, l, c = rows[i][2], rows[i][3], rows[i][4]; res = why = None
            tp = cfg["tp"] if cfg["tp"] else (abs(pos["tp_px"] / e - 1) if pos.get("tp_px") else None)
            if sd == 1:
                if cfg["sl"] and l <= e * (1 - cfg["sl"]): res, why = -cfg["sl"], "стоп"
                elif tp and h >= e * (1 + tp): res, why = tp, "цель"
            else:
                if cfg["sl"] and h >= e * (1 + cfg["sl"]): res, why = -cfg["sl"], "стоп"
                elif tp and l <= e * (1 - tp): res, why = tp, "цель"
            if res is None and i - pos["i"] >= cfg["hold"]: res, why = (c / e - 1) * sd, "срок"
            if res is not None:
                t = dt.datetime.fromtimestamp(rows[pos["i"]][0] / 1000, L)
                trades.append(dict(rule=rule, sym=sym, t=t, wd=WD[t.weekday()], hour=t.hour, week=0 if t < WK else 1, side=sd, res=res * 100, why=why))
                last_exit = i; pos = None
        for r, tp_px in sig.get(i, []):
            if r != rule or pos or i - last_exit < 2 * B: continue
            t = dt.datetime.fromtimestamp(rows[i][0] / 1000, L)
            sd = side_fn(t)
            if sd == 0: continue
            pos = dict(i=i, e=rows[i][4], sd=sd, tp_px=tp_px)
    return trades


def main():
    global WK
    files = [f for f in sorted(H.glob("*.json")) if not f.name.startswith("_")]
    data = {f.stem.upper() + "USDT": json.loads(f.read_text()) for f in files}
    data = {s: r for s, r in data.items() if len(r) >= 2000}
    t0 = min(r[0][0] for r in data.values()); WK = dt.datetime.fromtimestamp(t0 / 1000, L) + dt.timedelta(days=7)
    out = {}
    print(f"{'правило':16} {'база':>8} {'перев. час (все)':>17} {'перев. день×час':>16} {'честно: база нед2':>18} {'честно: перев.':>15}")
    for rule, cfg in rb.RULES.items():
        base_side = cfg["side"]
        base = []
        for s, rows in data.items(): base += simulate_side(s, rows, rule, lambda t: base_side)
        if not base: continue
        def bad_hours(tr, key):
            cells = defaultdict(float)
            for x in tr: cells[key(x)] += x["res"]
            return {k for k, v in cells.items() if v < 0}
        kh = lambda x: x["hour"]; kdh = lambda x: (x["wd"], x["hour"])
        # in-sample
        bh = bad_hours(base, kh); bdh = bad_hours(base, kdh)
        flip_h, flip_dh = [], []
        for s, rows in data.items():
            flip_h += simulate_side(s, rows, rule, lambda t: -base_side if t.hour in bh else base_side)
            flip_dh += simulate_side(s, rows, rule, lambda t: -base_side if (WD[t.weekday()], t.hour) in bdh else base_side)
        # честно: плохие часы по неделе 1, применяем к неделе 2
        b1 = [x for x in base if x["week"] == 0]; b2 = [x for x in base if x["week"] == 1]
        bh1 = bad_hours(b1, kh)
        flip_oos = []
        for s, rows in data.items():
            flip_oos += [x for x in simulate_side(s, rows, rule, lambda t: -base_side if t.hour in bh1 else base_side) if x["week"] == 1]
        S = lambda tr: sum(x["res"] for x in tr)
        out[rule] = dict(base=dict(n=len(base), sum=S(base)), flip_hour=dict(n=len(flip_h), sum=S(flip_h), bad_hours=sorted(bh)),
                         flip_dayhour=dict(n=len(flip_dh), sum=S(flip_dh), bad_cells=len(bdh)),
                         oos=dict(base_n=len(b2), base_sum=S(b2), flip_n=len(flip_oos), flip_sum=S(flip_oos), bad_hours_week1=sorted(bh1)),
                         flip_hour_trades=[dict(t=x["t"].strftime("%Y-%m-%d %H:%M"), wd=x["wd"], hour=x["hour"], sym=x["sym"][:-4], side="лонг" if x["side"] == 1 else "шорт", res=round(x["res"], 2), why=x["why"]) for x in flip_h])
        print(f"{rule:16} {S(base):>+7.0f}% {S(flip_h):>+10.0f}% ({len(flip_h):3}) {S(flip_dh):>+10.0f}% ({len(flip_dh):3}) {S(b2):>+12.0f}% ({len(b2):3}) {S(flip_oos):>+9.0f}% ({len(flip_oos):3})")
    (BASE / "claude/research/rules_flip.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
