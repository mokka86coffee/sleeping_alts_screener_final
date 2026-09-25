"""Эпизоды «монета зашла в первые три очереди» (queue_log с 07.09; старый журнал — сдвиг −1 ч) → признаки на момент захода и исход.
Исход: максимум за 48 ч от цены захода ≥ PUMP_JUMP_PCT (40%, мерка проекта «пошла»). Признаки — мерки для группировки, не правила:
 r1   интерес за 48 ч ≥ +15% при цене за 48 ч в пределах ±10% (R1 «интерес растёт при стоящей цене»)
 fneg минимальный фандинг за 48 ч ≤ −0.05% (шорты копятся)
 flush медиана доски за сутки ≤ −1% в момент захода (R8)
 lead  у другой монеты доски в этот момент +40% за сутки (лидер тянет на себя)
 ladder были импульсы за 90 дней до (дневной объём ≥8× и максимум ≥1.4× недельной медианы) (R13)
 topdn топ-трейдеры за 24 ч −10% и больше (R10)
Пишет episodes.csv рядом."""
import csv, json, statistics as st, sys
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path
B = Path("/Users/evgenijminko/Work/random/python"); sys.path.insert(0, str(B))
OUT = Path(__file__).with_name("episodes.csv")
def ts(s): return int(datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp() * 1000)
runs = {}
for path, shift in ((B / "_old_runs_20260916_1936UTC/output/queue_log.jsonl", -3600000), (B / "output/queue_log.jsonl", 0)):
    for l in path.read_text(encoding="utf-8").splitlines():
        try: r = json.loads(l)
        except ValueError: continue
        if isinstance(r.get("place"), int) and r["place"] <= 3 and r.get("sym") and r.get("at"):
            runs.setdefault(r["sym"], set()).add(ts(r["at"]) + shift)
eps = []
for sym, tt in runs.items():
    tt = sorted(tt); prev = None
    for t in tt:
        if prev is None or t - prev > 6 * 3600000: eps.append((sym, t))
        prev = t
tops = {p.stem: json.loads(p.read_text()) for p in (B / "cq_v2/hist/tops").glob("*.json")}
idx = {s: {k[0]: k for k in d["kl"]} for s, d in tops.items()}
def bar(s, t): return idx.get(s, {}).get(t // 1800000 * 1800000 - 1800000)
def board(t):
    ch = []; mx = 0
    for s, m in idx.items():
        if s == "BTCUSDT": continue
        a, b = bar(s, t), bar(s, t - 86400000)
        if a and b: c = (a[3] / b[3] - 1) * 100; ch.append(c); mx = max(mx, c) if True else mx
    return (st.median(ch) if ch else None), ch
from core_http import get_json
from core_config import BINANCE_FAPI
daily = {}
def ladder(sym, t):
    if sym not in daily:
        k = get_json(f"{BINANCE_FAPI}/fapi/v1/klines", {"symbol": sym, "interval": "1d", "startTime": t - 120 * 86400000, "limit": 150}, weight=2) or []
        daily[sym] = [(int(x[0]), float(x[2]), float(x[4]), float(x[7])) for x in k]
    d = [x for x in daily[sym] if x[0] < t - 86400000 and x[0] >= t - 90 * 86400000]
    for i in range(7, len(d)):
        vm = st.median(x[3] for x in d[i-7:i]); cm = st.median(x[2] for x in d[i-7:i])
        if d[i][3] >= 8 * vm and d[i][1] >= 1.4 * cm: return 1
    return 0
rows = []
for sym, t in eps:
    d = tops.get(sym)
    if not d: continue
    b0 = bar(sym, t)
    if not b0: continue
    fut = [k for k in d["kl"] if t <= k[0] < t + 48 * 3600000]
    if len(fut) < 60: continue
    p0 = b0[3]; up = max(k[1] for k in fut) / p0 - 1; dn = min(k[2] for k in fut) / p0 - 1
    b48 = bar(sym, t - 48 * 3600000)
    oi = {int(k): v for k, v in d["oi"].items()}
    o0, o1 = oi.get(t // 1800000 * 1800000 - 48 * 3600000), oi.get(t // 1800000 * 1800000)
    top = {int(k): v for k, v in d["top"].items()}
    t0, t1 = top.get(t // 1800000 * 1800000 - 24 * 3600000), top.get(t // 1800000 * 1800000)
    fr = [r for tt, r in d["fund"] if t - 48 * 3600000 <= tt <= t]
    med, ch = board(t)
    my = (b0[3] / bar(sym, t - 86400000)[3] - 1) * 100 if bar(sym, t - 86400000) else 0
    dt = datetime.fromtimestamp(t / 1000, timezone.utc); h = dt.hour
    rows.append(dict(sym=sym[:-4], at=datetime.fromtimestamp(t/1000 + 3*3600, timezone.utc).strftime("%d.%m %H:%M"),
        day=dt.strftime("%a"), ses="Сидней" if h >= 21 else "Токио" if h < 7 else "Лондон" if h < 13 else "НЙ",
        up48=round(up * 100), dn48=round(dn * 100), went=int(up >= 0.40),
        px48=round((p0 / b48[3] - 1) * 100) if b48 else None, oi48=round((o1 / o0 - 1) * 100) if o0 and o1 else None,
        fund_min=round(min(fr), 3) if fr else None, board=round(med, 1) if med is not None else None,
        lead=int(any(c >= 40 for c in ch if abs(c - my) > 1e-9)), top24=round((t1 / t0 - 1) * 100) if t0 and t1 else None,
        ladder=ladder(sym, t)))
for r in rows:
    r["r1"] = int(r["oi48"] is not None and r["oi48"] >= 15 and r["px48"] is not None and abs(r["px48"]) <= 10)
    r["fneg"] = int(r["fund_min"] is not None and r["fund_min"] <= -0.05)
    r["flush"] = int(r["board"] is not None and r["board"] <= -1)
    r["topdn"] = int(r["top24"] is not None and r["top24"] <= -10)
with OUT.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print("эпизодов", len(rows), "пошли", sum(r["went"] for r in rows))
