#!/usr/bin/env python3
"""ЛАБОРАТОРИЯ ТРЁХМИНУТОК (17.09, владелец: «если можем забрать двое суток сейчас, зачем ждать два часа»).
Читает cq_v2/tick/<монета>.jsonl (tick_fetch) и получасовки из нашего архива cq_v2/intraday. Ничего не пишет,
к бирже не ходит.

Честность: направление на каждую получасовку берётся ТОЛЬКО из того, что было известно на её закрытии —
вортекс и клингер по закрытым получасовкам биржи (те же формулы, что у lab_junctions). Оно действует на
следующие полчаса. Внутри этих получаса — трёхминутки.

Что считает:
  1. ПОПАДАНИЕ НАПРАВЛЕНИЯ — куда цена пошла в следующие полчаса, когда картина сказала «вверх»/«вниз».
  2. ШУМ — сколько волн ≥1%, ≥2%, ≥3% внутри получаса (по максимумам и минимумам трёхминуток), отдельно
     при направлении и без него: это и есть «от одного до десяти за полчаса».
  3. СДЕЛКИ ПО ПРАВИЛУ ВЛАДЕЛЬЦА: в коридоре вверх — только лонги; дно шума = цена отошла от бегущего максимума
     на порог отката и первая трёхминутка закрылась выше предыдущей; вход по её закрытию; выход — лимитка на
     цель (исполнена, если максимум трёхминутки её достиг); вход в минусе не закрывается; закрытие в минус —
     только когда картина показала обратное направление, по открытию первой трёхминутки после этого.
     Зеркально для шортов. Порог отката и цель — перебором: 1, 2, 3% и «шум монеты» (медиана размаха
     последних 8 получасовок).
    python3 lab_tick.py --only ONE
    python3 lab_tick.py --only ONE --trades
    python3 lab_tick.py                       # все монеты из cq_v2/tick
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
import lab_junctions as lj

TICK_DIR = BASE_DIR / "cq_v2" / "tick"
FEE = 0.001                  # комиссия за сделку, доля
BAR30 = 1800


def ticks(base: str) -> list[dict]:
    p = TICK_DIR / f"{base.lower()}.jsonl"
    by = {}
    for line in p.read_text(encoding="utf-8").splitlines() if p.exists() else []:
        try:
            r = json.loads(line)
            t = int(datetime.strptime(r["candle"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
        except (ValueError, KeyError, TypeError):
            continue
        r["t"] = t
        by[t] = r
    return [by[t] for t in sorted(by)]


def bars30(sym: str) -> list[tuple]:
    """закрытые получасовки из НАШЕГО архива (t, h, l, c, оборот): живой cq_v2/intraday плюс дневные gz — те же
    бары, по которым считают боты; к бирже не ходим (17.09, владелец: «в интрадее всё лежит»)"""
    base = sym.upper().replace("USDT", "")
    idx = lj.archive_index({base}, int(datetime.now(timezone.utc).timestamp()) - 30 * 86400)
    out = []
    for t in sorted(idx.get(base) or {}):
        r = idx[base][t]
        if not (r.get("px") and r.get("h") and r.get("l")):
            continue
        f = r.get("fut") or {}
        v = float(f.get("b") or 0) + float(f.get("s") or 0) or float((r.get("kv") or {}).get("qv") or 0)
        out.append((t, float(r["h"]), float(r["l"]), float(r["px"]), v))
    return out


def directions(bars: list[tuple]) -> dict:
    """t закрытия получасовки → направление на следующие полчаса: вортекс и клингер согласны — ±1, иначе 0"""
    vl, kl = lj.vortex_lines(bars), lj.klinger_lines(bars)
    out = {}
    for t, h, l, c, q in bars:
        if t not in vl or t not in kl:
            continue
        p, m = vl[t]
        k, s = kl[t]
        out[t + BAR30] = 1 if (p > m and k > s) else -1 if (m > p and k < s) else 0
    return out


def noise(bars: list[tuple], t: int, n: int = 8) -> float | None:
    """шум монеты на момент t: медиана размаха (h/l − 1) последних n закрытых получасовок"""
    prev = [(h / l - 1) for tb, h, l, c, q in bars if tb + BAR30 <= t][-n:]
    return st.median(prev) if len(prev) >= 3 else None


def swings(rows: list[dict], th: float) -> int:
    """число волн ≥ th внутри окна: зигзаг по максимумам и минимумам трёхминуток"""
    if not rows:
        return 0
    n, hi, lo, dir_ = 0, rows[0]["h"], rows[0]["l"], 0
    for r in rows:
        if dir_ >= 0 and r["h"] > hi:
            hi = r["h"]
        if dir_ <= 0 and r["l"] < lo:
            lo = r["l"]
        if dir_ >= 0 and r["l"] <= hi * (1 - th):
            n += 1; dir_ = -1; lo = r["l"]
        elif dir_ <= 0 and r["h"] >= lo * (1 + th):
            n += 1; dir_ = 1; hi = r["h"]
    return n


def simulate(rows: list[dict], dirs: dict, bars: list[tuple], pull, target) -> list[dict]:
    """сделки по правилу владельца; pull/target — доля или 'auto' (шум монеты)"""
    trades: list[dict] = []
    open_: list[dict] = []
    d_cur, run_hi, run_lo, prev_c = 0, None, None, None
    for r in rows:
        w = (r["t"] // BAR30) * BAR30                 # окно получаса, в котором стоит трёхминутка
        d = dirs.get(w, 0)
        nz = noise(bars, w)
        pl = nz if pull == "auto" else pull
        tg = nz if target == "auto" else target
        if d != d_cur:
            # картина сменилась: обратное направление закрывает всё открытое по открытию первой трёхминутки
            if d == -d_cur and d_cur != 0:
                for p in open_:
                    res = p["side"] * (r["o"] / p["px"] - 1) - FEE
                    trades.append(dict(p, t_out=r["t"], px_out=r["o"], res=res, why="смена направления"))
                open_ = []
            d_cur, run_hi, run_lo = d, r["h"], r["l"]
        # лимитки открытых — по размаху трёхминутки
        still = []
        for p in open_:
            tp = p["px"] * (1 + p["side"] * p["tg"])
            if (p["side"] > 0 and r["h"] >= tp) or (p["side"] < 0 and r["l"] <= tp):
                trades.append(dict(p, t_out=r["t"], px_out=tp, res=p["tg"] - FEE, why="цель лимиткой"))
            else:
                still.append(p)
        open_ = still
        if d_cur != 0 and pl and tg and prev_c is not None:
            run_hi = max(run_hi or r["h"], r["h"])
            run_lo = min(run_lo or r["l"], r["l"])
            if d_cur > 0 and r["l"] <= run_hi * (1 - pl) and r["c"] > prev_c:
                open_.append({"side": 1, "px": r["c"], "t": r["t"], "tg": tg, "pull": pl, "w": w})
                run_hi = r["h"]                                # новый отсчёт отката — от этого входа
            elif d_cur < 0 and r["h"] >= run_lo * (1 + pl) and r["c"] < prev_c:
                open_.append({"side": -1, "px": r["c"], "t": r["t"], "tg": tg, "pull": pl, "w": w})
                run_lo = r["l"]
        prev_c = r["c"]
    for p in open_:
        trades.append(dict(p, t_out=rows[-1]["t"], px_out=rows[-1]["c"], res=p["side"] * (rows[-1]["c"] / p["px"] - 1), why="открыта в конце"))
    return trades


def hm(t: int) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%d.%m %H:%M")


def report_coin(base: str, rows: list[dict], bars: list[tuple], detail: bool) -> dict:
    sym = base.upper() + "USDT"
    dirs = directions(bars)
    wins = sorted({(r["t"] // BAR30) * BAR30 for r in rows})
    wins = [w for w in wins if w in dirs and any(r["t"] >= w + BAR30 for r in rows)]
    print(f"\n{'═' * 8} {base.upper()} · трёхминуток {len(rows)} · {hm(rows[0]['t'])} — {hm(rows[-1]['t'])} · получасовок с картиной {len(wins)}")
    # 1. попадание направления
    for d, nm in ((1, "вверх"), (-1, "вниз"), (0, "нет направления")):
        ws = [w for w in wins if dirs[w] == d]
        if not ws:
            continue
        moves, ups = [], 0
        for w in ws:
            seg = [r for r in rows if w <= r["t"] < w + BAR30]
            if not seg:
                continue
            mv = seg[-1]["c"] / seg[0]["o"] - 1
            moves.append(mv * (d or 1))
            if mv * (d or 1) > 0:
                ups += 1
        if moves:
            print(f"  картина {nm:16s} n={len(moves):3d} · следующие полчаса по картине в {100 * ups / len(moves):3.0f}% · "
                  f"медиана хода {100 * st.median(moves):+.2f}%")
    # 2. шум
    for d, nm in ((1, "вверх"), (-1, "вниз"), (0, "нет")):
        ws = [w for w in wins if dirs[w] == d]
        if not ws:
            continue
        cnt = {th: [swings([r for r in rows if w <= r["t"] < w + BAR30], th) for w in ws] for th in (0.01, 0.02, 0.03)}
        nz = [noise(bars, w) for w in ws]
        nz = [x for x in nz if x]
        print(f"  шум при {nm:6s}: волн за полчаса ≥1% {st.mean(cnt[0.01]):.1f} · ≥2% {st.mean(cnt[0.02]):.1f} · ≥3% {st.mean(cnt[0.03]):.1f}"
              + (f" · размах получасовки медиана {100 * st.median(nz):.2f}%" if nz else ""))
    # 3. сделки — перебор
    print(f"  {'откат':>6s} {'цель':>6s} {'сделок':>7s} {'цель':>6s} {'смена':>6s} {'средний':>8s} {'в плюсе':>8s} {'сумма':>8s}")
    best = None
    for pull in (0.01, 0.02, 0.03, "auto"):
        for target in (0.01, 0.02, 0.03, "auto"):
            tr = simulate(rows, dirs, bars, pull, target)
            if not tr:
                continue
            r_ = [x["res"] for x in tr]
            row = (pull, target, len(tr), sum(1 for x in tr if x["why"].startswith("цель")), sum(1 for x in tr if x["why"].startswith("смена")),
                   st.mean(r_) * 100, 100 * sum(1 for x in r_ if x > 0) / len(r_), sum(r_) * 100)
            print(f"  {(pull if pull == 'auto' else f'{pull * 100:.0f}%'):>6s} {(target if target == 'auto' else f'{target * 100:.0f}%'):>6s} "
                  f"{row[2]:7d} {row[3]:6d} {row[4]:6d} {row[5]:+7.2f}% {row[6]:7.0f}% {row[7]:+7.1f}%")
            if best is None or row[7] > best[7]:
                best = row
    if detail:
        tr = simulate(rows, dirs, bars, "auto", "auto")
        print("  сделки (откат и цель — шум монеты):")
        for x in sorted(tr, key=lambda x: x["t"]):
            print(f"    {'лонг ' if x['side'] > 0 else 'шорт '} {hm(x['t'])} {x['px']:.6g} → {hm(x['t_out'])} {x['px_out']:.6g} · "
                  f"{x['res'] * 100:+.2f}% · {x['why']} · откат {x['pull'] * 100:.1f}% цель {x['tg'] * 100:.1f}%")
    return {"sym": sym, "best": best}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--trades", action="store_true")
    a = ap.parse_args()
    bases = ([x.strip().lower().replace("usdt", "") for x in a.only.split(",")] if a.only
             else sorted(p.stem for p in TICK_DIR.glob("*.jsonl")))
    for b in bases:
        rows = ticks(b)
        if len(rows) < 100:
            print(f"{b.upper()}: трёхминуток мало ({len(rows)})")
            continue
        try:
            bars = bars30(b.upper() + "USDT")
        except Exception as e:  # noqa: BLE001
            print(f"{b.upper()}: получасовки биржи не взялись: {type(e).__name__}: {e}")
            continue
        if len(bars) < 70:
            print(f"{b.upper()}: получасовок мало ({len(bars)})")
            continue
        report_coin(b, rows, bars, a.trades)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
