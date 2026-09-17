#!/usr/bin/env python3
"""БУМАЖНЫЙ БОТ «ДНО» (17.09, владелец: ENA — лонг от дна на белых пузырях 4ч, «хочется, чтобы такие вещи тоже
попадали в торговлю»). Пока НАБЛЮДЕНИЕ: в отбор очереди и в балл не входит, пишет свою книгу и журнал.

Вход — лонг (analytics_bottom.analyse):
  • ясный белый пузырь на четырёх часах за последние BOTTOM_BUBBLE_FRESH_4H баров;
  • его минимум не дальше BOTTOM_NEAR_PCT от дна BOTTOM_LOOKBACK_D дней, цена не ушла дальше BOTTOM_CHASE_PCT;
  • доводов «за» не меньше BOTTOM_MIN_ZA: клингер 30м или 4ч вверх, интерес и дельта за сутки в плюсе,
    ясный белый пузырь на получасовке; «против» пусто — нет свежего конца (вынос по доске концом не считается),
    нет ясного пузыря продажи 4ч после входного, нет «тянет одна».
Выход — «рука ушла» (стратегия владельца: выход только по событию):
  • ясный пузырь продажи на 4ч после входа;
  • событие конца на получасовке, если это не вынос по доске;
  • интерес падает BOTTOM_LEAVE_OI_RUNS баров подряд при цене не выше прошлого бара;
  • страховка — закрытие ниже дна на BOTTOM_STOP_BELOW; для класса DWF (unlocks.json → investors) цены-стопа
    нет: снятие дна у них и есть сбор (11.09, LAB и PLAY);
  • срок BOTTOM_HOLD_BARS получасовок.
В строку входа пишется весь список «за» и «против» и правило карточки о втором заходе к дну — через неделю
видно, сколько раз «ждать» было право.

Состояние output/paper_bottom.json (open, last_sig, signals — живые сигналы прогона для звёзд),
журнал output/paper_bottom.jsonl. Запуск из прогона; руками:
    python3 paper_bottom.py --only ENA                   # что сейчас, без записи
    python3 paper_bottom.py --only ENA --replay 8        # где сигнал вставал за 8 дней по архиву
    python3 paper_bottom.py --write
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
    from core_config import (BOTTOM_HOLD_BARS, BOTTOM_STOP_BELOW, BOTTOM_LEAVE_OI_RUNS, BOTTOM_MAX_PER_RUN,
                             BOTTOM_SIZE, BOTTOM_FEE)
except ImportError:
    BOTTOM_HOLD_BARS, BOTTOM_STOP_BELOW, BOTTOM_LEAVE_OI_RUNS, BOTTOM_MAX_PER_RUN = 144, 0.03, 4, 3
    BOTTOM_SIZE, BOTTOM_FEE = 1.0, 0.001

import analytics_bottom as ab

STATE = BASE_DIR / "output" / "paper_bottom.json"
LOG = BASE_DIR / "output" / "paper_bottom.jsonl"
BOOK_NAME = "paper_bottom"


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _dwf(sym: str) -> bool:
    """класс DWF — по полю investors в unlocks.json (ведётся руками)"""
    for p in (BASE_DIR / "unlocks.json", BASE_DIR / "output" / "unlocks.json"):
        d = _read(p)
        if not d:
            continue
        rec = d.get(sym) or d.get(sym.replace("USDT", "")) if isinstance(d, dict) else None
        if rec is None and isinstance(d, dict):
            rec = (d.get("coins") or {}).get(sym) or (d.get("coins") or {}).get(sym.replace("USDT", ""))
        inv = " ".join(map(str, (rec or {}).get("investors") or [])) if isinstance(rec, dict) else ""
        return "DWF" in inv.upper()
    return False


def _opposite_open(sym: str) -> str | None:
    """встречная позиция в соседней книге (как у paper_crowd): шорт там — лонг здесь не берём"""
    for nm in ("paper_end", "paper_crowd", "paper_fast"):
        d = _read(BASE_DIR / "output" / f"{nm}.json") or {}
        p = (d.get("open") or {}).get(sym)
        if not p:
            continue
        s = p.get("side")
        if s is None:
            s = -1 if (nm == "paper_end" or str(p.get("state")) == "short") else 1
        if int(s) < 0:
            return nm
    return None


def check_exit(pos: dict, rows: list[dict], ends: tuple | None) -> tuple[float, str] | None:
    """выход по барам после входа: рука ушла, страховка под дном, срок"""
    after = [r for r in rows if r["t"] > pos["t"]]
    if not after:
        return None
    e = float(pos["px"])
    b4 = ab.bars4h(rows)
    sells = [b for b in ab.bubbles4h(b4) if b["side"] == "sell" and b["sure"] == "ясный" and b["t"] > pos["t"]]
    ends_mine = set(ab.end_bars(rows))
    run_down, prev = 0, None
    for k, r in enumerate(after, 1):
        c = float(r["px"])
        res = c / e - 1
        # 1) ясный пузырь продажи 4ч — на закрытии его бара
        s4 = next((b for b in sells if b["t_end"] - ab.BAR == r["t"]), None)
        if s4:
            return res - BOTTOM_FEE, f"рука ушла: пузырь продажи 4ч {ab._hm(s4['t'])}"
        # 2) событие конца, не вынос по доске
        if r["t"] in ends_mine:
            share = ab.board_end_share(ends[0], r["t"], ends[1]) if ends else 0.0
            if not (share >= ab.BOARD_END_SHARE and ends and ends[1] >= ab.BOARD_END_MIN_COINS):
                return res - BOTTOM_FEE, f"рука ушла: событие конца на баре {k}"
        # 3) интерес вниз N баров подряд при цене не выше прошлого бара
        if prev is not None and r.get("oi") and prev.get("oi"):
            if float(r["oi"]) < float(prev["oi"]) and c <= float(prev["px"]):
                run_down += 1
            else:
                run_down = 0
            if run_down >= BOTTOM_LEAVE_OI_RUNS:
                return res - BOTTOM_FEE, f"рука ушла: интерес вниз {run_down} бара подряд"
        prev = r
        # 4) страховка под дном — по закрытию, не для класса DWF
        if pos.get("stop_px") and c < float(pos["stop_px"]):
            return res - BOTTOM_FEE, f"закрытие под дном на баре {k}"
        if k >= int(pos.get("hold") or BOTTOM_HOLD_BARS):
            return res - BOTTOM_FEE, f"срок {int(pos.get('hold') or BOTTOM_HOLD_BARS)} баров"
    return None


def _entry(sym: str, a: dict) -> dict:
    dwf = _dwf(sym)
    stop_px = None if dwf else a["bottom"] * (1 - BOTTOM_STOP_BELOW)
    e = a["px"]
    b = a["bubble"] or {}
    return {"rule": "дно: пузырь 4ч у дна", "side": 1, "t": a["t"], "px": e, "size": BOTTOM_SIZE,
            "target": None, "hold": BOTTOM_HOLD_BARS,
            "stop": round(1 - stop_px / e, 4) if stop_px else None, "stop_px": stop_px,
            "bottom": a["bottom"], "bottom_t": a["bottom_t"], "dist_bubble_pct": a.get("dist_bubble_pct"),
            "dist_now_pct": a.get("dist_now_pct"), "bubble_t": b.get("t"), "bubble_z": b.get("z"),
            "bubble_oi_pct": b.get("oi_pct"), "dwf": dwf,
            "za": [list(x) for x in a.get("za") or []], "protiv": [list(x) for x in a.get("protiv") or []],
            "card_rule": a.get("card_rule"), "second_quiet": a.get("second_quiet"),
            "oi24": a.get("oi24"), "d24": a.get("d24"),
            "why": a.get("why")}


def replay(sym: str, days: int) -> int:
    """прогон по истории: на каждом закрытом баре — встал ли сигнал (первый бар каждой серии)"""
    rows = ab.load_rows(sym, days=days + ab.BOTTOM_LOOKBACK_D)
    if not rows:
        print(f"{sym}: архива нет")
        return 1
    start = rows[-1]["t"] - days * 86_400_000
    was = False
    n = 0
    for r in rows:
        if r["t"] < start:
            continue
        a = ab.analyse(sym, rows=rows, upto=r["t"])
        if a["ok"] and not was:
            n += 1
            print(f"{ab._hm(r['t'])} UTC · цена {a['px']:.6g} · дно {a['bottom']:.6g} · от дна {a['dist_now_pct']:+.1f}% · "
                  f"{a['card_rule']}\n   {a['why']}")
        was = a["ok"]
    print(f"{sym}: сигналов за {days} дн — {n} (вынос по доске в прогоне по истории не учитывается)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--replay", type=int, default=0)
    a = ap.parse_args()
    if a.only:
        syms = [x.strip().upper() + ("" if x.strip().upper().endswith("USDT") else "USDT") for x in a.only.split(",")]
    else:
        syms = sorted(p.stem.upper() + "USDT" for p in ab.ARCH.glob("*.jsonl"))
    if a.replay:
        for s in syms:
            replay(s, a.replay)
        return 0
    state = _read(STATE) or {"open": {}}
    state.setdefault("open", {})
    now = int(time.time())
    ends = ab.board_ends(days=2)
    events, cands, signals = [], [], []
    for sym in syms:
        rows = ab.load_rows(sym, days=ab.BOTTOM_LOOKBACK_D + 3)
        if len(rows) < 60:
            continue
        pos = state["open"].get(sym)
        if pos:
            ex = check_exit(pos, rows, ends)
            if ex:
                res, why = ex
                events.append(dict(pos, sym=sym, kind="exit", result_pct=round(res * 100, 2),
                                   result_sized_pct=round(res * pos.get("size", 1.0) * 100, 2), why_exit=why, at=now))
                del state["open"][sym]
                print(f"paper_bottom: {sym} · выход · {why} · {res * 100:+.2f}%")
                pos = None
        r = ab.analyse(sym, rows=rows, ends=ends)
        if a.only:
            print(f"paper_bottom: {sym} · {'СИГНАЛ' if r['ok'] else 'нет'} · {r['why']}"
                  + (f" · {r.get('card_rule')}" if r.get("card_rule") else ""))
        if not r["ok"]:
            continue
        signals.append({"sym": sym, "t": r["t"], "px": r["px"], "bottom": r["bottom"],
                        "dist_now_pct": r["dist_now_pct"], "why": r["why"], "card_rule": r.get("card_rule")})
        if pos or r["t"] <= (state.get("last_sig", {}).get(sym) or 0):
            continue
        opp = _opposite_open(sym)
        if opp:
            print(f"paper_bottom: {sym} · пропуск — встречная позиция в {opp}")
            continue
        cands.append((sym, r))
    # несколько сразу — одна ставка на рынок, а не несколько сделок (как событие доски у толпы)
    cands.sort(key=lambda x: (-len(x[1]["za"]), x[1]["dist_now_pct"]))
    skipped = cands[BOTTOM_MAX_PER_RUN:]
    cands = cands[:BOTTOM_MAX_PER_RUN]
    if skipped:
        events.append({"kind": "board", "at": now, "taken": [s for s, _ in cands], "skipped": [s for s, _ in skipped]})
        for s, rr in skipped:
            state.setdefault("last_sig", {})[s] = rr["t"]
    for sym, r in cands:
        pos = dict(_entry(sym, r), opened_at=now)
        state["open"][sym] = pos
        state.setdefault("last_sig", {})[sym] = r["t"]
        events.append(dict(pos, sym=sym, kind="entry", at=now))
        print(f"paper_bottom: {sym} · вход лонг {r['px']:.6g} · дно {r['bottom']:.6g} · {r['why']} · карточка: {r.get('card_rule')}")
    state["signals"] = signals
    state["at"] = now
    if a.write:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE)
    print(f"paper_bottom: сигналов {len(signals)}, открыто {len(cands)}, закрыто "
          f"{sum(1 for e in events if e.get('kind') == 'exit')}, в позиции {len(state['open'])}"
          + ("" if a.write else " (без записи)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
