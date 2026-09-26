#!/usr/bin/env python3
"""ДЕНЬГИ «3 В ПЕРВЫХ» ПРИ ДЕПОЗИТЕ (26.09, владелец: «с депозитом 300$ заработал в 20 раз больше, чем бот
с 20000$ … нужно заработать уже»). Вопрос: сколько даёт та же книга, если ей отдать депозит целиком,
а не 500$ на сделку — при K одновременных слотах (размер = депозит / K), стопе до +20% (S) и сроке
удержания (H). Сигналы — те же серии очереди (paper_first3.signals), трёхминутки Binance — те же.
Ничего не выдумываем: правила книги (цель +40%, после +20% стоп в точку входа, пауза 48 ч) как есть.

    python3 claude/research/first3_money.py            # сетка K × S × H, итог в $ и на 10 дней
Кэш трёхминуток — в scratchpad (first3_k3.pkl), чтобы сетку гонять без повторной закачки.
"""
from __future__ import annotations
import os, pickle, sys, time
from pathlib import Path
BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
import paper_first3 as pf                                   # noqa: E402

CACHE = Path(os.environ.get("F3_CACHE", "/private/tmp/claude-501/-Users-evgenijminko-Work-random-python/"
                            "fc3cd797-73bf-4eb8-af7f-09dcc2d4dcc5/scratchpad/first3_k3.pkl"))
DEP = 20_000.0
FEE, BAR3, HALF = pf.FEE, pf.BAR3, pf.HALF
TARGET, BE, PAUSE = pf.FIRST3_TARGET, pf.FIRST3_BE, pf.FIRST3_PAUSE_H * 3600


def load():
    ld = pf.leaders(with_old=True)
    sigs = sorted(pf.signals(ld))
    now = time.time()
    if CACHE.exists():
        pre, sigs0, now0 = pickle.loads(CACHE.read_bytes())
        if sigs0 == sigs:
            pf._PRE.update(pre)
            return sigs, now0
    since = {}
    for a, s, _ in sigs:
        since[s] = min(a, since.get(s, a))
    print(f"сигналов {len(sigs)} по {len(since)} монетам · качаю трёхминутки…", flush=True)
    for s, a in since.items():
        pf._PRE[s] = pf.klines3(s, int(a * 1000) // BAR3 * BAR3, int(now * 1000))
    CACHE.write_bytes(pickle.dumps((dict(pf._PRE), sigs, now)))
    return sigs, now


def run(sigs, now, K, S, H, size=None):
    """K слотов, S — стоп до +20% (доля, None = нет), H — срок в часах (None = нет); size — фикс. размер ($)"""
    size = size or DEP / K
    op, last_exit, used, closed = {}, {}, {}, []
    peak_use = 0
    t = sigs[0][0]

    def advance(sym, pos, now_ms):
        e = pos["px"]
        for tb, o, h, l, c in pf.klines3(sym, pos["chk"], now_ms):
            pos["chk"] = tb + BAR3; pos["last"] = c
            if pos["armed"] and l <= e:
                return dict(res=0.0, why="в ноль", at=(tb + BAR3) / 1000)
            if not pos["armed"] and S is not None and l <= e * (1 - S):
                return dict(res=-S, why=f"стоп −{S*100:.0f}%", at=(tb + BAR3) / 1000)
            if h >= e * (1 + TARGET):
                return dict(res=TARGET, why="цель", at=(tb + BAR3) / 1000)
            if not pos["armed"] and h >= e * (1 + BE):
                pos["armed"] = True
            if H is not None and (tb + BAR3) / 1000 - pos["at"] >= H * 3600:
                return dict(res=c / e - 1, why=f"срок {H} ч", at=(tb + BAR3) / 1000)
        return None

    while t <= now:
        now_ms = int(t * 1000)
        for sym, pos in list(op.items()):
            cl = advance(sym, pos, now_ms)
            if cl:
                closed.append(dict(sym=sym, usd=size * (cl["res"] - FEE), **cl, opened=pos["at"]))
                last_exit[sym] = cl["at"]; del op[sym]
        for at, sym, st in sigs:
            if at > t or at <= t - HALF or sym in op or used.get(sym) == st:
                continue
            if t - last_exit.get(sym, 0) < PAUSE:
                continue
            used[sym] = st
            if len(op) >= K:
                continue
            k = pf.klines3(sym, int(at * 1000), int(at * 1000) + 10 * BAR3)
            if not k:
                continue
            px = k[0][1]
            op[sym] = dict(px=px, at=at, chk=(int(at * 1000) // BAR3 + 1) * BAR3, armed=False, last=px)
            peak_use = max(peak_use, len(op))
        t += HALF
    real = sum(c["usd"] for c in closed)
    unreal = sum(size * (p["last"] / p["px"] - 1) for p in op.values())
    days = (now - sigs[0][0]) / 86400
    won = sum(1 for c in closed if c["res"] >= TARGET - 1e-9)
    lost = sum(1 for c in closed if c["res"] < 0)
    worst_open = min((p["last"] / p["px"] - 1) * 100 for p in op.values()) if op else 0
    return dict(K=K, S=S, H=H, size=size, n=len(closed) + len(op), won=won, zero=len(closed) - won - lost, lost=lost,
                open=len(op), real=real, unreal=unreal, total=real + unreal, per10=(real + unreal) / days * 10,
                worst_open=worst_open, peak=peak_use)


def main():
    sigs, now = load()
    days = (now - sigs[0][0]) / 86400
    print(f"сигналов {len(sigs)} за {days:.1f} дн · депозит {DEP:.0f} $ · цель +{TARGET*100:.0f}% · после +{BE*100:.0f}% стоп в ноль\n")
    base = run(sigs, now, 99, None, None, size=500.0)
    print(f"как сейчас (500 $ на сделку, без лимита): сделок {base['n']} · +40%: {base['won']} · в ноль {base['zero']} · "
          f"висит {base['open']} · итог {base['total']:+.0f} $ ({base['per10']:+.0f} $/10 дн)\n")
    print(f"{'K':>2} {'стоп':>6} {'срок':>6} {'размер':>7} {'сделок':>6} {'+40%':>4} {'ноль':>4} {'стоп':>4} {'висит':>5} "
          f"{'взято $':>8} {'нереал $':>8} {'итог $':>8} {'$/10дн':>7} {'худш.вис':>8}")
    rows = []
    for K in (2, 3, 4, 5, 8):
        for S in (None, 0.10, 0.15, 0.20):
            for H in (None, 48, 96, 192):
                r = run(sigs, now, K, S, H)
                rows.append(r)
                print(f"{K:>2} {('—' if S is None else f'−{S*100:.0f}%'):>6} {('—' if H is None else f'{H} ч'):>6} "
                      f"{r['size']:>7.0f} {r['n']:>6} {r['won']:>4} {r['zero']:>4} {r['lost']:>4} {r['open']:>5} "
                      f"{r['real']:>+8.0f} {r['unreal']:>+8.0f} {r['total']:>+8.0f} {r['per10']:>+7.0f} {r['worst_open']:>+7.0f}%")
    best = sorted(rows, key=lambda r: -r["total"])[:5]
    print("\nлучшие по итогу:")
    for r in best:
        print(f"  K={r['K']} стоп={r['S']} срок={r['H']} → {r['total']:+.0f} $ ({r['per10']:+.0f} $/10 дн), сделок {r['n']}, +40%: {r['won']}, стопов {r['lost']}")


if __name__ == "__main__":
    main()
