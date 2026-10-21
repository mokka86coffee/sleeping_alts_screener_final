#!/usr/bin/env python3
"""АРБИТРАЖ ФАНДИНГА МЕЖДУ БИРЖАМИ — монитор (21.10.2026, владелец: «бота делать надо на всех биржах мониторить»).
Только наблюдение: сделок нет, правила бота это не читают. Публичные данные без ключей.

Каждый запуск берёт текущую ставку фандинга, её интервал (ч) и цену маркировки перпов USDT с бирж BINANCE, BYBIT, GATE, BITGET, MEXC, BINGX,
приводит ставку к суткам (ставка × 24 / интервал) и по каждой монете ищет пару бирж «лонг там, где ставка ниже; шорт там, где выше».
Разница за сутки минус комиссии четырёх сделок (FEE_RT, моя мерка 0,2 %) — чистый доход пары в сутки, если ставки удержатся.
Интервал неизвестен (биржа его не отдаёт в общем списке) — берётся 8 ч и помечается «8?».

Пишет output/funding_arb.json (последний срез) и дописывает output/funding_arb.jsonl (история для счёта, сколько держатся разницы).
    python3 funding_arb.py            # один срез, печать лучших пар
    python3 funding_arb.py --loop     # раз в EVERY_S секунд
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
OUT, HIST = BASE / "output" / "funding_arb.json", BASE / "output" / "funding_arb.jsonl"
FEE_RT = 0.20          # % — четыре сделки (вход и выход на двух биржах) по ~0,05 %, мерка Claude
MIN_NET = 0.10         # % в сутки чистыми — ниже в список не берём, мерка Claude
EVERY_S = 300
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"


def _j(url, **p):
    r = S.get(url, params=p or None, timeout=15); r.raise_for_status(); return r.json()


def binance():
    iv = {x["symbol"]: float(x["fundingIntervalHours"]) for x in _j("https://fapi.binance.com/fapi/v1/fundingInfo")}
    out = {}
    for x in _j("https://fapi.binance.com/fapi/v1/premiumIndex"):
        s = x["symbol"]
        if s.endswith("USDT") and x.get("lastFundingRate") not in (None, ""):
            out[s[:-4]] = (float(x["lastFundingRate"]) * 100, iv.get(s, 8.0), float(x["markPrice"]), True)
    return out


def bybit():
    iv, cur = {}, None
    while True:
        d = _j("https://api.bybit.com/v5/market/instruments-info", category="linear", limit=1000, **({"cursor": cur} if cur else {}))["result"]
        for x in d["list"]:
            if x.get("fundingInterval"):
                iv[x["symbol"]] = float(x["fundingInterval"]) / 60
        cur = d.get("nextPageCursor")
        if not cur:
            break
    out = {}
    for x in _j("https://api.bybit.com/v5/market/tickers", category="linear")["result"]["list"]:
        s = x["symbol"]
        if s.endswith("USDT") and x.get("fundingRate") not in (None, ""):
            out[s[:-4]] = (float(x["fundingRate"]) * 100, iv.get(s, 8.0), float(x["markPrice"] or 0), s in iv)
    return out


def gate():
    out = {}
    for x in _j("https://api.gateio.ws/api/v4/futures/usdt/contracts"):
        if x.get("in_delisting"):
            continue
        n = x["name"]
        if n.endswith("_USDT"):
            out[n[:-5]] = (float(x["funding_rate"]) * 100, float(x.get("funding_interval") or 28800) / 3600, float(x.get("mark_price") or 0), True)
    return out


def bitget():
    out = {}
    for x in _j("https://api.bitget.com/api/v2/mix/market/tickers", productType="USDT-FUTURES")["data"]:
        s = x["symbol"]
        if s.endswith("USDT") and x.get("fundingRate") not in (None, ""):
            out[s[:-4]] = (float(x["fundingRate"]) * 100, 8.0, float(x.get("markPrice") or x.get("lastPr") or 0), False)
    return out


def mexc():
    out = {}
    for x in _j("https://contract.mexc.com/api/v1/contract/ticker")["data"]:
        s = x["symbol"]
        if s.endswith("_USDT") and x.get("fundingRate") is not None:
            out[s[:-5]] = (float(x["fundingRate"]) * 100, 8.0, float(x.get("fairPrice") or x.get("lastPrice") or 0), False)
    return out


def bingx():
    out = {}
    for x in _j("https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex")["data"]:
        s = x["symbol"]
        if s.endswith("-USDT") and x.get("lastFundingRate") not in (None, ""):
            iv = float(x["fundingIntervalHours"]) if x.get("fundingIntervalHours") else 8.0
            out[s[:-5]] = (float(x["lastFundingRate"]) * 100, iv, float(x.get("markPrice") or 0), bool(x.get("fundingIntervalHours")))
    return out


EX = {"Binance": binance, "Bybit": bybit, "Gate": gate, "Bitget": bitget, "MEXC": mexc, "BingX": bingx}


def snap() -> dict:
    data, err = {}, {}
    with ThreadPoolExecutor(len(EX)) as tp:
        fut = {n: tp.submit(f) for n, f in EX.items()}
        for n, f in fut.items():
            try:
                data[n] = f.result()
            except Exception as e:  # noqa: BLE001
                err[n] = f"{type(e).__name__}: {str(e)[:120]}"
    coins = set().union(*[set(v) for v in data.values()]) if data else set()
    pairs = []
    for c in coins:
        q = [(n, *data[n][c]) for n in data if c in data[n] and data[n][c][2] > 0]
        if len(q) < 2:
            continue
        day = [(n, r * 24 / iv, r, iv, px, known) for n, r, iv, px, known in q]
        lo, hi = min(day, key=lambda x: x[1]), max(day, key=lambda x: x[1])
        gross = hi[1] - lo[1]
        net = gross - FEE_RT
        if net < MIN_NET:
            continue
        pairs.append(dict(coin=c, long=lo[0], short=hi[0], net_day=round(net, 3), gross_day=round(gross, 3),
                          long_rate=round(lo[2], 4), long_iv=lo[3], long_iv_known=lo[5], short_rate=round(hi[2], 4), short_iv=hi[3], short_iv_known=hi[5],
                          px_spread=round((hi[4] / lo[4] - 1) * 100, 2), n_ex=len(q)))
    pairs.sort(key=lambda p: -p["net_day"])
    return dict(t=time.time(), ex={n: len(v) for n, v in data.items()}, err=err, pairs=pairs)


def save(s: dict) -> None:
    OUT.parent.mkdir(exist_ok=True)
    tmp = OUT.with_suffix(".tmp"); tmp.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8"); tmp.replace(OUT)
    with HIST.open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(t=s["t"], pairs=s["pairs"][:60]), ensure_ascii=False) + "\n")


def show(s: dict, n: int = 15) -> None:
    print("бирж:", s["ex"], "ошибки:", s["err"] or "нет", "· пар выше порога:", len(s["pairs"]))
    for p in s["pairs"][:n]:
        iv = lambda v, k: f"{v:g}ч" + ("" if k else "?")
        print(f"{p['coin']:>10}  лонг {p['long']:<7} {p['long_rate']:+.4f}%/{iv(p['long_iv'], p['long_iv_known'])}  шорт {p['short']:<7} {p['short_rate']:+.4f}%/{iv(p['short_iv'], p['short_iv_known'])}"
              f"  → чистыми {p['net_day']:+.2f}%/сутки · спред цены {p['px_spread']:+.2f}% · бирж {p['n_ex']}")


if __name__ == "__main__":
    if "--loop" in sys.argv:
        while True:
            try:
                s = snap(); save(s); print(time.strftime("%H:%M:%S", time.gmtime()), "пар", len(s["pairs"]), "ошибки", s["err"] or "нет", flush=True)
            except Exception as e:  # noqa: BLE001
                print("сбой:", e, flush=True)
            time.sleep(EVERY_S)
    s = snap(); save(s); show(s)
