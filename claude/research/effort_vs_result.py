#!/usr/bin/env python3
"""УСИЛИЕ ПРОТИВ РЕЗУЛЬТАТА НА ПОЛКЕ — ТО, ЧТО ВЛАДЕЛЕЦ УВИДЕЛ НА MOVR (07.10: «вот кластера, это пик последнего роста movr», «я попросил разобраться и написал
что видел»). На вершине MOVR первый заход вверх взял +980 тыс. чистых покупок по рынку и дал +5 %, второй взял +1,57 млн и упёрся в тот же потолок — дальше обвал.
Здесь это ищется по всем монетам: цена ходит волнами (разворот от 1,5 % на 5 мин, 2 % на 10, 2,5 % на 15); берутся два соседних захода вверх к одной полке
(вершина второго не выше первой больше чем на 1,5 % и не ниже больше чем на 1,5 %). Цена захода — чистые покупки по рынку (дельта кластеров) на 1 % подъёма.
Случай «платят больше — потолок тот же»: цена второго захода выше первой в 1,5 раза и больше. Для сравнения — «платят меньше» и зеркало у дна.
Вход проверки — когда разворот от второй вершины подтверждён; дальше: сколько прошла цена вниз за 1 и 3 часа и пробила ли вторую вершину раньше.
    .venv/bin/python claude/research/effort_vs_result.py 5|10|15"""
import json, glob, sys, statistics as st, collections, datetime as dt
from pathlib import Path
D = Path(__file__).parent / "tvd"; TF = sys.argv[1]; U = dt.timezone.utc
REV = {"5": 0.015, "10": 0.02, "15": 0.025}[TF]; H1, H3 = 60 // int(TF), 180 // int(TF)
f = lambda t: dt.datetime.fromtimestamp(t, U).strftime("%d.%m %H:%M")


def legs(b, dl):
    """волны: [(направление, i_начала, i_конца, цена_начала, цена_конца, дельта, i_подтверждения)]"""
    out = []; d = 0; ext_i = 0; ext = b[0][4]; start_i = 0; start = b[0][4]
    hi_i = lo_i = 0
    for i in range(1, len(b)):
        if b[i][2] > b[hi_i][2]: hi_i = i
        if b[i][3] < b[lo_i][3]: lo_i = i
        if d >= 0 and b[i][4] <= b[hi_i][2] * (1 - REV) and hi_i > start_i:           # разворот вниз подтверждён: закончилась волна вверх
            if d == 1 or (d == 0 and b[hi_i][2] / b[start_i][3] - 1 >= REV):
                out.append((1, start_i, hi_i, b[start_i][3], b[hi_i][2], sum(dl[start_i:hi_i + 1]), i))
            d = -1; start_i = hi_i; lo_i = i
        elif d <= 0 and b[i][4] >= b[lo_i][3] * (1 + REV) and lo_i > start_i:
            if d == -1 or (d == 0 and 1 - b[lo_i][3] / b[start_i][2] >= REV):
                out.append((-1, start_i, lo_i, b[start_i][2], b[lo_i][3], sum(dl[start_i:lo_i + 1]), i))
            d = 1; start_i = lo_i; hi_i = i
    return out


G = collections.defaultdict(list)
for p in sorted(glob.glob(str(D / f"*_fp{TF}.json"))):
    d = json.load(open(p)); b = d["bars"]; fp = {x["i"]: x for x in d["fp"]}; n = len(b); sym = Path(p).name.split("_fp")[0]
    if n < 60: continue
    dl = [(fp[i]["buy"] - fp[i]["sell"]) if i in fp else 0.0 for i in range(n)]
    L = legs(b, dl)
    for sd in (1, -1):
        same = [x for x in L if x[0] == sd]
        for a, z in zip(same, same[1:]):
            m1 = abs(a[4] / a[3] - 1) * 100; m2 = abs(z[4] / z[3] - 1) * 100
            if abs(z[4] / a[4] - 1) > 0.015 or m1 <= 0 or m2 <= 0: continue           # не одна полка
            e1, e2 = a[5] * sd, z[5] * sd                                               # усилие в сторону захода
            if e1 <= 0 or e2 <= 0: kind = "заход без чистого усилия"
            else:
                c1, c2 = e1 / m1, e2 / m2
                kind = "платят больше, край тот же" if c2 >= 1.5 * c1 else "платят меньше" if c2 <= c1 / 1.5 else "платят столько же"
            k = z[6]                                                                    # свеча, на которой разворот подтверждён
            if k + H3 >= n: continue
            e = b[k][4]; stop = z[4]
            broke = next((j for j in range(k + 1, k + H3 + 1) if (b[j][2] > stop if sd == 1 else b[j][3] < stop)), None)
            r1 = (1 - b[k + H1][4] / e) * sd * 100; r3 = (1 - b[k + H3][4] / e) * sd * 100
            G[(sd, kind)].append(dict(sym=sym, t=b[k][0], r1=r1, r3=r3, broke=broke is not None, stop=abs(stop / e - 1) * 100, day=dt.datetime.fromtimestamp(b[k][0], U).strftime("%d.%m")))
print(f"таймфрейм {TF} мин · разворот волны {REV * 100:g}% · ход считается в сторону ОТ полки (плюс — цена ушла от края, как на MOVR)")
for sd, nm in ((1, "ДВА ЗАХОДА ВВЕРХ К ОДНОЙ ПОЛКЕ → ждём вниз"), (-1, "ДВА ЗАХОДА ВНИЗ К ОДНОМУ ДНУ → ждём вверх")):
    print(nm)
    for kind in ("платят больше, край тот же", "платят столько же", "платят меньше", "заход без чистого усилия"):
        v = G.get((sd, kind)) or []
        if len(v) < 15: print(f"  {kind}: мало случаев ({len(v)})"); continue
        days = collections.defaultdict(list)
        for x in v: days[x["day"]].append(x["r3"])
        print(f"  {kind:28s}: {len(v):4d} на {len({x['sym'] for x in v})} монетах · за 1 ч от полки {100 * sum(1 for x in v if x['r1'] > 0) / len(v):.0f}% ({st.mean(x['r1'] for x in v):+.2f}%) · за 3 ч {100 * sum(1 for x in v if x['r3'] > 0) / len(v):.0f}% ({st.mean(x['r3'] for x in v):+.2f}%) · край пробит за 3 ч у {100 * sum(1 for x in v if x['broke']) / len(v):.0f}% · до края в среднем {st.mean(x['stop'] for x in v):.1f}% · дней в плюс {sum(1 for q in days.values() if st.mean(q) > 0)} из {len(days)}")
