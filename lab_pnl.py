#!/usr/bin/env python3
"""СКОЛЬКО БЫ ВЫШЛО (16.09; владелец: «прогони по тому, что есть, твои стратегии — сколько бы получилось за день,
неделю, две недели»). Не край и не медианы — деньги на счёте по дням.

Правила (те же, что в бумажных ботах):
  • спайк:   +SPIKE% за 2 ч → шорт; цель 2.5%, стоп 3% по размаху, срок 12 ч; размер ×2 при сутках ≤ −8%,
             ×0.5 в первый час после открытия сессии (полугодие: гасят везде, слабее в первый час);
  • провал:  −SPIKE% за 2 ч → лонг, те же цель/стоп/срок, размер 0.5 (наблюдение — не держится между наборами);
  • z-шорт:  z(20) > +2 → выход z < 0, стоп 2%, срок 6 ч (30 дней: только при интересе не ↑ — здесь без интереса,
             как есть: на полугодии −0.13 на сделку, ожидание ноль);
  • конец:   только на барах с интересом из архива cq_v2/intraday (интерес −2% за бар, дельта <0, цена вниз) →
             шорт, размер и цель по росту за сутки, стоп 3%, срок 12 ч — там, где архив есть.
Деньги: капитал 100, одна сделка = SLOT% капитала × размер, одновременно не больше MAX_OPEN сделок; комиссия
0.1% за оборот; вход по закрытию сигнального бара, стоп — по размаху следующих баров, цель — по закрытию.
Отчёт: сделок, попаданий, средняя на сделку; P&L по дням; сумма за последний день, 7 и 14 дней; недельная таблица;
максимальная просадка; отдельно по каждому правилу.
Источник: --hourly (hourly/*.json, полгода) или получасовки биржи (get_klines, 30 дней).
`python3 lab_pnl.py --hourly --days 180`, `python3 lab_pnl.py --days 30`, `--rules спайк,конец`.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

FEE = 0.001
SPIKE = 0.08
SLOT = 10.0          # % капитала на сделку размера 1
MAX_OPEN = 5
OPENS = (21, 0, 7, 13)


def klines(sym: str, limit: int, hourly: bool):
    if hourly:
        p = BASE_DIR / "hourly" / f"{sym.replace('USDT', '').lower()}.json"
        try:
            arr = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        out = sorted((int(b["t"]), float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])) for b in arr if isinstance(b, dict) and b.get("t") and b.get("c"))
        return out[-limit:] if limit else out
    import core_binance as cb
    from core_binance import K_HIGH, K_LOW, K_OPEN, K_OPEN_TIME, get_klines
    KC = getattr(cb, "K_CLOSE", 4)
    ks = get_klines(sym, "30m", limit=limit) or []
    return sorted((int(k[K_OPEN_TIME]), float(k[K_OPEN]), float(k[K_HIGH]), float(k[K_LOW]), float(k[KC])) for k in ks)


def coins(hourly: bool) -> list[str]:
    if hourly:
        return sorted(p.stem.upper() + "USDT" for p in (BASE_DIR / "hourly").glob("*.json") if p.stem.lower() != "btc")
    try:
        nm = json.loads((BASE_DIR / "output" / "near_move.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return sorted(set(str(s).upper() + ("" if str(s).upper().endswith("USDT") else "USDT") for s in (nm.get("coins") or {}).keys()))


def archive(sym: str) -> dict:
    p = BASE_DIR / "cq_v2" / "intraday" / f"{sym.replace('USDT', '').lower()}.jsonl"
    out = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            t = int(datetime.strptime(r["candle"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
            out[t] = (r.get("oi"), (r.get("fut") or {}).get("d"))
        except (ValueError, KeyError):
            continue
    return out


def zs(C, i, N=20):
    w = C[i - N:i]
    m = sum(w) / N
    sd = (sum((x - m) ** 2 for x in w) / N) ** .5 or 1e-9
    return (C[i] - m) / sd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hourly", action="store_true")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--only")
    ap.add_argument("--rules", default="спайк,провал,z-шорт,конец")
    ap.add_argument("--stop", type=float, default=None, help="стоп для всех правил, доля (0.08 = 8 процентов); по умолчанию свой у каждого")
    ap.add_argument("--stop-close", action="store_true", help="стоп только по закрытию бара, не по хвосту")
    ap.add_argument("--no-stop", action="store_true", help="без стопа: выход по цели и по сроку")
    ap.add_argument("--slot", type=float, default=SLOT, help="процент капитала на сделку размера 1")
    ap.add_argument("--hedge", choices=["board", "btc"], default=None, help="вторая нога той же суммой: board — медиана доски, btc — биткоин")
    ap.add_argument("--max-board-spikes", type=int, default=None, help="шортить спайк, только если спайков на доске в этот час не больше K (одиночный спайк)")
    ap.add_argument("--max-spikes-12h", type=int, default=None, help="шортить спайк, только если спайков по доске за последние 12 ч не больше K (спокойный рынок)")
    ap.add_argument("--cap", type=float, default=None, help="потолок убытка по закрытию для всех правил, доля (0.25 = четверть): ракету отрезает, обычный ход не трогает")
    a = ap.parse_args()
    slot = a.slot
    BPH = 1 if a.hourly else 2
    rules = set(x.strip() for x in a.rules.split(","))
    syms = [x.strip().upper() + ("" if x.strip().upper().endswith("USDT") else "USDT") for x in a.only.split(",")] if a.only else coins(a.hourly)
    limit = a.days * 24 * BPH + 60
    signals = []
    closes = {}      # sym → {t: close} — для хеджа корзиной
    all_ks = {}
    for sym in syms:
        ks = klines(sym, limit, a.hourly)
        if len(ks) < 100:
            continue
        all_ks[sym] = ks
        closes[sym] = {k[0]: k[4] for k in ks}
    btc_c = {}
    if a.hedge == "btc":
        btc_c = {k[0]: k[4] for k in klines("BTCUSDT", limit, a.hourly)}

    spikes_at = defaultdict(int)
    if a.max_board_spikes is not None or a.max_spikes_12h is not None:
        for sym0, ks0 in all_ks.items():
            for i0 in range(2 * BPH, len(ks0)):
                if ks0[i0][4] / ks0[i0 - 2 * BPH][4] - 1 >= SPIKE:
                    spikes_at[ks0[i0][0]] += 1

    def board_move(t0, t1):
        """ход медианы доски между t0 и t1; None, если данных мало"""
        v = []
        for cc in closes.values():
            if t0 in cc and t1 in cc:
                v.append(cc[t1] / cc[t0] - 1)
        return st.median(v) if len(v) >= 8 else None

    for sym, ks in all_ks.items():
        T = [k[0] for k in ks]
        O = [k[1] for k in ks]
        H = [k[2] for k in ks]
        L = [k[3] for k in ks]
        C = [k[4] for k in ks]
        arc = archive(sym) if "конец" in rules else {}
        last_exit = -1
        for i in range(48 * BPH, len(ks) - 1):
            if i <= last_exit:
                continue
            sig = None
            r2 = C[i] / C[i - 2 * BPH] - 1
            r24 = C[i] / C[i - 24 * BPH] - 1
            d = datetime.fromtimestamp(T[i] / 1000, timezone.utc)
            since = min(((d.hour - o) % 24) + d.minute / 60 for o in OPENS)
            if "спайк" in rules and r2 >= SPIKE:
                if a.max_board_spikes is not None and spikes_at.get(T[i], 0) > a.max_board_spikes:
                    continue                      # общий памп — не шортим
                if a.max_spikes_12h is not None:
                    hot = sum(spikes_at.get(T[i] - k * 3600000 * (1 if a.hourly else 1), 0) for k in range(0, 13)) if a.hourly else \
                          sum(spikes_at.get(T[i] - k * 1800000, 0) for k in range(0, 25))
                    if hot > a.max_spikes_12h:
                        continue                  # горячие 12 часов — ракеты приходят отсюда
                size = 2.0 if r24 <= -0.08 else 1.0
                if since < 1:
                    size = 0.5
                sig = (-1, size, "спайк", 0.025, 0.03, 12 * BPH)
            elif "провал" in rules and r2 <= -SPIKE:
                sig = (1, 0.5, "провал", 0.025, 0.03, 12 * BPH)
            elif "z-шорт" in rules and i >= 20 and zs(C, i) > 2:
                sig = (-1, 1.0, "z-шорт", None, 0.02, 6 * BPH)
            elif "конец" in rules and T[i] in arc and T[i - 1] in arc:
                oi, dl = arc[T[i]]
                oi0 = arc[T[i - 1]][0]
                if oi and oi0 and dl is not None and oi / oi0 - 1 <= -0.02 and dl < 0 and C[i] < C[i - 1]:
                    run = (C[i - 1] / min(C[i - 48 * BPH:i]) - 1) * 100
                    size = 0.5 if run < 5 else 1.0 if run < 15 else 2.0 if run < 40 else 3.0
                    tgt = 0.02 if run < 5 else 0.035 if run < 15 else 0.06 if run < 40 else 0.10
                    sig = (-1, size, "конец", tgt, 0.03, 24 * BPH)
            if not sig:
                continue
            side, size, rule, tgt, stop, hold = sig
            if a.stop is not None:
                stop = a.stop
            e = C[i]
            res, why, j = None, "", i + 1
            mae = 0.0
            while j < len(ks) and j <= i + hold:
                adverse = (L[j] / e - 1) if side > 0 else -(H[j] / e - 1)
                mae = min(mae, adverse)
                if a.no_stop:
                    stopped = False
                elif a.stop_close:
                    stopped = side * (C[j] / e - 1) <= -stop
                else:
                    stopped = (L[j] / e - 1) <= -stop if side > 0 else (H[j] / e - 1) >= stop
                if stopped:
                    res, why = (side * (C[j] / e - 1) if a.stop_close else -stop), "стоп"
                    break
                if a.cap is not None and side * (C[j] / e - 1) <= -a.cap:
                    res, why = side * (C[j] / e - 1), "потолок"
                    break
                cur = side * (C[j] / e - 1)
                if tgt is not None and cur >= tgt:
                    res, why = cur, "цель"
                    break
                if tgt is None and j >= 20 and zs(C, j) < 0:
                    res, why = cur, "z<0"
                    break
                j += 1
            if res is None:
                j = min(j, len(ks) - 1)
                res, why = side * (C[j] / e - 1), "срок"
            net = res - FEE
            if a.hedge:
                hm = board_move(T[i], T[j]) if a.hedge == "board" else ((btc_c[T[j]] / btc_c[T[i]] - 1) if (T[i] in btc_c and T[j] in btc_c) else None)
                if hm is None:
                    continue
                net = net + (-side) * hm - FEE      # вторая нога: противоположная сторона той же суммой
            signals.append((T[i], T[j], sym, rule, size, net, why, mae))
            last_exit = j
    if not signals:
        print("сделок нет")
        return 0
    signals.sort()
    # ── деньги по дням: капитал 100, сделка = SLOT% × размер, не больше MAX_OPEN одновременно (по времени входа/выхода)
    cap = 100.0
    open_until = []
    pnl_day = defaultdict(float)
    taken = []
    for t_in, t_out, sym, rule, size, res, why, mae in signals:
        open_until = [x for x in open_until if x > t_in]
        if len(open_until) >= MAX_OPEN:
            continue
        open_until.append(t_out)
        money = cap * slot / 100 * size
        gain = money * res
        pnl_day[datetime.fromtimestamp(t_out / 1000, timezone.utc).strftime("%Y-%m-%d")] += gain
        taken.append((t_in, t_out, sym, rule, size, res, why, gain, mae))
    days = sorted(pnl_day)
    eq = 100.0
    peak = 100.0
    dd = 0.0
    curve = []
    for d in days:
        eq += pnl_day[d]
        peak = max(peak, eq)
        dd = min(dd, (eq - peak) / peak * 100)
        curve.append((d, pnl_day[d], eq))
    v = [x[5] for x in taken]
    mode = ("без стопа" if a.no_stop else ("стоп по закрытию" if a.stop_close else "стоп по хвосту") + (f" {a.stop * 100:.0f}%" if a.stop else "")) + (f" · хедж {a.hedge}" if a.hedge else "") + (f" · спайков на доске ≤{a.max_board_spikes}" if a.max_board_spikes is not None else "") + (f" · спайков за 12 ч ≤{a.max_spikes_12h}" if a.max_spikes_12h is not None else "") + (f" · потолок {a.cap * 100:.0f}%" if a.cap else "")
    maes = sorted(x[8] for x in taken)
    print(f"монет {len(syms)} · {'часовики' if a.hourly else 'получасовки'} · {a.days} дн · сигналов {len(signals)}, взято {len(taken)} (не больше {MAX_OPEN} одновременно) · капитал 100, сделка {slot}% × размер, комиссия 0.1% · {mode}\n")
    print(f"всего: попаданий {100 * sum(1 for x in v if x > 0) / len(v):.0f}% · средняя на сделку {100 * st.mean(v):+.2f}% · медиана {100 * st.median(v):+.2f}% · итог {eq - 100:+.1f}% · просадка {dd:.1f}% · дней с сделками {len(days)}")
    print(f"за последний день {curve[-1][1]:+.2f}% · за 7 дней {sum(x[1] for x in curve[-7:]):+.2f}% · за 14 дней {sum(x[1] for x in curve[-14:]):+.2f}% · в среднем в день {(eq - 100) / max(1, len(days)):+.2f}%\n")
    print(f"худший ход против позиции внутри сделки (без стопа это и есть риск): медиана {100 * st.median(maes):.1f}% · 95-й перцентиль {100 * maes[int(len(maes) * .05)]:.1f}% · самый худший {100 * maes[0]:.1f}%\n")
    print("── по правилам:")
    by = defaultdict(list)
    for x in taken:
        by[x[3]].append(x)
    for rule, xs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        vv = [x[5] for x in xs]
        g = sum(x[7] for x in xs)
        why = defaultdict(int)
        for x in xs:
            why[x[6]] += 1
            m_ = sorted(x[8] for x in xs)
        print(f"  {rule:<8} сделок {len(xs):>5} · попаданий {100 * sum(1 for y in vv if y > 0) / len(vv):3.0f}% · средняя {100 * st.mean(vv):+.2f}% · вклад в счёт {g:+.1f}% · худший ход внутри p95 {100 * m_[int(len(m_) * .05)]:.1f}% · выходы {dict(why)}")
    print("\n── по неделям (сумма P&L, % от начального капитала):")
    wk = defaultdict(float)
    for d, p, _ in curve:
        y, w, _ = datetime.strptime(d, "%Y-%m-%d").isocalendar()
        wk[f"{y}-нед{w:02d}"] += p
    for k, p in sorted(wk.items()):
        print(f"  {k}  {p:+6.2f}%")
    print("\n── последние 14 дней:")
    for d, p, e in curve[-14:]:
        print(f"  {d}  {p:+6.2f}%  счёт {e:7.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
