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
_CROWD = {"t": 0, "v": {}}      # 27.09 п.1: толпа по счетам (Binance globalLongShortAccountRatio), обновляется раз в 30 мин
STATE = BASE_DIR / "output" / "paper_fast3.json"; LOG = BASE_DIR / "output" / "paper_fast3.jsonl"
L = timezone(timedelta(hours=3))


def crowd_of(sym: str):
    """толпа по счетам, кэш 30 мин (27.09 п.1: ZEC — толпа 0.49 в шорте и интерес +9% за 6 ч, а за час +1.3% — список её не видел)"""
    if time.time() - _CROWD["t"] > 1800:
        _CROWD["v"] = {}; _CROWD["t"] = time.time()
    if sym not in _CROWD["v"]:
        g = get_json("https://fapi.binance.com/futures/data/globalLongShortAccountRatio", {"symbol": sym, "period": "15m", "limit": 1}, quiet_400=True) or [{}]
        try: _CROWD["v"][sym] = float(g[0].get("longShortRatio") or 0) or None
        except (TypeError, ValueError): _CROWD["v"][sym] = None
    return _CROWD["v"][sym]


def short_list() -> tuple[list[str], list[str], dict]:
    try:
        from core_config import FAST3_SHORT_CROWD_MAX as _cmax, FAST3_SHORT_OI6H as _oi6
    except ImportError:
        _cmax, _oi6 = 0.7, 5.0
    spike, climax, info = [], [], {}
    for p in ARCH.glob("*.jsonl"):
        sym = p.stem.upper() + "USDT"; r = rows_of(sym)
        if len(r) < 49:
            continue
        oi1, oi0, oi6b = r[-1].get("oi"), r[-3].get("oi"), r[-13].get("oi")
        oi1h = (float(oi1) / float(oi0) - 1) * 100 if oi1 and oi0 else None
        oi6h = (float(oi1) / float(oi6b) - 1) * 100 if oi1 and oi6b else None
        cf = coin_fon(r); info[sym] = dict(oi1h=oi1h, oi6h=oi6h, run24=cf.get("run24"), crowd=None)
        take = oi1h is not None and oi1h >= FAST3_SHORT_OI1H
        if not take and oi6h is not None and oi6h >= _oi6:               # п.1: деньги за 6 ч и толпа в шорте
            cr = crowd_of(sym); info[sym]["crowd"] = cr
            take = cr is not None and cr <= _cmax
        if take: spike.append(sym)
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


# ── КНИГА «ПРОБУЖДЕНИЕ» (27.09 07:30, владелец: QNT/Q/SOON/US/IN/2Z прошли мимо — выборка экрана обновляется раз в полчаса, старт
#    приходится на первые полчаса; «листинг от 100 дней, 5 млн оставляй»). Каждые 3 мин один запрос тикера по всему Binance: прирост
#    оборота за интервал ≥ WAKE_X × нормы (оборот суток / 480) и цена ≥ +WAKE_PCT % → только по таким качаем трёхминутки и интерес.
#    Вход по правилам всплеска/выноса этой же книги; журнал отдельный output/paper_wake.jsonl.
WAKE_BOOK = "пробуждение"; WAKE_STATE = BASE_DIR / "output" / "paper_wake.json"; WAKE_LOG = BASE_DIR / "output" / "paper_wake.jsonl"
_TK = {"t": 0, "v": {}}; _AGE = {"t": 0, "v": {}}


def listing_age_days() -> dict:
    if time.time() - _AGE["t"] > 6 * 3600:
        info = get_json("https://fapi.binance.com/fapi/v1/exchangeInfo") or {}
        now = time.time() * 1000
        _AGE["v"] = {s["symbol"]: (now - int(s.get("onboardDate") or 0)) / 86400_000 for s in info.get("symbols", []) if s["symbol"].endswith("USDT") and s.get("status") == "TRADING"}
        _AGE["t"] = time.time()
    return _AGE["v"]


def wake_candidates() -> list[dict]:
    try:
        from core_config import WAKE_X, WAKE_PCT, WAKE_MIN_QV, WAKE_MIN_AGE_DAYS
    except ImportError:
        WAKE_X, WAKE_PCT, WAKE_MIN_QV, WAKE_MIN_AGE_DAYS = 5.0, 1.0, 5_000_000, 100
    tk = get_json("https://fapi.binance.com/fapi/v1/ticker/24hr") or []
    now = {x["symbol"]: (float(x["quoteVolume"]), float(x["lastPrice"]), float(x["lowPrice"])) for x in tk if x["symbol"].endswith("USDT")}
    prev, t_prev = _TK["v"], _TK["t"]; _TK["v"], _TK["t"] = now, time.time()
    if not prev or time.time() - t_prev > 600:
        return []
    age = listing_age_days(); out = []
    dt_slots = max(1.0, (time.time() - t_prev) / 180)
    for s_, (qv, px, lo) in now.items():
        q0, p0, _ = prev.get(s_, (None, None, None))
        if not q0 or not p0 or qv < WAKE_MIN_QV or age.get(s_, 0) < WAKE_MIN_AGE_DAYS: continue
        d = qv - q0; norm = q0 / 480 * dt_slots; chg = (px / p0 - 1) * 100
        if norm > 0 and d >= WAKE_X * norm and chg >= WAKE_PCT:
            out.append(dict(sym=s_, chg=chg, x=d / norm, qv=qv, run24=(px / lo - 1) * 100 if lo else None))
    return out


def wake_step(state: dict, write: bool) -> list[str]:
    now = time.time(); now_ms = int(now * 1000); ev = []; msgs = []
    for sym, pos in list(state["open"].items()):                        # выходы — как у основной книги
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "3m", "startTime": int(pos["t_ms"]) + 180_000, "limit": 1000}, quiet_400=True, weight=5) or []
        k = [x for x in k if int(x[0]) + 180_000 <= now_ms]
        if not k: continue
        e, sd = float(pos["px"]), int(pos["side"]); hi = max(float(x[2]) for x in k); lo = min(float(x[3]) for x in k); c = float(k[-1][4]); res = why = None
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
            ev.append(dict(book=WAKE_BOOK, sym=sym, kind="exit_long" if sd == 1 else "exit_short", side=sd, px_in=e, px_out=round(e * (1 + res * sd), 8), opened_at=pos["at"], at=now,
                           result_pct=round(res * 100, 2), usd=round(FAST3_SIZE * (res), 2), why_exit=why, rule=pos["rule"], size=1.0))
            msgs.append(f"{sym[:-4]} {'лонг' if sd == 1 else 'шорт'} выход {why} {res * 100:+.2f}%"); state["last_exit"][sym] = now; del state["open"][sym]
        else:
            ev.append(dict(book=WAKE_BOOK, sym=sym, kind="follow", side=sd, px_in=e, px=c, result_pct=round((c / e - 1) * sd * 100, 2), at=now))
    cands = wake_candidates()
    for cd in cands:
        sym = cd["sym"]
        if sym in state["open"] or now - state["last_exit"].get(sym, 0) < 2 * 3600: continue
        oi = get_json("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": sym, "period": "5m", "limit": 13}, quiet_400=True) or []
        ov = [float(x["sumOpenInterestValue"]) for x in oi]; oi1h = (ov[-1] / ov[0] - 1) * 100 if len(ov) >= 13 and ov[0] else None
        oibar = (ov[-1] / ov[-2] - 1) if len(ov) >= 2 and ov[-2] else None
        cr = crowd_of(sym)
        r = scan(sym, True, (cd["run24"] or 0) >= FAST3_CLIMAX_RUN)
        if not r: continue
        _, px, t_bar, outs = r
        for sd, why, tp, sl, hold in outs:
            if sd == 1 and not ((oi1h is not None and oi1h >= FAST3_SHORT_OI1H) or (cr is not None and cr <= 0.7)):
                continue                                                  # всплеск без интереса и без шортов в топливе — не вход (R39)
            if sd == -1 and not (oibar is not None and oibar <= FAST3_CLIMAX_OI):
                continue
            pos = dict(sym=sym, side=sd, px=px, t_ms=t_bar, at=now, target=tp, stop=sl, hold_min=hold, rule=why + f" · пробуждение: оборот ×{cd['x']:.0f} за интервал", last_px=px, bars=0)
            state["open"][sym] = pos
            ev.append(dict(book=WAKE_BOOK, sym=sym, kind="entry", side=sd, px=px, at=now, usd_in=FAST3_SIZE, rule=pos["rule"], target=tp, stop=sl, hold_min=hold,
                           oi1h=oi1h, crowd=cr, wake_x=round(cd["x"], 1), wake_chg=round(cd["chg"], 2), qv24=round(cd["qv"]), fon=fon()))
            msgs.append(f"{sym[:-4]} {'лонг' if sd == 1 else 'шорт'} вход {px:.6g} · {pos['rule']}")
    if write:
        with WAKE_LOG.open("a", encoding="utf-8") as f:
            for r_ in ev: f.write(json.dumps(r_, ensure_ascii=False) + "\n")
        tmp = WAKE_STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8"); tmp.replace(WAKE_STATE)
    msgs.append(f"пробуждений {len(cands)}" + (": " + ", ".join(c['sym'][:-4] for c in cands[:8]) if cands else "") + f" · открыто {len(state['open'])}")
    return msgs


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--loop", action="store_true"); a = ap.parse_args()
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {"open": {}, "last_exit": {}}
    state.setdefault("open", {}); state.setdefault("last_exit", {})
    try:
        wstate = json.loads(WAKE_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        wstate = {"open": {}, "last_exit": {}}
    wstate.setdefault("open", {}); wstate.setdefault("last_exit", {})
    while True:
        try:
            for m in step(state, a.loop):
                print(f"{datetime.now(L):%H:%M:%S} {BOOK}: {m}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"{datetime.now(L):%H:%M:%S} {BOOK}: сбой {type(e).__name__}: {e}", flush=True)
        try:
            for m in wake_step(wstate, a.loop):
                print(f"{datetime.now(L):%H:%M:%S} {WAKE_BOOK}: {m}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"{datetime.now(L):%H:%M:%S} {WAKE_BOOK}: сбой {type(e).__name__}: {e}", flush=True)
        if not a.loop:
            return 0
        time.sleep(max(1, 180 - (time.time() % 180)))


if __name__ == "__main__":
    raise SystemExit(main())
