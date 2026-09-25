"""Вероятности по состояниям очереди (queue_log, в очереди) до конца СЛЕДУЮЩЕЙ сессии (границы 21/0/7/13 UTC).
Исходы: p5 — +5% раньше −5% (по получасовкам архива, бар где оба — считаем против); up — медиана максимума; dn — медиана минимума.
Цена — px записи. Архив cq_v2/intraday (закрытия исправлены 25.09)."""
import json, statistics as st
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
B = Path("/Users/evgenijminko/Work/random/python")
def ts(s): return int(datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp())
arch = {}
def bars(sym):
    if sym not in arch:
        p = B / "cq_v2/intraday" / f"{sym.replace('USDT','').lower()}.jsonl"; m = {}
        if p.exists():
            for l in p.read_text(encoding="utf-8").splitlines():
                try: r = json.loads(l)
                except ValueError: continue
                if r.get("candle") and r.get("h") and r.get("l"): m[ts(r["candle"])] = (float(r["h"]), float(r["l"]))
        arch[sym] = m
    return arch[sym]
BOUND = (0, 7, 13, 21)
def next_session_end(t):
    n = 0; x = t // 1800 * 1800
    while n < 2:
        x += 1800; h = datetime.fromtimestamp(x, timezone.utc)
        if h.minute == 0 and h.hour in BOUND: n += 1
    return x
stats = defaultdict(list); stats2 = defaultdict(list)
for l in (B / "output/queue_log.jsonl").read_text(encoding="utf-8").splitlines():
    try: r = json.loads(l)
    except ValueError: continue
    if not r.get("in_queue") or not r.get("px") or not r.get("sym"): continue
    t = ts(r["at"]); end = next_session_end(t); m = bars(r["sym"]); p0 = float(r["px"])
    up = dn = 0.0; res = None
    for b in range(t // 1800 * 1800 + 1800, end, 1800):
        if b not in m: continue
        h, lo = m[b]; up = max(up, h / p0 - 1); dn = min(dn, lo / p0 - 1)
        if res is None:
            if lo <= p0 * 0.95: res = 0
            elif h >= p0 * 1.05: res = 1
    if res is None: res = 2
    keys = [f"группа={r.get('group')}", f"сегодня={r.get('today')}", f"деньги={str(r.get('money'))[:30]}",
            f"лидер тянет={'да' if r.get('hold_reason') else 'нет'}", f"режим={r.get('mode')}", f"двигатель={r.get('engine')}",
            f"место={'1' if r.get('place')==1 else '2-3' if (r.get('place') or 99)<=3 else '4+'}", "ВСЕ"]
    med = r.get("board_med_24h"); dt = datetime.fromtimestamp(t, timezone.utc); hh = dt.hour
    bg = ["доска " + ("<-1" if med is not None and med < -1 else ">+1" if med is not None and med > 1 else "±1" if med is not None else "?"),
          "вых" if dt.weekday() >= 4 else "будни",
          "Сидней" if hh >= 21 else "Токио" if hh < 7 else "Лондон" if hh < 13 else "НЙ"]
    for k in keys:
        stats[k].append((res, up, dn))
        for b in bg: stats2[(k, b)].append(res)
out = ["# Вероятности по состояниям очереди — до конца следующей сессии (16–25.09)", "состояние · n · +5% первым · −5% первым · ни то ни другое · медиана макс · медиана мин"]
for k, v in sorted(stats.items(), key=lambda kv: (kv[0].split('=')[0], -sum(1 for x in kv[1] if x[0] == 1) / len(kv[1]))):
    if len(v) < 50: continue
    n = len(v); u = sum(1 for x in v if x[0] == 1); d = sum(1 for x in v if x[0] == 0)
    out.append(f"{k:<46} n {n:5d} · {u/n*100:3.0f}% · {d/n*100:3.0f}% · {(n-u-d)/n*100:3.0f}% · {st.median(x[1] for x in v)*100:+.1f}% · {st.median(x[2] for x in v)*100:+.1f}%")
out += ["", "# То же по фону: +5%/−5% первым (n); фон: доска за сутки, Пт–Вс против Пн–Чт, сессия прогона"]
for k in sorted(stats):
    if len(stats[k]) < 200: continue
    parts = []
    for b in ("доска <-1", "доска ±1", "доска >+1", "будни", "вых", "Сидней", "Токио", "Лондон", "НЙ"):
        v = stats2.get((k, b), [])
        if len(v) >= 40: parts.append(f"{b} {sum(1 for x in v if x==1)/len(v)*100:.0f}/{sum(1 for x in v if x==0)/len(v)*100:.0f} ({len(v)})")
    out.append(f"{k:<40} " + " · ".join(parts))
Path(__file__).with_name("state_probs.md").write_text("\n".join(out) + "\n", encoding="utf-8"); print("\n".join(out[out.index("") :]))
