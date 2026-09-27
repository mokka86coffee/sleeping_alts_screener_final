#!/usr/bin/env python3
"""ПЕРЕВОРОТ ВСПЛЕСКА: РОСТ НА СГОРАНИИ ШОРТОВ ПОД СТЕНУ (28.09, владелец по ENA 27.09 21:51: «продавец затарился и бахнул плиту, чтобы
выше не пошли»; «а почему выходить — просто брать обратную сторону»).

Каждая сделка быстрых книг (всплеск R39 — лонг, перевёрнутый — шорт) с 27.09 07:15 — те же входы, две стороны:
  как было (запись книги) и обратная сторона на тех же барах: цель 5%, стоп 5% (или над/под плитой, если плита ближе), выход — время
  выхода книги. Признаки на входе:
  - интерес на баре всплеска (Binance openInterestHist 5m: бар входа к предыдущему);
  - сгорание шортов вокруг всплеска (поток cq_v2/liq, OKX+Bybit — Binance в потоке нет): $ за −6…+3 мин и отношение к максимуму
    5-минутки этой монеты за прошлые сутки;
  - огромная плита сверху в пределах +5% (output/depth_events.jsonl, фьючерс, последний снимок до входа; журнал с 27.09 16:27):
    $ и доля суточного оборота.
Порогов нет — группы по знаку и квартилям самих данных.

    .venv/bin/python claude/research/spike_flip.py        # → spike_flip.md
"""
from __future__ import annotations

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
OUT = Path(__file__).with_name("spike_flip.md")
T0 = datetime(2026, 9, 27, 7, 15, tzinfo=L).timestamp()
B3 = 180_000


def rows(p: Path):
    out = []
    try:
        for ln in p.open(encoding="utf-8"):
            try:
                out.append(json.loads(ln))
            except ValueError:
                pass
    except OSError:
        pass
    return out


def trades():
    out = []
    for book, f in (("всплеск/вынос", "paper_fast3.jsonl"), ("пробуждение", "paper_wake.jsonl")):
        R = rows(ROOT / "output" / f)
        ent = {(r.get("sym"), round(float(r.get("at") or 0), 3)): r for r in R if r.get("kind") == "entry"}
        for r in R:
            if not str(r.get("kind", "")).startswith("exit") or float(r.get("opened_at") or 0) < T0:
                continue
            e = ent.get((r["sym"], round(float(r["opened_at"]), 3))) or {}
            out.append(dict(book=book, sym=r["sym"], side=int(r.get("side") or 1), px=float(r["px_in"]), t_in=float(r["opened_at"]), t_out=float(r["at"]),
                            res=float(r["result_pct"]), why=r.get("why_exit") or "", flip="перев" in (r.get("rule") or ""), oi1h=e.get("oi1h")))
    return out


def liq_index():
    idx = defaultdict(list)
    for p in sorted((ROOT / "cq_v2" / "liq").glob("2026-09-2*.jsonl")):
        seen = set()
        for r in rows(p):
            k = (r.get("t"), r.get("sym"), r.get("side"), r.get("usd"), r.get("src"))
            if k in seen:
                continue
            seen.add(k)
            idx[r["sym"]].append((int(r["t"]), r.get("side"), float(r.get("usd") or 0)))
    return idx


def walls_index():
    idx = defaultdict(list)
    for r in rows(ROOT / "output" / "depth_events.jsonl"):
        if r.get("kind") == "perp" and r.get("side") == "ask":
            idx[r["sym"]].append(r)
    return idx


def sim(k, e, sd, t_end, tp, sl):
    for x in k:
        if int(x[0]) + B3 > t_end * 1000:
            break
        hi, lo = float(x[2]), float(x[3])
        if sd == 1:
            if lo <= e * (1 - sl): return -sl * 100 - .1
            if hi >= e * (1 + tp): return tp * 100 - .1
        else:
            if hi >= e * (1 + sl): return -sl * 100 - .1
            if lo <= e * (1 - tp): return tp * 100 - .1
    last = [x for x in k if int(x[0]) + B3 <= t_end * 1000]
    return ((float(last[-1][4]) / e - 1) * 100 * sd - .1) if last else None


def main() -> int:
    T = trades(); LQ = liq_index(); WI = walls_index()
    out = []
    for tr in T:
        s, t_in = tr["sym"], tr["t_in"]
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": s, "interval": "3m", "startTime": int(t_in * 1000) // B3 * B3 + B3,
                     "endTime": int(tr["t_out"] * 1000) + B3, "limit": 500}, quiet_400=True, weight=2) or []
        # только то, что известно в момент входа (28.09: прежний счёт брал точку до 5 мин после входа — заглядывал в будущее)
        oi = get_json("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": s, "period": "5m", "endTime": int(t_in * 1000), "limit": 3},
                      quiet_400=True) or []
        ov = [float(x["sumOpenInterest"]) for x in oi if int(x["timestamp"]) <= t_in * 1000]
        oi_bar = round((ov[-1] / ov[-2] - 1) * 100, 2) if len(ov) >= 2 and ov[-2] else None
        oi_fut = get_json("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": s, "period": "5m", "endTime": int(t_in * 1000) + 300_000, "limit": 3},
                          quiet_400=True) or []
        of = [float(x["sumOpenInterest"]) for x in oi_fut]
        oi_after = round((of[-1] / of[-2] - 1) * 100, 2) if len(of) >= 2 and of[-2] else None
        L_ = LQ.get(s, [])
        sq = sum(u for t, sd_, u in L_ if sd_ == "short" and t_in * 1000 - 360_000 <= t <= t_in * 1000 + 180_000)
        prior = defaultdict(float)
        for t, sd_, u in L_:
            if sd_ == "short" and t_in * 1000 - 86400_000 <= t < t_in * 1000 - 360_000:
                prior[t // 300_000] += u
        sq_ratio = round(sq / max(prior.values()), 2) if prior and max(prior.values()) > 0 else (99.0 if sq > 0 else None)
        wall = wall_share = None
        ev = [r for r in WI.get(s, []) if r["t"] / 1000 <= t_in + 60]
        if ev:
            last = max(ev, key=lambda r: r["t"])
            if t_in - last["t"] / 1000 <= 600:
                up = [w for w in last["after"] if 0 < (w.get("dist") or 0) <= 5]
                if up:
                    w = max(up, key=lambda w: w["usd"])
                    wall = dict(px=w["px"], usd=w["usd"], dist=w["dist"]); wall_share = round(w["usd"] / last["qv24"] * 100, 3) if last.get("qv24") else None
        # обратная сторона: стоп за плитой, если плита ближе 5% (для шорта из лонга)
        osd = -tr["side"]
        sl = .05
        if osd == -1 and wall and wall["dist"] < 5:
            sl = min(.05, (wall["dist"] + .3) / 100)
        opp = sim(k, tr["px"], osd, tr["t_out"], .05, sl) if k else None
        sk = get_json("https://api.binance.com/api/v3/klines", {"symbol": s, "interval": "3m", "endTime": int(t_in * 1000), "limit": 10}, quiet_400=True, weight=2) or []
        sk = [x for x in sk if int(x[0]) + B3 <= t_in * 1000]
        spot_buy = round(sum(float(x[10]) for x in sk) / max(1.0, sum(float(x[7]) for x in sk)) * 100, 1) if sk else None
        out.append(dict(tr, spot_buy=spot_buy, oi_bar=oi_bar, oi_after=oi_after, sq=round(sq), sq_ratio=sq_ratio, wall=wall, wall_share=wall_share, opp=opp))
    L_md = [f"# Переворот всплеска — обе стороны ({datetime.now(L):%d.%m %H:%M})", "",
            f"Сделки быстрых книг с 27.09 07:15: {len(out)}. «как было» — запись книги; «обратная» — те же вход и время выхода, цель 5%, стоп 5% "
            "(у шорта из лонга — над плитой, если она ближе). Ликвидации — поток OKX+Bybit (Binance нет); плиты — журнал с 27.09 16:27.", "",
            "| группа | сделок | как было: в плюс · сумма | обратная: в плюс · сумма |", "|---|---|---|---|"]

    def line(lab, g):
        g = [x for x in g if x["opp"] is not None]
        if not g:
            return
        a = [x["res"] for x in g]; b = [x["opp"] for x in g]
        L_md.append(f"| {lab} | {len(g)} | {sum(1 for v in a if v > 0)} · {sum(a):+.1f}% | {sum(1 for v in b if v > 0)} · {sum(b):+.1f}% |")
    longs = [x for x in out if x["side"] == 1]
    line("все лонги-всплески", longs)
    line("все перевёрнутые (шорт)", [x for x in out if x["side"] == -1])
    line("лонг · интерес на баре ≤ 0", [x for x in longs if x["oi_bar"] is not None and x["oi_bar"] <= 0])
    line("лонг · интерес на баре > 0", [x for x in longs if x["oi_bar"] is not None and x["oi_bar"] > 0])
    line("(заглядывание) лонг · интерес через 5 мин после входа ≤ 0", [x for x in longs if x["oi_after"] is not None and x["oi_after"] <= 0])
    line("(заглядывание) лонг · интерес через 5 мин после входа > 0", [x for x in longs if x["oi_after"] is not None and x["oi_after"] > 0])
    line("лонг · интерес за час на входе ≥ +3%", [x for x in longs if x["oi1h"] is not None and x["oi1h"] >= 3])
    line("лонг · интерес за час на входе < +3%", [x for x in longs if x["oi1h"] is not None and x["oi1h"] < 3])
    A = lambda x: (x["oi1h"] is not None and x["oi1h"] >= 3) or (x["oi_bar"] is not None and x["oi_bar"] <= 0)   # noqa: E731
    line("лонг · интерес за час ≥ +3% ИЛИ последний 5-мин бар интереса ≤ 0", [x for x in longs if A(x)])
    line("лонг · остальные", [x for x in longs if not A(x)])
    line("связка · спот покупал 30 мин до входа (> 50%)", [x for x in longs if A(x) and x["spot_buy"] is not None and x["spot_buy"] > 50])
    line("связка · спот продавал 30 мин до входа (≤ 50%)", [x for x in longs if A(x) and x["spot_buy"] is not None and x["spot_buy"] <= 50])
    line("связка · спота нет", [x for x in longs if A(x) and x["spot_buy"] is None])
    for lab, lo, hi in (("до ворот сессий (до 17:26)", 0, datetime(2026, 9, 27, 17, 26, tzinfo=L).timestamp()), ("после ворот сессий", datetime(2026, 9, 27, 17, 26, tzinfo=L).timestamp(), 9e12)):
        line(f"{lab} · связка", [x for x in longs if A(x) and lo <= x["t_in"] < hi])
        line(f"{lab} · остальные", [x for x in longs if not A(x) and lo <= x["t_in"] < hi])
    line("лонг · шорты горели (есть в потоке)", [x for x in longs if x["sq"] > 0])
    line("лонг · шорты не горели", [x for x in longs if x["sq"] == 0])
    line("лонг · сгорание ≥ максимума 5 мин за сутки", [x for x in longs if x["sq_ratio"] is not None and x["sq_ratio"] >= 1])
    ws = sorted(x["wall_share"] for x in longs if x["wall_share"] is not None)
    if ws:
        q3 = ws[int(len(ws) * .75)] if len(ws) >= 4 else ws[-1]
        line(f"лонг · плита сверху в 5% есть (журнал)", [x for x in longs if x["wall"]])
        line(f"лонг · плиты сверху в 5% нет (журнал)", [x for x in longs if x["wall"] is None and x["t_in"] >= datetime(2026, 9, 27, 16, 27, tzinfo=L).timestamp()])
        line(f"лонг · плита ≥ {q3:.3f}% оборота (верхняя четверть)", [x for x in longs if x["wall_share"] is not None and x["wall_share"] >= q3])
    line("лонг · интерес ≤ 0 и шорты горели", [x for x in longs if x["oi_bar"] is not None and x["oi_bar"] <= 0 and x["sq"] > 0])
    L_md += ["", "## Сделки", "", "| вход | монета | книга | сторона | итог | обратная | интерес на баре | шорты сгорели $ (к макс. суток) | плита сверху |",
             "|---|---|---|---|---|---|---|---|---|"]
    for x in sorted(out, key=lambda x: x["t_in"]):
        w = f"{x['wall']['px']:.5g} +{x['wall']['dist']:.1f}% ${x['wall']['usd'] / 1e3:.0f}K ({x['wall_share']}%)" if x["wall"] else "—"
        L_md.append(f"| {datetime.fromtimestamp(x['t_in'], L):%d.%m %H:%M} | {x['sym'][:-4]} | {x['book']} | {'лонг' if x['side'] == 1 else 'шорт'} | {x['res']:+.1f}% | "
                    f"{(format(x['opp'], '+.1f') + '%') if x['opp'] is not None else '—'} | {x['oi_bar'] if x['oi_bar'] is not None else '—'} | "
                    f"{x['sq']} ({x['sq_ratio']}) | {w} |")
    OUT.write_text("\n".join(L_md) + "\n", encoding="utf-8")
    print("\n".join(L_md[:18]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
