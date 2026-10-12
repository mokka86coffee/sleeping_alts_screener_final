#!/usr/bin/env python3
"""ПУЗЫРИ РЫНОЧНЫХ ЗАЯВОК ПО НАШИМ ПОЛУЧАСОВКАМ (12.10.2026, владелец по GTC: «как нам сделать такие пузыри у нас?», «ну так сделай так же»,
«пусть они будут на наших звёздах отдельным значком, что они были недавно»).

Образец — индикатор TradingView «Market Order Bubbles — By Leviathan» (код закрыт, правило из описания): всплеск объёма рыночных заявок отмечается
пузырём, когда объём свечи выше порога «скользящее среднее (EMA) + множитель × стандартное отклонение»; порогов три — малый, средний, большой пузырь.
Пузырь НАД свечой — рыночные покупки (свеча вверх), ПОД свечой — рыночные продажи (свеча вниз). Автор читает их наоборот: пузырь продаж у низа —
вынос лонгов и поздние шорты, довод за разворот вверх; пузырь покупок у верха — вынос шортов и поздние лонги, довод за разворот вниз.

Данные — получасовки cq_v2/intraday/<монета>.jsonl (оборот фьючерса kv.qv, открытие o, закрытие px); с биржи ничего не запрашивается.
Числа индикатора в его описании не названы, владелец их не присылал — МЕРКИ НИЖЕ МОИ, подобраны по его графику GTC за 05–12.10 (30 минут): при них
пузыри встают на те же свечи, что у него (07.10 три подряд, 08.10, 09.10, 11.10, 12.10 у низа перед пампом, сам памп); размеры могут отличаться.

    .venv/bin/python market_bubbles.py GTCUSDT        # пузыри монеты за последние дни
"""
from __future__ import annotations

import json
import statistics as st
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent

MOB_EMA = 50                 # длина скользящего среднего оборота, свечей (мерка Claude)
MOB_STDEV = 50               # длина окна стандартного отклонения оборота, свечей (мерка Claude)
MOB_MULTS = (3.0, 5.0, 8.0)  # множители порогов: малый, средний, большой пузырь (мерки Claude)
MOB_RECENT_H = 7 * 24        # сколько часов значок держится на звезде — неделя, как сама звезда (12.10 11:25 UTC, владелец: «как раз время у звезды —
                             # неделя, вот пусть макс и висят, пока звезда на экране»; до этого стояли мои 24 ч)
SIZE = {1: "малый", 2: "средний", 3: "большой"}


def _rows(sym: str) -> list:
    p = BASE_DIR / "cq_v2" / "intraday" / (sym[:-4].lower() + ".jsonl" if sym.endswith("USDT") else sym.lower() + ".jsonl")
    out = {}
    try:
        for ln in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            qv = (r.get("kv") or {}).get("qv")
            if r.get("candle") and r.get("px") and qv:
                out[r["candle"]] = (r["candle"], float(r.get("o") or r["px"]), float(r["px"]), float(qv), float(r.get("h") or r["px"]), float(r.get("l") or r["px"]))
    except OSError:
        return []
    return [out[k] for k in sorted(out)]


def bubbles(sym: str, hours: float | None = None, now: float | None = None) -> list[dict]:
    """пузыри монеты по времени: [{t — конец свечи (unix UTC), candle, side: 'buy' | 'sell', size: 1..3, vol — оборот свечи $, px — цена закрытия,
    x — во сколько раз оборот выше среднего}]; hours — только за последние столько часов"""
    R = _rows(sym)
    need = max(MOB_EMA, MOB_STDEV) + 1
    if len(R) <= need:
        return []
    now = time.time() if now is None else now
    v = [r[3] for r in R]
    k = 2 / (MOB_EMA + 1); e = []; cur = None
    for x in v:
        cur = x if cur is None else cur + k * (x - cur); e.append(cur)
    out = []
    for i in range(need, len(R)):
        sd = st.pstdev(v[i - MOB_STDEV:i]); base = e[i - 1]
        lvl = 3 if v[i] > base + MOB_MULTS[2] * sd else 2 if v[i] > base + MOB_MULTS[1] * sd else 1 if v[i] > base + MOB_MULTS[0] * sd else 0
        if not lvl:
            continue
        t = datetime.strptime(R[i][0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() + 1800
        if hours is not None and now - t > hours * 3600:
            continue
        out.append(dict(t=t, candle=R[i][0], side="buy" if R[i][2] >= R[i][1] else "sell", size=lvl, vol=round(v[i]), px=R[i][2], x=round(v[i] / base, 1) if base else None))
    return out


def recent(sym: str, now: float | None = None) -> dict | None:
    """последний пузырь монеты за MOB_RECENT_H часов с готовыми подписями: mark — короткий значок («▽ 05:00» — продажи, «△ 10:30» — покупки, время UTC
    конца свечи; у пузыря не сегодняшнего дня — с датой: «▽ 10.10 16:30»), text — словами"""
    now = time.time() if now is None else now
    b = bubbles(sym, MOB_RECENT_H, now)
    if not b:
        return None
    x = b[-1]; d = datetime.fromtimestamp(x["t"], timezone.utc)
    sell = x["side"] == "sell"
    x["n"] = len(b)
    today = d.date() == datetime.fromtimestamp(now, timezone.utc).date()
    x["mark"] = f"{'▽' if sell else '△'} {d:%H:%M}" if today else f"{'▽' if sell else '△'} {d:%d.%m %H:%M}"   # не сегодняшний пузырь — с датой
    x["text"] = (f"{SIZE[x['size']]} пузырь {'продаж' if sell else 'покупок'} {d:%d.%m %H:%M} UTC (оборот ×{x['x']} к среднему)"
                 + (f", за неделю пузырей {len(b)}" if len(b) > 1 else ""))
    return x


def white_count(sym: str, now: float | None = None) -> int:
    """сколько БЕЛЫХ пузырей (рыночные продажи — пузырь под свечой, как на графике владельца) было у монеты на получасовках за MOB_RECENT_H часов.
    12.10 11:40 UTC, владелец: «дат не надо никаких и не надо последний — были белые или нет; чем больше таких пузырьков на получасовках, тем ярче
    пузырёк у звезды»"""
    return sum(1 for b in bubbles(sym, MOB_RECENT_H, now) if b["side"] == "sell")


def white_marks(syms: list, now: float | None = None) -> dict:
    """{монета: {"n": число белых пузырей за неделю, "b": яркость значка 0..1}} — яркость растёт с числом пузырей: у монеты с наибольшим числом среди
    переданных — 1.0, у остальных пропорционально, но не тусклее 0.35, чтобы и один пузырь был виден (шкала Claude); без белых пузырей монеты в ответе нет"""
    n = {s_: white_count(s_, now) for s_ in dict.fromkeys(syms)}
    top = max(n.values(), default=0)
    return {s_: {"n": k, "b": round(0.35 + 0.65 * k / top, 2)} for s_, k in n.items() if k > 0} if top else {}


if __name__ == "__main__":
    s = (sys.argv[1] if len(sys.argv) > 1 else "GTCUSDT").upper()
    for x in bubbles(s):
        print(x["candle"][5:16], "покупки △" if x["side"] == "buy" else "продажи ▽", SIZE[x["size"]], f"{x['vol'] / 1e3:.0f}K$ ×{x['x']}", x["px"])
    print("недавний:", (recent(s) or {}).get("text"))
