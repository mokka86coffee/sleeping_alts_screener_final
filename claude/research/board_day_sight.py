"""ДЕНЬГИ ПО R28: лонги «картины» в дни, которые на 06:00 UTC уже «поехали» (медиана доски за 6 ч > +0.5%), против остальных дней.
Сделки: output/paper_sight.jsonl (с 18.09), вход по времени opened_at. Медиана доски за 6 ч — по архиву получасовок cq_v2/hist/tops.
    .venv/bin/python claude/research/board_day_sight.py
"""
import json, statistics as st
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
B = Path("/Users/evgenijminko/Work/random/python"); H = 3600000
tops = {p.stem: {k[0]: k[3] for k in json.loads(p.read_text())["kl"]} for p in (B / "cq_v2/hist/tops").glob("*.json") if p.stem != "BTCUSDT"}
def board(t_ms, dt):
    ch = [m[t_ms] / m[t_ms - dt] - 1 for m in tops.values() if t_ms in m and t_ms - dt in m]
    return st.median(ch) * 100 if ch else None
rows = []
for l in (B / "output/paper_sight.jsonl").read_text().splitlines():
    try: r = json.loads(l)
    except ValueError: continue
    if r.get("kind") != "exit" or r.get("result_pct") is None or float(r.get("side", 1)) <= 0: continue
    t = float(r.get("opened_at") or r["at"]); rows.append((t, float(r["result_pct"])))
days = defaultdict(list)
for t, res in rows:
    d = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"); days[d].append((t, res))
def f(v): return f"n {len(v):4d} · плюс {sum(1 for x in v if x > 0) / len(v) * 100:3.0f}% · средн {st.mean(v):+5.2f}%" if v else "n 0"
print("день (UTC) · доска6 на 06:00 UTC · итог дня (мед24 на 24:00) · лонги «картины» за день · лонги после 06:00 UTC")
went, other = [], []
for d in sorted(days):
    dt = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc); t0 = int(dt.timestamp() * 1000)
    b6 = board(t0 + 6 * H, 6 * H); b24 = board(t0 + 24 * H, 24 * H)
    allv = [x[1] for x in days[d]]; after = [x[1] for x in days[d] if x[0] >= (t0 + 6 * H) / 1000]
    flag = "ПОЕХАЛА" if b6 is not None and b6 > 0.5 else "нет"
    (went if flag == "ПОЕХАЛА" else other).extend(after)
    s6 = '—' if b6 is None else f'{b6:+.1f}%'; s24 = '—' if b24 is None else f'{b24:+.1f}%'
    print(f"  {d} · {s6:>6} {flag:<8} · {s24:>6} · {f(allv)} · {f(after)}")
print(f"\nлонги после 06:00 UTC в дни «поехала» (доска6 > +0.5% на 06:00): {f(went)}")
print(f"лонги после 06:00 UTC в остальные дни:                          {f(other)}")
