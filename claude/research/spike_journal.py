#!/usr/bin/env python3
"""ЖУРНАЛ ТРЁХМИНУТНЫХ ВСПЛЕСКОВ С БУМАЖНОЙ ПОЗИЦИЕЙ 500 $ (26.09, владелец: «каждые 3 минуты приходи в Binance в течение получаса,
ищи такие монеты и пытайся поставить 500 $ в нужную позицию шорт или лонг, дополняй журнал, ищи ошибки, правь»).
Формат владельца (3m_journal.json): время скана → монета → link, reason{price, volume_3m}, action{position, entry_price, goal},
result{success, reason}. Добавлены поля: reason.oi_1h/oi_6h/funding/taker_buy/run_8h/since_spike/spike_age_min (наши признаки, R34/R36/R39),
action.stop/size_usd/why (почему такая сторона), result.pnl_pct/pnl_usd/max_pct/min_pct/closed_at/bars.
Решение (первая версия, пороги — рабочие для получаса наблюдения, не правило):
  лонг  — интерес за час ≥ +3% (деньги входят с ценой), фандинг ≤ +0.02%, покупатели по рынку на всплеске ≥ 50%, ход за 8 ч < +25%;
  шорт  — ход за 8 ч ≥ +15% и (интерес за час ≤ 0 или фандинг ≥ +0.05% или покупатели на всплеске < 45%) — выброс без денег/толпа в лонге;
  иначе — watch (позиции нет, причина записана). Цель ±3%, стоп ∓2%, срок 30 мин (10 трёхминуток).
    python3 claude/research/spike_journal.py --minutes 30      # цикл: скан каждые 3 минуты, журнал claude/research/3m_journal.json
    python3 claude/research/spike_journal.py --once            # один проход
"""
from __future__ import annotations
import argparse, json, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(Path(__file__).resolve().parent))
from core_http import get_json                                     # noqa: E402
import spike3m                                                     # noqa: E402

J = Path(__file__).with_name("3m_journal.json")
S = Path(__file__).with_name("3m_state.json")
L = timezone(timedelta(hours=3))
SIZE, GOAL, STOP, HOLD_MIN = 500.0, 0.03, 0.05, 30      # 26.09 владелец: стоп −5%, тейк 3–5% (первая цель +3%)
OI_LONG, FUND_LONG_MAX, TB_LONG, RUN_LONG_MAX = 3.0, 0.02, 50.0, 25.0
RUN_SHORT, FUND_SHORT, TB_SHORT = 15.0, 0.05, 45.0


def now_l():
    return datetime.now(L).strftime("%H:%M:%S")


def load(p, d):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return d


def decide(r):
    oi1, fund, tb, h8 = r.get("oi1h"), r.get("fund", 0.0), r.get("tb", 0.0), r.get("h8")
    why = []
    if h8 is not None and h8 >= RUN_SHORT and ((oi1 is not None and oi1 <= 0) or fund >= FUND_SHORT or tb < TB_SHORT):
        why.append(f"ход за 8ч +{h8:.0f}% и " + ("интерес уходит" if oi1 is not None and oi1 <= 0 else "толпа в лонге" if fund >= FUND_SHORT else "продавцы на всплеске"))
        return "short", " · ".join(why)
    if oi1 is not None and oi1 >= OI_LONG and fund <= FUND_LONG_MAX and tb >= TB_LONG and (h8 is None or h8 < RUN_LONG_MAX):
        why.append(f"интерес +{oi1:.1f}% за час с ценой, фандинг {fund:+.3f}%, покупатели {tb:.0f}%")
        return "long", " · ".join(why)
    if oi1 is None or oi1 < OI_LONG:
        why.append(f"интерес за час {('—' if oi1 is None else f'{oi1:+.1f}%')} < +{OI_LONG:.0f}% — всплеск без денег (R39: 11% дают +20%)")
    if fund > FUND_LONG_MAX:
        why.append(f"фандинг {fund:+.3f}% — толпа уже в лонге")
    if tb < TB_LONG:
        why.append(f"покупатели {tb:.0f}% — всплеск на продавцах")
    if h8 is not None and h8 >= RUN_LONG_MAX:
        why.append(f"ход за 8ч +{h8:.0f}% — поздно")
    return "watch", " · ".join(why)


def px_path(sym, t_from_ms):
    k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "3m", "startTime": t_from_ms, "limit": 40}, quiet_400=True) or []
    return [(int(x[0]), float(x[2]), float(x[3]), float(x[4])) for x in k]


def update_open(state, journal):
    now_ms = int(time.time() * 1000)
    for key, pos in list(state["open"].items()):
        sym, e, side = pos["sym"], float(pos["entry"]), pos["side"]
        k = [b for b in px_path(sym, pos["t_entry_ms"]) if b[0] + 180_000 <= now_ms]      # только закрытые
        if not k:
            continue
        sgn = 1 if side == "long" else -1
        hi = max(b[1] for b in k); lo = min(b[2] for b in k); c = k[-1][3]
        best = (hi / e - 1) * sgn * 100 if side == "long" else (1 - lo / e) * 100
        worst = (lo / e - 1) * 100 if side == "long" else (1 - hi / e) * 100
        pnl = (c / e - 1) * sgn * 100
        res = None
        if side == "long" and lo <= e * (1 - STOP) or side == "short" and hi >= e * (1 + STOP):
            res = (False, f"стоп −{STOP * 100:.0f}% (худшее {worst:+.1f}%)", -STOP * 100)
        elif side == "long" and hi >= e * (1 + GOAL) or side == "short" and lo <= e * (1 - GOAL):
            res = (True, f"цель +{GOAL * 100:.0f}% за {len(k)} трёхминуток", GOAL * 100)
        elif len(k) >= HOLD_MIN // 3:
            res = (pnl > 0, f"срок {HOLD_MIN} мин, закрыто по рынку {pnl:+.2f}% (лучшее {best:+.1f}%, худшее {worst:+.1f}%)", pnl)
        rec = journal[pos["scan"]][sym]
        rec["result"].update(pnl_pct=round(pnl, 2), pnl_usd=round(SIZE * pnl / 100, 1), max_pct=round(best, 2), min_pct=round(worst, 2), bars=len(k),
                             price_now=c)
        if res:
            ok, why, p = res
            rec["result"].update(success=ok, reason=why, pnl_pct=round(p, 2), pnl_usd=round(SIZE * p / 100, 1), closed_at=now_l())
            del state["open"][key]


def one_pass(state, journal):
    info = get_json("https://fapi.binance.com/fapi/v1/exchangeInfo") or {}
    syms = [s["symbol"] for s in info.get("symbols", []) if s["symbol"].endswith("USDT") and s.get("status") == "TRADING"]
    with ThreadPoolExecutor(8) as ex:
        hits = [r for r in ex.map(spike3m.scan, syms) if r]
    hits = [r for r in hits if r["ago"] <= 6]                       # свежие: всплеск в последних двух закрытых трёхминутках
    with ThreadPoolExecutor(4) as ex:
        hits = list(ex.map(spike3m.confirm, hits))
    ts = now_l()
    seen_recent = {v["sym"]: k for k, vv in journal.items() for v in [dict(sym=s, **x) for s, x in vv.items()]}
    entry = {}
    for r in hits:
        sym = r["sym"]
        if sym in state["open_syms"] or any(sym in journal[k] for k in list(journal)[-10:]):
            continue
        side, why = decide(r)
        px_now = float((get_json("https://fapi.binance.com/fapi/v1/ticker/price", {"symbol": sym}, quiet_400=True) or {}).get("price") or 0)
        rec = {
            "link": f"https://www.coinglass.com/tv/Binance_{sym}",
            "reason": {"price": f"{r['chg']:+.2f}%", "volume_3m": f"x{r['x']:.1f}", "volume_usd": round(r["qv"]), "taker_buy": f"{r['tb']:.0f}%",
                       "oi_1h": None if r.get("oi1h") is None else f"{r['oi1h']:+.1f}%", "oi_6h": None if r.get("oi6h") is None else f"{r['oi6h']:+.1f}%",
                       "funding": f"{r['fund']:+.4f}%", "run_8h": None if r.get("h8") is None else f"{r['h8']:+.1f}%",
                       "spike_age_min": r["ago"], "since_spike": f"{r['since']:+.2f}%",
                       "spike_time": datetime.fromtimestamp(r["t"] / 1000, L).strftime("%H:%M")},
            "action": {"position": side, "entry_price": px_now if side != "watch" else None, "goal": f"{'+' if side == 'long' else '-'}{GOAL * 100:.0f}%" if side != "watch" else None,
                       "stop": f"{'-' if side == 'long' else '+'}{STOP * 100:.0f}%" if side != "watch" else None,
                       "size_usd": SIZE if side != "watch" else 0, "hold_min": HOLD_MIN if side != "watch" else None, "why": why},
            "result": {"success": None, "reason": "открыта" if side != "watch" else "позиции нет", "pnl_pct": None, "pnl_usd": None},
        }
        entry[sym] = rec
        if side != "watch" and px_now:
            state["open"][f"{ts}:{sym}"] = dict(sym=sym, side=side, entry=px_now, t_entry_ms=int(time.time() * 1000) // 180_000 * 180_000, scan=ts)
            state["open_syms"].append(sym)
    if entry:
        journal[ts] = entry
    state["open_syms"] = [p["sym"] for p in state["open"].values()]
    return ts, hits, entry


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--minutes", type=int, default=0); ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    journal = load(J, {}); state = load(S, {"open": {}, "open_syms": []})
    t_end = time.time() + a.minutes * 60
    while True:
        update_open(state, journal)
        ts, hits, entry = one_pass(state, journal)
        J.write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8")
        S.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        opened = [f"{s} {v['action']['position']} {v['action']['entry_price']}" for s, v in entry.items() if v["action"]["position"] != "watch"]
        watched = [s for s, v in entry.items() if v["action"]["position"] == "watch"]
        print(f"{ts} · всплесков свежих {len(hits)} · позиции: {', '.join(opened) or '—'} · смотрим: {', '.join(x[:-4] for x in watched) or '—'} · открыто всего {len(state['open'])}", flush=True)
        if a.once or time.time() >= t_end:
            break
        time.sleep(max(1, 180 - (time.time() % 180)))


if __name__ == "__main__":
    main()
