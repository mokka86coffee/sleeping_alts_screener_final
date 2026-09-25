#!/usr/bin/env python3
"""ВЕРШИНЫ ХОДОВ — ЕСТЬ ЛИ ПРИЗНАК В МОМЕНТ ВЕРШИНЫ (25.09, владелец после ARK 14.09 и PLAY 25.09: «меряй»).

На двух вершинах было одно и то же: за последние час-полтора интерес резко растёт, фандинг на крайности, после
вершины интерес падает быстрее цены; у ARK ещё развернулись топ-трейдеры. Здесь — по всем монетам архива за
последние 30 суток (предел истории интереса и топ-трейдеров у Binance): отделяют ли эти признаки вершину от
продолжения.

Бары: монета «в ходу» по правилу проекта — закрытие получасовки на PUMP_JUMP_PCT и больше выше минимума
последних суток. Признаки на баре (всё известно на его закрытии):
  • oi_bar — изменение интереса за бар, %;   oi_1h — за два бара;
  • fund — последняя выплаченная ставка фандинга, %;
  • top_2h — изменение соотношения лонгов к шортам у топ-трейдеров за 4 бара;
  • oi_vs_px — изменение интереса за бар минус изменение цены за бар (интерес уходит быстрее цены — минус).
Исход — по следующим HORIZON_BARS барам: ход закрытия, доля «упала на DROP_PCT и больше», доля «выросла ещё на
DROP_PCT и больше» (по максимуму). Горизонт и DROP_PCT — мои числа для лаборатории, не правила.
Признак делится на трети по распределению самих баров «в ходу» — границы из данных, не мои.

    .venv/bin/python lab_tops.py --fetch     # скачать 30 суток по монетам cq_v2/intraday в cq_v2/hist/tops/
    .venv/bin/python lab_tops.py             # посчитать
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
try:
    from core_config import PUMP_JUMP_PCT
except ImportError:
    PUMP_JUMP_PCT = 40.0

CACHE = BASE_DIR / "cq_v2" / "hist" / "tops"
BAR = 1800_000
DAYS = 30
HORIZON_BARS = 24          # 12 часов
DROP_PCT = 10.0


def _page(url: str, params: dict, key: str, step: int, weight: int = 1) -> list:
    from core_http import get_json
    out, st_ = [], params["startTime"]
    end = params["endTime"]
    while st_ < end:
        p = dict(params, startTime=st_, endTime=min(end, st_ + step))
        rows = get_json(url, p, weight=weight) or []
        out += rows
        st_ += step
    seen, res = set(), []
    for r in out:
        t = int(r[key] if isinstance(r, dict) else r[0])
        if t not in seen:
            seen.add(t)
            res.append(r)
    return res


def fetch_one(sym: str) -> str:
    from core_config import BINANCE_FAPI
    now = int(time.time() * 1000) // BAR * BAR
    s = now - DAYS * 86400_000
    kl = _page(f"{BINANCE_FAPI}/fapi/v1/klines", {"symbol": sym, "interval": "30m", "startTime": s, "endTime": now,
                                                  "limit": 1500}, "t", 1400 * BAR, weight=10)
    oi = _page(f"{BINANCE_FAPI}/futures/data/openInterestHist", {"symbol": sym, "period": "30m", "startTime": s,
                                                                 "endTime": now, "limit": 500}, "timestamp", 480 * BAR)
    top = _page(f"{BINANCE_FAPI}/futures/data/topLongShortPositionRatio", {"symbol": sym, "period": "30m",
                                                                           "startTime": s, "endTime": now, "limit": 500},
                "timestamp", 480 * BAR)
    fu = _page(f"{BINANCE_FAPI}/fapi/v1/fundingRate", {"symbol": sym, "startTime": s - 86400_000, "endTime": now,
                                                       "limit": 1000}, "fundingTime", (DAYS + 2) * 86400_000)
    CACHE.mkdir(parents=True, exist_ok=True)
    data = {"kl": [[int(k[0]), float(k[2]), float(k[3]), float(k[4])] for k in kl if int(k[0]) + BAR <= now],
            "oi": {int(x["timestamp"]): float(x["sumOpenInterestValue"]) for x in oi},
            "top": {int(x["timestamp"]): float(x["longShortRatio"]) for x in top},
            "fund": sorted((int(x["fundingTime"]), float(x["fundingRate"]) * 100) for x in fu)}
    (CACHE / f"{sym}.json").write_text(json.dumps(data), encoding="utf-8")
    return f"{sym} {len(data['kl'])}/{len(data['oi'])}/{len(data['top'])}/{len(data['fund'])}"


def bars_of(data: dict, sym: str) -> list[dict]:
    kl, oi, top, fund = data["kl"], data["oi"], data["top"], data["fund"]
    out = []
    fi = 0
    for i, (t, h, l, c) in enumerate(kl):
        close_t = t + BAR
        while fi < len(fund) and fund[fi][0] <= close_t:
            fi += 1
        row = dict(sym=sym, t=t, h=h, l=l, c=c, oi=oi.get(close_t) or oi.get(t), top=top.get(close_t) or top.get(t),
                   fund=fund[fi - 1][1] if fi else None)
        out.append(row)
    return out


def features(b: list[dict], i: int) -> dict | None:
    if i < 48 or i + HORIZON_BARS >= len(b):
        return None
    low24 = min(x["l"] for x in b[i - 48:i + 1])
    if b[i]["c"] < low24 * (1 + PUMP_JUMP_PCT / 100):
        return None

    def ch(a, z):
        return (a / z - 1) * 100 if (a and z) else None
    f = dict(oi_bar=ch(b[i]["oi"], b[i - 1]["oi"]), oi_1h=ch(b[i]["oi"], b[i - 2]["oi"]), fund=b[i]["fund"],
             top_2h=ch(b[i]["top"], b[i - 4]["top"]))
    px_bar = ch(b[i]["c"], b[i - 1]["c"])
    f["oi_vs_px"] = (f["oi_bar"] - px_bar) if (f["oi_bar"] is not None and px_bar is not None) else None
    fw = b[i + 1:i + 1 + HORIZON_BARS]
    c = b[i]["c"]
    f["ret"] = (fw[-1]["c"] / c - 1) * 100
    f["dd"] = (min(x["l"] for x in fw) / c - 1) * 100
    f["up"] = (max(x["h"] for x in fw) / c - 1) * 100
    f["sym"], f["t"] = b[i]["sym"], b[i]["t"]
    return f


def report(rows: list[dict]) -> None:
    n = len(rows)
    syms = len({r["sym"] for r in rows})
    days = len({(r["sym"], r["t"] // 86400_000) for r in rows})
    print(f"баров «в ходу» {n} · монет {syms} · монето-дней {days} · горизонт {HORIZON_BARS // 2} ч\n")

    def line(name, g):
        if not g:
            return f"{name:<28} —"
        rr = [x["ret"] for x in g]
        return (f"{name:<28} n {len(g):4d} · ход за {HORIZON_BARS // 2} ч медиана {st.median(rr):+6.1f}% · "
                f"упала на {DROP_PCT:.0f}%+ {sum(x['dd'] <= -DROP_PCT for x in g) / len(g) * 100:3.0f}% · "
                f"выросла ещё на {DROP_PCT:.0f}%+ {sum(x['up'] >= DROP_PCT for x in g) / len(g) * 100:3.0f}%")
    print(line("все", rows))
    for key, title in (("oi_bar", "интерес за бар"), ("oi_1h", "интерес за час"), ("fund", "фандинг"),
                       ("top_2h", "топ-трейдеры за 2 ч"), ("oi_vs_px", "интерес минус цена за бар")):
        g = sorted([r for r in rows if r.get(key) is not None], key=lambda r: r[key])
        if len(g) < 30:
            continue
        k = len(g) // 3
        lo, mid, hi = g[:k], g[k:2 * k], g[2 * k:]
        print(f"\n{title}: трети по данным — до {lo[-1][key]:+.2f}, до {mid[-1][key]:+.2f}, выше")
        print(line("  нижняя треть", lo))
        print(line("  средняя", mid))
        print(line("  верхняя треть", hi))
    # сочетание, как на ARK и PLAY: интерес за час в верхней трети И фандинг на краю (верхняя или нижняя треть)
    g = [r for r in rows if r.get("oi_1h") is not None and r.get("fund") is not None]
    if len(g) >= 30:
        q = sorted(r["oi_1h"] for r in g)[2 * len(g) // 3]
        fs = sorted(r["fund"] for r in g)
        flo, fhi = fs[len(fs) // 3], fs[2 * len(fs) // 3]
        both = [r for r in g if r["oi_1h"] >= q and (r["fund"] <= flo or r["fund"] >= fhi)]
        rest = [r for r in g if r not in both]
        print("\nсочетание «интерес за час в верхней трети и фандинг в крайней трети»:")
        print(line("  есть", both))
        print(line("  нет", rest))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    syms = ([s.strip().upper() + ("" if s.strip().upper().endswith("USDT") else "USDT") for s in a.only.split(",")]
            if a.only else sorted(p.stem.upper() + "USDT" for p in (BASE_DIR / "cq_v2" / "intraday").glob("*.jsonl")))
    if a.fetch:
        with ThreadPoolExecutor(4) as ex:
            for i, r in enumerate(ex.map(fetch_one, syms), 1):
                if i % 20 == 0 or i == len(syms):
                    print(f"  {i}/{len(syms)} · {r}", flush=True)
        return 0
    rows = []
    for s in syms:
        p = CACHE / f"{s}.json"
        if not p.exists():
            continue
        b = bars_of(json.loads(p.read_text(encoding="utf-8")), s)
        for i in range(len(b)):
            f = features(b, i)
            if f:
                rows.append(f)
    if not rows:
        print("нет данных — сначала --fetch")
        return 0
    report(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
