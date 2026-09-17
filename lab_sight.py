#!/usr/bin/env python3
"""ЛАБОРАТОРИЯ «КАРТИНЫ» (17.09, владелец: «куда внедрять сразу — есть выборка за две недели, давай на ней проверять»).
Гоняет ПРАВИЛА paper_sight по архиву получасовок за --days дней (живые файлы cq_v2/intraday и дневные gz) — те же
голоса (votes_at), тот же выход и хедж (step). Ничего не пишет, только считает.

Фон на каждом баре — из самого архива: медиана хода доски за сутки и доля растущих по всем монетам архива,
биткоин за час — из btc.jsonl. Норма дельты для пузыря — по всей истории монеты в окне (у бота — по живому файлу).

Разрезы: всего и по стороне · по каждому голосу (когда он за / против / молчит при входе) · по числу голосов ·
по сессии входа · по дню · хеджи (сколько, что дали) · сравнение порогов SIGHT_MIN_SCORE и SIGHT_HEDGE_PCT.
    python3 lab_sight.py --days 14
    python3 lab_sight.py --days 14 --only AVA,LSK --trades     # каждая сделка строкой
"""
from __future__ import annotations

import argparse
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
import lab_junctions as lj
import paper_sight as ps

BAR = 1800


def load(days: int, only: set | None) -> dict:
    """база → список строк архива по свечам (с полем t в мс, как у бота)"""
    since = int(datetime.now(timezone.utc).timestamp()) - days * 86400
    idx = lj.archive_index(only, since)
    out = {}
    for base, by in idx.items():
        rows = []
        for t in sorted(by):
            r = by[t]
            if r.get("px") and r.get("h") and r.get("l"):
                r = dict(r, t=t * 1000)
                rows.append(r)
        if len(rows) >= ps.SIGHT_MIN_BARS + 8:
            out[base] = rows
    return out


def board_series(data: dict) -> dict:
    """t мс → (медиана хода за сутки по доске, доля растущих) — тем же способом, что market_bg, но из архива"""
    closes = {b: {r["t"]: float(r["px"]) for r in rows} for b, rows in data.items()}
    ts = sorted({t for c in closes.values() for t in c})
    out = {}
    for t in ts:
        moves = []
        for c in closes.values():
            p1, p0 = c.get(t), c.get(t - 48 * BAR * 1000)
            if p1 and p0:
                moves.append(p1 / p0 - 1)
        if len(moves) >= 20:
            out[t] = (st.median(moves) * 100, sum(1 for m in moves if m > 0) / len(moves))
    return out


def btc_series(data: dict) -> dict:
    c = {r["t"]: float(r["px"]) for r in data.get("BTC", [])}
    return {t: (p / c[t - 2 * BAR * 1000] - 1) * 100 for t, p in c.items() if c.get(t - 2 * BAR * 1000)}


def sess(t_ms: int) -> str:
    h = datetime.fromtimestamp(t_ms / 1000, timezone.utc).hour
    return "Сидней" if 21 <= h or h < 0 else "Токио" if h < 7 else "Лондон" if h < 13 else "Нью-Йорк"


def replay(data: dict, board: dict, btc: dict, min_score: int, hedge_pct: float, max_per_run: int,
           hold: int | None = None, target: float | None = None, drop: set | None = None) -> list[dict]:
    """сделки по всем монетам: вход по согласию, выходы по step(); лимит на прогон — по сумме голосов.
    hold / target — срок и цель вместо SIGHT_*; drop — голоса, которые не считаются (проверка «а без него?»)"""
    ps.SIGHT_MIN_SCORE, ps.SIGHT_HEDGE_PCT = min_score, hedge_pct
    if hold:
        ps.SIGHT_HOLD_BARS = hold
    if target:
        ps.SIGHT_TARGET = target
    drop = drop or set()
    S = {b: ps.series(rows) for b, rows in data.items()}
    ts = sorted({r["t"] for rows in data.values() for r in rows})
    pos: dict = {}
    trades: list[dict] = []
    idx = {b: {r["t"]: i for i, r in enumerate(rows)} for b, rows in data.items()}
    for t in ts:
        bg_m = board.get(t)
        bg = {"median": bg_m[0] if bg_m else None, "share": bg_m[1] if bg_m else None, "btc_h1": btc.get(t)}
        cands = []
        for b, rows in data.items():
            i = idx[b].get(t)
            if i is None:
                continue
            v = ps.votes_at(i, rows, S[b], bg)
            if v and drop:
                v = {k: x for k, x in v.items() if k not in drop}
            p = pos.get(b)
            if p:
                for e in ps.step(p, rows[:i + 1], v, 0):
                    if e["kind"] == "hedge":
                        p["n_hedge"] = p.get("n_hedge", 0) + 1
                if p.get("closed"):
                    trades.append({"sym": b, "side": p["side"], "t_in": p["t"], "t_out": t, "px": p["px"],
                                   "res": p["closed"]["res"] * 100, "why": p["closed"]["why"], "votes": p["votes"],
                                   "score": sum(p["votes"].values()), "hedges": p.get("n_hedge", 0),
                                   "hedge_res": sum(h.get("res", 0) for h in p.get("hedges") or []) * 100,
                                   "bars": p["bars"], "sess": sess(p["t"]), "day": datetime.fromtimestamp(p["t"] / 1000, timezone.utc).strftime("%m-%d")})
                    del pos[b]
                continue
            if v is None:
                continue
            s = ps.side_of(v)
            if s:
                cands.append((abs(sum(v.values())), b, s, v, float(rows[i]["px"])))
        cands.sort(key=lambda x: -x[0])
        for _, b, s, v, px in cands[:max_per_run]:
            pos[b] = {"side": s, "t": t, "px": px, "size": 1.0, "hedges": [], "bars": 0, "last_t": t, "votes": v}
    return trades


def _line(name: str, v: list[dict]) -> str:
    if not v:
        return f"{name:26s} n=0"
    r = [x["res"] for x in v]
    hit = 100 * sum(1 for x in r if x > 0) / len(r)
    return (f"{name:26s} n={len(v):4d} · средний {st.mean(r):+.2f}% · медиана {st.median(r):+.2f}% · в плюсе {hit:.0f}% · "
            f"сумма {sum(r):+.1f}% · хеджей на сделку {st.mean([x['hedges'] for x in v]):.1f}")


def report(trades: list[dict], detail: bool) -> None:
    if not trades:
        print("сделок нет")
        return
    print(_line("ВСЕ", trades))
    for s, nm in ((1, "лонги"), (-1, "шорты")):
        print(_line("  " + nm, [x for x in trades if x["side"] == s]))
    print("\nпо выходу:")
    for why in sorted({x["why"].split(" на баре")[0].split(" ")[0] for x in trades}):
        print(_line("  " + why, [x for x in trades if x["why"].startswith(why)]))
    print("\nпо голосу при входе (голос за сторону сделки / против / молчит):")
    keys = sorted({k for x in trades for k in x["votes"]})
    for k in keys:
        za = [x for x in trades if x["votes"].get(k, 0) * x["side"] > 0]
        pr = [x for x in trades if x["votes"].get(k, 0) * x["side"] < 0]
        ml = [x for x in trades if x["votes"].get(k, 0) == 0]
        print(f"  {k:10s} за: {(_line('', za)[27:]) if za else 'n=0'}")
        print(f"  {'':10s} молчит: {(_line('', ml)[27:]) if ml else 'n=0'}")
        if pr:
            print(f"  {'':10s} против: {_line('', pr)[27:]}")
    print("\nпо числу голосов:")
    for n in sorted({abs(x["score"]) for x in trades}):
        print(_line(f"  {n} голосов", [x for x in trades if abs(x["score"]) == n]))
    print("\nпо сессии входа:")
    for s_ in ("Сидней", "Токио", "Лондон", "Нью-Йорк"):
        print(_line("  " + s_, [x for x in trades if x["sess"] == s_]))
    print("\nпо дню входа:")
    for d in sorted({x["day"] for x in trades}):
        print(_line("  " + d, [x for x in trades if x["day"] == d]))
    hs = [x for x in trades if x["hedges"]]
    print(f"\nхеджи: сделок с хеджем {len(hs)} из {len(trades)} · хеджей всего {sum(x['hedges'] for x in trades)} · "
          f"хеджи дали в сумме {sum(x['hedge_res'] for x in trades):+.1f}% · сделки с хеджем: {_line('', hs)[27:] if hs else 'n=0'}")
    by = defaultdict(list)
    for x in trades:
        by[x["sym"]].append(x)
    worst = sorted(by.items(), key=lambda kv: sum(t["res"] for t in kv[1]))
    print("\nхудшие монеты: " + " · ".join(f"{k} {sum(t['res'] for t in v):+.1f}% ({len(v)})" for k, v in worst[:5]))
    print("лучшие монеты: " + " · ".join(f"{k} {sum(t['res'] for t in v):+.1f}% ({len(v)})" for k, v in worst[-5:][::-1]))
    if detail:
        print("\nсделки:")
        for x in sorted(trades, key=lambda x: x["t_in"]):
            hm = lambda t: datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%d.%m %H:%M")
            print(f"  {x['sym']:8s} {'лонг ' if x['side'] > 0 else 'шорт '} {hm(x['t_in'])} → {hm(x['t_out'])} · {x['res']:+6.2f}% · "
                  f"{x['why'][:22]:22s} · хеджей {x['hedges']} · {ps._txt(x['votes'])}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--only")
    ap.add_argument("--trades", action="store_true")
    ap.add_argument("--min-score", type=int, default=ps.SIGHT_MIN_SCORE)
    ap.add_argument("--hedge", type=float, default=ps.SIGHT_HEDGE_PCT)
    ap.add_argument("--max-per-run", type=int, default=ps.SIGHT_MAX_PER_RUN)
    ap.add_argument("--hold", type=int, default=0, help="срок в барах вместо SIGHT_HOLD_BARS")
    ap.add_argument("--target", type=float, default=0.0, help="цель долей вместо SIGHT_TARGET, например 0.02")
    ap.add_argument("--drop", default="", help="голоса, которые не считать, через запятую: доска,тейкер")
    ap.add_argument("--hedge-by", default="", choices=["", "close", "range"], help="хедж по закрытию бара или по триггеру внутри бара")
    ap.add_argument("--sweep", action="store_true", help="сравнить пороги голосов 3..6 и хеджа 1, 1.5, 2 и 3 процента")
    ap.add_argument("--sweep-hold", action="store_true", help="сравнить пороги голосов 3..6 и срок 6, 12, 24, 48 баров")
    a = ap.parse_args()
    only = {x.strip().upper().replace("USDT", "") for x in a.only.split(",")} if a.only else None
    all_data = load(a.days, None if (only is None or "BTC" in only) else only | {"BTC"})
    data = all_data if only is None else {b: r for b, r in all_data.items() if b in only}
    print(f"монет {len(data)} · баров {sum(len(r) for r in data.values())} · окно {a.days} дн")
    board, btc = board_series(all_data), btc_series(all_data)
    print(f"фон: баров с доской {len(board)} · с биткоином {len(btc)}")
    drop = {x.strip() for x in a.drop.split(",") if x.strip()}
    if a.hedge_by:
        ps.SIGHT_HEDGE_BY = a.hedge_by
    if a.sweep_hold:
        print(f"\n{'порог голосов':>14s} {'срок':>6s} {'сделок':>7s} {'средний':>8s} {'в плюсе':>8s} {'сумма':>8s} {'по сроку':>9s} {'хеджей':>7s}")
        for ms in (3, 4, 5, 6):
            for hd in (6, 12, 24, 48):
                tr = replay(data, board, btc, ms, a.hedge, a.max_per_run, hold=hd, target=a.target or None, drop=drop)
                if not tr:
                    print(f"{ms:14d} {hd:6d} {0:7d}")
                    continue
                r = [x["res"] for x in tr]
                print(f"{ms:14d} {hd:6d} {len(tr):7d} {st.mean(r):+7.2f}% {100 * sum(1 for x in r if x > 0) / len(r):7.0f}% "
                      f"{sum(r):+7.1f}% {sum(1 for x in tr if x['why'].startswith('срок')):9d} {sum(x['hedges'] for x in tr):7d}")
        return 0
    if a.sweep:
        print(f"\n{'порог голосов':>14s} {'хедж':>6s} {'сделок':>7s} {'средний':>8s} {'в плюсе':>8s} {'сумма':>8s} {'хеджей':>7s}")
        for ms in (3, 4, 5, 6):
            for hp in (0.01, 0.015, 0.02, 0.03):
                tr = replay(data, board, btc, ms, hp, a.max_per_run, hold=a.hold or None, target=a.target or None, drop=drop)
                if not tr:
                    print(f"{ms:14d} {hp * 100:5.1f}% {0:7d}")
                    continue
                r = [x["res"] for x in tr]
                print(f"{ms:14d} {hp * 100:5.1f}% {len(tr):7d} {st.mean(r):+7.2f}% {100 * sum(1 for x in r if x > 0) / len(r):7.0f}% "
                      f"{sum(r):+7.1f}% {sum(x['hedges'] for x in tr):7d}")
        return 0
    trades = replay(data, board, btc, a.min_score, a.hedge, a.max_per_run, hold=a.hold or None, target=a.target or None, drop=drop)
    print(f"порог голосов {a.min_score} · хедж при −{a.hedge * 100:.1f}% ({'по триггеру' if ps.SIGHT_HEDGE_BY == 'range' else 'по закрытию'}) · "
          f"цель {ps.SIGHT_TARGET * 100:.0f}% лимиткой · срок {ps.SIGHT_HOLD_BARS} баров"
          + (f" · без голосов: {', '.join(sorted(drop))}" if drop else "") + "\n")
    report(trades, a.trades)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
