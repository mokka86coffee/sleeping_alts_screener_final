#!/usr/bin/env python3
"""ШОРТ НА ПАМПЕ: ВХОД НА ВЫНОСЕ СО СТОПОМ 3 % И ПОВТОРОМ (06.10, владелец по GRIFFAIN: «бот на пампе должен ставить стоп 3%, если был повторный вынос
то повторно заходить в шорт», «тут входить надо на выносе а не на самом пампе»). Те же 62 сигнала и те же данные TradingView, что в pump_end_r58.py
(часовые бары и ликвидации, 06.09–03.10), те же выходы владельца от 03.10 (после −5 % стоп на вход; через 6 ч стоп на вход или закрытие; срок).
Сравниваются: вход на возврате к верху свечи выноса (как в боте) и вход сразу по закрытию часа выноса; стоп 10 % и 3 %; повтор на новом выносе после стопа.
Суммы — в $ при 500 $ на сделку, комиссия 0,1 % на сделку. С Binance ничего не запрашивается.
    .venv/bin/python claude/research/pump_end_stop3.py"""
import io, contextlib, runpy, sys
from pathlib import Path
with contextlib.redirect_stdout(io.StringIO()):
    G = runpy.run_path(str(Path(__file__).parent / "pump_end_r58.py"))
P, idx, coins, own_exit2 = G["P"], G["idx"], G["coins"], G["own_exit2"]
SIZE, FEE = 500.0, 0.001


def next_squeeze(sym, b, q0, end):
    """следующий час рекордного выноса шортов после бара q0 — условие как в chain() исходного счёта"""
    LS = {y[0]: abs(y[2]) for y in coins[sym].get("liq") or [] if len(y) > 2 and y[2]}
    for q in range(q0, end + 1):
        t = b[q][0]; win = LS.get(t, 0.0); prev = [v for h, v in LS.items() if t - 86400 <= h < t]
        if win > 0 and prev:
            mx = max(prev); mean = sum(prev) / len(prev)
            if win >= (1.3 * mx if (len(prev) > 1 and mx >= 2 * mean) else 2 * mx): return q
    return None


def one(x, mode, sl, hold, redo):
    """→ (сумма долей по сигналу, число входов, чем кончился последний)"""
    b, i = idx(x); tot, n, how = 0.0, 0, None
    if mode == "top":                                                   # как в боте: уровень — максимум свечи выноса, вход при касании в следующие 24 ч
        lvl = b[i][2]; j = None
        if b[i][4] >= lvl: j, e, same = i, b[i][4], False
        else:
            for q in range(i + 1, min(len(b), i + 25)):
                if b[q][2] >= lvl: j, e, same = q, lvl, True; break
        if j is None: return None
    else:
        j, e, same = i, b[i][4], False
    end = min(len(b) - hold - 2, i + 48)
    while True:
        r, how = own_exit2(b, j, e, same, hold=hold, sl=sl)
        if r is None: break
        tot += r - FEE; n += 1
        if how != "стоп" or n >= redo: break
        sq = next((q for q, row in enumerate(b[j:j + hold + 2], j) if row[2] >= e * (1 + sl)), j)   # бар стопа
        q2 = next_squeeze(x["sym"], b, sq + (0 if mode == "now" else 1), end) if sq <= end else None
        if q2 is None or q2 <= j: break
        j, e, same = q2, b[q2][4], False                                # повтор — по закрытию часа нового выноса
    return (tot, n, how) if n else None


tm = sorted(x["t"] for x in P)[len(P) // 2]
print(f"сигналов «рост и памп + рекордный вынос шортов»: {len(P)} · деньги при {SIZE:.0f} $ на сделку\n")
for hold in (16, 72):
    print(f"срок {hold} ч:")
    for nm, mode, sl, redo in (("как в боте: вход на возврате к верху свечи, стоп 10 %", "top", .10, 1),
                               ("вход на возврате к верху свечи, стоп 3 %", "top", .03, 1),
                               ("вход сразу на выносе, стоп 10 %", "now", .10, 1),
                               ("вход сразу на выносе, стоп 3 %", "now", .03, 1),
                               ("вход сразу на выносе, стоп 3 %, повтор на новом выносе (до 3 шортов)", "now", .03, 3)):
        R = [(x, one(x, mode, sl, hold, redo)) for x in P]; R = [(x, r) for x, r in R if r]
        s = lambda g: sum(r[0] for _, r in g) * SIZE
        h1 = [z for z in R if z[0]["t"] < tm]; h2 = [z for z in R if z[0]["t"] >= tm]
        ne = sum(r[1] for _, r in R)
        print(f"  {nm:70s} сигналов {len(R):2d} · входов {ne:2d} · итог {s(R):+7.0f} $ (половины {s(h1):+.0f} / {s(h2):+.0f}) · в плюс {sum(1 for _, r in R if r[0] > 0)} · стопом кончились {sum(1 for _, r in R if r[2] == 'стоп')}")
    print()
