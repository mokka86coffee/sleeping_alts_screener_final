#!/usr/bin/env python3
"""ЖИВОЙ ПОТОК ЛИКВИДАЦИЙ (26.09, владелец: «да, подключай поток ликвидаций Binance»).

Ликвидации по сторонам пропали 24.09 вместе с Coinglass; истории нет ни у одной биржи — копим живой поток с момента включения.
Зачем: R21 из claude/research/rules.md — пик выноса ШОРТОВ стоит на вершине импульса (LSK 13.09, PHA и ARK 26.09), стадия «конец».

ИСТОЧНИКИ (LIQ_SOURCES): «okx» — канал liquidation-orders на весь рынок одной подпиской (70 наших монет); «bybit» — allLiquidation
по каждой нашей монете, что есть на Bybit (135); вместе — 137 из 155. Поток фьючерсов Binance («binance», !forceOrder@arr)
с машины владельца молчит: рукопожатие проходит, кадров нет — проверено 26.09 в его терминале и у меня, при этом спот Binance,
OKX и Bybit отдают кадры сразу. Символы пишутся как у Binance («ONEUSDT»), так их читают срез и архив. Ликвидации разных бирж —
разные деньги, но сторона и момент выноса те же; сводка складывает источники.

Пишет:
  • cq_v2/liq/<ГГГГ-ММ-ДД>.jsonl — каждое событие: {"t": мс, "sym", "side": "long"|"short", "usd", "px", "src"};
  • output/liq_sides.json — раз в LIQ_FLUSH_SEC по монетам: за 24 ч и 1 ч по сторонам плюс 48 получасовых корзин
    [[t30, long_usd, short_usd], …]; читают binance_fetch (поле liq → архив liq24) и карточка.
При старте перечитывает архив за сутки, чтобы перезапуск не обнулял окно. Обрыв одного источника — его переподключение, другой живёт.
Запускается дочерним процессом из run.py --loop (гаснет вместе с ним); руками: python3 liq_stream.py
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
    from core_config import LIQ_FLUSH_SEC, LIQ_KEEP_DAYS, LIQ_SOURCES
except ImportError:
    LIQ_FLUSH_SEC, LIQ_KEEP_DAYS, LIQ_SOURCES = 60, 30, ("okx", "bybit")
from sources_storage import write_atomic

URLS = {"okx": "wss://ws.okx.com:8443/ws/v5/public", "bybit": "wss://stream.bybit.com/v5/public/linear",
        "binance": "wss://fstream.binance.com/ws/!forceOrder@arr"}
OKX_SUB = {"op": "subscribe", "args": [{"channel": "liquidation-orders", "instType": "SWAP"}]}
LIQ_DIR = BASE_DIR / "cq_v2" / "liq"
STATE = BASE_DIR / "output" / "liq_sides.json"
ARCH = BASE_DIR / "cq_v2" / "intraday"
BUCKET = 1800_000
DAY = 86_400_000


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} liq: {msg}", flush=True)


class Book:
    """получасовые корзины по монетам: {sym: {t30: [long_usd, short_usd]}}, не старше суток"""

    def __init__(self) -> None:
        self.b: dict[str, dict[int, list[float]]] = defaultdict(dict)
        self.n = 0
        self.by_src: dict[str, int] = defaultdict(int)

    def add(self, sym: str, t: int, side: str, usd: float, src: str = "") -> None:
        k = t // BUCKET * BUCKET
        cell = self.b[sym].setdefault(k, [0.0, 0.0])
        cell[0 if side == "long" else 1] += usd
        self.n += 1
        self.by_src[src] += 1

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
            coins[sym] = {"long24h": round(sum(v[0] for _, v in bars)), "short24h": round(sum(v[1] for _, v in bars)),
                          "long1h": round(sum(v[0] for k, v in bars if k >= now - 3600_000)),
                          "short1h": round(sum(v[1] for k, v in bars if k >= now - 3600_000)),
                          "bars": [[k, round(v[0]), round(v[1])] for k, v in bars[-48:]]}
        return {"at": datetime.fromtimestamp(now / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "since": datetime.fromtimestamp(since / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sources": list(LIQ_SOURCES), "events": self.n, "events_by_source": dict(self.by_src), "coins": coins}


def reload(book: Book, now: int) -> tuple[int, int | None]:
    """перечитать архив за сутки после перезапуска; вернуть (событий, самое раннее t)"""
    n, first = 0, None
    for d in (now - DAY, now):
        p = LIQ_DIR / f"{datetime.fromtimestamp(d / 1000, timezone.utc).strftime('%Y-%m-%d')}.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            t = int(r["t"])
            first = t if first is None else min(first, t)
            if t >= now - DAY:
                book.add(r["sym"], t, r["side"], float(r["usd"]), r.get("src", ""))
                n += 1
    return n, first


def prune(now: int) -> None:
    cut = now - LIQ_KEEP_DAYS * DAY
    for p in LIQ_DIR.glob("*.jsonl"):
        try:
            if datetime.strptime(p.stem, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000 < cut:
                p.unlink()
        except ValueError:
            continue


def our_symbols() -> set[str]:
    return {p.stem.upper() + "USDT" for p in ARCH.glob("*.jsonl")}


def okx_contracts() -> dict[str, float]:
    """instId → ctVal (монет в одном контракте) для USDT-свопов OKX"""
    from core_http import get_json
    rows = (get_json("https://www.okx.com/api/v5/public/instruments", {"instType": "SWAP"}, weight=1) or {}).get("data") or []
    return {r["instId"]: float(r["ctVal"]) for r in rows if r.get("instId", "").endswith("-USDT-SWAP") and r.get("ctVal")}


def bybit_symbols() -> list[str]:
    """наши монеты, которые торгуются на Bybit как USDT-перпы"""
    from core_http import get_json
    have = set()
    cursor = None
    for _ in range(5):
        q = {"category": "linear", "limit": 1000}
        if cursor:
            q["cursor"] = cursor
        res = ((get_json("https://api.bybit.com/v5/market/instruments-info", q, weight=1) or {}).get("result") or {})
        have |= {r["symbol"] for r in (res.get("list") or []) if str(r.get("symbol", "")).endswith("USDT")}
        cursor = res.get("nextPageCursor")
        if not cursor:
            break
    return sorted(our_symbols() & have)


def parse(src: str, msg: str, ct: dict[str, float]) -> list[tuple[str, int, str, float, float]]:
    """(sym, t, side, usd, px) из кадра источника; side — какую ПОЗИЦИЮ ликвидировали"""
    d = json.loads(msg)
    out = []
    if src == "okx":
        for item in d.get("data") or []:
            inst = str(item.get("instId") or "")
            if not inst.endswith("-USDT-SWAP"):
                continue
            sym = inst.split("-")[0] + "USDT"
            for x in item.get("details") or []:
                try:
                    px = float(x["bkPx"]); usd = float(x["sz"]) * ct.get(inst, 0.0) * px
                    out.append((sym, int(x["ts"]), "long" if x.get("posSide") == "long" else "short", usd, px))
                except (KeyError, TypeError, ValueError):
                    continue
    elif src == "bybit":
        if not str(d.get("topic", "")).startswith("allLiquidation."):
            return out
        for x in d.get("data") or []:
            try:
                px = float(x["p"]); usd = float(x["v"]) * px
                # S — сторона ордера ликвидации: Sell закрывает лонг, Buy закрывает шорт (как у Binance)
                out.append((str(x["s"]), int(x["T"]), "long" if x.get("S") == "Sell" else "short", usd, px))
            except (KeyError, TypeError, ValueError):
                continue
    else:
        o = d.get("o") or {}
        s, side_o = str(o.get("s") or ""), str(o.get("S") or "")
        if s and side_o in ("SELL", "BUY"):
            try:
                px = float(o.get("ap") or o.get("p") or 0)
                out.append((s, int(o.get("T") or time.time() * 1000), "long" if side_o == "SELL" else "short",
                            px * float(o.get("z") or o.get("q") or 0), px))
            except (TypeError, ValueError):
                pass
    return out


async def source(src: str, book: Book, ct: dict[str, float], syms: list[str], flush) -> None:
    import websockets
    backoff = 5
    while True:
        try:
            async with websockets.connect(URLS[src], ping_interval=20, ping_timeout=20, max_queue=4096) as ws:
                if src == "okx":
                    await ws.send(json.dumps(OKX_SUB))
                elif src == "bybit":
                    for i in range(0, len(syms), 10):
                        await ws.send(json.dumps({"op": "subscribe", "args": [f"allLiquidation.{s}" for s in syms[i:i + 10]]}))
                log(f"{src}: подключён" + (f", подписок {len(syms)}" if src == "bybit" else ""))
                backoff = 5
                async for msg in ws:
                    try:
                        events = parse(src, msg, ct)
                    except ValueError:
                        continue
                    for sym, t, side, usd, px in events:
                        book.add(sym, t, side, usd, src)
                        day = datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d")
                        with (LIQ_DIR / f"{day}.jsonl").open("a", encoding="utf-8") as fh:
                            fh.write(json.dumps({"t": t, "sym": sym, "side": side, "usd": round(usd, 2), "px": px, "src": src}) + "\n")
                    if events:
                        flush()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — сеть не должна ронять сборщик
            log(f"{src}: обрыв: {type(e).__name__}: {str(e)[:120]} · снова через {backoff} с")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)


async def run() -> None:
    LIQ_DIR.mkdir(parents=True, exist_ok=True)
    book = Book()
    now = int(time.time() * 1000)
    n0, first = reload(book, now)
    since = first or now
    ct = okx_contracts() if "okx" in LIQ_SOURCES else {}
    syms = bybit_symbols() if "bybit" in LIQ_SOURCES else []
    log(f"старт · источники {', '.join(LIQ_SOURCES)} · из архива {n0} событий · монет {len(book.b)}"
        + (f" · контрактов OKX {len(ct)}" if ct else "") + (f" · монет на Bybit {len(syms)}" if syms else ""))
    prune(now)
    last = {"t": 0.0}

    def flush() -> None:
        if time.time() - last["t"] >= LIQ_FLUSH_SEC:
            last["t"] = time.time()
            write_atomic(STATE, json.dumps(book.snapshot(int(time.time() * 1000), since), ensure_ascii=False))

    await asyncio.gather(*(source(s, book, ct, syms, flush) for s in LIQ_SOURCES))


def main() -> int:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log("остановлен")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
