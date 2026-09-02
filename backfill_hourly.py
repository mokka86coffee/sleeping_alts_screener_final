#!/usr/bin/env python3
"""Дозабор часов НАЗАД до 180 дней. Проверено 02.09 на одной странице:
end_time в миллисекундах отдаёт страницу старше — работает.

Причина: --update в coinglass_hourly.py дописывал только новые часы
ВПЕРЁД от последней свечи, назад в историю не ходил. Отсюда у всех
ровно тысяча.

    python3 backfill_hourly.py BTC        # одна монета
    python3 backfill_hourly.py            # все, у кого меньше 180 дней
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from coinglass_fetch import get, _key, PAUSE_SEC

DAYS = 180
STEP = 3600 * 1000
HOURLY = Path("hourly")


def d(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%d.%m")


EXCHANGES = ("Binance", "Bybit", "OKX", "Bingx")   # порядок попыток


def page(sym, end, key, exchange="Binance"):
    code, body = get("/futures/price/history",
                     {"exchange": exchange, "symbol": sym, "interval": "1h",
                      "limit": 1000, "end_time": end}, key)
    rows = (body.get("data") if isinstance(body, dict) else None) or []
    out = []
    for r in rows:
        try:
            out.append({"t": int(r["time"]), "o": float(r["open"]),
                        "h": float(r["high"]), "l": float(r["low"]),
                        "c": float(r["close"]),
                        "v": float(r.get("volume_usd") or 0)})
        except (KeyError, TypeError, ValueError):
            pass
    return code, out


def backfill(coin, key):
    f = HOURLY / f"{coin.lower()}.json"
    have = []
    if f.exists():
        try:
            have = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            have = []
    floor = int(time.time() * 1000) - DAYS * 86400 * 1000
    if not have:
        # Файла нет — монета не из журнала (SOL, NEAR). Заводим с нуля:
        # первая страница от сейчас, дальше как обычно назад.
        print(f"  {coin}: файла нет — завожу с нуля")
        oldest = int(time.time() * 1000) + STEP
    else:
        oldest = min(r["t"] for r in have)
    if oldest <= floor:
        print(f"  {coin}: уже {len(have)} свечей с {d(oldest)} — полный")
        return
    sym = coin if coin.endswith("USDT") else coin + "USDT"
    seen = {r["t"] for r in have}
    added, pages = 0, 0
    exchange = EXCHANGES[0]
    while oldest > floor and pages < 8:
        code, rows = page(sym, oldest - STEP, key, exchange)
        pages += 1
        time.sleep(PAUSE_SEC)
        new = [r for r in rows if r["t"] not in seen and r["t"] >= floor]
        if code == 200 and not rows:
            # Пустая страница — истории на этой бирже раньше нет: пара
            # молодая. Пробуем следующую биржу: та же пара могла жить
            # там раньше. Для ширины (вверх/вниз за час) смешение
            # площадок допустимо — направление то же.
            nxt = EXCHANGES.index(exchange) + 1 if exchange in EXCHANGES else 99
            if nxt < len(EXCHANGES):
                print(f"  {coin}: на {exchange} истории раньше {d(oldest)} нет — "
                      f"пробую {EXCHANGES[nxt]}")
                exchange = EXCHANGES[nxt]
                continue
            print(f"  {coin}: истории раньше {d(oldest)} нет ни на одной "
                  f"из бирж — пара молодая, это не поломка")
            break
        if code != 200 or not new:
            print(f"  {coin}: стр.{pages} код {code}, строк {len(rows)}, "
                  f"новых 0 — стоп")
            break
        for r in new:
            seen.add(r["t"])
        have.extend(new)
        added += len(new)
        oldest = min(r["t"] for r in new)
        print(f"  {coin}: стр.{pages} +{len(new)} · дошли до {d(oldest)}")
        if len(rows) < 1000:
            break
    have.sort(key=lambda r: r["t"])
    f.write_text(json.dumps(have, separators=(",", ":")), encoding="utf-8")
    print(f"  {coin}: итого {len(have)} свечей с {d(have[0]['t'])} · добавлено {added}")


def main():
    key = _key()
    if not key:
        print("нет COINGLASS_KEY"); return 1
    HOURLY.mkdir(exist_ok=True)
    if len(sys.argv) > 1:
        coins = [c.upper() for c in sys.argv[1:]]
    else:
        coins = sorted(f.stem.upper() for f in HOURLY.glob("*.json"))
    t0 = time.time()
    for c in coins:
        backfill(c, key)
    print(f"готово за {time.time() - t0:.0f} с")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
