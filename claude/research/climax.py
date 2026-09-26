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
JUMP = 40.0   # ход за 48 ч, при котором монета «в ходу» (PUMP_JUMP_PCT проекта)
print("ПРОСПЕКТИВНО: сигнал = бар, чей объём в долларах — максимум за последние 48 ч, при закрытии ≥ +40% к закрытию 48 ч назад (монета «в ходу»).")
print("Окно поиска: вершина − 72 ч … вершина + 24 ч. Первый сигнал в окне и все сигналы отдельно.\n")
print(f"{'монета':<9}{'ход1':>6} {'вершина':<12}| сигналов | ПЕРВЫЙ: сдвиг к вершине ч · ×медиана48 · покуп% | после: 6ч · 12ч · 24ч · макс↑ до вершины")
res, allsig = [], []
for r in rows:
    try:
        tp = loc(r["peak1"])
    except Exception:
        continue
    try:
        k = kl(r["sym"], tp - 5 * 24 * H, tp + 48 * H)
    except Exception as e:
        print(r["sym"], "нет данных:", e); continue
    by = {x[0]: i for i, x in enumerate(k)}
    sigs = []
    for i, x in enumerate(k):
        if not (tp - 72 * H <= x[0] <= tp + 24 * H): continue
        j = by.get(x[0] - 48 * H)
        if j is None: continue
        if x[3] / k[j][3] - 1 < JUMP / 100: continue
        prev = k[j:i]
        if x[4] < max(p[4] for p in prev): continue
        med = st.median(p[4] for p in prev) or 1
        after = {dt: ((k[i + 2 * dt][3] / x[3] - 1) * 100 if i + 2 * dt < len(k) else None) for dt in (6, 12, 24)}
        # максимум закрытия дальше в окне (до вершины + 24 ч) — сколько ещё дал ход
        fut = [p[3] for p in k[i + 1:] if p[0] <= tp + 24 * H]
        more = (max(fut) / x[3] - 1) * 100 if fut else 0.0
        sofar = (x[3] / float(r["start_px"]) - 1) * 100 if r.get("start_px") else None
        bar = (x[3] / k[i - 1][3] - 1) * 100 if i > 0 else 0.0   # сама свеча рекорда: вертикаль или нет
        sigs.append(dict(t=x[0], shift=(x[0] - tp) / H, ratio=x[4] / med, buy=x[5] / x[4] * 100 if x[4] else 50, after=after, more=more, sofar=sofar, bar=bar))
    if not sigs: 
        print(f"{r['sym']:<9}{r['move1_pct']:>5}% {r['peak1']:<12}| 0"); continue
    s0 = sigs[0]
    f = lambda v: "  —  " if v is None else f"{v:+5.1f}"
    print(f"{r['sym']:<9}{r['move1_pct']:>5}% {r['peak1']:<12}| {len(sigs):3d}      | {s0['shift']:+6.1f} · ×{s0['ratio']:5.1f} · {s0['buy']:3.0f}% | {f(s0['after'][6])} · {f(s0['after'][12])} · {f(s0['after'][24])} · {f(s0['more'])}")
    res.append(dict(sym=r["sym"], first=s0, n=len(sigs))); allsig += sigs
    time.sleep(0.15)
n = len(res)
print(f"\nСВОДКА: ходов с сигналом {n}, всего сигналов {len(allsig)}")
def grp(name, g):
    if not g: return
    a24 = [x["after"][24] for x in g if x["after"][24] is not None]; a6 = [x["after"][6] for x in g if x["after"][6] is not None]
    more = [x["more"] for x in g]
    print(f"  {name}: n={len(g)} · через 6 ч ниже {sum(1 for v in a6 if v < 0)}/{len(a6)} (медиана {st.median(a6) if a6 else 0:+.1f}%) · через 24 ч ниже {sum(1 for v in a24 if v < 0)}/{len(a24)} (медиана {st.median(a24) if a24 else 0:+.1f}%)"
          f" · ход дал ещё ≥+10% до вершины — {sum(1 for v in more if v >= 10)}/{len(more)} · ≥+30% — {sum(1 for v in more if v >= 30)}/{len(more)} · медиана ещё {st.median(more):+.1f}%")
firsts = [x["first"] for x in res]
grp("ПЕРВЫЙ сигнал хода", firsts)
grp("  первый сигнал в ±2 ч от вершины", [x for x in firsts if abs(x["shift"]) <= 2])
grp("  первый сигнал раньше вершины (>2 ч)", [x for x in firsts if x["shift"] < -2])
grp("ВСЕ сигналы", allsig)
grp("  все сигналы: объём ≥ ×20 к медиане 48 ч", [x for x in allsig if x["ratio"] >= 20])
grp("  все сигналы: объём < ×20", [x for x in allsig if x["ratio"] < 20])
grp("  все сигналы: покупатели-агрессоры ≥ 55%", [x for x in allsig if x["buy"] >= 55])
grp("  все сигналы: покупатели ≤ 45%", [x for x in allsig if x["buy"] <= 45])
print("  РАЗРЕЗ ПО ПРОЙДЕННОМУ ХОДУ (закрытие бара сигнала к старту хода из anatomy):")
grp("  все сигналы: ход до бара < +100%", [x for x in allsig if x["sofar"] is not None and x["sofar"] < 100])
grp("  все сигналы: ход до бара +100…+200%", [x for x in allsig if x["sofar"] is not None and 100 <= x["sofar"] < 200])
grp("  все сигналы: ход до бара ≥ +200%", [x for x in allsig if x["sofar"] is not None and x["sofar"] >= 200])
lasts = [x for x in allsig if x["shift"] > -6 and x["shift"] <= 2]
grp("  сигналы за 6 ч до вершины (±2 ч) — что было бы видно: ", lasts)
print("  РАЗРЕЗ ПО САМОЙ СВЕЧЕ РЕКОРДА (кадр DYDX: вертикаль на рекордном обороте в далеко зашедшем тренде):")
grp("  все сигналы: свеча рекорда — вертикаль (≥ +15% за получасовку)", [x for x in allsig if x["bar"] >= 15])
grp("  все сигналы: свеча рекорда обычная (< +15%)", [x for x in allsig if x["bar"] < 15])
grp("  вертикаль и ход до неё ≥ +100% (далеко зашедший тренд)", [x for x in allsig if x["bar"] >= 15 and x["sofar"] is not None and x["sofar"] >= 100])
grp("  вертикаль и ход до неё < +100%", [x for x in allsig if x["bar"] >= 15 and x["sofar"] is not None and x["sofar"] < 100])
grp("  обычная свеча и ход до неё ≥ +100%", [x for x in allsig if x["bar"] < 15 and x["sofar"] is not None and x["sofar"] >= 100])
near = sum(1 for x in firsts if abs(x["shift"]) <= 2)
print(f"  первый сигнал попадает в ±2 ч от вершины: {near}/{n}; медиана сдвига первого сигнала {st.median(x['shift'] for x in firsts):+.1f} ч")
