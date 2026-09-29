#!/usr/bin/env python3
"""СИГНАЛЫ КАНАЛА «Volume Spikes» (Bybit 3m) 29.09 — что было после всплеска (владелец 29.09: «скрины с архива разбирай… смотри что было после всплеска»).
Список — signals.json (монета, время поста UTC+3, изменение цены %, рост объёма ×). Данные Bybit linear: 3m свечи, интерес 5m; фон — дневки 90 дн.
По сигналу: бар всплеска (3m, закрыт к времени поста), лучший ход вверх / вниз за 1 ч и 4 ч от закрытия бара, что было раньше (+5% или −5%),
интерес за час до и за час после, где цена в диапазоне 90 дн."""
import json, urllib.request, datetime as dt
from pathlib import Path
L = dt.timezone(dt.timedelta(hours=3)); H = Path(__file__).parent
def g(u):
    return json.load(urllib.request.urlopen(u, timeout=20))
def kl(sym, iv, start, end):
    r = g(f"https://api.bybit.com/v5/market/kline?category=linear&symbol={sym}&interval={iv}&start={start}&end={end}&limit=1000")["result"]["list"]
    return sorted([[int(x[0])] + [float(v) for v in x[1:6]] + [float(x[6])] for x in r])   # t o h l c vol turnover
out = []
for s in json.load(open(H / "signals.json")):
    sym = s["sym"] + "USDT"
    t = dt.datetime(2026, 9, 29, *map(int, s["time"].split(":")), tzinfo=L).timestamp() * 1000
    try:
        k = kl(sym, 3, int(t - 2 * 3600e3), int(t + 4 * 3600e3 + 3600e3))
    except Exception as e:
        out.append(dict(**s, err=str(e))); continue
    if not k:
        out.append(dict(**s, err="нет свечей")); continue
    bar = max((x for x in k if x[0] + 180e3 <= t + 60e3), key=lambda x: x[0])   # последний закрытый 3m-бар к посту
    e = bar[4]; t0 = bar[0] + 180e3
    def win(h):
        w = [x for x in k if t0 <= x[0] < t0 + h * 3600e3]
        return (max(x[2] for x in w) / e - 1) * 100, (min(x[3] for x in w) / e - 1) * 100, (w[-1][4] / e - 1) * 100
    first = None
    for x in k:
        if x[0] < t0: continue
        if x[2] >= e * 1.05 and x[3] <= e * 0.95: first = "оба в одном баре"; break
        if x[2] >= e * 1.05: first = "+5% раньше"; break
        if x[3] <= e * 0.95: first = "−5% раньше"; break
    try:
        oi = g(f"https://api.bybit.com/v5/market/open-interest?category=linear&symbol={sym}&intervalTime=5min&startTime={int(t0-3600e3)}&endTime={int(t0+3600e3)}&limit=200")["result"]["list"]
        oi = sorted((int(x["timestamp"]), float(x["openInterest"])) for x in oi)
        o0 = min(oi, key=lambda z: abs(z[0] - t0))[1]; ob = oi[0][1]; oa = oi[-1][1]
        oi_b, oi_a = (o0 / ob - 1) * 100, (oa / o0 - 1) * 100
    except Exception:
        oi_b = oi_a = None
    d = kl(sym, "D", int(t - 90 * 86400e3), int(t))
    lo = min(x[3] for x in d); hi = max(x[2] for x in d)
    u1, d1, c1 = win(1); u4, d4, c4 = win(4)
    out.append(dict(**s, px=e, bar_pct=(bar[4] / bar[1] - 1) * 100, up1=u1, dn1=d1, c1=c1, up4=u4, dn4=d4, c4=c4, first=first,
                    oi_before=oi_b, oi_after=oi_a, x90=e / lo, from_hi90=(e / hi - 1) * 100))
json.dump(out, open(H / "spike_after.json", "w"), ensure_ascii=False, indent=0)
f = lambda v: "—" if v is None else f"{v:+.1f}"
print("монета время | 1ч: вверх/вниз/закр | 4ч: вверх/вниз/закр | что раньше ±5% | OI час до/после | ×90мин, от макс90")
for r in out:
    if r.get("err"): print(r["sym"], r["time"], "ошибка", r["err"][:60]); continue
    print(f"{r['sym']:8} {r['time']} | {f(r['up1'])}/{f(r['dn1'])}/{f(r['c1'])} | {f(r['up4'])}/{f(r['dn4'])}/{f(r['c4'])} | {r['first'] or 'ни то ни то'} | {f(r['oi_before'])}/{f(r['oi_after'])} | ×{r['x90']:.2f} {f(r['from_hi90'])}")
