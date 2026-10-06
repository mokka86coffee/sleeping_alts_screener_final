#!/usr/bin/env python3
"""ЧТО БЫЛО ОБЩЕГО У МОНЕТ, ЧТО ПОШЛИ (06.10, владелец: «запиши это как главный признак для звёзд», «проверь по остальным за последние 3 недели»,
«что было общего у всех, что пошли — SOPH, LSK и т. д.»; показал RLC 4D и GALA 1M: цена у дна, интерес на максимуме — «вот что должно было очень давно пойти»).
Список пошедших — по дневным свечам BingX (открытые данные, файл из scratchpad). Картина до хода и на старте — по данным TradingView владельца
(claude/research/tvd: дневные бары и интерес в монетах, часовой фандинг; сняты 03.10 — почасового интереса там нет). С Binance ничего не запрашивается. Время — UTC.
«Пошла» — максимум дня к базе (минимум из открытия этого дня и минимумов двух дней до него) ×1,5 и больше; старт — день базы; картина «до» — по дням строго раньше старта.
    .venv/bin/python claude/research/movers_sign.py <bingx_1d.json>"""
import json, sys, os, statistics as st, datetime as dt
from pathlib import Path
U = dt.timezone.utc
TVD = Path(__file__).parent / "tvd"
D = 86400
day = lambda y, m, d: dt.datetime(y, m, d, tzinfo=U).timestamp()
fd = lambda t: dt.datetime.fromtimestamp(t, U).strftime("%d.%m")
WEEKS = [day(2026, 9, 1), day(2026, 9, 8), day(2026, 9, 15), day(2026, 9, 22), day(2026, 9, 29)]   # пять недель (SOPH пошла 07–08.09); последняя — до 06.10
bx = json.load(open(sys.argv[1]))


def tv(sym, res):
    try:
        j = json.load(open(TVD / f"{sym}USDT.P_{res}.json"))
    except (OSError, ValueError):
        return None
    oi = {x[0]: x[1] for x in j.get("oi", []) if x[1]}
    fu = {x[0]: x[1] for x in j.get("fund", []) if x[1] is not None}
    return [(b[0], b[1], b[2], b[3], b[4], oi.get(b[0]), fu.get(b[0])) for b in j["bars"]]


def rise_in(k, a, b):
    """лучший ход со стартом базы в [a, b): (раз, день вершины, день базы)"""
    best = (0, None, None)
    for j in range(len(k)):
        c = [(k[j][1], k[j][0])] + [(x[3], x[0]) for x in k[max(0, j - 2):j]]
        base, tb = min(c)
        if not (a <= tb < b): continue
        r = k[j][2] / base
        if r > best[0]: best = (r, k[j][0], tb)
    return best


def feats(d1, t):
    """картина по дневным данным TV на конец дня перед t; 180 дней и вся снятая история (до ~650 дней)"""
    h = [x for x in d1 if x[0] < t]
    if len(h) < 120 or t - h[-1][0] > 4 * D or not h[-1][5]: return None
    c, oi = h[-1][4], h[-1][5]
    o = {}
    for tag, w in (("", h[-180:]), ("_all", h)):
        lo, hi = min(x[3] for x in w), max(x[2] for x in w)
        ois = [x[5] for x in w if x[5]]
        if len(ois) < 60: return None
        o["pos" + tag] = (c - lo) / (hi - lo) if hi > lo else 0.5
        o["above_low" + tag] = c / lo
        o["oi_max" + tag] = oi / max(ois)
        o["oi_min" + tag] = oi / min(ois)
    o30 = next((x[5] for x in reversed(h[:-30]) if x[5]), None)
    f7 = [x[6] for x in h[-7:] if x[6] is not None]
    r14 = h[-14:]
    o5 = next((x[5] for x in reversed(h[:-5]) if x[5]), None)
    o10 = next((x[5] for x in reversed(h[:-10]) if x[5]), None)
    o.update(oi5=oi / o5 if o5 else None, oi10=oi / o10 if o10 else None, px5=c / h[-6][4], oi30=oi / o30 if o30 else None, f7=st.mean(f7) if f7 else None, flat14=max(x[2] for x in r14) / min(x[3] for x in r14), px30=c / h[-31][4])
    return o


NAMES = [("pos", "место цены в диапазоне 180 дн (0 — дно, 1 — верх)"), ("pos_all", "место цены в диапазоне всей истории"),
         ("above_low", "цена к минимуму 180 дн, раз"), ("above_low_all", "цена к минимуму всей истории, раз"),
         ("oi_max", "интерес в монетах к своему максимуму 180 дн"), ("oi_max_all", "интерес к своему максимуму всей истории"),
         ("oi_min", "интерес к своему минимуму 180 дн, раз"), ("oi5", "интерес к тому, что был 5 дн назад, раз"),
         ("oi10", "интерес к тому, что был 10 дн назад, раз"), ("px5", "цена к цене 5 дн назад, раз"), ("oi30", "интерес к тому, что был 30 дн назад, раз"),
         ("f7", "фандинг, среднее за 7 дн, %"), ("flat14", "размах цены за 14 дн до старта, раз"), ("px30", "цена к цене 30 дн назад, раз")]
rows, d1s = [], {}
for s, k in bx.items():
    d1 = tv(s, "1D")
    if not d1: continue
    d1s[s] = d1
    for i, w in enumerate(WEEKS):
        r, tt, tb = rise_in(k, w, w + 7 * D)
        f = feats(d1, tb if (r >= 1.5 and tb) else w)                  # пошедшим — на день перед базой, остальным — на начало недели
        if f: rows.append((s, i, f, r, tt, tb))
print(f"монет-недель: {len(rows)} | монет: {len({x[0] for x in rows})} | пошло ×1,5+: {sum(1 for x in rows if x[3] >= 1.5)} | ×2+: {sum(1 for x in rows if x[3] >= 2)}")
q = lambda v, p: sorted(v)[min(len(v) - 1, int(len(v) * p))]
print("\nМЕДИАНА (четверть … три четверти): пошедшие ×2+ | пошедшие ×1,5–2 | остальные")
for key, nm in NAMES:
    out = []
    for cond in (lambda r: r >= 2, lambda r: 1.5 <= r < 2, lambda r: r < 1.5):
        v = [x[2][key] for x in rows if cond(x[3]) and x[2][key] is not None]
        out.append(f"{st.median(v):.2f} ({q(v, .25):.2f}…{q(v, .75):.2f}) n={len(v)}")
    print(f"- {nm}: " + " | ".join(out))
print("\nДОЛЯ ПОШЕДШИХ ПО ТРЕТЯМ ПРИЗНАКА (все монеты-недели — три равные части): пошло ×1,5+ и ×2+ из числа в трети; в скобках ×1,5+ по неделям")
for key, nm in NAMES:
    v = sorted(x[2][key] for x in rows if x[2][key] is not None)
    a, b = v[len(v) // 3], v[2 * len(v) // 3]
    line = []
    for nm3, cond in (("низ", lambda z: z < a), ("середина", lambda z: a <= z < b), ("верх", lambda z: z >= b)):
        g = [x for x in rows if x[2][key] is not None and cond(x[2][key])]
        wk = "/".join(str(sum(1 for x in g if x[1] == i and x[3] >= 1.5)) for i in range(len(WEEKS)))
        line.append(f"{nm3}: {sum(1 for x in g if x[3] >= 1.5)} и {sum(1 for x in g if x[3] >= 2)} из {len(g)} ({wk})")
    print(f"- {nm} [границы {a:.2f} и {b:.2f}]: " + " | ".join(line))

print("\nПО ДЕСЯТЫМ ДОЛЯМ (все монеты-недели — десять равных частей по признаку, от меньшего к большему): пошло ×1,5+ (и ×2+) из числа")
for key in ("oi5", "oi10", "oi30", "oi_min", "flat14", "above_low_all"):
    v = sorted(x[2][key] for x in rows if x[2][key] is not None)
    cut = [v[len(v) * i // 10] for i in range(1, 10)]
    out = []
    for i in range(10):
        lo_, hi_ = (cut[i - 1] if i else float("-inf")), (cut[i] if i < 9 else float("inf"))
        g_ = [x for x in rows if x[2][key] is not None and lo_ <= x[2][key] < hi_]
        out.append(f"{sum(1 for x in g_ if x[3] >= 1.5)}({sum(1 for x in g_ if x[3] >= 2)})/{len(g_)}")
    print(f"- {dict(NAMES)[key]}: " + " ".join(out) + f" | верхняя десятая — от {cut[-1]:.2f}")
print("\nСВЯЗКИ (знак фандинга за 7 дн × интерес за 30 дн и за 5 дн): монет-недель, пошло ×1,5+ и ×2+, по неделям")
def cnt(name, cond):
    g_ = [x for x in rows if cond(x[2])]
    wk = " ".join(f"{sum(1 for x in g_ if x[1] == i and x[3] >= 1.5)}/{sum(1 for x in g_ if x[1] == i)}" for i in range(len(WEEKS)))
    n15 = sum(1 for x in g_ if x[3] >= 1.5)
    print(f"- {name}: {n15} и {sum(1 for x in g_ if x[3] >= 2)} из {len(g_)} ({100 * n15 / max(1, len(g_)):.0f} %) | {wk}")
ok_ = lambda f, *k: all(f[x] is not None for x in k)
cnt("все", lambda f: True)
cnt("фандинг в минусе", lambda f: ok_(f, "f7") and f["f7"] < 0)
cnt("фандинг в минусе, интерес за 30 дн вырос", lambda f: ok_(f, "f7", "oi30") and f["f7"] < 0 and f["oi30"] > 1)
cnt("фандинг в минусе, интерес за 30 дн упал", lambda f: ok_(f, "f7", "oi30") and f["f7"] < 0 and f["oi30"] <= 1)
cnt("интерес за 5 дн вырос, цена за 5 дн не выросла", lambda f: ok_(f, "oi5") and f["oi5"] > 1 and f["px5"] <= 1)
cnt("интерес за 5 дн вырос, цена за 5 дн выросла", lambda f: ok_(f, "oi5") and f["oi5"] > 1 and f["px5"] > 1)
cnt("интерес за 5 дн упал, цена за 5 дн выросла", lambda f: ok_(f, "oi5") and f["oi5"] <= 1 and f["px5"] > 1)
cnt("интерес за 5 дн упал, цена за 5 дн не выросла", lambda f: ok_(f, "oi5") and f["oi5"] <= 1 and f["px5"] <= 1)

print("\nКАРТИНА GALA (цена у дна И интерес у максимума, вся история): трети по цене × трети по интересу → пошло ×1,5+ / ×2+ из числа")
vp = sorted(x[2]["pos_all"] for x in rows); vo = sorted(x[2]["oi_max_all"] for x in rows)
pa, pb, oa, ob = vp[len(vp) // 3], vp[2 * len(vp) // 3], vo[len(vo) // 3], vo[2 * len(vo) // 3]
for pn, pc in (("цена: низ", lambda z: z < pa), ("цена: середина", lambda z: pa <= z < pb), ("цена: верх", lambda z: z >= pb)):
    line = []
    for on, oc in (("интерес: низ", lambda z: z < oa), ("середина", lambda z: oa <= z < ob), ("верх", lambda z: z >= ob)):
        g = [x for x in rows if pc(x[2]["pos_all"]) and oc(x[2]["oi_max_all"])]
        line.append(f"{on}: {sum(1 for x in g if x[3] >= 1.5)}/{sum(1 for x in g if x[3] >= 2)} из {len(g)}")
    print(f"- {pn} | " + " | ".join(line))
print(f"  границы: цена {pa:.2f} и {pb:.2f}; интерес {oa:.2f} и {ob:.2f}")

print("\nПОШЕДШИЕ ×2+ ПО ОДНОЙ: до старта (дневные TV) → на ходу (дневной интерес, часовой фандинг) → после")
print("монета база→вершина ход | до: цена к мин. истории, место цены, интерес к своему макс. и мин. истории, интерес за 30 дн, интерес и цена за 5 дн | на ходу: интерес на вершине к старту, мин. фандинг %, доля часов в минусе | через 2 дня: интерес к старту, цена к вершине")
agg = []
g = lambda v, p=2: "—" if v is None else f"{v:.{p}f}"
for s, i, f, r, tt, tb in sorted(rows, key=lambda x: -x[3]):
    if r < 2: continue
    d1 = d1s[s]
    b0 = [x for x in d1 if x[0] < tb]; oi0 = b0[-1][5] if b0 else None
    top = next((x for x in d1 if x[0] == tt), None); oit = top[5] if top else None
    a2 = next((x for x in d1 if x[0] == tt + 2 * D), None)
    h = tv(s, "60") or []
    fu = [x[6] for x in h if tb <= x[0] < tt + D and x[6] is not None]
    neg = sum(1 for v in fu if v < 0) / len(fu) if fu else None
    kx = {x[0]: x for x in bx[s]}; hi = kx[tt][2]; p2 = kx.get(tt + 2 * D)
    print(f"{s:9s} {fd(tb)}→{fd(tt)} ×{r:.2f} | ×{g(f['above_low_all'])}, {g(f['pos_all'])}, {g(f['oi_max_all'])} и ×{g(f['oi_min_all'], 1)}, ×{g(f['oi30'])}, за 5 дн ×{g(f['oi5'])} (цена ×{g(f['px5'])}) | "
          f"×{g(oit / oi0 if oit and oi0 else None)}, {g(min(fu) if fu else None, 3)}, {g(neg)} | ×{g(a2[5] / oi0 if a2 and a2[5] and oi0 else None)}, {g((p2[4] / hi - 1) * 100 if p2 else None, 0)}%")
    agg.append((s, oit / oi0 if oit and oi0 else None, min(fu) if fu else None, neg, a2[5] / oi0 if a2 and a2[5] and oi0 else None, f))
ok = [a for a in agg if a[1]]
print(f"\nИТОГ по ×2+ ({len(agg)} ходов, с данными на вершине {len(ok)}): интерес в монетах на вершине выше, чем до старта, — у {sum(1 for a in ok if a[1] > 1)}; в полтора раза и больше — у {sum(1 for a in ok if a[1] >= 1.5)}; вдвое и больше — у {sum(1 for a in ok if a[1] >= 2)}")
fo = [a for a in agg if a[2] is not None]
print(f"фандинг уходил в минус на ходу — у {sum(1 for a in fo if a[2] < 0)} из {len(fo)}; больше половины часов хода в минусе — у {sum(1 for a in fo if a[3] > .5)}")
st2 = [a for a in agg if a[4]]
print(f"через 2 дня после вершины интерес выше, чем до старта, — у {sum(1 for a in st2 if a[4] > 1)} из {len(st2)}")
print("\nSOPH, GALA, RLC, LSK — все недели:")
for x in rows:
    if x[0] in ("SOPH", "GALA", "RLC", "LSK"):
        f = x[2]; print(f"  {x[0]} нед.{x[1] + 1} ход ×{x[3]:.2f} ({fd(x[5]) if x[5] else '—'}) | цена к мин. истории ×{f['above_low_all']:.2f}, место {f['pos_all']:.2f}, интерес к макс. {f['oi_max_all']:.2f}, к мин. ×{f['oi_min_all']:.1f}, за 30 дн ×{g(f['oi30'])}, фандинг 7 дн {g(f['f7'], 3)}")
json.dump(rows, open(os.path.join(os.path.dirname(sys.argv[1]), "movers_rows.json"), "w"))
