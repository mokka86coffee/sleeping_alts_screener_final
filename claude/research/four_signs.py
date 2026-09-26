"""СКОЛЬКО ЛИДЕРОВ МЕСЯЦА БЫЛИ «ЧЕТВЁРКАМИ» НА СТАРТЕ (26.09, случай RARE: 4 признака near_move из 5 — без группы, вне очереди).
Переигрываем judge() из near_move.py по дневному архиву cq_v2/<coin>.json, обрезанному датой: накануне старта хода (start − 1 день) и в день старта.
Ходы — anatomy.csv (100 лидеров, первый большой ход). Считаем балл (число признаков), группу и каких признаков не хватило.
    .venv/bin/python claude/research/four_signs.py
"""
import csv, json, sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
import near_move as nm
SIGNS = ["плечо копится", "плечо копилось", "пузырь у дна", "сбор ", "оборот в затишье", "плечо ×", "шортов сгорело", "сбор удержан", "двигатель: спрос"]
def cut(d, day):
    return {k: [r for r in v if r.get("datetime", "")[:10] <= day] for k, v in d.items() if isinstance(v, list)}
rows = list(csv.DictReader(open(Path(__file__).with_name("anatomy.csv"), encoding="utf-8")))
# точка Б: день перед первым баром, где закрытие ≥ +40% к закрытию 48 ч назад (монета «в ходу» — очередь обязана видеть её накануне)
from datetime import timezone
L3 = timezone(timedelta(hours=3)); H = 3600000
def first_move_day(sym, t_start, t_peak):
    p = ROOT / "cq_v2" / "hist" / "tops" / f"{sym}USDT.json"
    if not p.exists(): return None
    kl = json.loads(p.read_text())["kl"]; by = {k[0]: k[3] for k in kl}
    for k in kl:
        t = k[0]
        if t < t_start or t > t_peak: continue
        p48 = by.get(t - 48 * H)
        if p48 and k[3] / p48 - 1 >= 0.40:
            return (datetime.fromtimestamp(t / 1000, L3) - timedelta(days=1)).strftime("%Y-%m-%d")
    return None
res = []
print(f"{'монета':<9}{'старт':<12}| накануне: балл группа | в день старта: балл группа | чего нет накануне")
for r in rows:
    try:
        dt = datetime.strptime(r["start"] + ".2026", "%d.%m %H:%M.%Y")
    except Exception:
        continue
    p = ROOT / "cq_v2" / f"{r['sym'].lower()}.json"
    if not p.exists():
        continue
    d = json.loads(p.read_text())
    out = {}
    try:
        tp = datetime.strptime(r["peak1"] + ".2026", "%d.%m %H:%M.%Y")
        dayB = first_move_day(r["sym"], int(dt.replace(tzinfo=L3).timestamp() * 1000), int(tp.replace(tzinfo=L3).timestamp() * 1000))
    except Exception:
        dayB = None
    for tag, day in (("eve", (dt - timedelta(days=1)).strftime("%Y-%m-%d")), ("day", dt.strftime("%Y-%m-%d")), ("B", dayB or dt.strftime("%Y-%m-%d"))):
        try:
            j = nm.judge(cut(d, day))
        except Exception as e:
            j = None
        out[tag] = j
    je, jd = out["eve"], out["day"]
    have = " ".join(w[:14] for w in (je or {}).get("why", []))
    missing = [s for s in SIGNS if je and not any(w.startswith(s) or s in w for w in je["why"])]
    print(f"{r['sym']:<9}{r['start']:<12}| {(je or {}).get('score', '—'):>4} {str((je or {}).get('group')):<8} | {(jd or {}).get('score', '—'):>4} {str((jd or {}).get('group')):<8} | " + ", ".join(m.strip() for m in missing if m not in ("плечо копилось",))[:90])
    jb = out["B"]
    res.append(dict(sym=r["sym"], se=(je or {}).get("score"), ge=(je or {}).get("group"), sd=(jd or {}).get("score"), gd=(jd or {}).get("group"),
                    sb=(jb or {}).get("score"), gb=(jb or {}).get("group"), missB=[m for m in SIGNS if jb and not any(m in w for w in jb["why"])], miss=missing, move=float(r["move1_pct"]), dayB=dayB))
n = len(res)
print(f"\nСВОДКА по {n} лидерам:")
for tag, key, gkey in (("накануне старта (минимум зигзага)", "se", "ge"), ("в день старта", "sd", "gd"), ("Б: накануне первого +40% за 48 ч", "sb", "gb")):
    c = Counter((x[key] if x[key] is not None else "нет данных") for x in res)
    g = Counter(str(x[gkey]) for x in res)
    print(f"  {tag}: балл {dict(sorted(c.items(), key=lambda kv: str(kv[0])))} · группа {dict(g)}")
    print(f"    в очереди (балл ≥5) — {sum(1 for x in res if x[key] is not None and x[key] >= 5)}/{n}; четвёрки — {sum(1 for x in res if x[key] == 4)}/{n}; тройки и ниже — {sum(1 for x in res if x[key] is not None and x[key] <= 3)}/{n}")
mc = Counter()
for x in res:
    if x["sb"] == 4:
        for m in x["missB"]: mc[m.strip()] += 1
print(f"  у четвёрок в точке Б не хватало: {dict(mc.most_common())}")
print("  четвёрки в точке Б:", [(x['sym'], x['dayB'], [m.strip() for m in x['missB'] if m.strip() not in ('плечо копилось',)]) for x in res if x['sb'] == 4])
bigB = [x for x in res if x["move"] >= 100]
print(f"  ходы ≥+100% ({len(bigB)}) в точке Б: в очереди {sum(1 for x in bigB if x['sb'] is not None and x['sb'] >= 5)}, четвёрки {sum(1 for x in bigB if x['sb'] == 4)}, ниже {sum(1 for x in bigB if x['sb'] is not None and x['sb'] <= 3)}")
big = [x for x in res if x["move"] >= 100]
print(f"  ходы ≥+100% ({len(big)}): накануне в очереди {sum(1 for x in big if x['se'] is not None and x['se'] >= 5)}, четвёрки {sum(1 for x in big if x['se'] == 4)}, ниже {sum(1 for x in big if x['se'] is not None and x['se'] <= 3)}")
