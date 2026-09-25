#!/usr/bin/env python3
"""ПЛИТЫ СТАКАНА РАЗ В ТРИ МИНУТЫ (25.09, владелец: «нужны две вещи — сделки из новой стратегии и те монеты, что я
заношу в файл руками; по ним проверка плит раз в три минуты»).

Зовёт run.py --loop своим потоком раз в три минуты. Монеты — открытые сделки «3 в первых подряд»
(output/paper_first3.json) и монеты watch.json. По каждой: снимок стакана фьючерса и спота и судьба стен — функциями depth_fetch (те же пороги
стены, то же «съели / сняли»). Снимки держатся в своей памяти output/depth_tick.json — получасовой стакан, его
архив и карточка не трогаются.

Тревога — как у прогона (run.py _fast_alerts): ушла стена, простоявшая не меньше DEPTH_TICK_MIN_SNAPS снимков,
не дальше 30% от цены. Строка «⏱ МОМЕНТ» в том же виде, вместо «после N пр.» — «стояла N мин».
Ключи отправленного — в общем output/alerts_sent.json с меткой tick: прогон по той же стене второй раз не шлёт.

    python3 depth_tick.py              # что ушло бы сейчас, без записи и без телеграма
    python3 depth_tick.py --write      # снимок, память, телеграм (так зовёт run.py)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
try:
    from core_config import DEPTH_TICK_MIN_SNAPS, DEPTH_SPOT
except ImportError:
    DEPTH_TICK_MIN_SNAPS, DEPTH_SPOT = 10, True

import depth_fetch as df

FIRST3 = BASE_DIR / "output" / "paper_first3.json"
WATCH = BASE_DIR / "watch.json"
MEM = BASE_DIR / "output" / "depth_tick.json"
SENT = BASE_DIR / "output" / "alerts_sent.json"
SNAP_MIN = 3
KEEP = 40                      # снимков на монету — два часа, дольше судьбе смотреть незачем
FAR_PCT = 30                   # дальше — застрявшие продавцы, как в run.py _fast_alerts


def _read(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def coins() -> list[str]:
    """сделки нового бота, потом монеты владельца; повторы схлопываются"""
    out = list(((_read(FIRST3, {}) or {}).get("open") or {}).keys())
    for c in (_read(WATCH, {}) or {}).get("coins") or []:
        s = str((c or {}).get("sym") or "").upper()
        if s:
            out.append(s if s.endswith("USDT") else s + "USDT")
    return list(dict.fromkeys(s.upper() for s in out))


def take(sym: str, ts: int) -> dict | None:
    raw = df.get_depth(sym)
    snap = df.snapshot(sym, raw, ts) if raw else None
    if not snap:
        return None
    if DEPTH_SPOT:
        sraw = df.get_spot_depth(sym)
        ss = df.snapshot(sym, sraw, ts, kind="spot") if sraw else None
        if ss:
            snap["walls"] = sorted(snap["walls"] + ss["walls"], key=lambda w: -w["usd"])[:24]
    return {"t": snap["t"], "mid": snap["mid"], "walls": snap["walls"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    syms = coins()
    mem = _read(MEM, {}) or {}
    sent = _read(SENT, {}) or {}
    ts = int(time.time() // 60 * 60 * 1000)
    lines, keys = [], []
    for sym in syms:
        snap = take(sym, ts)
        if not snap:
            print(f"depth_tick: {sym} — стакан не получен")
            continue
        hist = mem.get(sym) or []
        # дыра в памяти (монета выпадала из списка, прогон стоял) — судьбу по старому снимку не судим
        if hist and ts - int(hist[-1]["t"]) > 2 * SNAP_MIN * 60_000:
            hist = []
        ft = df.fate(sym, snap, hist)
        for g in ft["gone"]:
            if g["runs"] < DEPTH_TICK_MIN_SNAPS or abs(g.get("dist_pct") or 0) > FAR_PCT:
                continue
            k = f"wall|{sym}|{g['side']}|{g['px']}|{g['at']}|tick"
            if k in sent:
                continue
            ask = g["side"] == "ask"
            what = (f"съели — прошли {'вверх' if ask else 'вниз'}" if g["fate"] == "съели"
                    else f"убрали — цена не доходила, {'путь вверх свободен' if ask else 'опора ушла'}")
            lines.append(f"{sym[:-4]} · {'потолок' if ask else 'пол'} {g['px']:.6g} ({g['dist_pct']:+.1f}%, "
                         f"${g.get('usd', 0) / 1e3:.0f}K) {what}, стояла {g['runs'] * SNAP_MIN} мин")
            keys.append(k)
        mem[sym] = (hist + [snap])[-KEEP:]
    mem = {s: h for s, h in mem.items() if h and ts - int(h[-1]["t"]) <= KEEP * SNAP_MIN * 60_000}
    for ln in lines:
        print(f"depth_tick: {ln}")
    print(f"depth_tick: монет {len(syms)} · тревог {len(lines)}")
    if not a.write:
        return 0
    from sources_storage import write_atomic
    write_atomic(MEM, json.dumps(mem, ensure_ascii=False))
    if lines:
        from send_brief_telegram import load_config, send_telegram
        cfg = load_config()
        if cfg and send_telegram("⏱ МОМЕНТ\n" + "\n".join(lines[:8]), cfg):
            sent = _read(SENT, {}) or {}          # перечитать: прогон мог дописать своё за эти секунды
            now = int(time.time())
            sent.update({k: now for k in keys})
            sent = {k: v for k, v in sent.items() if v >= now - 3 * 86400}
            write_atomic(SENT, json.dumps(sent, ensure_ascii=False))
        else:
            print("depth_tick: телеграм не ушёл")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
