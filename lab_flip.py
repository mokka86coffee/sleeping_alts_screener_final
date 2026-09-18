#!/usr/bin/env python3
"""ПЕРЕВОРОТ ПО ТРЁХМИНУТКАМ (17.09, владелец). Правило, как сказано:
  • по всем монетам сразу лонг по закрытию свечи;
  • следующая свеча: позиция в минусе (закрытие хуже входа) — закрыть и взять противоположную;
  • цель +3% — лимитка, исполнена, когда размах свечи её достиг; после цели снова ЛОНГ;
  • шорт — зеркально: в минусе — закрыть, взять лонг; цель −3% — закрыть, взять лонг.
Ничего больше. Комиссия FEE за каждое закрытие; рядом печатается результат без комиссии — чтобы было видно,
где механика, а где цена переворотов. Читает cq_v2/tick, ничего не пишет.
    python3 lab_flip.py                 # все монеты
    python3 lab_flip.py --only ONE --trades
    python3 lab_flip.py --target 0.02 --fee 0.0005
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent

TICK_DIR = BASE_DIR / "cq_v2" / "tick"


def ticks(p: Path) -> list[dict]:
    by = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            t = int(datetime.strptime(r["candle"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
        except (ValueError, KeyError, TypeError):
            continue
        r["t"] = t
        by[t] = r
    return [by[t] for t in sorted(by)]


def run(rows: list[dict], target: float, fee: float, tol=0.0, bars: int = 1) -> list[dict]:
    """tol — порог переворота: доля или 'auto' (медиана размаха трёхминуток монеты, шум); bars — сколько свечей
    против подряд нужно для переворота (17.09: переворот на первой же свече — это шум, 89% сделок в минус)"""
    if tol == "auto":
        rng = sorted(float(r["h"]) / float(r["l"]) - 1 for r in rows if float(r["l"]) > 0)
        tol = rng[len(rng) // 2] if rng else 0.0
    trades = []
    side, e, t_in, against = 1, float(rows[0]["c"]), rows[0]["t"], 0
    for r in rows[1:]:
        h, l, c = float(r["h"]), float(r["l"]), float(r["c"])
        tp = e * (1 + side * target)
        hit = (h >= tp) if side > 0 else (l <= tp)
        if hit:
            trades.append({"side": side, "t_in": t_in, "px_in": e, "t_out": r["t"], "px_out": tp, "res": target - fee, "why": "цель"})
            side, e, t_in, against = 1, c, r["t"], 0           # после цели — снова лонг
            continue
        res = side * (c / e - 1)
        against = against + 1 if res < -tol else 0
        if against >= bars:
            trades.append({"side": side, "t_in": t_in, "px_in": e, "t_out": r["t"], "px_out": c, "res": res - fee, "why": "переворот"})
            side, e, t_in, against = -side, c, r["t"], 0
    return trades


def line(name: str, tr: list[dict], fee: float) -> str:
    if not tr:
        return f"{name:10s} сделок нет"
    r = [x["res"] for x in tr]
    r0 = [x["res"] + fee for x in tr]
    tg = [x for x in tr if x["why"] == "цель"]
    fl = [x for x in tr if x["why"] == "переворот"]
    return (f"{name:10s} сделок {len(tr):5d} · цель {len(tg):4d} · переворотов {len(fl):5d} · средний переворот {100 * st.mean([x['res'] + fee for x in fl]) if fl else 0:+.2f}% · "
            f"итог с комиссией {100 * sum(r):+8.1f}% · без комиссии {100 * sum(r0):+8.1f}% · в плюсе {100 * sum(1 for x in r if x > 0) / len(r):.0f}%")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--target", type=float, default=0.03)
    ap.add_argument("--fee", type=float, default=0.001, help="комиссия за закрытие, доля")
    ap.add_argument("--trades", action="store_true")
    ap.add_argument("--tol", default="0", help="порог переворота: доля (0.005) или auto — шум монеты")
    ap.add_argument("--bars", type=int, default=1, help="свечей против подряд для переворота")
    a = ap.parse_args()
    tol = "auto" if a.tol == "auto" else float(a.tol)
    bases = ([x.strip().lower().replace("usdt", "") for x in a.only.split(",")] if a.only
             else sorted(p.stem for p in TICK_DIR.glob("*.jsonl")))
    allt = []
    per = []
    for b in bases:
        p = TICK_DIR / f"{b}.jsonl"
        if not p.exists():
            continue
        rows = ticks(p)
        if len(rows) < 100:
            continue
        tr = run(rows, a.target, a.fee, tol, a.bars)
        allt += tr
        per.append((sum(x["res"] for x in tr), b, tr))
        if a.trades:
            hm = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%d.%m %H:%M")
            for x in tr:
                print(f"  {b.upper():8s} {'лонг ' if x['side'] > 0 else 'шорт '} {hm(x['t_in'])} {x['px_in']:.6g} → {hm(x['t_out'])} {x['px_out']:.6g} · {100 * x['res']:+.2f}% · {x['why']}")
    per.sort(key=lambda x: -x[0])
    print(f"цель {a.target * 100:.0f}% · комиссия {a.fee * 100:.2f}% за закрытие · порог переворота {a.tol} · свечей против {a.bars} · монет {len(per)}")
    for s, b, tr in per:
        print(line(b.upper(), tr, a.fee))
    print("\n" + line("ВСЕГО", allt, a.fee))
    fl = [x for x in allt if x["why"] == "переворот"]
    if fl:
        print(f"переворотов на монету в сутки: {len(fl) / max(1, len(per)) / 2:.0f} · медиана минуса переворота {100 * st.median([x['res'] + a.fee for x in fl]):+.2f}% · "
              f"дней {2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
