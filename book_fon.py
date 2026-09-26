#!/usr/bin/env python3
"""ФОН ДЛЯ КНИГ (27.09, владелец: «вход только при фоне, где правило работало»; поля — как в claude/research/trade_context.py).
Считается из архива получасовок cq_v2/intraday по всем монетам архива, один раз за процесс:
  board6 / board24 — медиана хода монет за 6 ч / 24 ч (%), up24 — доля монет в плюсе за 24 ч (%), leader / leader_run48 — лидер 48 ч,
  h_since_break / broken — часы после последнего слома лидера (paper_sight.leader_break_recent), sessions / wd / hour — время UTC+3.
"""
from __future__ import annotations
import statistics as st, time
from datetime import datetime, timezone, timedelta
_CACHE: dict = {}
SES = (("Сидней", 0, 9), ("Токио", 3, 12), ("Лондон", 10, 19), ("Нью-Йорк", 16, 25))
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def fon() -> dict:
    if "v" in _CACHE:
        return _CACHE["v"]
    out: dict = {}
    try:
        from paper_book_base import rows_of, ARCH
        ch6, ch24, lead = [], [], None
        for p in ARCH.glob("*.jsonl"):
            r = rows_of(p.stem.upper() + "USDT")
            if len(r) < 97:
                continue
            c, c6, c24, c48 = float(r[-1]["px"]), float(r[-13]["px"]), float(r[-49]["px"]), float(r[-97]["px"])
            if c6: ch6.append(c / c6 - 1)
            if c24: ch24.append(c / c24 - 1)
            if c48 and (lead is None or c / c48 > lead[1]): lead = (p.stem.upper(), c / c48)
        out.update(board6=round(st.median(ch6) * 100, 2) if ch6 else None, board24=round(st.median(ch24) * 100, 2) if ch24 else None,
                   up24=round(sum(1 for x in ch24 if x > 0) / len(ch24) * 100, 1) if ch24 else None,
                   leader=lead[0] if lead else None, leader_run48=round((lead[1] - 1) * 100, 1) if lead else None)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
    try:
        from paper_sight import leader_break_recent
        lb = leader_break_recent([], 1.0)
        out.update(h_since_break=round((time.time() * 1000 - lb[1]) / 3600_000, 1) if lb else None, broken=lb[0][:-4] if lb else None)
    except Exception:  # noqa: BLE001
        out.update(h_since_break=None, broken=None)
    t = datetime.now(timezone(timedelta(hours=3))); h = t.hour
    out.update(wd=WD[t.weekday()], hour=h, sessions=[n for n, a, b in SES if a <= (h if h >= a else h + 24) < b])
    _CACHE["v"] = out
    return out


def coin_fon(rows: list[dict]) -> dict:
    """состояние монеты на последней получасовке: ход от мин 24 ч, от макс 24 ч, интерес 24 ч, объём часа к среднему часу суток"""
    if len(rows) < 49:
        return {}
    c = float(rows[-1]["px"]); w = rows[-48:]
    lo = min(float(r.get("l") or r["px"]) for r in w); hi = max(float(r.get("h") or r["px"]) for r in w)
    oi0, oi1 = rows[-49].get("oi"), rows[-1].get("oi")
    qv = [float(((r.get("kv") or {}).get("qv")) or 0) for r in w]
    return dict(run24=round((c / lo - 1) * 100, 1) if lo else None, from_hi24=round((c / hi - 1) * 100, 1) if hi else None,
                oi24=round((float(oi1) / float(oi0) - 1) * 100, 1) if oi0 and oi1 else None,
                vol1h_vs_day=round(sum(qv[-2:]) / (sum(qv) / 24), 2) if sum(qv) else None)
