#!/usr/bin/env python3
"""ФОН СДЕЛОК (27.09, владелец: «собери информацию по всем фонам, что у нас есть, для сделок, которые вышли в плюс»).
К каждой сделке rules_trades.json на момент входа: доска (медиана 6 ч / 24 ч по 144 лидерам, доля в плюсе за сутки), лидер суток
и его ход 48 ч, часов после последнего слома лидера (лидер ≥ +70%/48 ч, закрытие ≤ 0.85 × макс 24 ч), сессии (UTC+3), день/час,
состояние монеты: ход от минимума 24 ч и 7 дн, от максимума 24 ч, интерес 24 ч, фандинг, толпа, топы, покупатели за час, объём часа к суткам.
    python3 claude/research/trade_context.py     # → rules_trades_ctx.json + сводка медиан по правилам (плюс / минус)
"""
from __future__ import annotations
import json, statistics as st, datetime as dt, bisect
from pathlib import Path
from collections import defaultdict
BASE = Path(__file__).resolve().parents[2]
H = BASE / "cq_v2" / "hist3m"; B = 20; L = dt.timezone(dt.timedelta(hours=3))
SES = (("Сидней", 0, 9), ("Токио", 3, 12), ("Лондон", 10, 19), ("Нью-Йорк", 16, 25))

data = {f.stem.upper() + "USDT": json.loads(f.read_text()) for f in sorted(H.glob("*.json")) if not f.name.startswith("_")}
data = {s: r for s, r in data.items() if len(r) >= 2000}
T = {s: [r[0] for r in rows] for s, rows in data.items()}


def idx(s, t):
    i = bisect.bisect_right(T[s], t) - 1
    return i if i >= 0 else None


def board(t):
    ch6, ch24, up = [], [], 0
    for s, rows in data.items():
        i = idx(s, t)
        if i is None or i < 24 * B: continue
        c = rows[i][4]; c6 = rows[i - 6 * B][4]; c24 = rows[i - 24 * B][4]
        if c6: ch6.append(c / c6 - 1)
        if c24: ch24.append(c / c24 - 1); up += c > c24
    return (st.median(ch6) * 100 if ch6 else None, st.median(ch24) * 100 if ch24 else None, up / len(ch24) * 100 if ch24 else None)


def leader(t):
    best = None
    for s, rows in data.items():
        i = idx(s, t)
        if i is None or i < 48 * B: continue
        c48 = rows[i - 48 * B][4]
        if c48 and (best is None or rows[i][4] / c48 > best[1]): best = (s, rows[i][4] / c48)
    return best


# сломы лидеров по всей истории (первый бар слома)
breaks = []
for s, rows in data.items():
    n = len(rows); last = -10**9
    for i in range(48 * B, n):
        c = rows[i][4]; c48 = rows[i - 48 * B][4]
        if not c48 or c / c48 - 1 < 0.70: continue
        hi24 = max(r[2] for r in rows[i - 24 * B:i + 1])
        if c <= 0.85 * hi24 and rows[i - 1][4] > 0.85 * max(r[2] for r in rows[i - 24 * B - 1:i]) and i - last > 24 * B:
            breaks.append((rows[i][0], s)); last = i
breaks.sort()
BT = [b[0] for b in breaks]


def since_break(t):
    j = bisect.bisect_right(BT, t) - 1
    return ((t - BT[j]) / 3600_000, breaks[j][1]) if j >= 0 else (None, None)


def coin_state(s, t):
    i = idx(s, t); rows = data[s]
    if i is None or i < 24 * B: return {}
    r = rows[i]; c = r[4]
    lo24 = min(x[3] for x in rows[i - 24 * B:i + 1]); hi24 = max(x[2] for x in rows[i - 24 * B:i + 1])
    lo7 = min(x[3] for x in rows[max(0, i - 7 * 24 * B):i + 1])
    oi24 = rows[i - 24 * B][7]
    q1 = sum(x[5] for x in rows[i - B:i + 1]); b1 = sum(x[6] for x in rows[i - B:i + 1]); q24 = sum(x[5] for x in rows[i - 24 * B:i + 1])
    return dict(run24=(c / lo24 - 1) * 100 if lo24 else None, run7=(c / lo7 - 1) * 100 if lo7 else None, from_hi24=(c / hi24 - 1) * 100 if hi24 else None,
                oi24=(r[7] / oi24 - 1) * 100 if r[7] and oi24 else None, fund=r[8], crowd=r[9], tops=r[10],
                buy1h=b1 / q1 * 100 if q1 else None, vol1h_vs_day=(q1 / (q24 / 24)) if q24 else None)


def main():
    trades = json.load(open(BASE / "claude/research/rules_trades.json"))
    cache = {}
    out = []
    for x in trades:
        t_local = dt.datetime.strptime(x["t"], "%Y-%m-%d %H:%M").replace(tzinfo=L); t = int(t_local.timestamp() * 1000)
        key = t // 900_000                                   # фон по 15-минутной сетке, чтобы не считать 995 раз
        if key not in cache:
            b6, b24, up = board(t); ld = leader(t); sb, bsym = since_break(t)
            cache[key] = dict(board6=b6, board24=b24, up24=up, leader=(ld[0][:-4] if ld else None), leader_run48=((ld[1] - 1) * 100 if ld else None),
                              h_since_break=sb, broken=(bsym[:-4] if bsym else None))
        h = t_local.hour
        ses = [n for n, a, b in SES if a <= (h if h >= a else h + 24) < b]
        out.append(dict(x, **cache[key], sessions=ses, **coin_state(x["sym"], t)))
    (BASE / "claude/research/rules_trades_ctx.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    fields = [("board6", "доска 6ч %"), ("board24", "доска 24ч %"), ("up24", "доля в плюсе 24ч %"), ("leader_run48", "ход лидера 48ч %"), ("h_since_break", "ч после слома"),
              ("run24", "ход монеты от мин 24ч %"), ("run7", "от мин 7дн %"), ("from_hi24", "от макс 24ч %"), ("oi24", "интерес 24ч %"), ("fund", "фандинг %"),
              ("crowd", "толпа L/S"), ("tops", "топы L/S"), ("buy1h", "покупатели 1ч %"), ("vol1h_vs_day", "объём 1ч к среднему")]
    by = defaultdict(list)
    for x in out: by[x["rule"]].append(x)
    md = ["# Фон сделок: медианы у выигравших и проигравших (27.09, trade_context.py)\n"]
    for rule, tr in by.items():
        w = [x for x in tr if x["res"] > 0]; l = [x for x in tr if x["res"] <= 0]
        md.append(f"\n## {rule} — в плюс {len(w)}, в минус {len(l)}\n\n| фон | выиграли (медиана) | проиграли (медиана) |\n|---|---|---|")
        for k, name in fields:
            vw = [x[k] for x in w if x.get(k) is not None]; vl = [x[k] for x in l if x.get(k) is not None]
            md.append(f"| {name} | {st.median(vw):+.2f} | {st.median(vl):+.2f} |" if vw and vl else f"| {name} | — | — |")
        sw = defaultdict(int); sl = defaultdict(int)
        for x in w:
            for s_ in x["sessions"]: sw[s_] += 1
        for x in l:
            for s_ in x["sessions"]: sl[s_] += 1
        md.append("| сессии (сделок) | " + ", ".join(f"{k} {v}" for k, v in sw.items()) + " | " + ", ".join(f"{k} {v}" for k, v in sl.items()) + " |")
        lw = defaultdict(int)
        for x in w: lw[x["leader"]] += 1
        md.append("| лидер суток у выигравших | " + ", ".join(f"{k} {v}" for k, v in sorted(lw.items(), key=lambda kv: -kv[1])[:6]) + " | |")
    (BASE / "claude/research/trade_context.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
