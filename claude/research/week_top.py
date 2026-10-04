#!/usr/bin/env python3
"""R62 НА ДАННЫХ (03.10 22:30, владелец по BR: «смотрим самую высокую точку за неделю, если цена от неё ушла на 30 % — не берём лонги, а наоборот, на отскоках берём шорты с целью 5 % и
стопом 10 %»). 1) 301 вход бота по всплеску за неделю (журнал до слияния): монета ниже недельной вершины на 30 %+ или нет → что дал лонг бота и что дал бы шорт 5/10 за сутки
(часовые бары TradingView). 2) Вся доска, часовые 06.09–03.10: «отскок» = часовая свеча вверх на 3 %+; шорт 5/10 за сутки и лонг 5/10 в монетах ниже недельной вершины на 30 %+ и в остальных."""
import json, glob, sys, bisect
from pathlib import Path
from datetime import datetime, timezone, timedelta
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT)); D = Path(__file__).parent / "tvd"; L = timezone(timedelta(hours=3))
import fast_tier as ft
own = ft._own_mm(); B = {}
for f in glob.glob(str(D / "*_60.json")):
    d = json.load(open(f))
    if isinstance(d, dict): B[d["sym"].split(":")[1].replace(".P", "")] = d["bars"]
def walk(side, e, bars, tp=.05, sl=.10):
    for (t, o, h, l, c, v) in bars:
        if side == 1:
            if l <= e * (1 - sl): return -sl
            if h >= e * (1 + tp): return tp
        else:
            if h >= e * (1 + sl): return -sl
            if l <= e * (1 - tp): return tp
    return side * (bars[-1][4] / e - 1) if bars else None
def rep(nm, g, keys):
    if len(g) < 8: print(f"    {nm:40s} мало ({len(g)})"); return
    s = f"    {nm:40s} n={len(g):5d}"
    for k, lab in keys:
        v = [x[k] for x in g if x[k] is not None]
        if v: s += f" · {lab} {(sum(v) * 1000 - len(v)) / len(v):+6.1f}$ (в плюс {sum(1 for q in v if q > 0) * 100 // len(v)}%)"
    print(s)
# 1. входы бота за неделю
S = '/private/tmp/claude-501/-Users-evgenijminko-Work-random-python/d82eedff-7b9d-4661-aef5-52266ba7899d/scratchpad/replay/day/backup/paper_fast3_171044.jsonl'
ent, ex = {}, {}
for p in (S, str(ROOT / "output" / "paper_wake.jsonl")):
    for l in open(p):
        try: r = json.loads(l)
        except ValueError: continue
        if r.get("kind") == "entry" and r.get("side") == 1: ent[(r["sym"], round(r["at"]))] = r
        elif r.get("kind") == "exit_long": ex[(r["sym"], round(r.get("opened_at", 0)))] = r
rows = []
for k, e in ent.items():
    x = ex.get(k); b = B.get(e["sym"])
    if not x or not b or "ошибка сканера" in str(x.get("why_exit")): continue
    ts = [y[0] for y in b]; i = bisect.bisect_right(ts, e["at"]) - 1
    if i < 168 or i + 24 >= len(b): continue
    top = max(y[2] for y in b[i - 168:i]); drop = 1 - e["px"] / top
    rows.append(dict(drop=drop, fact=x["result_pct"] / 100 + .001, sh=walk(-1, e["px"], b[i + 1:i + 25]), t=e["at"]))
print(f"1. ЛОНГИ БОТА ЗА НЕДЕЛЮ с часовыми данными: {len(rows)}")
K1 = (("fact", "лонг бота (как было)"), ("sh", "шорт 5/10 за сутки"))
rep("ниже недельной вершины на 30 %+", [r for r in rows if r["drop"] >= .30], K1); rep("ниже на 15–30 %", [r for r in rows if .15 <= r["drop"] < .30], K1); rep("ниже на 0–15 %", [r for r in rows if r["drop"] < .15], K1)
# 2. вся доска
sig = []
for sym, b in B.items():
    if sym in own or len(b) < 400: continue
    for i in range(168, len(b) - 25):
        o, h, l, c = b[i][1:5]
        if c / o - 1 < .03: continue
        top = max(y[2] for y in b[i - 168:i + 1]); drop = 1 - c / top
        sig.append(dict(t=b[i][0], drop=drop, sh=walk(-1, c, b[i + 1:i + 25]), lo=walk(1, c, b[i + 1:i + 25]), sym=sym))
tm = sorted(s["t"] for s in sig)[len(sig) // 2]
print(f"\n2. ВСЯ ДОСКА, отскок = часовая свеча вверх на 3 %+: {len(sig)} случаев · {datetime.fromtimestamp(min(s['t'] for s in sig), L):%d.%m}–{datetime.fromtimestamp(max(s['t'] for s in sig), L):%d.%m}")
K2 = (("sh", "шорт 5/10"), ("lo", "лонг 5/10"))
for lo, hi, nm in ((.30, 9, "ниже недельной вершины на 30 %+"), (.15, .30, "ниже на 15–30 %"), (0, .15, "ниже на 0–15 %")):
    g = [s for s in sig if lo <= s["drop"] < hi]; rep(nm, g, K2); rep("   первая половина периода", [s for s in g if s["t"] < tm], K2); rep("   вторая половина", [s for s in g if s["t"] >= tm], K2)
