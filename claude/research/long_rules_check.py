#!/usr/bin/env python3
"""ЛОНГИ БОТА НА ПРАВИЛАХ ВЫХОДА БОТА (29.09, владелец: «ты не считал, но предлагаешь правило»). Не задним числом: выход так, как его
делает бот после правок 28.09 — стоп / вынос шортов с входа (fuel_exit: крупнейший часовой вынос шортов за историю монеты, только в плюсе) /
срок (час выхода следующей сессии, R41 через стык). Ликвидации — Coinglass (все биржи, 15m → по часам, история ~10 дн до входа).

Варианты стопа: −5% (как сейчас) · «−5%, но не выше начала пампа» (начало пампа = минимум часа до входа).
Отдельно: лонги, где на входе уже вынесли шорты (вынос с начала прошлой сессии ≥ крупнейшего часа истории — как _flush в боте).

    .venv/bin/python claude/research/long_rules_check.py
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
L = timezone(timedelta(hours=3))
SES = (("Сидней", 0, 3), ("Токио", 3, 10), ("Лондон", 10, 16), ("Нью-Йорк", 16, 24))
EXIT_H = {"Сидней": 10, "Токио": 10, "Лондон": 16, "Нью-Йорк": 24}          # FAST3_SES_EXIT_H


def ses_end(t: float) -> float:
    """час выхода следующей сессии после стыка (как ses_gate с side)"""
    d = datetime.fromtimestamp(t, L)
    name = next(n for n, a, b in SES if a <= d.hour < b)
    end = d.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=EXIT_H[name])
    nn = next(n for n, a, b in SES if a <= end.hour < b)
    end2 = end.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=EXIT_H[nn])
    if end2 <= end:
        end2 += timedelta(days=1)
    return end2.timestamp()


def clean(v):
    return v if isinstance(v, (int, float)) and v == v else 0.0


def main() -> int:
    T = [x for x in json.load(open(HERE / "cgr" / "trades.json")) if x["side"] == 1]
    res: dict = {}
    for x in T:
        f = HERE / "cgx" / f"{x['sym']}_15.json"
        if not f.exists():
            continue
        R = [r for r in json.load(open(f))["rows"] if r.get("c")]
        hs: dict = {}
        for r in R:
            h = int(r["t"] // 3600 * 3600); hs[h] = hs.get(h, 0) + clean(r.get("liq_short"))
        t0, e = x["t_in"], x["px_in"]
        h0 = int(t0 // 3600 * 3600)
        past = [v for h, v in hs.items() if h < h0]
        if not past or h0 - min(hs) < 3 * 86400:
            continue
        top = max(past)
        d = datetime.fromtimestamp(t0, L)
        i = next(j for j, s in enumerate(SES) if s[1] <= d.hour < s[2])
        pa = SES[i - 1][1]
        w0 = (d.replace(hour=pa, minute=0, second=0, microsecond=0) - (timedelta(days=1) if i == 0 else timedelta(0))).timestamp()
        pre = [v for h, v in hs.items() if w0 <= h < h0 + 3600 and h <= t0]
        sq = bool(pre) and max(pre) >= top > 0                        # на входе уже вынесли шорты (как _flush)
        start = min((r["l"] for r in R if t0 - 3600 - 900 <= r["t"] < t0), default=e)
        end = ses_end(t0)
        W = [r for r in R if t0 < r["t"] and r["t"] + 900 <= end + 900]

        def run(stop_px: float) -> float:
            for r in W:
                if r["l"] <= stop_px:
                    return (stop_px / e - 1) * 100
                h = int(r["t"] // 3600 * 3600)
                if hs.get(h, 0) >= top and r["c"] > e and h >= h0:     # вынос шортов ≥ крупнейшего часа истории, в плюсе
                    return (r["c"] / e - 1) * 100
            return ((W[-1]["c"] if W else e) / e - 1) * 100

        V = {"стоп −5%": run(e * 0.95), "стоп −5%, но не выше начала пампа": run(min(e * 0.95, start * 0.999))}
        for k, v in V.items():
            for g in ("все", "на входе вынесли шорты" if sq else "без выноса на входе"):
                res.setdefault((g, k), []).append(v)
        res.setdefault(("все", "факт бота"), []).append(x["res"])
        res.setdefault(("на входе вынесли шорты" if sq else "без выноса на входе", "факт бота"), []).append(x["res"])
    for (g, k), v in sorted(res.items()):
        print(f"{g:24} {k:36} n={len(v):2} плюс={sum(1 for z in v if z > 0):2} сумма={sum(v):+7.1f}% ({sum(v) * 5:+.0f}$) худшая={min(v):+.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
