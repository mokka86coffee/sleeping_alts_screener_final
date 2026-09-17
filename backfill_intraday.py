#!/usr/bin/env python3
"""ДОЗАБОР АРХИВА ДЛЯ НОВОЙ МОНЕТЫ (17.09, владелец: ONE шесть часов в первых и лидер, а в журнале её нет —
её архив начался 17.09 14:30, когда она попала в список; всё, что смотрит в историю, её не видит).
Для монеты, у которой в cq_v2/intraday меньше BACKFILL_MIN_BARS получасовок, дотягивает с биржи историю в формате
строки архива: цена, открытие, размах, оборот, покупки по рынку (дельта, тейкер), интерес по истории Binance.
Фандинга в истории нет — поле пустое; строки помечены backfill: true. Живые строки не трогаются: файл
переписывается как объединение по свече, живая строка главнее.
Сеть — через core_binance (общий лимитер). Запуск из прогона по всем файлам с короткой историей; руками:
    python3 backfill_intraday.py --only ONE
    python3 backfill_intraday.py            # все монеты списка с историей короче порога
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
try:
    from core_config import BACKFILL_MIN_BARS, BACKFILL_BARS
except ImportError:
    BACKFILL_MIN_BARS, BACKFILL_BARS = 200, 1440          # порог «истории мало» и сколько тянуть (1440 — 30 дней)
try:
    from core_http import log
except ImportError:
    def log(msg: str) -> None:
        print(msg, flush=True)

import core_binance as cb
from core_binance import get_klines

ARCH = BASE_DIR / "cq_v2" / "intraday"
K_T, K_O, K_H, K_L, K_C = (getattr(cb, "K_OPEN_TIME", 0), getattr(cb, "K_OPEN", 1), getattr(cb, "K_HIGH", 2),
                           getattr(cb, "K_LOW", 3), getattr(cb, "K_CLOSE", 4))
K_V, K_Q, K_N, K_TBQ = (getattr(cb, "K_VOLUME", 5), getattr(cb, "K_QUOTE_VOLUME", 7), getattr(cb, "K_TRADES", 8),
                        getattr(cb, "K_TAKER_BUY_QUOTE", 10))


def _existing(p: Path) -> dict:
    out = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("candle"):
            out[r["candle"]] = r
    return out


def _oi_map(sym: str, limit: int) -> dict:
    """свеча → интерес $ из истории интереса биржи по 30 минут (до 500 точек — 10 дней; дальше пусто)"""
    out = {}
    try:
        hist = cb.get_oi_history(sym, "30m", min(500, limit)) or []
    except Exception:  # noqa: BLE001
        return out
    for x in hist:
        if not isinstance(x, dict):
            continue
        ts = x.get("timestamp") or x.get("time") or x.get("t")
        v = x.get("sumOpenInterestValue") or x.get("oi_usd") or x.get("sumOpenInterest")
        if ts is None or v is None:
            continue
        try:
            t = int(ts) // 1000 if int(ts) > 10 ** 11 else int(ts)
            out[datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")] = float(v)
        except (ValueError, TypeError):
            continue
    return out


def backfill(sym: str, bars: int, write: bool) -> int:
    base = sym.replace("USDT", "").lower()
    p = ARCH / f"{base}.jsonl"
    have = _existing(p)
    ks = get_klines(sym, "30m", limit=bars) or []
    now = time.time()
    ks = [k for k in ks if int(k[K_T]) // 1000 + 1800 <= now]
    if not ks:
        return 0
    oi = _oi_map(sym, bars)
    new = {}
    prev_oi = None
    for k in ks:
        c = datetime.fromtimestamp(int(k[K_T]) // 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if c in have:
            prev_oi = have[c].get("oi") or prev_oi
            continue
        qv = float(k[K_Q] or 0)
        tb = float(k[K_TBQ] or 0) if len(k) > K_TBQ else 0.0
        o = oi.get(c)
        row = {"candle": c, "sym": sym, "px": float(k[K_C]), "o": float(k[K_O]), "h": float(k[K_H]), "l": float(k[K_L]),
               "oi": o, "oi_chg_pct": (round((o / prev_oi - 1) * 100, 2) if (o and prev_oi) else None),
               "funding": None,
               "fut": {"b": round(tb, 2), "s": round(qv - tb, 2), "d": round(2 * tb - qv, 2),
                       "tk": round(tb / (qv - tb), 4) if qv > tb > 0 else None},
               "kv": {"v": float(k[K_V] or 0), "qv": round(qv, 2)}, "backfill": True}
        if o:
            prev_oi = o
        new[c] = row
    if write and new:
        merged = dict(new)
        merged.update(have)                                    # живая строка главнее дозабранной
        ARCH.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text("\n".join(json.dumps(merged[c], ensure_ascii=False) for c in sorted(merged)) + "\n", encoding="utf-8")
        tmp.replace(p)
    return len(new)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--bars", type=int, default=BACKFILL_BARS)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    if a.only:
        syms = [x.strip().upper() + ("" if x.strip().upper().endswith("USDT") else "USDT") for x in a.only.split(",")]
    else:
        syms = []
        for p in sorted(ARCH.glob("*.jsonl")):
            n = sum(1 for _ in p.open(encoding="utf-8"))
            if n < BACKFILL_MIN_BARS:
                syms.append(p.stem.upper() + "USDT")
    total = 0
    for sym in syms:
        try:
            n = backfill(sym, a.bars, not a.no_write)
            total += n
            log(f"дозабор: {sym} · {n} получасовок" + ("" if n else " · нечего") + (" (без записи)" if a.no_write else ""))
        except Exception as e:  # noqa: BLE001
            log(f"дозабор: {sym} · сбой {type(e).__name__}: {e}")
    log(f"дозабор: монет {len(syms)} · строк {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
