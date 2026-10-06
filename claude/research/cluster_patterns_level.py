#!/usr/bin/env python3
"""ПАТТЕРНЫ КЛАСТЕРОВ ВЛАДЕЛЬЦА У УРОВНЯ (07.10: «паттерны для 5-10 минут макс 15», на схеме паттерн стоит у уровня). Берутся только свечи, которые
обновляют максимум (растущая) или минимум (падающая) последних 24 свечей — то есть пришли к краю. Класс свечи: где лежит её максимальный объём
(у начала хода / в середине / у конца) и кто преобладал на этом уровне. Дальше — куда цена ушла за 4 и 12 свечей, считая в сторону самой свечи
(плюс — продолжение, минус — разворот), и на скольких днях из имеющихся ход был в одну сторону.
Чтение схемы: объём у конца хода — «сдерживающий» (ждём разворот); у начала — «толкающий»/«поддерживающий» (ждём продолжение); в середине — «проталкивающий» (продолжение).
    .venv/bin/python claude/research/cluster_patterns_level.py 5|10|15"""
import json, glob, sys, statistics as st, collections, datetime as dt
from pathlib import Path
D = Path(__file__).parent / "tvd"; TF = sys.argv[1]; U = dt.timezone.utc
R = collections.defaultdict(list); coins = 0
for p in sorted(glob.glob(str(D / f"*_fp{TF}.json"))):
    d = json.load(open(p)); b = d["bars"]; fp = {x["i"]: x for x in d["fp"]}; n = len(b); coins += 1
    for i in range(24, n - 13):
        o, h, l, c = b[i][1:5]; rng = h - l
        if rng <= 0 or c == o or i not in fp or not fp[i]["levels"]: continue
        sd = 1 if c > o else -1
        if sd == 1 and h <= max(x[2] for x in b[i - 24:i]): continue
        if sd == -1 and l >= min(x[3] for x in b[i - 24:i]): continue
        pos = (fp[i]["poc"] - l) / rng; pos = pos if sd == 1 else 1 - pos
        third = "у конца хода (сдерживающий)" if pos > 2 / 3 else "у начала хода (толкающий)" if pos < 1 / 3 else "в середине (проталкивающий)"
        lv = max(fp[i]["levels"], key=lambda x: x[1] + x[2]); dom = "за ход" if (lv[1] - lv[2]) * sd > 0 else "против хода"
        R[(("рост" if sd == 1 else "падение"), third, dom)].append(((b[i + 4][4] / c - 1) * sd * 100, (b[i + 12][4] / c - 1) * sd * 100, dt.datetime.fromtimestamp(b[i][0], U).strftime("%d.%m")))
tot = [x for v in R.values() for x in v]
print(f"таймфрейм {TF} мин · монет {coins} · свечей у края {len(tot)} · в среднем по всем: продолжение через 4 свечи {100 * sum(1 for x in tot if x[0] > 0) / len(tot):.1f}% ({st.mean(x[0] for x in tot):+.2f}%), через 12 — {100 * sum(1 for x in tot if x[1] > 0) / len(tot):.1f}% ({st.mean(x[1] for x in tot):+.2f}%)")
order = ["у начала хода (толкающий)", "в середине (проталкивающий)", "у конца хода (сдерживающий)"]
for dr in ("рост", "падение"):
    print(f"  свеча — {dr} с новым {'максимумом' if dr == 'рост' else 'минимумом'}:")
    for th in order:
        for dom in ("за ход", "против хода"):
            v = R.get((dr, th, dom)) or []
            if len(v) < 40: continue
            days = collections.defaultdict(list)
            for x in v: days[x[2]].append(x[1])
            print(f"    объём {th:28s} · {dom:11s}: {len(v):5d} · через 4: {100 * sum(1 for x in v if x[0] > 0) / len(v):4.1f}% ({st.mean(x[0] for x in v):+.2f}%) · через 12: {100 * sum(1 for x in v if x[1] > 0) / len(v):4.1f}% ({st.mean(x[1] for x in v):+.2f}%) · дней с продолжением {sum(1 for q in days.values() if st.mean(q) > 0)} из {len(days)}")
