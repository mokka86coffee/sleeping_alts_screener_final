"""ДЕНЬ, КОГДА ПОЕХАЛА ДОСКА — видно ли его в первые часы (хвост 2 из CONTEXT.md; R15: заходы в первые идут в такие дни 35–50%, иначе ~5%).
Архив получасовок cq_v2/hist/tops (30 дней). По каждому дню (UTC): медиана доски за сутки на 24:00 (итог дня), и в разрезах по часам дня —
медиана доски за 6 ч и доля растущих за 6 ч на 03/06/09/12/15/18/21 UTC. Дни владельца: 11.09, 16–18.09; по R27 — 20–21.09.
    .venv/bin/python claude/research/board_day.py
"""
import json, statistics as st
from datetime import datetime, timezone
from pathlib import Path
P = Path(__file__).resolve().parents[2] / "cq_v2" / "hist" / "tops"
kl = {p.stem: {k[0]: k[3] for k in json.loads(p.read_text())["kl"]} for p in P.glob("*.json") if p.stem != "BTCUSDT"}
H = 3600000
def board(t, dt):
    r = [m[t] / m[t - dt] - 1 for m in kl.values() if t in m and t - dt in m]
    return (st.median(r) * 100, sum(1 for x in r if x > 0) / len(r) * 100) if r else (None, None)
ts = sorted(set().union(*[set(m) for m in kl.values()]))
days = sorted({t // (24 * H) * 24 * H for t in ts if t - ts[0] >= 24 * H})
rows = []
for d in days:
    end = d + 24 * H
    if end not in kl[next(iter(kl))] and end > ts[-1]:
        continue
    m24, s24 = board(end, 24 * H)
    if m24 is None:
        continue
    hours = {}
    for h in (3, 6, 9, 12, 15, 18, 21):
        m6, s6 = board(d + h * H, 6 * H)
        mday, _ = board(d + h * H, h * H)  # медиана с начала дня
        hours[h] = (m6, s6, mday)
    rows.append((d, m24, s24, hours))
dn = lambda d: datetime.fromtimestamp(d / 1000, timezone.utc).strftime("%d.%m %a")
print("день (UTC)     итог: мед24 / доля↑ | по часам UTC: медиана за 6 ч / доля растущих за 6 ч / медиана с начала дня")
print(f"{'':<15}{'':<14}| " + " | ".join(f"{h:>2}:00            " for h in (3, 6, 9, 12, 15, 18, 21)))
for d, m24, s24, hours in rows:
    cells = [f"{v[0]:+4.1f}/{v[1]:3.0f}/{v[2]:+4.1f}" if v[0] is not None else "      —       " for h, v in sorted(hours.items())]
    print(f"{dn(d):<15}{m24:+5.1f}% / {s24:3.0f}% | " + " | ".join(cells))
top = sorted(rows, key=lambda r: -r[1])[:6]
print("\nШесть лучших дней по итогу суток: " + ", ".join(f"{dn(r[0])} {r[1]:+.1f}%" for r in top))
print("Худшие: " + ", ".join(f"{dn(r[0])} {r[1]:+.1f}%" for r in sorted(rows, key=lambda r: r[1])[:4]))
# ранний признак: медиана за 6 ч на 06:00 UTC (Токио) и на 09:00 — как связана с итогом дня
for h in (3, 6, 9):
    xs = [(r[3][h][0], r[1]) for r in rows if r[3][h][0] is not None]
    pos = [y for x, y in xs if x > 0.5]; neg = [y for x, y in xs if x <= 0.5]
    print(f"медиана за 6 ч на {h:02d}:00 UTC > +0.5%: дней {len(pos)}, итог дня > +1% у {sum(1 for y in pos if y > 1)}, медиана итога {st.median(pos) if pos else 0:+.1f}%"
          f" · ≤ +0.5%: дней {len(neg)}, итог > +1% у {sum(1 for y in neg if y > 1)}, медиана итога {st.median(neg) if neg else 0:+.1f}%")
