#!/usr/bin/env python3
"""Внутридневной архив (05.09, владелец: «писать рядом с квантом данные внутри дня,
которые уже собираем, и смотреть»): `cq_v2/intraday/<база>.jsonl` — ОДНА строка на
закрытую получасовку по каждой монете журнала. Ничего нового не считает — только
перестаёт терять то, что прогон уже собрал и перезаписал бы следующим срезом.

В строке (всё, чего нет, — null; список `missing` говорит, чего именно):
  candle, sym, px                         — свеча (UTC, начало), пара, закрытие бара
  fut: {b, s, d, tk}                      — перп за бар: покупки, продажи, дельта, тейкер бара
  spot: {b, s, d, tk}                     — спот за бар (у перповых монет null)
  oi, oi_chg_pct                          — интерес $ и его ход за сутки (срез)
  funding, taker24, delta24               — фандинг, тейкер и дельта за сутки (срез)
  liq24: {long, short}                    — ликвидации за сутки по сторонам
  oi_type                                 — тип часа по плечу: long_open / short_open / short_close / long_close / flat
  plot, stage                             — шаблон и стадия репутации на эту свечу
  zones: {up: [[цена, вес]×3], down: [...]} — три плотнейшие полосы карты на сторону
  missing                                 — чего не было в источниках

Читатели: разбор «что стояло за сутки до хода» по монетам, которые пошли (4, ARB), и
по тем, кто не пошёл. Запуск — из прогона после сбора Coinglass и быстрых срезов;
руками: `python3 intraday_archive.py --only 4` (одна монета, печать без записи) или
`--write`. Свеча уже в файле — не дублируется. Дозабор простоя пишет сюда же через
`--candle` (штамп свечи в ISO).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

OUT_DIR = BASE_DIR / "cq_v2" / "intraday"


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _last_jsonl_by_sym(path: Path, key: str = "sym") -> dict:
    """Последняя строка по каждой монете из jsonl (лог ликвидности)."""
    out: dict = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        s = str(r.get(key) or "").upper()
        if s:
            out[s] = r
    return out


def _bar_at(series: list, candle_ms: int) -> dict | None:
    for b in series or []:
        t = b.get("t")
        try:
            t = int(t)
        except (TypeError, ValueError):
            continue
        if t < 1e12:
            t *= 1000
        if t == candle_ms:
            return b
    return None


def _legs(bar: dict | None) -> dict | None:
    if not bar:
        return None
    b, s = bar.get("b"), bar.get("s")
    if b is None and s is None:
        return None
    b, s = float(b or 0), float(s or 0)
    return {"b": round(b, 0), "s": round(s, 0), "d": round(b - s, 0), "tk": round(b / s, 3) if s else None}


def _top3(zones: list, above: bool, px: float) -> list:
    zs = [z for z in zones or [] if z.get("price") and ((z["price"] > px) if above else (z["price"] <= px))]
    zs.sort(key=lambda z: -(z.get("usd") or z.get("weight") or 0))
    return [[round(float(z["price"]), 8), round(float(z.get("usd") or z.get("weight") or 0), 2)] for z in zs[:3]]


def build_rows(candle_ms: int, only: list[str] | None = None) -> list[dict]:
    cg = _read(BASE_DIR / "output" / "coinglass_fetch.json") or {}
    coins = cg.get("coins") or {}
    rep = _read(BASE_DIR / "output" / "reputation.json") or {}
    oit = (_read(BASE_DIR / "output" / "oi_types.json") or {}).get("coins") or {}
    liq_last = _last_jsonl_by_sym(BASE_DIR / "output" / "liq_log.jsonl")
    candle = __import__("time").strftime("%Y-%m-%dT%H:%M:00Z", __import__("time").gmtime(candle_ms / 1000))
    rows = []
    syms = only or sorted(coins.keys())
    for sym in syms:
        sym = sym.upper()
        if not sym.endswith("USDT"):
            sym += "USDT"
        c = coins.get(sym) or coins.get(sym.replace("USDT", "")) or {}
        missing: list[str] = list(c.get("missing") or [])
        fut = _legs(_bar_at((c.get("fut") or {}).get("series") or [], candle_ms))
        spot = _legs(_bar_at((c.get("spot") or {}).get("series") or [], candle_ms))
        if fut is None and "fut" not in missing:
            missing.append("fut_bar")
        # тип часа по плечу — час, в который попадает свеча
        oi_type = None
        hours = (oit.get(sym) or {}).get("hours") or []
        hour_ms = (candle_ms // 3600000) * 3600000
        for h in hours:
            if int(h[0]) == hour_ms or int(h[0]) == hour_ms + 3600000:
                oi_type = h[1]
                break
        if oi_type is None and hours:
            missing.append("oi_type")
        r = rep.get(sym) or {}
        lq = liq_last.get(sym.replace("USDT", "")) or {}
        px = None
        for cand in (lq.get("px"), r.get("px"), r.get("close")):
            if cand:
                px = float(cand)
                break
        zones = None
        if lq and px:
            zh = lq.get("zones_hour") or lq.get("zones_day") or []
            zones = {"up": _top3(zh, True, px), "down": _top3(zh, False, px)}
        elif lq:
            missing.append("zones")
        rows.append({
            "candle": candle, "sym": sym, "px": px,
            "fut": fut, "spot": spot,
            "oi": c.get("oiUsd"), "oi_chg_pct": c.get("oiChgPct"),
            "funding": c.get("funding"),
            "taker24": (c.get("fut") or {}).get("taker"),
            "delta24": (round(((c.get("fut") or {}).get("buyUsd") or 0) - ((c.get("fut") or {}).get("sellUsd") or 0), 0)
                        if c.get("fut") else None),
            "liq24": {"long": (c.get("liq") or {}).get("long24h"), "short": (c.get("liq") or {}).get("short24h")} if c.get("liq") else None,
            "oi_type": oi_type,
            "plot": (r.get("plot") or "").split("(")[0].strip() or None, "stage": r.get("stage"),
            "zones": zones,
            "missing": missing,
        })
    return rows


def write_rows(rows: list[dict]) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for r in rows:
        base = r["sym"].replace("USDT", "").lower()
        p = OUT_DIR / f"{base}.jsonl"
        if p.exists():
            tail = p.read_text(encoding="utf-8")[-4000:]
            if f'"candle": "{r["candle"]}"' in tail:
                continue   # свеча уже записана
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="монеты через запятую")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--candle", help="свеча ISO (для дозабора); по умолчанию — последняя закрытая")
    a = ap.parse_args()
    if a.candle:
        from datetime import datetime, timezone
        t = a.candle.replace("Z", "+00:00")
        d = datetime.fromisoformat(t)
        candle_ms = int((d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp() * 1000)
    else:
        import candle_gate
        candle_ms = candle_gate.boundary()
    rows = build_rows(candle_ms, [x.strip() for x in a.only.split(",")] if a.only else None)
    if not a.write:
        for r in rows[:3]:
            print(json.dumps(r, ensure_ascii=False))
        print(f"строк {len(rows)} (без записи; --write чтобы записать)")
        return 0
    n = write_rows(rows)
    print(f"intraday: записано {n} строк из {len(rows)} → {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
