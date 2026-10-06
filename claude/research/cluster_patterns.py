#!/usr/bin/env python3
"""ПАТТЕРНЫ КЛАСТЕРОВ ВЛАДЕЛЬЦА — НАСКОЛЬКО РАБОЧИЕ (07.10, владелец показал схему: «сдерживающий, толкающий, поддерживающий, проталкивающий»,
«у меня паттерны даже есть», «не знаю насколько рабочие»). По каждой закрытой свече: направление, где в свече лежит максимальный объём (POC: низ / середина /
верх) и кто на этом уровне преобладал (покупки или продажи по рынку). Дальше — что сделала цена за следующую свечу и за четыре, в сторону самой свечи.
Данные — кластеры с графика владельца (tvd/*_fp<TF>.json). Чтение схемы владельца: у растущей свечи объём вверху — «сдерживающий» (ждём разворот),
внизу — «толкающий / поддерживающий» (ждём продолжение), в середине — «проталкивающий» (продолжение); у падающей — зеркально.
    .venv/bin/python claude/research/cluster_patterns.py [TF=30] [крупные]"""
import json, glob, sys, statistics as st, collections
from pathlib import Path
D = Path(__file__).parent / "tvd"; TF = sys.argv[1] if len(sys.argv) > 1 else "30"; BIG = "крупные" in sys.argv
R = collections.defaultdict(list); coins = 0
for p in sorted(glob.glob(str(D / f"*_fp{TF}.json"))):
    d = json.load(open(p)); b = d["bars"]; fp = {x["i"]: x for x in d["fp"]}; n = len(b); coins += 1
    rngs = sorted((x[2] - x[3]) / x[4] for x in b if x[4]); med = rngs[len(rngs) // 2] if rngs else 0
    for i in range(1, n - 5):
        o, h, l, c = b[i][1:5]; rng = h - l
        if rng <= 0 or c == o or i not in fp or not fp[i]["levels"]: continue
        if BIG and rng / c < 2 * med: continue
        sd = 1 if c > o else -1
        pos = (fp[i]["poc"] - l) / rng; pos = pos if sd == 1 else 1 - pos            # 0 — у начала хода свечи, 1 — у её конца
        third = "у конца хода" if pos > 2 / 3 else "у начала хода" if pos < 1 / 3 else "в середине"
        lv = max(fp[i]["levels"], key=lambda x: x[1] + x[2]); dom = "за ход" if (lv[1] - lv[2]) * sd > 0 else "против хода"
        R[(third, dom)].append(((b[i + 1][4] / c - 1) * sd * 100, (b[i + 4][4] / c - 1) * sd * 100, Path(p).name))
print(f"монет {coins} · свечей {sum(len(v) for v in R.values())} · таймфрейм {TF} мин" + (" · только крупные свечи (размах от двух медиан)" if BIG else ""))
print("где максимальный объём · кто преобладал на этом уровне → сделок · следующая свеча в ту же сторону % (средний ход %) · через 4 свечи в ту же сторону % (средний ход %)")
for k in sorted(R, key=lambda k: ("у начала хода", "в середине", "у конца хода").index(k[0]) * 2 + (k[1] == "против хода")):
    v = R[k]; a = [x[0] for x in v]; c4 = [x[1] for x in v]
    print(f"  объём {k[0]:14s} · {k[1]:11s} → {len(v):5d} · {100 * sum(1 for x in a if x > 0) / len(v):4.1f}% ({st.mean(a):+.2f}) · {100 * sum(1 for x in c4 if x > 0) / len(v):4.1f}% ({st.mean(c4):+.2f})")
allv = [x for v in R.values() for x in v]
print(f"  все свечи вместе → {len(allv)} · {100 * sum(1 for x in allv if x[0] > 0) / len(allv):.1f}% ({st.mean(x[0] for x in allv):+.2f}) · {100 * sum(1 for x in allv if x[1] > 0) / len(allv):.1f}% ({st.mean(x[1] for x in allv):+.2f})")
