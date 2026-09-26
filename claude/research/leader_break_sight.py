"""Лонги «картины» (output/paper_sight.jsonl) в сутки после слома лидера (R27) против остальных лонгов при доске >+1%; разрез по знаку медианы доски за 6 ч.
    .venv/bin/python claude/research/leader_break_sight.py"""
import json, statistics as st
from datetime import datetime, timezone, timedelta
from pathlib import Path
B = Path("/Users/evgenijminko/Work/random/python")
tops = {p.stem: {k[0]: k[3] for k in json.loads(p.read_text())["kl"]} for p in (B / "cq_v2/hist/tops").glob("*.json") if p.stem != "BTCUSDT"}
memo = {}
def board(t):
    k = int(t) // 1800 * 1800 * 1000 - 1800000
    if k not in memo:
        ch = [m[k] / m[k - 86400000] - 1 for m in tops.values() if k in m and k - 86400000 in m]
        memo[k] = st.median(ch) * 100 if ch else None
    return memo[k]
L = timezone(timedelta(hours=3))
def loc(s): return datetime.strptime(s + ".2026", "%d.%m %H:%M.%Y").replace(tzinfo=L).timestamp()
breaks = {"слом AKE 19.09": loc("19.09 20:00"), "слом PTB 21.09": loc("21.09 23:00"), "слом MUBARAK 23.09": loc("23.09 07:30"),
          "слом AKE 20.09 (доска ±1)": loc("20.09 08:00"), "слом ONE 20.09 (доска падала)": loc("20.09 14:00")}
shakes = {"встряска ONE 18.09": loc("18.09 02:00"), "встряска ONE 19.09": loc("19.09 06:00"), "встряска SYN 17.09": loc("17.09 13:00")}
rows = []
for l in (B / "output/paper_sight.jsonl").read_text().splitlines():
    try: r = json.loads(l)
    except ValueError: continue
    if r.get("kind") != "exit" or r.get("result_pct") is None or float(r.get("side", 1)) <= 0: continue
    t = float(r.get("opened_at") or r["at"]); rows.append((t, float(r["result_pct"]), r["sym"]))
def f(v): return f"n {len(v):4d} · плюс {sum(1 for x in v if x > 0)/len(v)*100:3.0f}% · средн {st.mean(v):+5.2f}% · медиана {st.median(v):+5.2f}%" if v else "n 0"
print("Лонги «картины» (exit, result_pct), вход в окне после события:")
used = set()
for name, t0 in list(breaks.items()) + list(shakes.items()):
    for h0, h1 in ((0, 6), (6, 24), (0, 24)):
        v = [x[1] for x in rows if t0 + h0 * 3600 <= x[0] < t0 + h1 * 3600]
        print(f"  {name:<30} {h0:>2}–{h1:<2} ч: {f(v)}")
    used |= {x[0] for x in rows if t0 <= x[0] < t0 + 24 * 3600 and name.startswith("слом")}
rest = [x for x in rows if x[0] not in used]
b1 = [x[1] for x in rest if (b := board(x[0])) is not None and b > 1]
print(f"\n  ОСТАЛЬНЫЕ лонги при доске >+1% (без суток после сломов): {f(b1)}")
b0 = [x[1] for x in rest if (b := board(x[0])) is not None and -1 <= b <= 1]
print(f"  остальные лонги при доске ±1%: {f(b0)}")
allb = [x[1] for x in rows if t0 is not None]
brk = [x[1] for x in rows if any(t0 <= x[0] < t0 + 24 * 3600 for n, t0 in breaks.items() if "доска" not in n)]
print(f"  ИТОГО сутки после 3 сломов на ехавшей доске: {f(brk)}")
print(f"  по монетам в эти сутки (топ убытков):")
from collections import defaultdict
bs = defaultdict(list)
for t, res, s in rows:
    if any(t0 <= t < t0 + 24 * 3600 for n, t0 in breaks.items() if "доска" not in n): bs[s].append(res)
for s, v in sorted(bs.items(), key=lambda kv: st.mean(kv[1]))[:8]: print(f"    {s[:-4]:<9} n {len(v):2d} средн {st.mean(v):+5.1f}%")

# --- медиана доски за 6 ч на входе: отделяет ли плохие часы 6–24 после слома ---
memo6 = {}
def board6(t):
    k = int(t) // 1800 * 1800 * 1000 - 1800000
    if k not in memo6:
        ch = [m[k] / m[k - 6 * 3600000] - 1 for m in tops.values() if k in m and k - 6 * 3600000 in m]
        memo6[k] = st.median(ch) * 100 if ch else None
    return memo6[k]
print("\nМедиана доски за 6 ч на входе (знак) — часы 6–24 после 3 сломов на ехавшей доске против остальных лонгов при доске24 >+1%:")
def split(name, sel):
    v = [x for x in rows if sel(x)]
    pos = [x[1] for x in v if (b := board6(x[0])) is not None and b > 0]
    neg = [x[1] for x in v if (b := board6(x[0])) is not None and b <= 0]
    print(f"  {name:<44} доска6 > 0: {f(pos)}\n  {'':<44} доска6 ≤ 0: {f(neg)}")
inwin = lambda x: any(t0 + 6 * 3600 <= x[0] < t0 + 24 * 3600 for n, t0 in breaks.items() if "доска" not in n)
split("часы 6–24 после сломов (AKE19/PTB/MUBARAK)", inwin)
split("остальные лонги при доске24 >+1%", lambda x: x[0] not in used and (b := board(x[0])) is not None and b > 1)
split("сутки после встрясок (ONE18/ONE19/SYN17)", lambda x: any(t0 <= x[0] < t0 + 24 * 3600 for t0 in shakes.values()))

# --- сессии: часы 6–24 после сломов на ехавшей доске — по сессии входа (Сидней 21–07, Токио 00–07 → здесь: Сидней 21–00, Токио 00–07, Лондон 07–13, НЙ 13–21 UTC)
def sess(t):
    h = datetime.fromtimestamp(t, timezone.utc).hour
    return "Сидней" if h >= 21 else "Токио" if h < 7 else "Лондон" if h < 13 else "НЙ"
print("\nПо сессии входа (UTC: Токио 00–07, Лондон 07–13, НЙ 13–21, Сидней 21–00):")
for name, sel in (("часы 6–24 после сломов", inwin), ("остальные лонги при доске24 >+1%", lambda x: x[0] not in used and (b := board(x[0])) is not None and b > 1)):
    for sn in ("Токио", "Лондон", "НЙ", "Сидней"):
        v = [x[1] for x in rows if sel(x) and sess(x[0]) == sn]
        print(f"  {name:<36} {sn:<7} {f(v)}")
