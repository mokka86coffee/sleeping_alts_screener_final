#!/usr/bin/env python3
"""ЗАГРУЗКА ИНТЕРЕСОМ (23.10.2026, владелец: «капитализация мелкая, накоплено дохера»; IRYS 23.10 ×13 за день — стоял седьмым в этом счёте 22.10).
Для каждой монеты архива cq_v2/intraday: интерес Binance в монетах сейчас (последняя получасовка) к медиане интереса за год по дневкам
TradingView (claude/research/tvd/<SYM>USDT.P_1D.json, собраны 03–06.10), просадка цены от максимума тех же дневок, капа и монеты в обращении
с CoinGecko (поиск по символу, крупнейшая капа; кэш output/oi_load_cg.json на CG_TTL). Это карта, где лежит заряд, а не сигнал.
Пишет output/oi_load.json: {"at", "rows": [{sym, x, dd, cap, oi_usd, funding, cg}]}, по убыванию x. Пересчёт не чаще раза в EVERY_S.
    python3 oi_load.py            # пересчитать, если устарело, и напечатать первые 20
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
import time
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
OUT, CG = BASE / "output" / "oi_load.json", BASE / "output" / "oi_load_cg.json"
EVERY_S = 3600         # пересчёт раз в час — мерка Claude
CG_TTL = 6 * 3600      # капа и предложение с CoinGecko — раз в 6 ч
MIN_DAYS = 200         # дневок интереса в истории TradingView не меньше — иначе медиана года не считается


def _last_row(p: Path) -> dict | None:
    try:
        with p.open("rb") as f:
            f.seek(0, 2); n = f.tell(); f.seek(max(0, n - 4000))
            return json.loads(f.read().decode(errors="ignore").strip().splitlines()[-1])
    except (OSError, ValueError, IndexError):
        return None


def _cg(syms: list[str]) -> dict:
    try:
        c = json.loads(CG.read_text(encoding="utf-8"))
        if time.time() - c.get("at", 0) < CG_TTL:
            return c["m"]
    except (OSError, ValueError, KeyError):
        pass
    m: dict = {}
    for i in range(0, len(syms), 50):
        ch = [s.replace("1000", "").lower() for s in syms[i:i + 50]]
        d = None
        for _ in range(4):
            try:
                d = requests.get("https://api.coingecko.com/api/v3/coins/markets", timeout=40,
                                 params={"vs_currency": "usd", "symbols": ",".join(ch), "include_tokens": "top", "per_page": 250}).json()
            except (requests.RequestException, ValueError):
                d = None
            if isinstance(d, list):
                break
            time.sleep(20)
        for c in d if isinstance(d, list) else []:
            s = c["symbol"].lower()
            if c.get("circulating_supply") and c.get("market_cap") and (s not in m or c["market_cap"] > m[s]["cap"]):
                m[s] = dict(id=c["id"], cap=c["market_cap"], circ=c["circulating_supply"])
        time.sleep(6)
    if m:
        tmp = CG.with_suffix(".tmp"); tmp.write_text(json.dumps(dict(at=time.time(), m=m)), encoding="utf-8"); tmp.replace(CG)
    return m


def build(force: bool = False) -> dict:
    try:
        old = json.loads(OUT.read_text(encoding="utf-8"))
        if not force and time.time() - old.get("at", 0) < EVERY_S:
            return old
    except (OSError, ValueError):
        pass
    rows = []
    for p in sorted((BASE / "cq_v2" / "intraday").glob("*.jsonl")):
        s = p.stem.upper(); tv = BASE / "claude" / "research" / "tvd" / f"{s}USDT.P_1D.json"
        r = _last_row(p)
        if not tv.exists() or not r or not r.get("oi") or not r.get("px"):
            continue
        try:
            t = json.loads(tv.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        oi = [v for _, v in t.get("oi") or [] if v]
        if len(oi) < MIN_DAYS:
            continue
        px = float(r["px"]); med = st.median(oi[-365:]); hi = max(b[2] for b in t["bars"])
        rows.append(dict(sym=s + "USDT", x=round(r["oi"] / px / med, 2), dd=round((px / hi - 1) * 100, 1), oi_usd=round(r["oi"]), funding=r.get("funding")))
    cg = _cg([x["sym"][:-4] for x in rows])
    for x in rows:
        c = cg.get(x["sym"][:-4].replace("1000", "").lower())
        x["cap"], x["cg"] = (round(c["cap"]), c["id"]) if c else (None, None)
    rows.sort(key=lambda x: -x["x"])
    out = dict(at=time.time(), rows=rows)
    tmp = OUT.with_suffix(".tmp"); tmp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8"); tmp.replace(OUT)
    return out


if __name__ == "__main__":
    o = build(force="--force" in sys.argv)
    for x in o["rows"][:20]:
        print(f"{x['sym'][:-4]}: ×{x['x']} · от максимума {x['dd']}% · капа {round((x['cap'] or 0) / 1e6, 1)} млн $ · фандинг {x['funding']}")
