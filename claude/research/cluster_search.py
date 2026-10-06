#!/usr/bin/env python3
"""ПОИСК НЕСЛУЧАЙНОГО В КЛАСТЕРАХ (07.10, владелец: «вот и смотри и ищи закономерности», «хоть всю ночь занимай», «главное результат»).
Не свечные признаки, а то, чего на свече нет: кто бил по рынку и где он остался. По каждой закрытой 30-минутной свече считаются:
  дельта — чистые покупки по рынку, доля объёма; поглощение — дельта против хода свечи (били в одну сторону, свеча закрылась в другую);
  застрявшие покупатели — доля покупок по рынку за последние 4 часа, сделанных ВЫШЕ текущей цены (они в минусе); застрявшие продавцы — доля продаж НИЖЕ цены.
Для каждого признака — крайние десятые доли всех свечей и что цена сделала дальше за 2 и 8 часов; отдельно по дням (сколько дней признак дал ход в свою сторону).
Данные — кластеры с графика владельца (tvd/*_fp30.json, ~6 суток, все монеты пульса).
    .venv/bin/python claude/research/cluster_search.py"""
import json, glob, statistics as st, collections, datetime as dt
from pathlib import Path
D = Path(__file__).parent / "tvd"; U = dt.timezone.utc
rows = []
for p in sorted(glob.glob(str(D / "*_fp30.json"))):
    d = json.load(open(p)); b = d["bars"]; fp = {x["i"]: x for x in d["fp"]}; n = len(b)
    for i in range(96, n - 17):
        if i not in fp or not b[i][5]: continue
        o, h, l, c, v = b[i][1:6]
        dl = (fp[i]["buy"] - fp[i]["sell"]) / v
        body = (c / o - 1)
        tb = ts = ab = bl = 0.0
        for j in range(i - 7, i + 1):
            if j not in fp: continue
            for pr, bu, se in fp[j]["levels"]:
                ab += bu; bl += se
                if pr > c: tb += bu
                if pr < c: ts += se
        hi48 = max(x[2] for x in b[i - 96:i]); lo48 = min(x[3] for x in b[i - 96:i])
        rows.append(dict(day=dt.datetime.fromtimestamp(b[i][0], U).strftime("%d.%m"), dl=dl, absorb=-dl * (1 if body > 0 else -1 if body < 0 else 0), up=body > 0,
                         tb=tb / ab if ab else None, ts=ts / bl if bl else None, r4=(b[i + 4][4] / c - 1) * 100, r16=(b[i + 16][4] / c - 1) * 100,
                         pos48=(c - lo48) / (hi48 - lo48) if hi48 > lo48 else .5, run48=hi48 / lo48))
print(f"свечей {len(rows)} · базовый ход: за 2 ч {st.mean(r['r4'] for r in rows):+.2f}%, за 8 ч {st.mean(r['r16'] for r in rows):+.2f}%, выше через 8 ч у {100 * sum(1 for r in rows if r['r16'] > 0) / len(rows):.0f}%")
def show(name, g, side):
    if len(g) < 30: print(f"  {name}: мало случаев ({len(g)})"); return
    by = collections.defaultdict(list)
    for r in g: by[r["day"]].append(r["r16"] * side)
    print(f"  {name}: {len(g)} · за 2 ч {st.mean(r['r4'] for r in g):+.2f}% · за 8 ч {st.mean(r['r16'] for r in g):+.2f}% · в ожидаемую сторону через 8 ч {100 * sum(1 for r in g if r['r16'] * side > 0) / len(g):.0f}% · дней в ожидаемую сторону {sum(1 for v in by.values() if st.mean(v) > 0)} из {len(by)}")
def dec(key, lo_name, hi_name, lo_side, hi_side, sub=None, tag=""):
    g = [r for r in rows if r.get(key) is not None and (sub is None or sub(r))]
    if len(g) < 300: print(f"  {tag}{key}: мало данных"); return
    v = sorted(r[key] for r in g); a, z = v[len(v) // 10], v[9 * len(v) // 10]
    show(f"{tag}{lo_name} (нижняя десятая, до {a:.2f})", [r for r in g if r[key] <= a], lo_side)
    show(f"{tag}{hi_name} (верхняя десятая, от {z:.2f})", [r for r in g if r[key] >= z], hi_side)
print("\nВСЕ СВЕЧИ")
dec("dl", "сильные продажи по рынку", "сильные покупки по рынку", -1, 1)
dec("absorb", "дельта по ходу свечи", "поглощение: дельта против хода свечи", 1, 1)
show("поглощение вверх: били продажами (дельта в нижней десятой), свеча закрылась выше открытия", [r for r in rows if r["up"] and r["dl"] <= sorted(x["dl"] for x in rows)[len(rows) // 10]], 1)
show("поглощение вниз: били покупками (дельта в верхней десятой), свеча закрылась ниже открытия", [r for r in rows if not r["up"] and r["dl"] >= sorted(x["dl"] for x in rows)[9 * len(rows) // 10]], -1)
dec("tb", "покупателей выше цены почти нет", "застрявшие покупатели: покупки последних 4 ч в основном выше цены", 1, -1)
dec("ts", "продавцов ниже цены почти нет", "застрявшие продавцы: продажи последних 4 ч в основном ниже цены", -1, 1)
print("\nТОЛЬКО ПОСЛЕ РОСТА (размах за 48 ч от ×1,3) И ЦЕНА В ВЕРХНЕЙ ТРЕТИ ЭТОГО РАЗМАХА")
S = lambda r: r["run48"] >= 1.3 and r["pos48"] >= 2 / 3
dec("dl", "сильные продажи по рынку", "сильные покупки по рынку", -1, 1, S, "у верха: ")
dec("tb", "покупателей выше почти нет", "застрявшие покупатели", 1, -1, S, "у верха: ")
dec("ts", "продавцов ниже почти нет", "застрявшие продавцы", -1, 1, S, "у верха: ")
print("\nТОЛЬКО ПОСЛЕ ПАДЕНИЯ (размах за 48 ч от ×1,3) И ЦЕНА В НИЖНЕЙ ТРЕТИ")
S2 = lambda r: r["run48"] >= 1.3 and r["pos48"] <= 1 / 3
dec("dl", "сильные продажи по рынку", "сильные покупки по рынку", -1, 1, S2, "у низа: ")
dec("tb", "покупателей выше почти нет", "застрявшие покупатели", 1, -1, S2, "у низа: ")
dec("ts", "продавцов ниже почти нет", "застрявшие продавцы", -1, 1, S2, "у низа: ")
