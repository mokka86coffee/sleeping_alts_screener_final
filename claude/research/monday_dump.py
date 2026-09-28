#!/usr/bin/env python3
"""ПОНЕДЕЛЬНИК-СЛИВ (28.09, владелец 27.09: «завтра понедельник, думаю все сольют вместе с биткоином как всегда — отмечай, чтобы стало правилом»).

Каждый день 30 дней (UTC+3, 00:00–24:00) по 159 монетам архива cq_v2/hist30 (30m) + свежие 30m свечи Binance после конца архива:
  - доска дня: медиана доходности монет за день и по сессиям (Сидней 00–03, Токио 03–10, Лондон 10–16, Нью-Йорк 16–24);
  - доля монет в минусе за день; BTC за день;
  - «монета против себя»: медиана по монетам (доходность дня − медиана дневных доходностей этой монеты за 30 дн).
Понедельники против остальных дней недели. Порогов нет — сравнение рангов и медиан.

    .venv/bin/python claude/research/monday_dump.py        # → monday_dump.md
"""
from __future__ import annotations

import glob
import json
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core_http import get_json  # noqa: E402

L = timezone(timedelta(hours=3))
OUT = Path(__file__).with_name("monday_dump.md")
SES = [("Сидней", 0, 3), ("Токио", 3, 10), ("Лондон", 10, 16), ("Нью-Йорк", 16, 24)]
DOW = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def bars(path: str) -> dict[int, tuple[float, float]]:
    """t → (open, close) по 30m; архив + свежие свечи Binance после его конца"""
    rows = json.load(open(path))
    out = {int(r["t"]): (float(r["o"]), float(r["px"])) for r in rows if r.get("o") and r.get("px")}
    sym = Path(path).stem.upper() + "USDT"
    last = max(out) if out else 0
    k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "30m", "startTime": last + 1800_000, "limit": 200},
                 quiet_400=True) or []
    for x in k:
        if int(x[0]) + 1800_000 <= datetime.now().timestamp() * 1000 + 1800_000:
            out[int(x[0])] = (float(x[1]), float(x[4]))
    return out


def span_ret(b: dict, t0: int, t1: int):
    ks = [t for t in b if t0 <= t < t1]
    if len(ks) < 2:
        return None
    return (b[max(ks)][1] / b[min(ks)][0] - 1) * 100


def main() -> int:
    files = sorted(glob.glob(str(ROOT / "cq_v2" / "hist30" / "*.json")))
    B = {Path(f).stem.upper(): bars(f) for f in files}
    btc = B.pop("BTC", None)
    days = sorted({datetime.fromtimestamp(t / 1000, L).date() for b in B.values() for t in b})
    days = [d for d in days if d > days[0]]                    # первый день архива неполный
    per = defaultdict(dict)                                     # day → coin → ret
    ses = defaultdict(lambda: defaultdict(list))                # day → session → [ret]
    for c, b in B.items():
        for d in days:
            t0 = int(datetime(d.year, d.month, d.day, tzinfo=L).timestamp() * 1000)
            r = span_ret(b, t0, t0 + 86400_000)
            if r is not None:
                per[d][c] = r
            for nm, h0, h1 in SES:
                rs = span_ret(b, t0 + h0 * 3600_000, t0 + h1 * 3600_000)
                if rs is not None:
                    ses[d][nm].append(rs)
    coin_med = {c: st.median([per[d][c] for d in days if c in per[d]]) for c in B if any(c in per[d] for d in days)}
    rows = []
    for d in days:
        v = per[d]
        if len(v) < 50:
            continue
        t0 = int(datetime(d.year, d.month, d.day, tzinfo=L).timestamp() * 1000)
        rows.append(dict(d=d, dow=DOW[d.weekday()], med=st.median(v.values()), neg=sum(1 for x in v.values() if x < 0) / len(v) * 100,
                         rel=st.median(v[c] - coin_med[c] for c in v), btc=span_ret(btc, t0, t0 + 86400_000) if btc else None,
                         ses={nm: (st.median(ses[d][nm]) if ses[d][nm] else None) for nm, _, _ in SES}, n=len(v),
                         full=len(v) and max(t for t in (btc or {})) >= t0 + 86400_000 - 1800_000))
    by = sorted(rows, key=lambda r: r["med"])
    rank = {r["d"]: i + 1 for i, r in enumerate(by)}
    f = lambda x: "—" if x is None else f"{x:+.1f}%"  # noqa: E731
    md = [f"# Понедельник-слив ({datetime.now(L):%d.%m %H:%M})", "",
          f"Дней: {len(rows)} ({rows[0]['d']:%d.%m}–{rows[-1]['d']:%d.%m}), монет {len(B)} (архив cq_v2/hist30 30m + свежие свечи Binance). "
          "Доска — медиана доходности монет за день (UTC+3); «против себя» — медиана (день монеты − её медианный день); ранг 1 — худший день.", "",
          "| день | | доска | в минусе | против себя | BTC | Сидней | Токио | Лондон | Нью-Йорк | ранг из " + str(len(rows)) + " |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['d']:%d.%m} | {r['dow']} | {f(r['med'])} | {r['neg']:.0f}% | {f(r['rel'])} | {f(r['btc'])} | " +
                  " | ".join(f(r['ses'][nm]) for nm, _, _ in SES) + f" | {rank[r['d']]}" + ("" if r["full"] else " (день не кончился)") + " |")
    md += ["", "## По дням недели (медианы по дням)", "", "| день | дней | доска | в минусе | против себя | BTC | худших ¼ |", "|---|---|---|---|---|---|---|"]
    q = len(rows) // 4
    worst = {r["d"] for r in by[:q]}
    for i, nm in enumerate(DOW):
        g = [r for r in rows if r["dow"] == nm]
        if not g:
            continue
        md.append(f"| {nm} | {len(g)} | {f(st.median(r['med'] for r in g))} | {st.median(r['neg'] for r in g):.0f}% | "
                  f"{f(st.median(r['rel'] for r in g))} | {f(st.median(r['btc'] for r in g if r['btc'] is not None))} | "
                  f"{sum(1 for r in g if r['d'] in worst)} из {len(g)} |")
    md += ["", "## Понедельники по сессиям (медиана доски от открытия сессии)", "", "| день | Сидней | Токио | Лондон | Нью-Йорк |", "|---|---|---|---|---|"]
    for r in rows:
        if r["dow"] == "пн":
            md.append(f"| {r['d']:%d.%m} | " + " | ".join(f(r['ses'][nm]) for nm, _, _ in SES) + " |")
    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
