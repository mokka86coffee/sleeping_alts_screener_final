#!/usr/bin/env python3
"""Одна монета, одна страница НАЗАД. Ничего больше.

Берёт последнюю свечу из hourly/<coin>.json, просит у Coinglass одну
страницу до неё и печатает, что пришло: сколько свечей, с какой по
какую дату, старше ли они того, что уже лежит. Файл не трогает.

    python3 one_page_back.py BTC
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from coinglass_fetch import get, _key, PAUSE_SEC

coin = (sys.argv[1] if len(sys.argv) > 1 else "BTC").upper()
sym = coin if coin.endswith("USDT") else coin + "USDT"
key = _key()
if not key:
    print("нет COINGLASS_KEY"); sys.exit(1)

f = Path("hourly") / f"{coin.lower()}.json"
have = []
if f.exists():
    try:
        have = json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        pass


def d(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%d.%m %H:%M")


if have:
    oldest = min(r["t"] for r in have)
    print(f"в файле: {len(have)} свечей · с {d(oldest)} по {d(max(r['t'] for r in have))}")
    end = oldest - 3600 * 1000
else:
    print("файла нет — прошу страницу от сейчас")
    end = int(time.time() * 1000)

print(f"прошу страницу до {d(end)} · end_time={end}")
code, body = get("/futures/price/history",
                 {"exchange": "Binance", "symbol": sym, "interval": "1h",
                  "limit": 1000, "end_time": end}, key)
print(f"код {code}")
rows = (body.get("data") if isinstance(body, dict) else None) or []
if not rows:
    print("строк 0 · тело:", str(body)[:200]); sys.exit(1)
ts = sorted(int(r["time"]) for r in rows if r.get("time"))
print(f"пришло {len(ts)} свечей · с {d(ts[0])} по {d(ts[-1])}")
if have:
    newer = sum(1 for t in ts if t < oldest)
    print(f"из них СТАРШЕ файла: {newer}"
          + ("" if newer else "  ← окно не сдвинулось, параметр не работает"))
print("первая строка:", str(rows[0])[:120])
