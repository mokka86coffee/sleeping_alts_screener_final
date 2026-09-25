"""Сделки бумажных книг (output/paper_*.jsonl, kind exit*) → шанс плюса и средний результат по стратегии/правилу и по фону на входе.
Фон: медиана доски за сутки на входе (по архиву получасовок cq_v2/hist/tops), Пт–Вс/Пн–Чт, сессия входа. Результат — result_pct книги
(у «картины» с 23.09 выходы по трёхминуткам; до того — по получасовкам: старые числа грубее)."""
import json, statistics as st
from collections import defaultdict
from datetime import datetime, timezone
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
agg = defaultdict(list)
for p in sorted((B / "output").glob("paper_*.jsonl")):
    book = p.stem.replace("paper_", "")
    for l in p.read_text(encoding="utf-8").splitlines():
        try: r = json.loads(l)
        except ValueError: continue
        if not str(r.get("kind", "")).startswith("exit") or r.get("result_pct") is None: continue
        t_in = r.get("opened_at") or r.get("entry_at") or r.get("at")
        if not t_in: continue
        side = r.get("side"); side = ("лонг" if float(side) > 0 else "шорт") if side is not None else ("шорт" if book == "end" else "лонг")
        rule = str(r.get("rule") or r.get("why") or "").split(":")[0][:22] or book
        res = float(r["result_pct"]); dt = datetime.fromtimestamp(float(t_in), timezone.utc); h = dt.hour
        b = board(float(t_in))
        bg = ["доска<-1" if b is not None and b < -1 else "доска>+1" if b is not None and b > 1 else "доска±1",
              "вых" if dt.weekday() >= 4 else "будни", "Сидней" if h >= 21 else "Токио" if h < 7 else "Лондон" if h < 13 else "НЙ"]
        for key in ((book, side, "ВСЕ"), (book, side, rule)):
            agg[key + ("",)].append(res)
            for x in bg: agg[key + (x,)].append(res)
def f(v): return f"n {len(v):3d} · плюс {sum(1 for x in v if x > 0)/len(v)*100:3.0f}% · средн {st.mean(v):+5.1f}%"
out = ["# Книги ботов: шанс плюса и средний результат (по правилу и фону на входе)"]
for key in sorted(k for k in agg if k[3] == ""):
    v = agg[key]
    if len(v) < 8: continue
    parts = [f"{x} {sum(1 for y in agg[key[:3]+(x,)] if y > 0)/len(agg[key[:3]+(x,)])*100:.0f}%/{st.mean(agg[key[:3]+(x,)]):+.1f} ({len(agg[key[:3]+(x,)])})"
             for x in ("доска<-1","доска±1","доска>+1","будни","вых","Сидней","Токио","Лондон","НЙ") if len(agg.get(key[:3]+(x,), [])) >= 5]
    out.append(f"{key[0]:<7}{key[1]:<5}{key[2]:<23} {f(v)} | " + " · ".join(parts))
Path(__file__).with_name("bots.md").write_text("\n".join(out) + "\n", encoding="utf-8"); print("\n".join(out))
