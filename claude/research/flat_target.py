"""04.10 — цель шорта «низ флэта» вместо постоянных 5/10 % (владелец по 1000CAT: «цена ниже флэта… почему тогда цель такая далёкая», «вноси»).
Счёт по закрытым шортам журнала бота (paper_fast3.jsonl, paper_wake.jsonl) на часовых и дневных свечах TradingView (claude/research/tvd, Binance не трогаем):
флэт = размах 5 закрытых дневных свечей до входа ≤ FAST3_LADDER_FLAT_MAX; низ флэта = минимум этих 5 дней. Если низ ближе цели сделки — выходим на нём."""
import json, sys, time
from pathlib import Path
from datetime import datetime, timezone, timedelta
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from core_config import FAST3_LADDER_FLAT_DAYS as FD, FAST3_LADDER_FLAT_MAX as FM
L = timezone(timedelta(hours=3)); TV = ROOT / "claude" / "research" / "tvd"
def bars(sym, res):
    p = TV / f"{sym}.P_{res}.json"
    if not p.exists(): return None
    return json.load(open(p))["bars"]
ent = {}; ex = []
for f in ("paper_fast3.jsonl", "paper_wake.jsonl"):
    for l in open(ROOT / "output" / f, encoding="utf-8"):
        try: r = json.loads(l)
        except ValueError: continue
        if r.get("kind") == "entry" and r.get("side") == -1: ent[(r["sym"], round(r["at"]))] = r
        if r.get("kind") == "exit_short": ex.append(r)
rows = []; skip = 0
for r in ex:
    e = r.get("px_in"); t0 = r.get("opened_at"); t1 = r["at"]
    d = bars(r["sym"], "1D"); h = bars(r["sym"], "60")
    if not e or not t0 or not d or not h: skip += 1; continue
    day0 = int(t0 // 86400) * 86400
    dd = [b for b in d if b[0] < day0][-FD:]
    if len(dd) < FD or h[-1][0] + 3600 < t1: skip += 1; continue
    hi5 = max(b[2] for b in dd); lo5 = min(b[3] for b in dd); flat = hi5 / lo5 - 1
    en = ent.get((r["sym"], round(t0))) or {}; tg = float(en.get("target") or 0.10)
    hh = [b for b in h if b[0] >= t0 and b[0] + 3600 <= t1]
    low = min((b[3] for b in hh), default=None)
    rows.append(dict(sym=r["sym"], day=datetime.fromtimestamp(t1, L).strftime("%d.%m"), e=e, lo5=lo5, hi5=hi5, flat=flat, tg=tg, res=r["result_pct"], usd=r.get("usd", r["result_pct"] * 10),
                     dist=(e / lo5 - 1) * 100, pos=(e - lo5) / (hi5 - lo5) if hi5 > lo5 else None, hit=low is not None and low <= lo5, why=r.get("why_exit", "")))
print(f"закрытых шортов {len(ex)}, со свечами {len(rows)}, без данных {skip}; флэт: размах {FD} дн ≤ {FM:.0%}")
ap = [x for x in rows if x["flat"] <= FM and x["e"] > x["lo5"] and x["lo5"] > x["e"] * (1 - x["tg"])]
print(f"правило применимо (флэт, вход выше низа, низ ближе цели): {len(ap)} из {len(rows)}")
def summ(name, xs):
    if not xs: print(name, "нет"); return
    old = sum(x["usd"] for x in xs); new = sum((x["dist"] / (1 + x["dist"] / 100) * 10 if x["hit"] else x["usd"]) for x in xs)
    print(f"{name}: {len(xs)} сд. · как было {old:+.0f} $ ({sum(x['usd'] > 0 for x in xs)} в плюс) · с целью на низу флэта {new:+.0f} $ · дошли до низа {sum(x['hit'] for x in xs)} · дошли до своей цели {sum('цель' in x['why'] for x in xs)}")
summ("все применимые", ap)
for lo, hi_ in ((0, 2), (2, 5), (5, 10)):
    summ(f"  до низа флэта {lo}–{hi_} %", [x for x in ap if lo <= x["dist"] < hi_])
for nm, f in (("  вход в нижней половине флэта", lambda x: x["pos"] is not None and x["pos"] < .5), ("  вход в верхней половине флэта", lambda x: x["pos"] is not None and x["pos"] >= .5)):
    summ(nm, [x for x in ap if f(x)])
print("по дням (применимые): " + " · ".join(f"{dy} {sum(x['usd'] for x in ap if x['day'] == dy):+.0f}→{sum((x['dist'] / (1 + x['dist'] / 100) * 10 if x['hit'] else x['usd']) for x in ap if x['day'] == dy):+.0f} $ ({sum(x['day'] == dy for x in ap)})" for dy in sorted({x['day'] for x in ap}, key=lambda s: (s[3:], s[:2]))))
hitn = [x for x in ap if x["hit"]]
print("дошедшие до низа: потом (как было) " + ", ".join(f"{x['sym'][:-4]} низ +{x['dist'] / (1 + x['dist'] / 100):.1f}% / было {x['res']:+.1f}%" for x in hitn[:40]))
import collections
print("цели сделок:", dict(collections.Counter(round(x["tg"], 3) for x in ap)))
print("до низа, %:", dict(sorted(collections.Counter(int(x["dist"]) for x in ap).items())))
print("чем вышли:", dict(collections.Counter(x["why"].split(" ")[0] + " " + (x["why"].split(" ")[1] if len(x["why"].split(" ")) > 1 else "") for x in ap).most_common(8)))
