#!/usr/bin/env python3
"""Часовые свечи с Binance Futures напрямую — без ключа, полгода.

ЗАЧЕМ. Coinglass отдаёт историю мелочи не с листинга, а с момента,
когда сам начал её вести: BLESS на Binance торгуется с октября, а у
Coinglass — с 22.07. Для BTC у него полгода, для мелочи нет. Binance
— источник, Coinglass — пересказ; за свечами идём к источнику.

Публичный эндпоинт fapi.binance.com/fapi/v1/klines: до 1500 свечей за
запрос, ключ не нужен, лимит 2400 веса в минуту (запрос стоит 5-10).
Формат файла тот же, что у coinglass_hourly: hourly/<coin>.json со
списком {"t","o","h","l","c","v"}. Дописывает только недостающее.

    python3 backfill_binance.py BLESS            # одна
    python3 backfill_binance.py BLESS ONG SKR    # несколько
    python3 backfill_binance.py                  # все из hourly/
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://fapi.binance.com/fapi/v1/klines"
DAYS = 180
STEP = 3600 * 1000
LIMIT = 1500
PAUSE = 0.25
HOURLY = Path("hourly")


def d(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%d.%m")


def klines(sym, end_ms):
    q = urllib.parse.urlencode({"symbol": sym, "interval": "1h",
                                "limit": LIMIT, "endTime": end_ms})
    req = urllib.request.Request(BASE + "?" + q,
                                 headers={"User-Agent": "screener/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"msg": str(e)}
    except Exception as e:
        return 0, {"msg": f"{type(e).__name__}: {e}"}
    rows = []
    for k in body if isinstance(body, list) else []:
        # [openTime, open, high, low, close, volume, closeTime, quoteVolume, …]
        try:
            rows.append({"t": int(k[0]), "o": float(k[1]), "h": float(k[2]),
                         "l": float(k[3]), "c": float(k[4]),
                         "v": float(k[7]) if len(k) > 7 else 0.0})
        except (IndexError, TypeError, ValueError):
            pass
    return 200, rows


def backfill(coin):
    sym = coin if coin.endswith("USDT") else coin + "USDT"
    f = HOURLY / f"{coin.lower()}.json"
    have = []
    if f.exists():
        try:
            have = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            have = []
    floor = int(time.time() * 1000) - DAYS * 86400 * 1000
    seen = {r["t"] for r in have}
    oldest = min(seen) if seen else int(time.time() * 1000) + STEP
    if have and oldest <= floor:
        print(f"  {coin}: уже {len(have)} свечей с {d(oldest)} — полный")
        return
    print(f"  {coin}: {'файла нет — завожу с нуля' if not have else f'в файле {len(have)} с {d(oldest)}'}")
    added, pages = 0, 0
    while oldest > floor and pages < 6:
        code, rows = klines(sym, oldest - STEP)
        pages += 1
        time.sleep(PAUSE)
        if code != 200:
            print(f"  {coin}: код {code} · {str(rows.get('msg', rows))[:80]}")
            break
        new = [r for r in rows if r["t"] not in seen and r["t"] >= floor]
        if not rows:
            print(f"  {coin}: истории на Binance раньше {d(oldest)} нет — "
                  f"пара листилась позже")
            break
        if not new:
            break
        for r in new:
            seen.add(r["t"])
        have.extend(new)
        added += len(new)
        oldest = min(r["t"] for r in new)
        print(f"  {coin}: стр.{pages} +{len(new)} · дошли до {d(oldest)}")
        if len(rows) < LIMIT:
            break
    have.sort(key=lambda r: r["t"])
    HOURLY.mkdir(exist_ok=True)
    f.write_text(json.dumps(have, separators=(",", ":")), encoding="utf-8")
    if have:
        print(f"  {coin}: итого {len(have)} свечей с {d(have[0]['t'])} · "
              f"добавлено {added}")


def main():
    if len(sys.argv) > 1:
        coins = [c.upper() for c in sys.argv[1:]]
    else:
        coins = sorted(f.stem.upper() for f in HOURLY.glob("*.json"))
    t0 = time.time()
    for c in coins:
        backfill(c)
    print(f"готово за {time.time() - t0:.0f} с")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
