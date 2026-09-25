#!/usr/bin/env python3
"""ЖИВОЙ ПОТОК ЛИКВИДАЦИЙ BINANCE (26.09, владелец: «да, подключай поток ликвидаций Binance»).

Ликвидации по сторонам пропали 24.09 вместе с Coinglass; истории у Binance нет, есть только живой поток всего рынка
wss://fstream.binance.com/ws/!forceOrder@arr — копим с момента включения. Зачем: R21 из claude/research/rules.md —
пик выноса ШОРТОВ стоит на вершине импульса (LSK 13.09, PHA и ARK 26.09), это признак стадии «конец».

Событие потока: сторона ордера SELL — ликвидирован ЛОНГ, BUY — ликвидирован ШОРТ; сумма = средняя цена × исполненное.
Пишет:
  • cq_v2/liq/<ГГГГ-ММ-ДД>.jsonl — каждое событие: {"t": мс, "sym", "side": "long"|"short", "usd", "px"} (сырой архив по дням);
  • output/liq_sides.json — раз в LIQ_FLUSH_SEC по каждой монете: за 24 ч и за 1 ч по сторонам плюс 48 получасовых корзин
    [[t30, long_usd, short_usd], …]; читают binance_fetch (поле liq → архив liq24) и карточка.
При старте перечитывает сегодняшний и вчерашний архив, чтобы перезапуск не обнулял сутки. Обрыв связи — переподключение
с паузой. Запускается дочерним процессом из run.py --loop (гаснет вместе с ним); руками: python3 liq_stream.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
try:
    from core_config import LIQ_FLUSH_SEC, LIQ_KEEP_DAYS
except ImportError:
    LIQ_FLUSH_SEC, LIQ_KEEP_DAYS = 60, 30
from sources_storage import write_atomic

URL = "wss://fstream.binance.com/ws/!forceOrder@arr"
LIQ_DIR = BASE_DIR / "cq_v2" / "liq"
STATE = BASE_DIR / "output" / "liq_sides.json"
BUCKET = 1800_000
DAY = 86_400_000


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} liq: {msg}", flush=True)


class Book:
    """получасовые корзины по монетам: {sym: {t30: [long_usd, short_usd]}}, не старше суток"""

    def __init__(self) -> None:
        self.b: dict[str, dict[int, list[float]]] = defaultdict(dict)
        self.n = 0

    def add(self, sym: str, t: int, side: str, usd: float) -> None:
        k = t // BUCKET * BUCKET
        cell = self.b[sym].setdefault(k, [0.0, 0.0])
        cell[0 if side == "long" else 1] += usd
        self.n += 1

    def trim(self, now: int) -> None:
        cut = now - DAY - BUCKET
        for sym in list(self.b):
            self.b[sym] = {k: v for k, v in self.b[sym].items() if k >= cut}
            if not self.b[sym]:
                del self.b[sym]

    def snapshot(self, now: int, since: int) -> dict:
        self.trim(now)
        coins = {}
        for sym, cells in self.b.items():
            bars = sorted(cells.items())
            l24 = sum(v[0] for _, v in bars)
            s24 = sum(v[1] for _, v in bars)
            l1 = sum(v[0] for k, v in bars if k >= now - 3600_000)
            s1 = sum(v[1] for k, v in bars if k >= now - 3600_000)
            coins[sym] = {"long24h": round(l24), "short24h": round(s24), "long1h": round(l1), "short1h": round(s1),
                          "bars": [[k, round(v[0]), round(v[1])] for k, v in bars[-48:]]}
        return {"at": datetime.fromtimestamp(now / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "since": datetime.fromtimestamp(since / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source": "binance !forceOrder@arr", "events": self.n, "coins": coins}


def reload(book: Book, now: int) -> int:
    """перечитать архив за сутки после перезапуска"""
    n = 0
    for d in (now - DAY, now):
        p = LIQ_DIR / f"{datetime.fromtimestamp(d / 1000, timezone.utc).strftime('%Y-%m-%d')}.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if int(r["t"]) >= now - DAY:
                book.add(r["sym"], int(r["t"]), r["side"], float(r["usd"]))
                n += 1
    return n


def prune(now: int) -> None:
    cut = now - LIQ_KEEP_DAYS * DAY
    for p in LIQ_DIR.glob("*.jsonl"):
        try:
            if datetime.strptime(p.stem, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000 < cut:
                p.unlink()
        except ValueError:
            continue


async def run() -> None:
    import websockets
    LIQ_DIR.mkdir(parents=True, exist_ok=True)
    book = Book()
    now = int(time.time() * 1000)
    since = now
    n0 = reload(book, now)
    if n0:
        rows = [int(json.loads(l)["t"]) for p in sorted(LIQ_DIR.glob("*.jsonl"))[-2:] for l in p.read_text(encoding="utf-8").splitlines()[:1]]
        since = min(rows) if rows else now
    log(f"старт · из архива {n0} событий · монет {len(book.b)}")
    prune(now)
    last_flush = 0.0
    backoff = 5
    while True:
        try:
            async with websockets.connect(URL, ping_interval=20, ping_timeout=20, max_queue=4096) as ws:
                log("подключён")
                backoff = 5
                async for msg in ws:
                    try:
                        o = json.loads(msg).get("o") or {}
                        sym, side_o = str(o.get("s") or ""), str(o.get("S") or "")
                        if not sym or side_o not in ("SELL", "BUY"):
                            continue
                        t = int(o.get("T") or time.time() * 1000)
                        usd = float(o.get("ap") or o.get("p") or 0) * float(o.get("z") or o.get("q") or 0)
                        side = "long" if side_o == "SELL" else "short"
                    except (TypeError, ValueError):
                        continue
                    book.add(sym, t, side, usd)
                    day = datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d")
                    with (LIQ_DIR / f"{day}.jsonl").open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps({"t": t, "sym": sym, "side": side, "usd": round(usd, 2),
                                             "px": float(o.get("ap") or o.get("p") or 0)}) + "\n")
                    if time.time() - last_flush >= LIQ_FLUSH_SEC:
                        last_flush = time.time()
                        write_atomic(STATE, json.dumps(book.snapshot(int(time.time() * 1000), since), ensure_ascii=False))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — сеть не должна ронять сборщик
            log(f"обрыв: {type(e).__name__}: {str(e)[:120]} · снова через {backoff} с")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)


def main() -> int:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log("остановлен")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
