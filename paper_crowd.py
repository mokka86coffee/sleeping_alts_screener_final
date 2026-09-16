#!/usr/bin/env python3
"""БУМАЖНЫЙ БОТ «ПРОТИВ ТОЛПЫ ПО ФОНУ» (16.09). Второй бот рядом с paper_fast: короткие сделки, до 3 часов.
Что дала неделя 11–16.09 на 16 монетах (lab_intraday по архивам):
  • шорт «против толпы» — три бара подряд «лонги открывают» при фандинге около нуля → цель −1.5%:
    63% попаданий, +0.42% на сделку; при ровных 12 часах монеты — 78%;
  • шорт по перекупленности — z(20) > +2 при цене монеты вверх за 12 ч → выход z < 0: 53%, +0.68%;
  • лонг «за толпой» — три бара «лонги закрывают» при цене монеты вниз за 12 ч → цель +1.5%: 67%, +0.59%.
Лонги по перекупленности/RSI в минус — их здесь нет. Это ОДНА неделя одного фона; бот и нужен, чтобы через
две-четыре недели фон сменился и правила показали себя на другом. Правила — в журнал, не в деньги.

Данные: cq_v2/intraday/<монета>.jsonl (px, h, l, oi_type, funding) по всем монетам с ≥25 барами.
Стоп PAPER_CROWD_STOP по размаху бара, удержание ≤ PAPER_CROWD_HOLD баров, комиссия PAPER_CROWD_FEE, размер 1.0.
Состояние output/paper_crowd.json, журнал output/paper_crowd.jsonl (входы и выходы с причиной, фоном и результатом).
Запуск из прогона после архива; руками `python3 paper_crowd.py --only ARK` (без записи), `--write`.
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
    from core_config import PAPER_CROWD_STOP, PAPER_CROWD_HOLD, PAPER_CROWD_FEE, PAPER_CROWD_TARGET
except ImportError:
    PAPER_CROWD_STOP, PAPER_CROWD_HOLD, PAPER_CROWD_FEE, PAPER_CROWD_TARGET = 0.02, 6, 0.001, 0.015

ARCH = BASE_DIR / "cq_v2" / "intraday"
STATE = BASE_DIR / "output" / "paper_crowd.json"
LOG = BASE_DIR / "output" / "paper_crowd.jsonl"


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def rows_of(sym: str) -> list[dict]:
    p = ARCH / f"{sym.replace('USDT', '').lower()}.jsonl"
    out = []
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("px") and r.get("h") and r.get("l"):
            r["t"] = int(datetime.strptime(r["candle"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
            out.append(r)
    return out


def zs(C, i, N=20):
    w = C[i - N:i]
    m = sum(w) / N
    sd = (sum((x - m) ** 2 for x in w) / N) ** .5 or 1e-9
    return (C[i] - m) / sd


def signal(rows: list[dict]) -> dict | None:
    """Сигнал на последнем закрытом баре по трём правилам; None — тихо."""
    if len(rows) < 25:
        return None
    C = [r["px"] for r in rows]
    i = len(rows) - 1
    px12 = C[i - 1] / C[i - 24] - 1 if i >= 24 else 0.0
    bg = "↓" if px12 < -0.02 else "↑" if px12 > 0.02 else "ровно"
    fund = rows[i].get("funding")
    fund0 = fund is not None and -0.01 <= fund <= 0.02
    ot = [r.get("oi_type") for r in rows[i - 2:i + 1]]
    z = zs(C, i)
    base = {"t": rows[i]["t"], "px": C[i], "bg12": bg, "px12": round(px12 * 100, 2), "fund": fund, "z": round(z, 2)}
    if ot == ["long_open"] * 3 and fund0 and bg != "↑":
        return dict(base, side=-1, rule="против толпы: 3×лонги открывают", target=PAPER_CROWD_TARGET)
    if z > 2 and bg == "↑":
        return dict(base, side=-1, rule="перекуплен: z>+2 при ходе вверх 12ч", target=None)
    if ot == ["long_close"] * 3 and bg == "↓":
        return dict(base, side=1, rule="за толпой: 3×лонги закрывают при ходе вниз 12ч", target=PAPER_CROWD_TARGET)
    return None


def check_exit(pos: dict, rows: list[dict]) -> tuple[float, str] | None:
    """Выход по барам, закрытым после входа: стоп по размаху, цель по закрытию (или z<0 для z-правила), срок."""
    after = [r for r in rows if r["t"] > pos["t"]]
    if not after:
        return None
    e, side = pos["px"], pos["side"]
    C = [r["px"] for r in rows]
    for k, r in enumerate(after, 1):
        stopped = (r["l"] / e - 1) <= -PAPER_CROWD_STOP if side > 0 else (r["h"] / e - 1) >= PAPER_CROWD_STOP
        if stopped:
            return -PAPER_CROWD_STOP - PAPER_CROWD_FEE, f"стоп на баре {k}"
        res = side * (r["px"] / e - 1)
        if pos.get("target") is not None and res >= pos["target"]:
            return res - PAPER_CROWD_FEE, f"цель на баре {k}"
        if pos.get("target") is None:
            idx = rows.index(r)
            if idx >= 20 and side < 0 and zs(C, idx) < 0:
                return res - PAPER_CROWD_FEE, f"z<0 на баре {k}"
        if k >= PAPER_CROWD_HOLD:
            return res - PAPER_CROWD_FEE, f"срок {PAPER_CROWD_HOLD} баров"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    if a.only:
        syms = [x.strip().upper() + ("" if x.strip().upper().endswith("USDT") else "USDT") for x in a.only.split(",")]
    else:
        syms = sorted(p.stem.upper() + "USDT" for p in ARCH.glob("*.jsonl"))
    state = _read(STATE) or {"open": {}}
    now = int(time.time())
    opened, closed = [], []
    for sym in syms:
        rows = rows_of(sym)
        if len(rows) < 25:
            continue
        pos = state["open"].get(sym)
        if pos:
            ex = check_exit(pos, rows)
            if ex:
                res, why = ex
                closed.append(dict(pos, sym=sym, kind="exit", result_pct=round(res * 100, 2), why_exit=why, at=now))
                del state["open"][sym]
                print(f"paper_crowd: {sym} · выход · {why} · {res * 100:+.2f}% · {pos['rule']}")
                pos = None
        sig = signal(rows)
        if sig and not pos and sig["t"] > (state.get("last_sig", {}).get(sym) or 0):
            state["open"][sym] = dict(sig, opened_at=now)
            state.setdefault("last_sig", {})[sym] = sig["t"]
            opened.append(dict(sig, sym=sym, kind="entry", at=now))
            print(f"paper_crowd: {sym} · вход {'шорт' if sig['side'] < 0 else 'лонг'} {sig['px']:.6g} · {sig['rule']} · фон 12ч {sig['bg12']} · фандинг {sig['fund']}")
    if a.write:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            for r in opened + closed:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE)
    print(f"paper_crowd: открыто {len(opened)}, закрыто {len(closed)}, в позиции {len(state['open'])}" + ("" if a.write else " (без записи)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
