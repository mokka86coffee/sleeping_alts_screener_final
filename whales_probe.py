#!/usr/bin/env python3
"""Пробник китов v2 (31.08): печатает ТЕЛО ответа — 400 сам скажет,
какого параметра не хватило. Запуск: python3 whales_probe.py"""
import json, os, urllib.request, urllib.parse
try:
    from config import load as _cfg
    _cfg()
except Exception:
    pass
KEY = os.environ.get("COINGLASS_KEY", "")
BASE = "https://open-api-v4.coinglass.com/api"
POINTS = [
    ("/hyperliquid/whale-alert", {"size": "20"}),
    ("/hyperliquid/whale-position", {"size": "20"}),
    ("/futures/orderbook/large-limit-order", {"exchange": "Binance",
                                             "symbol": "BTCUSDT"}),
    ("/spot/orderbook/large-limit-order", {"exchange": "Binance",
                                           "symbol": "BTCUSDT"}),
    ("/futures/orderbook/large-limit-order-history",
     {"exchange": "Binance", "symbol": "BTCUSDT"}),
]
for path, prm in POINTS:
    url = BASE + path + ("?" + urllib.parse.urlencode(prm) if prm else "")
    req = urllib.request.Request(url, headers={"CG-API-KEY": KEY,
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode()
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
    except Exception as e:
        print(f"{path:44s} СЕТЬ {type(e).__name__}: {e}")
        continue
    try:
        d = json.loads(body)
        rows = d.get("data")
        n = len(rows) if isinstance(rows, list) else "-"
        print(f"{path:44s} code={d.get('code')} msg={d.get('msg')} rows={n}")
        if isinstance(rows, list) and rows:
            print("   пример:", json.dumps(rows[0], ensure_ascii=False)[:220])
    except ValueError:
        print(f"{path:44s} НЕ-JSON: {body[:160]}")
