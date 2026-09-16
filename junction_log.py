#!/usr/bin/env python3
"""ЖУРНАЛ СТЫКОВ И РЕЖИМА ЛИДЕРОВ (16.09; владелец: «внедряй всё сразу в журнал, пока как наблюдения, на ботов не
распространяется, потом будем внедрять в торговлю после накопления информации»).

Каждый прогон, только по лидерам (ход за сутки ≥ JUNCTION_LEAD_MIN и место в первых JUNCTION_LEAD_TOP доски, плюс
JUNCTION_TAIL_H часов после — там разворот), в output/junction_log.jsonl дописываются строки:
  • kind=signal — сигнал быстрых по линиям на одном из последних JUNCTION_RECENT_BARS баров (вортекс «давят
    продавцы/покупатели», клингер «выдыхается», «оба» — определения в lab_junctions): где он относительно стыка,
    плечо на баре, отход от вершины, фон (биткоин и доска за 6 ч, день недели, сессия) и меры режима на этом баре;
  • kind=regime — замер режима лидера на последнем баре (analytics_regime: Хёрст, цена потока, загиб роста,
    энтропия, самовозбуждение выносов, кто ведёт) с тем же фоном — чтобы меры проверялись и без сигнала;
  • kind=outcome — когда прошло 12 ч после бара: ответ сессии и интерес в ответе (для сигналов у стыка), ход через
    6 и 12 ч (у сигнала — в его сторону, у режима — сырой), к доске, биткоин за то же окно. Строка сигнала не
    переписывается — исход ложится отдельной строкой с тем же id (факты не отсекаются).
НАБЛЮДЕНИЕ: ни один бот этот журнал не читает. Разбор — `python3 lab_junctions.py --journal`.

ЛИДЕРЫ — по ходу за сутки из сводки прогона (output/near_move.json): архив получасовок у новой монеты может быть
короче суток (16.09, BR: в сводке +158%, а в архиве суточного хода ещё нет). Когда монета последний раз была
лидером — в output/junction_state.json; окно JUNCTION_TAIL_H после этого она ещё считается лидером.
Время — только UTC (секунды эпохи и ISO с Z). Свечи — биржа (core_binance) только по лидерам, открытым ожиданиям
и биткоину; доска и фон — по архиву получасовок без сети.
  python3 junction_log.py --only BR     # одна монета, без записи — показать, что легло бы
  python3 junction_log.py --write       # из прогона
"""
from __future__ import annotations

import argparse
import json
import sys
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
try:
    from core_config import JUNCTION_RECENT_BARS, JUNCTION_KLINES
except ImportError:
    JUNCTION_RECENT_BARS, JUNCTION_KLINES = 4, 320

import analytics_regime as ar
import lab_junctions as lj

BAR = lj.BAR
UTC = timezone.utc
LOG = BASE_DIR / "output" / "junction_log.jsonl"
STATE = BASE_DIR / "output" / "junction_state.json"      # когда монета последний раз была лидером (UTC, секунды)
MATURE_S = 12 * 3600 + BAR                 # исход через 12 ч после закрытия бара


def _iso(t: int) -> str:
    return datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _series(t_end: int, n: int, d: dict) -> list:
    """значения ряда по барам, старые слева, последним — бар t_end; дыра — None"""
    return [d.get(t_end - (n - 1 - k) * BAR) for k in range(n)]


def regime_at(t: int, closes: dict, deltas: dict, ois: dict) -> dict:
    n = max(ar.REGIME_HURST_BARS, ar.REGIME_BRANCH_BARS) + 1
    cs = _series(t, n, closes)
    # меры считаются по непрерывному хвосту: дыра в ценах обрезает окно
    k = len(cs)
    while k > 0 and cs[k - 1] is not None:
        k -= 1
    cs = cs[k:]
    if len(cs) < 25:
        return {}
    ds = _series(t, len(cs), deltas)
    os_ = _series(t, len(cs), ois)
    return ar.measures(cs, ds if sum(1 for x in ds if x is not None) >= 16 else None,
                       os_ if sum(1 for x in os_ if x is not None) >= 16 else None)


def main() -> int:
    ap = argparse.ArgumentParser(description="журнал наблюдений: сигналы и режим лидеров")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--only", help="одна монета, без доски (лидер — если ход за сутки не меньше порога)")
    a = ap.parse_args()
    cfg = Namespace(near=lj.JUNCTION_NEAR_MIN, answer=lj.JUNCTION_ANSWER_BARS, vx_bars=lj.JUNCTION_VX_BARS,
                    kl_gap=lj.JUNCTION_KL_GAP, pair=lj.JUNCTION_PAIR)
    now = int(datetime.now(UTC).timestamp())
    t_last = (now // BAR) * BAR - BAR                      # последняя закрытая получасовка — по часам эпохи, не по архиву
    only = {x.strip().upper().replace("USDT", "") for x in a.only.split(",")} if a.only else None
    arch = lj.archive_index(None, now - 4 * 86400)         # доска и фон — по всем монетам архива
    closes = {b + "USDT": {t: float(r["px"]) for t, r in rows.items() if r and r.get("px")} for b, rows in arch.items()}
    closes = {s: c for s, c in closes.items() if c}
    board = lj.board_median(closes)
    recent = [t_last - k * BAR for k in range(JUNCTION_RECENT_BARS)]

    cache: dict = {}

    def bars(sym: str) -> list:
        if sym not in cache:
            try:
                cache[sym] = lj.bars_of(sym, JUNCTION_KLINES)
            except Exception as e:  # noqa: BLE001
                print(f"junction_log: {sym} — свечи не получены: {type(e).__name__}: {e}")
                cache[sym] = []
        return cache[sym]

    # ход за сутки: сводка прогона; одна монета (--only) — по её свечам биржи
    ch24: dict = {}
    if only:
        for base in only:
            cc = {t: x for t, _, _, x, _ in bars(base + "USDT")}
            tl = max(cc) if cc else None
            if tl and cc.get(tl - 48 * BAR):
                ch24[base + "USDT"] = lj.pct(cc[tl - 48 * BAR], cc[tl])
    else:
        nm = lj._read(BASE_DIR / "output" / "near_move.json") or {}
        for sym, v in (nm.get("coins") or {}).items():
            x = ((v or {}).get("today") or {}).get("px_chg_pct")
            if isinstance(x, (int, float)):
                ch24[str(sym).upper() if str(sym).upper().endswith("USDT") else str(sym).upper() + "USDT"] = float(x)
        if not ch24:                                        # сводки нет — по архиву, где суточный ход есть
            for sym, c in closes.items():
                tl = max(c)
                if c.get(tl - 48 * BAR):
                    ch24[sym] = lj.pct(c[tl - 48 * BAR], c[tl])
    ranked = sorted(ch24.items(), key=lambda x: -x[1])
    rank = {s: i + 1 for i, (s, _) in enumerate(ranked)}
    now_lead = [s for s, v in (ranked if only else ranked[:lj.JUNCTION_LEAD_TOP]) if v >= lj.JUNCTION_LEAD_MIN]
    state = (lj._read(STATE) or {}) if not only else {}
    last = dict(state.get("leader_last") or {})
    for s in now_lead:
        last[s] = t_last
    tail = int(lj.JUNCTION_TAIL_H * 3600)
    last = {s: t for s, t in last.items() if t_last - int(t) <= tail}
    leaders = sorted(last)

    rows = lj._jl(LOG)
    have = {r.get("id") for r in rows if r.get("kind") in ("signal", "regime")}
    done = {r.get("id") for r in rows if r.get("kind") == "outcome"}
    # созревшие без исхода; старше пяти суток не ждём — свечей на них в запросе уже нет
    pending = [r for r in rows if r.get("kind") in ("signal", "regime") and r.get("id") not in done
               and now - 5 * 86400 <= int(r.get("t") or 0) <= now - MATURE_S
               and (only is None or r.get("sym", "").replace("USDT", "") in only)]

    btc = {t: c for t, _, _, c, _ in bars("BTCUSDT")}
    new = []
    for s in leaders:
        b = bars(s)
        if len(b) < 80:
            continue
        base = s.replace("USDT", "")
        c = {t: x for t, _, _, x, _ in b}
        oi = lj.oi_of(arch.get(base, {}))
        dl = lj.delta_of(arch.get(base, {}))
        common = {"sym": s, "leader_ch24": None if ch24.get(s) is None else round(ch24[s], 1), "rank": rank.get(s)}
        for t, kind, side, extra in lj.signals_of(b, cfg):
            if t not in recent or not c.get(t):
                continue
            sid = f"S|{s}|{t}|{kind}|{side}"
            if sid in have:
                continue
            cat, t_open = lj.junction(t, cfg.near)
            lev, lev_off = lj.leverage(oi, t)
            top = max([c[t - k * BAR] for k in range(12) if c.get(t - k * BAR)] or [c[t]])
            new.append(dict(common, kind="signal", id=sid, t=t, at=_iso(t + BAR), tz="UTC", sig=kind, side=side,
                            px=c[t], extra=extra, cat=cat, t_open=t_open,
                            sess=lj.sess_name(t_open) if t_open else "", lev=lev, lev_off=lev_off,
                            from_top=round(lj.pct(top, c[t]), 2), bg=lj.background(t, btc, board),
                            m=regime_at(t, c, dl, oi)))
            have.add(sid)
        t = max(c)
        rid = f"R|{s}|{t}"
        if rid not in have and t in recent:
            lev, lev_off = lj.leverage(oi, t)
            new.append(dict(common, kind="regime", id=rid, t=t, at=_iso(t + BAR), tz="UTC", px=c[t],
                            lev=lev, lev_off=lev_off, bg=lj.background(t, btc, board), m=regime_at(t, c, dl, oi)))
            have.add(rid)

    outs = []
    for r in pending:
        s, t = r["sym"], int(r["t"])
        b = bars(s)
        c = {x: y for x, _, _, y, _ in b}
        hi = {x: h for x, h, _, _, _ in b}
        lo = {x: l for x, _, l, _, _ in b}
        if not c.get(t + 24 * BAR):
            continue                                     # свечей на исход ещё нет — вернёмся следующим прогоном
        side = int(r.get("side") or 0)
        oi = lj.oi_of(arch.get(s.replace("USDT", ""), {}))
        ans = oi_ans = None
        if r.get("kind") == "signal":
            ans, oi_ans = lj.answer(side, r.get("cat") or "", t, r.get("t_open"), float(r["px"]), c, hi, lo, oi,
                                    cfg.answer)
        res = lj.outcome(side, t, float(r["px"]), c, board, btc)
        outs.append({"kind": "outcome", "id": r["id"], "sym": s, "t": t, "at": _iso(now), "tz": "UTC",
                     "ans": ans, "oi_ans": oi_ans, "res": {str(k): list(v) for k, v in res.items()}})

    n_sig = sum(1 for x in new if x["kind"] == "signal")
    n_reg = sum(1 for x in new if x["kind"] == "regime")
    for x in new:
        if x["kind"] == "signal":
            print(f"junction_log: {x['sym'][:-4]} · {x['sig']} {'вниз' if x['side'] < 0 else 'вверх'} · {x['cat']}"
                  f"{' ' + x['sess'] if x['sess'] else ''} · плечо {x['lev'] or '—'} · от вершины {x['from_top']:+.1f}%"
                  f" · биткоин 6ч {x['bg'].get('btc6')} · бар {x['at']}")
    if a.write and not only:
        tmp = STATE.with_suffix(".tmp")
        STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps({"leader_last": last, "at": _iso(now)}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE)
    if a.write and (new or outs):
        from core_lock import locked
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with locked(LOG):
            with LOG.open("a", encoding="utf-8") as f:
                for x in new + outs:
                    f.write(json.dumps(x, ensure_ascii=False) + "\n")
    if only and not leaders:
        print("junction_log: " + ", ".join(f"{b} — ход за сутки {ch24.get(b + 'USDT', float('nan')):+.1f}%" for b in sorted(only))
              + f" · порог лидера {lj.JUNCTION_LEAD_MIN:g}%")
    print(f"junction_log: лидеров {len(leaders)} ({', '.join(x[:-4] for x in leaders) or '—'}) · сигналов +{n_sig}"
          f" · замеров режима +{n_reg} · исходов +{len(outs)} · ждут исхода {len(pending) - len(outs)}"
          + ("" if a.write else " (без записи)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
