#!/usr/bin/env python3
"""ВЫХОД ВЫШЕ +40% ДЛЯ «3 В ПЕРВЫХ» (26.09, владелец: «+40% и выход было без анализа, если есть уверенность хода —
выход выше»). На сетке first3_money.py цель +50/60% давала больше денег на тех же сделках, значит победители идут дальше.
Варианты на тех же сигналах, K=4 слота по 5000 $, до +40% всё как в книге (после +20% стоп в ноль, срок 48 ч):
  • фикс — цель +40% (как сейчас);
  • трейл T — после +40% стоп T% ниже максимума хода; срок 48 ч после +40% не действует (H2 — общий потолок часов);
  • ступени — после +40% стоп на +20%, после +60% стоп на +40%, после +80% на +60% … (шаг 20 п.).
    python3 claude/research/first3_trail.py
"""
from __future__ import annotations
import sys, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import first3_money as fm                                     # noqa: E402
import paper_first3 as pf                                     # noqa: E402

K, H = 4, 48


def run(sigs, now, mode, T=None, H2=None):
    size = fm.DEP / K
    op, last_exit, used, closed = {}, {}, {}, []
    t = sigs[0][0]

    def advance(sym, pos, now_ms):
        e = pos["px"]
        for tb, o, h, l, c in pf.klines3(sym, pos["chk"], now_ms):
            pos["chk"] = tb + fm.BAR3; pos["last"] = c
            pos["max"] = max(pos["max"], h)
            at = (tb + fm.BAR3) / 1000
            if not pos["won"]:
                if pos["armed"] and l <= e:
                    return dict(res=0.0, why="ноль", at=at)
                if h >= e * (1 + fm.TARGET):
                    if mode == "фикс":
                        return dict(res=fm.TARGET, why="цель", at=at)
                    pos["won"] = True
                    pos["stop"] = e * (1 + 0.20) if mode == "ступени" else None
                    continue
                if not pos["armed"] and h >= e * (1 + fm.BE):
                    pos["armed"] = True
                if at - pos["at"] >= H * 3600:
                    return dict(res=c / e - 1, why="срок", at=at)
            else:
                if mode == "трейл":
                    st = pos["max"] * (1 - T)
                    if l <= st:
                        return dict(res=st / e - 1, why="трейл", at=at)
                else:                                          # ступени
                    step = int((pos["max"] / e - 1) // 0.20) * 0.20 - 0.20       # +60% → стоп +40%
                    pos["stop"] = max(pos["stop"], e * (1 + step))
                    if l <= pos["stop"]:
                        return dict(res=pos["stop"] / e - 1, why="ступень", at=at)
                if H2 and at - pos["at"] >= H2 * 3600:
                    return dict(res=c / e - 1, why=f"потолок {H2} ч", at=at)
        return None

    while t <= now:
        now_ms = int(t * 1000)
        for sym, pos in list(op.items()):
            cl = advance(sym, pos, now_ms)
            if cl:
                closed.append(dict(sym=sym, usd=size * (cl["res"] - fm.FEE), opened=pos["at"], **cl))
                last_exit[sym] = cl["at"]; del op[sym]
        for at, sym, st in sigs:
            if at > t or at <= t - fm.HALF or sym in op or used.get(sym) == st:
                continue
            if t - last_exit.get(sym, 0) < fm.PAUSE:
                continue
            used[sym] = st
            if len(op) >= K:
                continue
            k = pf.klines3(sym, int(at * 1000), int(at * 1000) + 10 * fm.BAR3)
            if not k:
                continue
            op[sym] = dict(px=k[0][1], at=at, chk=(int(at * 1000) // fm.BAR3 + 1) * fm.BAR3, armed=False,
                           last=k[0][1], max=k[0][1], won=False, stop=None)
        t += fm.HALF
    real = sum(c["usd"] for c in closed)
    unreal = sum(size * (p["last"] / p["px"] - 1) for p in op.values())
    won = [c for c in closed if c["why"] in ("цель", "трейл", "ступень") or (c["why"].startswith("потолок"))]
    return dict(n=len(closed), won=len(won), real=real, unreal=unreal, total=real + unreal,
                wins=sorted((round(c["res"] * 100) for c in won), reverse=True), open=len(op))


def main():
    sigs, now = fm.load()
    print(f"{'вариант':22} {'сделок':>6} {'победы':>6} {'взято':>7} {'нереал':>7} {'итог':>7}  ходы победителей, %")
    rows = []
    for mode, T, H2 in [("фикс", None, None)] + [("трейл", T, H2) for T in (0.10, 0.15, 0.20, 0.25) for H2 in (None, 96, 192)] \
                       + [("ступени", None, H2) for H2 in (None, 96, 192)]:
        r = run(sigs, now, mode, T, H2)
        name = mode + (f" {T*100:.0f}%" if T else "") + (f" · потолок {H2} ч" if H2 else "")
        rows.append((name, r))
        print(f"{name:22} {r['n']:>6} {r['won']:>6} {r['real']:>+7.0f} {r['unreal']:>+7.0f} {r['total']:>+7.0f}  {r['wins']}")


if __name__ == "__main__":
    main()
