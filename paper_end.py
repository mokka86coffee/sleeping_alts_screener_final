#!/usr/bin/env python3
"""БУМАЖНЫЙ БОТ «ШОРТ ПО КОНЦУ» (16.09; владелец: «у нас выборка каждые полчаса, сколько всего закончилось — по ним
бахнули шорты; чем больше был рост до сигнала, тем больше размер шорта»).
Бар «конец»: интерес −2% за бар при отрицательной дельте и цене ниже предыдущей — то самое событие конца из
near_move. По 16 архивам 11–16.09 (122 бара) против контроля «любой бар той же недели»:
  рост за сутки до сигнала <5%:  шорт 12 ч медиана +1.70% (контроль +0.66%), ≥+2% в 47% (контроль 28%);
  5–15%:                         +3.77% (контроль +1.11%), 61% (41%);
  15–40%:                        +5.91% (контроль +0.85%), 60% (40%), n=10;
  худший ход против шорта за 6 ч при росте ≥15%: медиана 0.2%, 75-й перцентиль 1.9%.
Размер — по росту: PAPER_END_SIZE = {<5%: 0.5, 5–15%: 1.0, 15–40%: 2.0, >40%: 3.0}; цель — по росту
(PAPER_END_TARGET), стоп PAPER_END_STOP по размаху, срок PAPER_END_HOLD баров. Одна неделя одного фона — журналить.
Данные: cq_v2/intraday/<монета>.jsonl. Состояние output/paper_end.json, журнал output/paper_end.jsonl.
Запуск из прогона; руками `python3 paper_end.py --only ARK` (без записи), `--write`.
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
    from core_config import PAPER_END_STOP, PAPER_END_HOLD, PAPER_END_FEE, PAPER_END_SIZE, PAPER_END_TARGET, PAPER_END_OI_DROP
except ImportError:
    PAPER_END_STOP, PAPER_END_HOLD, PAPER_END_FEE, PAPER_END_OI_DROP = 0.03, 24, 0.001, -0.02
    PAPER_END_SIZE = [(5, 0.5), (15, 1.0), (40, 2.0), (10 ** 9, 3.0)]
    PAPER_END_TARGET = [(5, 0.02), (15, 0.035), (40, 0.06), (10 ** 9, 0.10)]
try:
    from core_config import PAPER_END_BOARD_N, PAPER_END_MAX_PER_RUN
except ImportError:
    PAPER_END_BOARD_N, PAPER_END_MAX_PER_RUN = 5, 5

ARCH = BASE_DIR / "cq_v2" / "intraday"
STATE = BASE_DIR / "output" / "paper_end.json"
LOG = BASE_DIR / "output" / "paper_end.jsonl"


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
        if r.get("px") and r.get("oi"):
            r["t"] = int(datetime.strptime(r["candle"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
            out.append(r)
    return out


def bucket(table, run_pct: float):
    for lim, val in table:
        if run_pct < lim:
            return val
    return table[-1][1]


def signal(rows: list[dict]) -> dict | None:
    if len(rows) < 50:
        return None
    i = len(rows) - 1
    C = [r["px"] for r in rows]
    OI = [r["oi"] for r in rows]
    d = (rows[i].get("fut") or {}).get("d") or 0
    oi_chg = OI[i] / OI[i - 1] - 1 if OI[i - 1] else 0
    if not (oi_chg <= PAPER_END_OI_DROP and d < 0 and C[i] < C[i - 1]):
        return None
    run = (C[i - 1] / min(C[i - 48:i]) - 1) * 100
    return {"t": rows[i]["t"], "px": C[i], "run_pct": round(run, 1), "oi_bar_pct": round(oi_chg * 100, 2), "delta": d,
            "size": bucket(PAPER_END_SIZE, run), "target": bucket(PAPER_END_TARGET, run), "rule": "конец: интерес −2% за бар, дельта <0, цена вниз"}


def check_exit(pos: dict, rows: list[dict]):
    after = [r for r in rows if r["t"] > pos["t"]]
    e = pos["px"]
    for k, r in enumerate(after, 1):
        if r.get("h") and (r["h"] / e - 1) >= PAPER_END_STOP:
            return -PAPER_END_STOP - PAPER_END_FEE, f"стоп на баре {k}"
        res = e / r["px"] - 1
        if res >= pos["target"]:
            return res - PAPER_END_FEE, f"цель на баре {k}"
        if k >= PAPER_END_HOLD:
            return res - PAPER_END_FEE, f"срок {PAPER_END_HOLD} баров"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    syms = ([x.strip().upper() + ("" if x.strip().upper().endswith("USDT") else "USDT") for x in a.only.split(",")] if a.only
            else sorted(p.stem.upper() + "USDT" for p in ARCH.glob("*.jsonl")))
    state = _read(STATE) or {"open": {}, "last_sig": {}}
    now = int(time.time())
    opened, closed = [], []
    cands = []
    for sym in syms:
        rows = rows_of(sym)
        if len(rows) < 50:
            continue
        pos = state["open"].get(sym)
        if pos:
            ex = check_exit(pos, rows)
            if ex:
                res, why = ex
                closed.append(dict(pos, sym=sym, kind="exit", result_pct=round(res * 100, 2), result_sized_pct=round(res * pos["size"] * 100, 2), why_exit=why, at=now))
                del state["open"][sym]
                print(f"paper_end: {sym} · выход · {why} · {res * 100:+.2f}% × размер {pos['size']} = {res * pos['size'] * 100:+.2f}%")
                pos = None
        sig = signal(rows)
        if sig and not pos and sig["t"] > (state.get("last_sig", {}).get(sym) or 0):
            cands.append((sym, sig))
    # СОБЫТИЕ ДОСКИ (16.09: первый живой прогон открыл 20 шортов разом — это одна ставка ×20, «конец» в час слива
    # случается у всех). Если кандидатов ≥ PAPER_END_BOARD_N — берём PAPER_END_MAX_PER_RUN с наибольшим ростом до
    # сигнала (там край выше), остальным пишем last_sig, чтобы не открыть на следующем прогоне; событие — в журнал.
    if len(cands) >= PAPER_END_BOARD_N:
        cands.sort(key=lambda x: -x[1]["run_pct"])
        skipped = cands[PAPER_END_MAX_PER_RUN:]
        cands = cands[:PAPER_END_MAX_PER_RUN]
        for sym, sig in skipped:
            state.setdefault("last_sig", {})[sym] = sig["t"]
        opened.append({"kind": "board", "at": now, "n": len(cands) + len(skipped), "taken": [s for s, _ in cands], "skipped": [s for s, _ in skipped]})
        print(f"paper_end: событие доски — «конец» у {len(cands) + len(skipped)} монет, беру {len(cands)}: {', '.join(s[:-4] for s, _ in cands)}")
    for sym, sig in cands:
        state["open"][sym] = dict(sig, opened_at=now)
        state.setdefault("last_sig", {})[sym] = sig["t"]
        opened.append(dict(sig, sym=sym, kind="entry", at=now))
        print(f"paper_end: {sym} · шорт {sig['px']:.6g} · рост до сигнала {sig['run_pct']:+.1f}% → размер {sig['size']}, цель {sig['target'] * 100:.1f}% · интерес {sig['oi_bar_pct']:+.2f}% за бар")
    if a.write:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            for r in opened + closed:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE)
    print(f"paper_end: открыто {len(opened)}, закрыто {len(closed)}, в позиции {len(state['open'])}" + ("" if a.write else " (без записи)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
