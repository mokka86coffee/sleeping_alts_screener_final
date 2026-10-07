#!/usr/bin/env python3
"""ДИСТАНЦИЯ ТЕКУЩЕГО РЫНКА (07.10, владелец: «эти 14 случаев и есть показатель текущего рынка», «если я бегаю по утрам неделю, буду пробегать максимум примерно
одно расстояние, через неделю оно будет больше по тем или иным причинам», «как ты хочешь замерять рынок что было год назад — там деньги несли все, сейчас не несут»).
Только свежее окно: кластерные 30-минутки с графика владельца за ~6 суток по всем монетам (tv_footprint.py 30 …). Памп — подъём от 30 % не дольше двух суток.
Считается, сколько пампы проходят сейчас, за сколько, сколько отдают после вершины — и где на этой дистанции стоят монеты, которые бегут прямо сейчас.
Старые данные сюда не подмешиваются; пересчитывать раз в день-два.
    .venv/bin/python claude/research/market_distance.py"""
import json, glob, statistics as st, datetime as dt
from pathlib import Path
D = Path(__file__).parent / "tvd"; U = dt.timezone.utc
f = lambda t: dt.datetime.fromtimestamp(t, U).strftime("%d.%m %H:%M")
done, live = [], []
for p in sorted(glob.glob(str(D / "*_fp30.json"))):
    d = json.load(open(p)); b = d["bars"]; n = len(b); sym = Path(p).name.replace("_fp30.json", "")
    if n < 120: continue
    T = max(range(n), key=lambda i: b[i][2]); S = min(range(max(0, T - 96), T + 1), key=lambda i: b[i][3])
    if T - S < 2 or b[T][2] / b[S][3] < 1.3: continue
    hi, lo = b[T][2], b[S][3]; age = n - 1 - T
    row = dict(sym=sym, x=hi / lo, h=(T - S) / 2, top=b[T][0], age_h=age / 2, now=(b[-1][4] / hi - 1) * 100, back=(hi - b[-1][4]) / (hi - lo) * 100,
               a8=(b[T + 16][4] / hi - 1) * 100 if T + 16 < n else None, wd=dt.datetime.fromtimestamp(b[T][0], U).weekday(), hour=dt.datetime.fromtimestamp(b[T][0], U).hour)
    (done if age >= 16 else live).append(row)
if not done: raise SystemExit("в окне нет законченных пампов")
xs = sorted(r["x"] for r in done); hs = sorted(r["h"] for r in done); q = lambda v, p: v[min(len(v) - 1, int(len(v) * p))]
a8 = [r["a8"] for r in done if r["a8"] is not None]; bk = [r["back"] for r in done]
t0 = min(json.load(open(p))["bars"][0][0] for p in glob.glob(str(D / "*_fp30.json"))[:20])
print(f"окно с {f(t0)} UTC · законченных пампов (вершине больше 8 ч): {len(done)} · ещё бегут: {len(live)}")
print(f"дистанция: середина ×{st.median(xs):.2f}, обычно от ×{q(xs, .25):.2f} до ×{q(xs, .75):.2f}, самый длинный ×{xs[-1]:.2f} · дальше ×3 ушли {sum(1 for x in xs if x >= 3)} из {len(xs)}")
print(f"время подъёма: середина {st.median(hs):.0f} ч, обычно {q(hs, .25):.0f}–{q(hs, .75):.0f} ч")
print(f"после вершины: через 8 ч ниже у {sum(1 for x in a8 if x < 0)} из {len(a8)}, середина {st.median(a8):+.0f}% · отдано подъёма к этой минуте: середина {st.median(bk):.0f}%, удержались (отдали меньше трети) {sum(1 for x in bk if x < 33)} из {len(bk)}")
print(f"вершины в азиатские часы (21–07 UTC): {sum(1 for r in done if r['hour'] >= 21 or r['hour'] < 7)} из {len(done)} · в выходные: {sum(1 for r in done if r['wd'] >= 5)} из {len(done)}")
print("законченные: " + " · ".join(f"{r['sym']} ×{r['x']:.2f}/{r['h']:.0f}ч/{r['now']:+.0f}%" for r in sorted(done, key=lambda r: -r["x"])))
med = st.median(xs)
print("\nбегут сейчас (вершина моложе 8 ч): монета · пройдено · часов подъёма · доля недельной дистанции · от вершины")
for r in sorted(live, key=lambda r: -r["x"]):
    print(f"  {r['sym']:9s} ×{r['x']:.2f} · {r['h']:.0f} ч · {100 * (r['x'] - 1) / (med - 1):.0f}% · {r['now']:+.0f}%")
