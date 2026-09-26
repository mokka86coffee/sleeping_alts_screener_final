#!/usr/bin/env python3
"""ОБЩИЙ КАРКАС БУМАЖНЫХ КНИГ ПО ПОЛУЧАСОВКАМ (26.09): одна позиция на монету, вход по сигналу на последнем закрытом баре архива, выход — цель по
максимуму бара, стоп по минимуму, срок в барах; журнал entry/exit/follow, состояние {"open", "last_exit", "last_sig"}. Используют paper_interest.py и
paper_second.py. Данные: cq_v2/intraday/<монета>.jsonl (px, h, l, oi, funding, fut, spot, kv), output/near_move.json (nums.run_from_low7)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
ARCH = BASE_DIR / "cq_v2" / "intraday"
FEE = 0.001


def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def rows_of(sym: str) -> list[dict]:
    """получасовки архива по порядку свечей, без будущих; повтор свечи — последняя запись"""
    p = ARCH / f"{sym.replace('USDT', '').lower()}.jsonl"
    by: dict = {}
    if not p.exists():
        return []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("px") and r.get("candle"):
            try:
                r["t"] = int(datetime.strptime(r["candle"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
            except ValueError:
                continue
            by[r["t"]] = r
    now_ms = int(time.time() * 1000)
    # 26.09: история 30 дн с Binance (claude/research/hist30.py → cq_v2/hist30) — в архиве спот только с 23.09, фандинг с ~23.09,
    # интерес с ~18.09; книге «второй ход» нужна база до 20 дн. Поля hist30 подставляются туда, где у архива пусто.
    h = BASE_DIR / "cq_v2" / "hist30" / f"{sym.replace('USDT', '').lower()}.json"
    if h.exists():
        try:
            for r in json.loads(h.read_text(encoding="utf-8")):
                t = int(r["t"])
                if t in by:
                    for k in ("oi", "funding", "spot", "h", "l"):
                        if by[t].get(k) is None and r.get(k) is not None:
                            by[t][k] = r[k]
                else:
                    by[t] = dict(r, candle=datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), sym=sym)
        except (OSError, ValueError):
            pass
    return [by[t] for t in sorted(by) if t <= now_ms]


def nums_of(sym: str) -> dict:
    nm = read_json(BASE_DIR / "output" / "near_move.json") or {}
    return (((nm.get("coins") or {}).get(sym) or {}).get("nums") or {})


def hm(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%d.%m %H:%M")


def run_book(book: str, state_path: Path, log_path: Path, signal, size: float, pause_h: float, only: str | None, write: bool) -> int:
    """один шаг книги: выходы по открытым позициям по новым барам, потом входы по сигналам последнего бара"""
    syms = ([x.strip().upper() + ("" if x.strip().upper().endswith("USDT") else "USDT") for x in only.split(",")] if only
            else sorted(p.stem.upper() + "USDT" for p in ARCH.glob("*.jsonl")))
    state = read_json(state_path) or {"open": {}, "last_exit": {}, "last_sig": {}}
    for k in ("open", "last_exit", "last_sig"):
        state.setdefault(k, {})
    now = int(time.time())
    events: list[dict] = []
    for sym in syms:
        rows = rows_of(sym)
        if len(rows) < 100:
            continue
        pos = state["open"].get(sym)
        if pos:
            e = float(pos["px"])
            for r in rows:
                if r["t"] <= int(pos.get("last_t") or pos["t"]):
                    continue
                pos["last_t"] = r["t"]; pos["bars"] = int(pos.get("bars") or 0) + 1
                h, l, c = float(r.get("h") or r["px"]), float(r.get("l") or r["px"]), float(r["px"])
                pos["max_px"] = max(float(pos.get("max_px") or e), h); pos["last_px"] = c
                res, why = None, None
                if pos.get("stop") is not None and l <= e * (1 - float(pos["stop"])):        # 26.09: стоп может быть выключен (None)
                    res, why = -float(pos["stop"]) - FEE, f"стоп −{float(pos['stop']) * 100:.0f}% на баре {pos['bars']}"
                elif h >= e * (1 + float(pos["target"])):
                    res, why = float(pos["target"]) - FEE, f"цель +{float(pos['target']) * 100:.0f}% на баре {pos['bars']}"
                elif pos["bars"] >= int(pos["hold"]):
                    res, why = c / e - 1 - FEE, f"срок {pos['hold']} баров"
                if why:
                    events.append(dict(book=book, sym=sym, kind="exit", px_in=e, px_out=round(e * (1 + res + FEE), 8), opened_at=pos["at"], at=now,
                                       result_pct=round(res * 100, 2), usd=round(size * res, 2), why_exit=why, mfe_pct=round((pos["max_px"] / e - 1) * 100, 2), rule=pos.get("rule")))
                    state["last_exit"][sym] = now
                    del state["open"][sym]
                    print(f"{book}: {sym} · выход · {why} · {res * 100:+.2f}% · макс {(pos['max_px'] / e - 1) * 100:+.1f}%")
                    pos = None
                    break
            if pos:
                events.append(dict(book=book, sym=sym, kind="follow", px_in=e, px=pos["last_px"], result_pct=round((pos["last_px"] / e - 1) * 100, 2),
                                   mfe_pct=round((pos["max_px"] / e - 1) * 100, 2), bars=pos["bars"], at=now))
        if state["open"].get(sym):
            continue
        if now - float(state["last_exit"].get(sym) or 0) < pause_h * 3600:
            continue
        sig = signal(rows, nums_of(sym))
        if not sig or sig["t"] <= int(state["last_sig"].get(sym) or 0):
            continue
        state["last_sig"][sym] = sig["t"]
        pos = dict(sym=sym, px=float(sig["px"]), t=sig["t"], at=now, size=size, target=float(sig["target"]),
                   stop=(None if sig.get("stop") is None else float(sig["stop"])), hold=int(sig["hold"]),
                   rule=sig["rule"], max_px=float(sig["px"]), last_px=float(sig["px"]), bars=0, last_t=sig["t"])
        state["open"][sym] = pos
        events.append(dict(book=book, sym=sym, kind="entry", px=pos["px"], at=now, usd_in=size, rule=sig["rule"], target=pos["target"], stop=pos["stop"], **{k: v for k, v in sig.items() if k not in ("t", "px", "target", "stop", "hold", "rule")}))
        print(f"{book}: {sym} · вход лонг {pos['px']:.6g} · {sig['rule']} · цель +{pos['target'] * 100:.0f}% · " + ("без стопа" if pos['stop'] is None else f"стоп −{pos['stop'] * 100:.0f}%"))
    if write:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            for r in events:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp = state_path.with_suffix(".tmp"); tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8"); tmp.replace(state_path)
    n_in = sum(1 for e in events if e["kind"] == "entry"); n_out = sum(1 for e in events if e["kind"] == "exit")
    print(f"{book}: открыто {n_in}, закрыто {n_out}, в позиции {len(state['open'])}" + ("" if write else " (без записи)"))
    return 0
