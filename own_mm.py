#!/usr/bin/env python3
"""МОНЕТЫ СО СВОИМ ММ (27.09, владелец: «такое гавно выносить в отдельный список, чтобы бот в них не попадал и чтобы они не ломали
правила; помечать, что у них свой мм со своими стратегиями»; «да» на порог из счёта claude/research/own_life.md).

output/own_mm.json — {at, coins: {SYM: {block, why, flush20, worst, rec_h, corr, handwriting}}}:
  block=True — ≥ OWN_MM_FLUSH_N проколов одной свечой глубже OWN_MM_FLUSH_PCT % за 30 дн (15m, от максимума 2 ч, mm_flush.py): стоп быстрых
               книг −5% такие свечи выбивают; быстрые книги в них не входят (fast_tier), их сделки не идут в счёт правил (fast_days, fast_review);
  block=False — пометка: правила на монете хуже обычного на 20+ п. при ≥ 5 сделках (own_life_stats.json) — «свой ММ», в счёт правил не идёт.
Пересчёт раз в сутки — fast_tier зовёт, если файлу больше OWN_MM_MAX_AGE_H.

    .venv/bin/python own_mm.py
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "claude" / "research"))
import core_config as cc  # noqa: E402

OUT = BASE_DIR / "output" / "own_mm.json"
N = getattr(cc, "OWN_MM_FLUSH_N", 2)
PCT = getattr(cc, "OWN_MM_FLUSH_PCT", 20.0)


def build() -> dict:
    import mm_flush
    syms = mm_flush.universe()
    ev = defaultdict(list)
    with ThreadPoolExecutor(4) as ex:
        for s, k in zip(syms, ex.map(mm_flush.klines, syms)):
            if len(k) > 200:
                ev[s] = mm_flush.events(s, k)
    coins = {}
    for s, g in ev.items():
        deep = [e for e in g if e["depth"] <= -PCT]
        if len(deep) >= N:
            rc = sorted(e["rec_h"] for e in deep if e["rec_h"] is not None)
            rec = rc[len(rc) // 2] if rc else None
            coins[s] = dict(block=True, why=f"{len(deep)} прокола одной свечой глубже {PCT:.0f}% за 30 дн", flush20=len(deep),
                            worst=min(e["depth"] for e in g), rec_h=rec,
                            handwriting=(f"проколы до {min(e['depth'] for e in g):.0f}% одной свечой"
                                         + (f", половину выкупают за {rec} ч" if rec is not None else ", выкупа за 6 ч нет")
                                         + f"; перед проколом ход от минимума суток до +{max((e['run24'] or 0) for e in deep):.0f}%"))
    # пометка по правилам (без запрета): правила на монете хуже обычного на 20+ п. при ≥ 5 сделках
    try:
        rows = json.loads((BASE_DIR / "claude" / "research" / "own_life_stats.json").read_text())["rows"]
        for r in rows:
            if r["n"] >= 5 and r["win"] is not None and r["win"] - r["exp"] <= -20 and r["sym"] not in coins:
                coins[r["sym"]] = dict(block=False, why=f"правила на монете: {r['n']} сделок, в плюс {r['win']}% против обычных {r['exp']}%",
                                       corr=r["corr"], handwriting="свой ММ: наши правила на монете не работают")
    except (OSError, ValueError, KeyError):
        pass
    return dict(at=int(time.time()), rule=f"≥ {N} прокола глубже {PCT:.0f}% за 30 дн (15m)", universe=len(syms), coins=coins)


def load() -> dict:
    try:
        return json.loads(OUT.read_text(encoding="utf-8")).get("coins") or {}
    except (OSError, ValueError):
        return {}


def blocked() -> set:
    return {s for s, v in load().items() if v.get("block")}


if __name__ == "__main__":
    import fcntl
    lk = open(OUT.with_suffix(".lock"), "w")
    try:
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit(0)
    d = build()
    tmp = OUT.with_suffix(".tmp"); tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8"); tmp.replace(OUT)
    b = sorted(s[:-4] for s, v in d["coins"].items() if v["block"]); m = sorted(s[:-4] for s, v in d["coins"].items() if not v["block"])
    print(f"own_mm: запрет {len(b)}: {', '.join(b)}\n        пометка {len(m)}: {', '.join(m)}")
