#!/usr/bin/env python3
"""ЛИДЕРЫ ЗА МЕСЯЦ: монеты, которые были в первых трёх очереди 3+ прогона подряд, — далеко ли пошли, в какие дни и в какое время (30.09, владелец: «попробуй лидеров посмотреть,
там больше история, какие монеты, что были в первых 3+ раза подряд, далеко пошли, и в какие дни и в какое время» → «прямо за месяц посмотри»).

Данные: журнал очереди queue_log.jsonl (с 07.09, старый журнал _old_runs_* — сдвиг −1 ч, как в episodes.py) — место монеты по прогонам (каждые 30 мин); цены — 30-минутные бары
cq_v2/intraday (с 31.08). Серия = прогоны подряд (шаг ≤ 45 мин) с местом ≤ 3; серия «3+» — не короче 3 прогонов. Момент захода = 3-й прогон серии; цена захода = закрытие последнего
закрытого 30-мин бара на этот момент. Исход: максимум и минимум от цены захода за 24 и 48 ч, когда был максимум, закрытие через 24 ч, а также ход ДО момента захода (за 24 ч) — «уже убежала» или «спала».
Порог «пошла» — мерка проекта PUMP_JUMP_PCT (40 %); рядом даны доли ≥10 и ≥20 %. Дни — по UTC+3, время захода — час UTC+3.
    .venv/bin/python claude/research/leaders_month.py   → leaders_month.md / leaders_month.json"""
import json, statistics as st
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]; HERE = Path(__file__).parent
L = timezone(timedelta(hours=3))
try:
    import sys; sys.path.insert(0, str(ROOT)); from core_config import PUMP_JUMP_PCT as JUMP
except Exception:  # noqa: BLE001
    JUMP = 40.0
def ts(s): return int(datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp() * 1000)

# 1) места по прогонам
runs = defaultdict(dict)                                         # sym → {t_ms: place}
for path, shift in ((ROOT / "_old_runs_20260916_1936UTC/output/queue_log.jsonl", -3600000), (ROOT / "output/queue_log.jsonl", 0)):
    if not path.exists(): continue
    for l in path.read_text(encoding="utf-8").splitlines():
        try: r = json.loads(l)
        except ValueError: continue
        if r.get("sym") and r.get("at"):
            runs[r["sym"]][ts(r["at"]) + shift] = r.get("place") if isinstance(r.get("place"), int) else None
allt = sorted({t for d in runs.values() for t in d})                # все прогоны

# 2) бары
bars = {}
for p in (ROOT / "cq_v2" / "intraday").glob("*.jsonl"):
    B = []
    for l in p.read_text(encoding="utf-8").splitlines():
        try: r = json.loads(l)
        except ValueError: continue
        if r.get("px") and r.get("h") and r.get("l"):
            B.append((ts(r["candle"]), float(r["px"]), float(r["h"]), float(r["l"])))
    B.sort(); bars[p.stem.upper() + "USDT"] = B

# 3) серии и исходы
eps = []
for sym, d in runs.items():
    B = bars.get(sym)
    if not B: continue
    tt = [t for t in allt if d.get(t) is not None and d[t] <= 3]
    cur = []
    for t in tt + [None]:
        if t is not None and (not cur or t - cur[-1] <= 45 * 60_000):
            cur.append(t); continue
        if len(cur) >= 3:
            t3 = cur[2]; keys = [b[0] for b in B]
            i = bisect_right(keys, t3 - 30 * 60_000) - 1                # последний закрытый 30-мин бар к t3
            if i >= 1:
                p0 = B[i][1]
                def win(h):
                    w = [b for b in B if B[i][0] < b[0] <= B[i][0] + h * 3600_000]
                    return w
                w24, w48 = win(24), win(48)
                pre = [b for b in B if B[i][0] - 24 * 3600_000 <= b[0] <= B[i][0]]
                if len(w24) >= 40:                                       # хотя бы ~20 ч данных после
                    hi24 = max(b[2] for b in w24); lo24 = min(b[3] for b in w24)
                    tmax = max(w24, key=lambda b: b[2])[0]
                    hi48 = max(b[2] for b in w48) if len(w48) >= 80 else None
                    eps.append(dict(sym=sym[:-4], t=t3, day=datetime.fromtimestamp(t3 / 1000, L).strftime("%d.%m"), hh=datetime.fromtimestamp(t3 / 1000, L).hour,
                                    wd=("пн", "вт", "ср", "чт", "пт", "сб", "вс")[datetime.fromtimestamp(t3 / 1000, L).weekday()], streak=len(cur), p0=p0,
                                    up24=(hi24 / p0 - 1) * 100, dn24=(lo24 / p0 - 1) * 100, cl24=(w24[-1][1] / p0 - 1) * 100,
                                    up48=None if hi48 is None else (hi48 / p0 - 1) * 100, h_to_max=(tmax - B[i][0]) / 3600_000,
                                    pre24=((p0 / pre[0][1] - 1) * 100 if len(pre) > 20 else None)))
        cur = [t] if t is not None else []
json.dump(eps, open(HERE / "leaders_month.json", "w"), ensure_ascii=False, indent=0)

def share(g, k, th): return f"{sum(1 for e in g if e[k] is not None and e[k] >= th) * 100 // max(1, len(g))}%"
def line(g):
    if len(g) < 5: return f"n={len(g)} — мало"
    return (f"n={len(g)} · ≥+10%: {share(g,'up24',10)} · ≥+20%: {share(g,'up24',20)} · ≥+{JUMP:g}%: {share(g,'up24',JUMP)} · медиана максимума {st.median(e['up24'] for e in g):+.1f}% · "
            f"медиана просадки до максимума −{abs(st.median(e['dn24'] for e in g)):.1f}% · закрытие через 24 ч {st.median(e['cl24'] for e in g):+.1f}%")
md = [f"# Лидеры за месяц: серии в первых трёх 3+ прогона подряд ({datetime.now(L):%d.%m %H:%M})", "",
      f"Эпизодов: {len(eps)} на {len({e['sym'] for e in eps})} монетах, период {min(e['day'] for e in eps) if eps else '—'}…{max(e['day'] for e in eps) if eps else '—'} (журнал очереди с 07.09; цены 30 мин с 31.08). "
      f"«Пошла» — максимум за 24 ч ≥ +{JUMP:g}% от цены захода (мерка проекта). Расчёт по группам, не проверено; серия монеты внутри дня может повторяться.", "",
      "## Все и по длине серии", "", f"- все: {line(eps)}"]
for lab, fn in (("серия 3–5 прогонов", lambda e: e["streak"] <= 5), ("серия 6–11", lambda e: 6 <= e["streak"] <= 11), ("серия 12+ (6 ч и дольше)", lambda e: e["streak"] >= 12)):
    md.append(f"- {lab}: {line([e for e in eps if fn(e)])}")
md += ["", "## До захода монета уже бежала или спала (ход за 24 ч до захода)", ""]
for lab, fn in (("до захода ≥ +10% (уже бежала)", lambda e: e["pre24"] is not None and e["pre24"] >= 10), ("до захода −10…+10% (спала)", lambda e: e["pre24"] is not None and -10 < e["pre24"] < 10),
                ("до захода ≤ −10% (падала)", lambda e: e["pre24"] is not None and e["pre24"] <= -10)):
    md.append(f"- {lab}: {line([e for e in eps if fn(e)])}")
md += ["", "## По дням (UTC+3)", "", "| день | эпизодов | ≥ +20% | ≥ +40% | медиана максимума |", "|---|---|---|---|---|"]
for d in sorted({e["day"] for e in eps}, key=lambda x: (x[3:5], x[:2])):
    g = [e for e in eps if e["day"] == d]
    md.append(f"| {d} | {len(g)} | {share(g,'up24',20)} | {share(g,'up24',JUMP)} | {st.median(e['up24'] for e in g):+.1f}% |")
md += ["", "## По дню недели", "", "| день | эпизодов | ≥ +20% | ≥ +40% | медиана максимума |", "|---|---|---|---|---|"]
for w in ("пн", "вт", "ср", "чт", "пт", "сб", "вс"):
    g = [e for e in eps if e["wd"] == w]
    if g: md.append(f"| {w} | {len(g)} | {share(g,'up24',20)} | {share(g,'up24',JUMP)} | {st.median(e['up24'] for e in g):+.1f}% |")
md += ["", "## По часу захода (UTC+3, группами)", "", "| время | эпизодов | ≥ +20% | ≥ +40% | медиана максимума |", "|---|---|---|---|---|"]
for lab, lo, hi in (("00–03 Сидней", 0, 3), ("03–07", 3, 7), ("07–10", 7, 10), ("10–13 Лондон", 10, 13), ("13–16", 13, 16), ("16–20 Нью-Йорк", 16, 20), ("20–24", 20, 24)):
    g = [e for e in eps if lo <= e["hh"] < hi]
    if g: md.append(f"| {lab} | {len(g)} | {share(g,'up24',20)} | {share(g,'up24',JUMP)} | {st.median(e['up24'] for e in g):+.1f}% |")
far = sorted([e for e in eps if e["up24"] >= JUMP], key=lambda e: -e["up24"])
md += ["", f"## Ушли далеко (максимум за 24 ч ≥ +{JUMP:g}%): {len(far)} эпизодов", "", "| монета | заход (UTC+3) | серия | до захода 24 ч | максимум 24 ч | когда максимум (ч после) | просадка до | закрытие 24 ч |", "|---|---|---|---|---|---|---|---|"]
for e in far:
    md.append(f"| {e['sym']} | {e['day']} {e['hh']:02d}:xx {e['wd']} | {e['streak']} | {'—' if e['pre24'] is None else f'{e['pre24']:+.0f}%'} | {e['up24']:+.0f}% | {e['h_to_max']:.0f} | {e['dn24']:.0f}% | {e['cl24']:+.0f}% |")
per = defaultdict(list)
for e in eps: per[e["sym"]].append(e)
md += ["", "## По монетам (≥ 3 серий)", "", "| монета | серий | ≥ +20% | максимум лучшей | дни |", "|---|---|---|---|---|"]
for s, g in sorted(per.items(), key=lambda kv: -len(kv[1])):
    if len(g) >= 3: md.append(f"| {s} | {len(g)} | {share(g,'up24',20)} | {max(e['up24'] for e in g):+.0f}% | {', '.join(sorted({e['day'] for e in g}, key=lambda x: (x[3:5], x[:2])))} |")
(HERE / "leaders_month.md").write_text("\n".join(md) + "\n", encoding="utf-8"); print("\n".join(md[:46]))
