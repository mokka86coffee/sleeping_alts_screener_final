#!/usr/bin/env python3
"""СЛИВ ОДНОЙ СВЕЧОЙ — ПОЧЕРК ММ (27.09, владелец по Q: «смотри какая дичь — у каждой монеты может быть свой мм; такое гавно выносить
в отдельный список, чтобы бот в них не попадал»).

Q 26–27.09 (BingX 15m): подъём лестницей → вершина обрывается одной свечой ~−50% → выкуп за часы → снова. Стоп −5% для такой монеты — корм.

Счёт: Binance USDT-перпы, которые может взять быстрый бот (оборот суток ≥ WAKE_MIN_QV, листинг ≥ WAKE_MIN_AGE_DAYS), 15m за 30 дней.
Событие: от максимума последних 2 ч до минимума этой и следующей свечи — падение (глубина); выкуп — за 6 ч после минимума цена вернула
половину падения; лестница — ход от минимума 24 ч до того максимума. События одной монеты — не чаще раза в 4 ч. Порога здесь нет:
пишутся все события глубже 10% (нижняя граница замера), список собирает владелец по распределению.

    .venv/bin/python claude/research/mm_flush.py        # → mm_flush.md, mm_flush.json (события и сводка по монетам)
"""
from __future__ import annotations

import json
import statistics as st
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core_http import get_json  # noqa: E402
import core_config as cc  # noqa: E402

L = timezone(timedelta(hours=3))
B15 = 900_000
DAYS = 30
OUT_MD = Path(__file__).with_name("mm_flush.md")
OUT_JS = Path(__file__).with_name("mm_flush.json")


def universe() -> list[str]:
    tk = get_json("https://fapi.binance.com/fapi/v1/ticker/24hr", weight=40) or []
    info = get_json("https://fapi.binance.com/fapi/v1/exchangeInfo", weight=1) or {}
    now = time.time() * 1000
    age = {s["symbol"]: (now - int(s.get("onboardDate") or 0)) / 86400_000 for s in info.get("symbols", [])
           if s["symbol"].endswith("USDT") and s.get("status") == "TRADING" and s.get("contractType") == "PERPETUAL"}
    return sorted(t["symbol"] for t in tk if t["symbol"] in age and float(t.get("quoteVolume") or 0) >= cc.WAKE_MIN_QV
                  and age[t["symbol"]] >= cc.WAKE_MIN_AGE_DAYS)


def klines(sym: str) -> list[list]:
    out, end = [], int(time.time() * 1000)
    start = end - DAYS * 86400_000
    t = start
    while t < end:
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "15m", "startTime": t, "limit": 1500},
                     quiet_400=True, weight=10) or []
        if not k:
            break
        out += k
        t = int(k[-1][0]) + B15
        if len(k) < 1500:
            break
    return out


def events(sym: str, k: list[list]) -> list[dict]:
    h = [float(x[2]) for x in k]; lo = [float(x[3]) for x in k]
    out, last = [], -10**9
    for i in range(96, len(k) - 1):
        top_i = max(range(i - 8, i + 1), key=lambda j: h[j])
        top = h[top_i]
        bot_i = min((i, i + 1), key=lambda j: lo[j])
        bot = lo[bot_i]
        depth = (bot / top - 1) * 100 if top else 0
        if depth > -10 or bot_i - last < 16:
            continue
        # только если сам обрыв — в эти 1–2 свечи (а не медленное сползание за 2 ч)
        if (lo[i - 1] / top - 1) * 100 < depth / 2:
            continue
        rec = None
        half = bot + (top - bot) / 2
        for j in range(bot_i + 1, min(len(k), bot_i + 25)):
            if h[j] >= half:
                rec = round((j - bot_i) * 15 / 60, 2)
                break
        lo24 = min(lo[i - 96:i])
        out.append(dict(sym=sym, t=int(k[bot_i][0]) // 1000, depth=round(depth, 1), top=top, bot=bot, rec_h=rec,
                        run24=round((top / lo24 - 1) * 100, 1) if lo24 else None))
        last = bot_i
    return out


def our_trades() -> dict:
    res = defaultdict(list)
    for f in ("paper_fast3.jsonl", "paper_wake.jsonl"):
        for ln in (ROOT / "output" / f).open(encoding="utf-8"):
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if str(r.get("kind", "")).startswith("exit") and r.get("result_pct") is not None:
                res[r["sym"]].append(float(r["result_pct"]))
    return res


def main() -> int:
    t0 = time.time()
    syms = universe()
    ev = []
    with ThreadPoolExecutor(4) as ex:
        for sym, k in zip(syms, ex.map(klines, syms)):
            if len(k) > 200:
                ev += events(sym, k)
    by = defaultdict(list)
    for e in ev:
        by[e["sym"]].append(e)
    coins = []
    for s, g in by.items():
        d = [e["depth"] for e in g]
        rc = [e for e in g if e["rec_h"] is not None]
        coins.append(dict(sym=s, n10=len(g), n20=sum(1 for x in d if x <= -20), n30=sum(1 for x in d if x <= -30), worst=min(d),
                          med=round(st.median(d), 1), rec=round(len(rc) / len(g) * 100), rec_h=round(st.median([e["rec_h"] for e in rc]), 1) if rc else None,
                          last=max(e["t"] for e in g)))
    coins.sort(key=lambda c: (c["worst"], -c["n10"]))
    OUT_JS.write_text(json.dumps(dict(at=int(time.time()), universe=len(syms), events=ev, coins=coins), ensure_ascii=False))
    tr = our_trades()
    L_ = [f"# Слив одной свечой — почерк ММ ({datetime.now(L):%d.%m %H:%M})", "",
          f"Выборка: {len(syms)} перпов Binance, которые может взять быстрый бот (оборот ≥ {cc.WAKE_MIN_QV / 1e6:.0f}M$, листинг ≥ {cc.WAKE_MIN_AGE_DAYS} дн),"
          f" 15m за {DAYS} дн. Событие — падение от максимума 2 ч до минимума 1–2 свечей глубже 10%, само падение — в эти свечи. Выкуп — половина"
          f" падения за 6 ч.", "",
          "## Сколько монет делают такие проколы", "", "| порог глубины | монет хоть раз | монет ≥ 2 раз | событий |", "|---|---|---|---|"]
    for thr in (10, 15, 20, 30, 40):
        cnt = defaultdict(int)
        for e in ev:
            if e["depth"] <= -thr:
                cnt[e["sym"]] += 1
        L_.append(f"| −{thr}% | {len(cnt)} | {sum(1 for v in cnt.values() if v >= 2)} | {sum(cnt.values())} |")
    L_ += ["", "## Монеты (худший прокол, число проколов глубже 10/20/30%, медиана глубины, доля выкупа за 6 ч и медиана часов, наши сделки)", "",
           "| монета | худший | ≥10 / ≥20 / ≥30 | медиана | выкуп | часов | последний | наши сделки быстрых книг |", "|---|---|---|---|---|---|---|---|"]
    for c in coins[:60]:
        t = tr.get(c["sym"], [])
        ts = f"{len(t)} · {sum(1 for x in t if x > 0)} в плюс · {sum(t):+.1f}%" if t else "—"
        L_.append(f"| {c['sym'][:-4]} | {c['worst']:.0f}% | {c['n10']} / {c['n20']} / {c['n30']} | {c['med']:.0f}% | {c['rec']}% | {c['rec_h'] if c['rec_h'] is not None else '—'} | "
                  f"{datetime.fromtimestamp(c['last'], L):%d.%m %H:%M} | {ts} |")
    # наши сделки по группам глубины худшего прокола монеты
    L_ += ["", "## Наши сделки быстрых книг по группам монет (худший прокол монеты за 30 дн)", "", "| группа | сделок | в плюс | сумма |", "|---|---|---|---|"]
    worst = {c["sym"]: c["worst"] for c in coins}
    grp = defaultdict(list)
    for s, t in tr.items():
        w = worst.get(s)
        key = "проколов глубже 10% не было" if w is None else ("худший ≤ −30%" if w <= -30 else "худший −20…−30%" if w <= -20 else "худший −10…−20%")
        grp[key] += t
    for k in ("проколов глубже 10% не было", "худший −10…−20%", "худший −20…−30%", "худший ≤ −30%"):
        g = grp.get(k, [])
        if g:
            L_.append(f"| {k} | {len(g)} | {sum(1 for x in g if x > 0)} | {sum(g):+.1f}% |")
    L_ += ["", f"_Посчитано за {time.time() - t0:.0f} с. События — mm_flush.json._"]
    OUT_MD.write_text("\n".join(L_) + "\n", encoding="utf-8")
    print("\n".join(L_[:16]))
    print("…")
    print("\n".join(L_[-8:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
