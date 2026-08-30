#!/usr/bin/env python3
"""Сборщик CryptoQuant v2 — деривативы всего журнала (30.08.2026).

Подтверждено боем: /v2/market/cq/swap/* отдаёт по symbol=<base>_all
funding-rate, open-interest, liquidation, ohlcv, trade; на тарифе
Advanced — окна day и hour, история год, лимит 60 запросов в минуту.

Режимы:
  python3 cryptoquant_fetch.py --daily              # 30 дн всем (по умолчанию)
  python3 cryptoquant_fetch.py --daily --days 365   # ГОД дневок всем (~6 мин)
  python3 cryptoquant_fetch.py --only ena,btr --days 3   # смоук
  python3 cryptoquant_fetch.py --hourly btr --days 365   # год ПОЧАСОВО одной

Вход: env CQ_TOKEN; leaders.json рядом (базы = тикеры журнала).
Выход: cq_v2/<base>.json — {"funding":[...], "oi":[...],
"liq":[...], "ohlcv":[...], "trade":[...]}, свежие точки первыми
(как отдаёт API); сводка cq_v2/_summary.json. Запись атомарная,
ошибки монеты не роняют прогон, пауза держит лимит тарифа.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://api.cryptoquant.com/v2/market/cq/swap"
METRICS = [("funding", "funding-rate"), ("oi", "open-interest"),
           ("liq", "liquidation"), ("ohlcv", "ohlcv"),
           ("trade", "trade")]
PAUSE = 1.1          # 60/мин с запасом
FULL_DAYS = 365      # полный бэкфилл новичку в режиме --update
RETRIES = 3
OUT = Path("cq_v2")


def get(url: str, token: str):
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}",
                      "User-Agent": "curl/8.4.0",
                      "Accept": "application/json"})
    last = None
    for i in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (401, 402, 403):
                try:
                    desc = json.loads(e.read().decode())
                    desc = (desc.get("status") or {}).get(
                        "description") or desc
                except Exception:
                    desc = ""
                print(f"    отказ {e.code}: {desc}")
                return None
            last = f"HTTP {e.code}"
            if e.code == 429:
                time.sleep(5 * (i + 1))
                continue
        except Exception as e:  # сеть
            last = str(e)
        time.sleep(2 * (i + 1))
    print(f"    пропуск после {RETRIES} попыток: {last}")
    return None


def fetch_series(base_sym: str, metric_path: str, window: str,
                 days: int, token: str) -> list:
    """Тянет ряд с пагинацией по from/to (для hour), одним куском
    для day (365 точек влезают в limit=1000)."""
    rows, to = [], None
    need = days if window == "day" else days * 24
    cap = 365 if window == "day" else 1000   # потолок глубины тарифа
    while len(rows) < need:
        limit = min(cap, need - len(rows))
        url = (f"{BASE}/{metric_path}?symbol={base_sym}_all"
               f"&window={window}&limit={limit}")
        if to:
            url += f"&to={to}"
        body = get(url, token)
        time.sleep(PAUSE)
        if not body:
            break
        chunk = ((body.get("result") or {}).get("data")) or []
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < limit:
            break
        # следующая страница — от самой старой точки страницы
        oldest = chunk[-1].get("datetime", "")
        to = oldest.replace("-", "").replace(" ", "T").replace(":", "")
        if not to:
            break
    return rows[:need]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily", action="store_true", default=True)
    ap.add_argument("--hourly", metavar="BASE",
                    help="почасовой год одной монете")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--only", help="базы через запятую (смоук)")
    ap.add_argument("--journal", help="путь к leaders.json")
    ap.add_argument("--out", help="каталог архива (по умолчанию ./cq_v2)")
    ap.add_argument("--update", action="store_true",
                    help="дозабор: свежие дни поверх существующих файлов")
    a = ap.parse_args()

    try:                                   # ключи из config.json,
        from config import load as _cfg   # export главнее файла
        _cfg()
    except Exception:
        pass
    token = os.environ.get("CQ_TOKEN", "").strip()
    if not token:
        print("нет CQ_TOKEN в окружении")
        return 1

    if a.hourly:
        bases = [a.hourly.lower()]
        window = "hour"
    else:
        window = "day"
        if a.only:
            bases = [b.strip().lower() for b in a.only.split(",")]
        else:
            here = Path(__file__).resolve().parent
            spots = ([Path(a.journal)] if a.journal else
                     [Path("leaders.json"), here / "leaders.json",
                      here.parent / "leaders.json"])
            src = next((p for p in spots if p.exists()), None)
            if not src:
                print("leaders.json не найден; искал: " +
                      ", ".join(str(p) for p in spots))
                print("положи рядом или укажи --journal /путь/leaders.json")
                return 1
            print(f"журнал: {src}")
            raw = json.loads(src.read_text())
            bases = sorted(k[:-4].lower() for k in raw
                           if k != "_meta" and k.endswith("USDT"))

    global OUT
    if a.out:
        OUT = Path(a.out)

    hc = get(f"{BASE}/funding-rate?symbol=ena_all&window=day&limit=2",
             token)
    if not hc:
        print("токен/тариф не отвечает даже на минимальный запрос — стоп")
        return 1
    print("токен жив (health-check пройден)")

    OUT.mkdir(exist_ok=True)
    summary = {"window": window, "days": a.days, "coins": {}}
    print(f"сборщик v2: монет {len(bases)} · окно {window} · "
          f"дней {a.days} · ~{len(bases) * len(METRICS)} запросов")

    for n, b in enumerate(bases, 1):
        old = {}
        fp = OUT / f"{b}.json"
        if a.update and fp.exists():
            try:
                old = json.loads(fp.read_text())
            except Exception:
                old = {}
        coin = {}
        for key, path in METRICS:
            if a.update:
                # у ряда есть история — дотянуть хвост; ряда нет
                # (новая монета журнала) — полный бэкфилл сразу
                depth = 4 if old.get(key) else FULL_DAYS
            else:
                depth = a.days
            rows = fetch_series(b, path, window, depth, token)
            if a.update and old.get(key):
                seen = {r["datetime"] for r in rows}
                rows = rows + [r for r in old[key]
                               if r["datetime"] not in seen]
            coin[key] = rows
        got = {k: len(v) for k, v in coin.items()}
        summary["coins"][b] = got
        tmp = OUT / f".{b}.tmp"
        tmp.write_text(json.dumps(coin, ensure_ascii=False))
        tmp.replace(OUT / f"{b}.json")
        print(f"  [{n}/{len(bases)}] {b}: " +
              " ".join(f"{k}={v}" for k, v in got.items()))

    (OUT / "_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"готово: {OUT}/ · сводка _summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
