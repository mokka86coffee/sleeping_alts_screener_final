#!/usr/bin/env python3
"""ТРЁХМИНУТНАЯ СТУПЕНЬ (27.09, владелец: «зачем прогон для всех монет, если всплеск нужен только у тех, у кого был интерес за час —
раз в полчаса отбираем, каждые 3 минуты смотрим только их»). Книга «всплеск/вынос».
Короткий список — из архива получасовок (cq_v2/intraday, обновляется прогоном): монеты, у которых интерес за час ≥ FAST3_SHORT_OI1H %
(кандидаты на всплеск, лонг) и монеты с ходом от минимума 24 ч ≥ FAST3_SHORT_RUN24 % (кандидаты на вынос, шорт).
Каждые 3 минуты по списку — последняя закрытая трёхминутка Binance:
  всплеск (R39): объём ≥ FAST3_SPIKE_X × медианы 30 баров и ≥ FAST3_SPIKE_MINQ $, бар ≥ +FAST3_SPIKE_PCT → лонг; +5 / −5 / 2 ч;
  вынос (R21): бар ≥ +FAST3_CLIMAX_BAR и интерес на баре ≤ FAST3_CLIMAX_OI → шорт; −8 / +6 / 12 ч.
Выходы своих позиций каждые 3 минуты. Журнал output/paper_fast3.jsonl (entry / exit_long / exit_short / follow), состояние output/paper_fast3.json.
    python3 fast_tier.py --loop      # запускает прогон один раз (PAPER_FAST3_ENABLED), живёт сам
    python3 fast_tier.py             # один проход без записи
"""
from __future__ import annotations
import argparse, json, statistics as st, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
from core_http import get_json
from core_config import (FAST3_SIZE, FAST3_SPIKE_X, FAST3_SPIKE_MINQ, FAST3_SPIKE_PCT, FAST3_SPIKE_TP, FAST3_SPIKE_SL, FAST3_SPIKE_HOLD_MIN,
                         FAST3_CLIMAX_BAR, FAST3_CLIMAX_RUN, FAST3_CLIMAX_OI, FAST3_CLIMAX_TP, FAST3_CLIMAX_SL, FAST3_CLIMAX_HOLD_MIN,
                         FAST3_SHORT_OI1H, FAST3_SHORT_RUN24)
from paper_book_base import rows_of, ARCH
from book_fon import fon, coin_fon

BOOK = "всплеск/вынос"; FEE = 0.001
STATE = BASE_DIR / "output" / "paper_fast3.json"; LOG = BASE_DIR / "output" / "paper_fast3.jsonl"
L = timezone(timedelta(hours=3))


def short_list() -> tuple[list[str], list[str], dict]:
    spike, climax, info = [], [], {}
    for p in ARCH.glob("*.jsonl"):
        sym = p.stem.upper() + "USDT"; r = rows_of(sym)
        if len(r) < 49:
            continue
        oi1, oi0 = r[-1].get("oi"), r[-3].get("oi")
        oi1h = (float(oi1) / float(oi0) - 1) * 100 if oi1 and oi0 else None
        cf = coin_fon(r); info[sym] = dict(oi1h=oi1h, run24=cf.get("run24"), crowd=None)
        if oi1h is not None and oi1h >= FAST3_SHORT_OI1H: spike.append(sym)
        if cf.get("run24") is not None and cf["run24"] >= FAST3_SHORT_RUN24: climax.append(sym)
    return spike, climax, info


def scan(sym: str, want_spike: bool, want_climax: bool):
    k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "3m", "limit": 33}, quiet_400=True) or []
    if len(k) < 33:
        return None
    k = k[:-1]; qv = [float(x[7]) for x in k]; c = [float(x[4]) for x in k]; med = st.median(qv[:-1]); bar = c[-1] / c[-2] - 1
    out = []
    if want_spike and med > 0 and qv[-1] >= FAST3_SPIKE_X * med and qv[-1] >= FAST3_SPIKE_MINQ and bar >= FAST3_SPIKE_PCT:
        out.append((1, f"всплеск: бар {bar * 100:+.2f}% на объёме ×{qv[-1] / med:.1f} ({qv[-1] / 1e3:.0f}K$) (R39)", FAST3_SPIKE_TP, FAST3_SPIKE_SL, FAST3_SPIKE_HOLD_MIN))
    if want_climax and bar >= FAST3_CLIMAX_BAR:
        oi = get_json("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": sym, "period": "5m", "limit": 3}, quiet_400=True) or []
        ov = [float(x["sumOpenInterestValue"]) for x in oi]
        if len(ov) >= 2 and ov[-1] / ov[-2] - 1 <= FAST3_CLIMAX_OI:
            out.append((-1, f"вынос: бар {bar * 100:+.1f}% и интерес на баре {(ov[-1] / ov[-2] - 1) * 100:+.1f}% — шорты сгорели (R21)", FAST3_CLIMAX_TP, FAST3_CLIMAX_SL, FAST3_CLIMAX_HOLD_MIN))
    return sym, c[-1], int(k[-1][0]), out


def step(state: dict, write: bool) -> list[str]:
    now = time.time(); now_ms = int(now * 1000); ev = []; msgs = []
    # выходы
    for sym, pos in list(state["open"].items()):
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "3m", "startTime": int(pos["t_ms"]) + 180_000, "limit": 1000}, quiet_400=True, weight=5) or []
        k = [x for x in k if int(x[0]) + 180_000 <= now_ms]
        if not k:
            continue
        e, sd = float(pos["px"]), int(pos["side"]); hi = max(float(x[2]) for x in k); lo = min(float(x[3]) for x in k); c = float(k[-1][4])
        res = why = None
        if sd == 1:
            if lo <= e * (1 - pos["stop"]): res, why = -pos["stop"], "стоп"
            elif hi >= e * (1 + pos["target"]): res, why = pos["target"], "цель"
        else:
            if hi >= e * (1 + pos["stop"]): res, why = -pos["stop"], "стоп"
            elif lo <= e * (1 - pos["target"]): res, why = pos["target"], "цель"
        if res is None and len(k) * 3 >= pos["hold_min"]: res, why = (c / e - 1) * sd, f"срок {pos['hold_min']} мин"
        pos["last_px"] = c; pos["bars"] = len(k)
        if res is not None:
            res -= FEE
            ev.append(dict(book=BOOK, sym=sym, kind="exit_long" if sd == 1 else "exit_short", side=sd, px_in=e, px_out=round(e * (1 + res * sd), 8), opened_at=pos["at"],
                           at=now, result_pct=round(res * 100, 2), usd=round(FAST3_SIZE * res, 2), why_exit=why, rule=pos["rule"], size=1.0))
            msgs.append(f"{sym[:-4]} {'лонг' if sd == 1 else 'шорт'} выход {why} {res * 100:+.2f}%")
            state["last_exit"][sym] = now; del state["open"][sym]
        else:
            ev.append(dict(book=BOOK, sym=sym, kind="follow", side=sd, px_in=e, px=c, result_pct=round((c / e - 1) * sd * 100, 2), at=now))
    # входы
    spike, climax, info = short_list()
    todo = sorted(set(spike) | set(climax))
    with ThreadPoolExecutor(6) as ex:
        res_all = [r for r in ex.map(lambda s: scan(s, s in spike, s in climax), todo) if r]
    bg = fon()
    for sym, px, t_bar, outs in res_all:
        for sd, why, tp, sl, hold in outs:
            if sym in state["open"] or now - state["last_exit"].get(sym, 0) < 2 * 3600:
                continue
            pos = dict(sym=sym, side=sd, px=px, t_ms=t_bar, at=now, target=tp, stop=sl, hold_min=hold, rule=why, last_px=px, bars=0)
            state["open"][sym] = pos
            ev.append(dict(book=BOOK, sym=sym, kind="entry", side=sd, px=px, at=now, usd_in=FAST3_SIZE, rule=why, target=tp, stop=sl, hold_min=hold,
                           oi1h=info.get(sym, {}).get("oi1h"), run24=info.get(sym, {}).get("run24"), fon=bg))
            msgs.append(f"{sym[:-4]} {'лонг' if sd == 1 else 'шорт'} вход {px:.6g} · {why}")
    if write:
        with LOG.open("a", encoding="utf-8") as f:
            for r in ev:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp = STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8"); tmp.replace(STATE)
    msgs.append(f"список: всплеск {len(spike)}, вынос {len(climax)} · открыто {len(state['open'])}")
    return msgs


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--loop", action="store_true"); a = ap.parse_args()
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {"open": {}, "last_exit": {}}
    state.setdefault("open", {}); state.setdefault("last_exit", {})
    while True:
        try:
            for m in step(state, a.loop):
                print(f"{datetime.now(L):%H:%M:%S} {BOOK}: {m}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"{datetime.now(L):%H:%M:%S} {BOOK}: сбой {type(e).__name__}: {e}", flush=True)
        if not a.loop:
            return 0
        time.sleep(max(1, 180 - (time.time() % 180)))


if __name__ == "__main__":
    raise SystemExit(main())
