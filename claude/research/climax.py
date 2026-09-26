"""КУЛЬМИНАЦИОННЫЙ ОБЪЁМ И ВЕРШИНА (26.09, по видео Щукина, video_shukin_volumes.md п. 2: «максимальный объём хода стоит на вершине, дальше в 90% укатка»).
Проверка на наших лидерах из anatomy.csv (первый большой ход: start → peak1). Получасовки фьючерсов Binance с объёмом в долларах (quote volume)
и долей покупок по рынку (taker buy). Для каждого хода: бар с максимальным объёмом в окне [start, peak1 + 24 ч] — где он стоит относительно вершины
(часы, минус = раньше вершины), во сколько раз больше медианного объёма хода, доля покупателей-агрессоров в нём, и что дальше: закрытие через
6/12/24 ч от закрытия этого бара, максимум цены после него за 24 ч (дотянула ли выше). Мерки для разметки, не правила.
    .venv/bin/python claude/research/climax.py
"""
import csv, json, statistics as st, time, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
L = timezone(timedelta(hours=3)); H = 3600000
def loc(s): return int(datetime.strptime(s + ".2026", "%d.%m %H:%M.%Y").replace(tzinfo=L).timestamp() * 1000)
def kl(sym, t0, t1):
    out, t = [], t0
    while t < t1:
        u = f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}USDT&interval=30m&startTime={t}&endTime={t1}&limit=1500"
        d = json.loads(urllib.request.urlopen(u, timeout=20).read())
        if not d: break
        out += d; t = d[-1][0] + 1800000
        if len(d) < 1500: break
    return [(k[0], float(k[2]), float(k[3]), float(k[4]), float(k[7]), float(k[10])) for k in out]  # t, hi, lo, close, quote vol, taker buy quote
rows = list(csv.DictReader(open(Path(__file__).with_name("anatomy.csv"), encoding="utf-8")))
print(f"{'монета':<9}{'ход1':>6} {'вершина':<12}| макс.объём: сдвиг ч · ×медиана · доля покуп | после бара макс.объёма: 6ч · 12ч · 24ч · макс↑24ч | вершина после макс.объёма?")
res = []
for r in rows:
    try:
        t0, tp = loc(r["start"]), loc(r["peak1"])
    except Exception:
        continue
    try:
        k = kl(r["sym"], t0, tp + 48 * H)
    except Exception as e:
        print(r["sym"], "нет данных:", e); continue
    if len(k) < 4: continue
    win = [x for x in k if t0 <= x[0] <= tp + 24 * H]
    if not win: continue
    mx = max(win, key=lambda x: x[4]); med = st.median(x[4] for x in win) or 1
    shift = (mx[0] - tp) / H
    buy = mx[5] / mx[4] * 100 if mx[4] else None
    after = {dt: next(((x[3] / mx[3] - 1) * 100 for x in k if x[0] == mx[0] + dt * H), None) for dt in (6, 12, 24)}
    hi24 = [x[1] for x in k if mx[0] < x[0] <= mx[0] + 24 * H]
    up24 = (max(hi24) / mx[3] - 1) * 100 if hi24 else None
    # настоящая вершина хода (максимум закрытия в окне) относительно бара макс. объёма
    top = max(win, key=lambda x: x[3]); top_after = (top[0] - mx[0]) / H
    f = lambda v: "  —  " if v is None else f"{v:+5.1f}"
    print(f"{r['sym']:<9}{r['move1_pct']:>5}% {r['peak1']:<12}| {shift:+6.1f} · ×{mx[4] / med:4.1f} · {buy:3.0f}% | {f(after[6])} · {f(after[12])} · {f(after[24])} · {f(up24)} | вершина через {top_after:+.1f} ч")
    res.append(dict(sym=r["sym"], shift=shift, ratio=mx[4] / med, buy=buy, after=after, up24=up24, top_after=top_after, move=float(r["move1_pct"])))
    time.sleep(0.15)
n = len(res)
print(f"\nСВОДКА по {n} ходам (окно: старт → вершина + 24 ч):")
near = [x for x in res if abs(x["shift"]) <= 2]
before = [x for x in res if x["shift"] < -2]; later = [x for x in res if x["shift"] > 2]
print(f"  бар макс.объёма в ±2 ч от вершины — {len(near)}/{n}; раньше вершины (>2 ч) — {len(before)}; позже (уже на спаде) — {len(later)}")
for name, g in (("±2 ч от вершины", near), ("раньше вершины", before), ("позже вершины", later)):
    if not g: continue
    a24 = [x["after"][24] for x in g if x["after"][24] is not None]
    dn = sum(1 for v in a24 if v < 0)
    up = [x["up24"] for x in g if x["up24"] is not None]
    print(f"  {name}: n={len(g)} · через 24 ч после бара ниже — {dn}/{len(a24)} (медиана {st.median(a24) if a24 else 0:+.1f}%) · "
          f"дотянула выше на ≥+10% за 24 ч — {sum(1 for v in up if v >= 10)}/{len(up)} · ×медиана {st.median(x['ratio'] for x in g):.1f} · доля покупателей {st.median(x['buy'] for x in g):.0f}%")
# сдвиг «раньше»: на сколько часов раньше вершины стоит макс. объём — распределение
sh = sorted(x["shift"] for x in before)
if sh: print(f"  когда раньше: медиана {st.median(sh):+.1f} ч, диапазон {sh[0]:+.1f}…{sh[-1]:+.1f} ч")
