#!/usr/bin/env python3
"""СВОДКА ПО queue_log (01.10, владелец: «прогони queue_log, посмотри, какие монеты пошли в тот день, в который очередь показывала в первых монету больше 3 раз подряд, и сделай сводку: в какие сессии
монета пошла и когда появилась в очереди»).

Серия = прогоны подряд (шаг ≤ 45 мин) с местом 1–3, длина ≥ 4 («больше 3 раз подряд»). Журнал: output/queue_log.jsonl (с 16.09; старый _old_runs_* со сдвигом −1 ч, как в leaders_month.py).
Для каждой серии:
  · «появилась в очереди» — начало непрерывного пребывания в очереди (любое место, шаг ≤ 45 мин) до серии; «в первых» — первый прогон серии; «4-й раз подряд» — момент, когда условие выполнилось;
  · цена входа — закрытие последнего закрытого 30-мин бара на момент первого прогона серии (cq_v2/intraday, 31.08+); дальше 24 ч: максимум и его время, ход по сессиям (закрытие к закрытию по окнам
    Сидней 00–03, Токио 03–10, Лондон 10–16, Нью-Йорк 16–24 по UTC+3), «пошла» = максимум за 24 ч от цены входа ≥ PUMP_JUMP_PCT проекта (40 %), рядом доли ≥ 10 и ≥ 20 %.
Время везде UTC+3. Результат — claude/research/queue_first_series.md. Только запись, не проверено вне выборки.
    .venv/bin/python claude/research/queue_first_series.py"""
import json
from bisect import bisect_right
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
import statistics as st

ROOT = Path(__file__).resolve().parents[2]; HERE = Path(__file__).parent
L = timezone(timedelta(hours=3))
try:
    import sys; sys.path.insert(0, str(ROOT)); from core_config import PUMP_JUMP_PCT as JUMP
except Exception:  # noqa: BLE001
    JUMP = 40.0
MIN_LEN = 4
SES = (("Сидней", 0, 3), ("Токио", 3, 10), ("Лондон", 10, 16), ("Нью-Йорк", 16, 24))
def ts(s): return int(datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp() * 1000)
def ses(ms):
    h = datetime.fromtimestamp(ms / 1000, L).hour
    return next(n for n, a, b in SES if a <= h < b)
def hh(ms): return datetime.fromtimestamp(ms / 1000, L).strftime("%d.%m %H:%M")

runs = defaultdict(dict)                                          # sym → {t_ms: place|None}
for path, shift in ((ROOT / "_old_runs_20260916_1936UTC/output/queue_log.jsonl", -3600000), (ROOT / "output/queue_log.jsonl", 0)):
    if not path.exists(): continue
    for l in path.open(encoding="utf-8"):
        try: r = json.loads(l)
        except ValueError: continue
        if r.get("sym") and r.get("at") and not str(r["sym"]).startswith("_"):
            runs[r["sym"]][ts(r["at"]) + shift] = r.get("place") if isinstance(r.get("place"), int) else None
allt = sorted({t for d in runs.values() for t in d})
bars = {}
for p in (ROOT / "cq_v2" / "intraday").glob("*.jsonl"):
    B = []
    for l in p.open(encoding="utf-8"):
        try: r = json.loads(l)
        except ValueError: continue
        if r.get("px") and r.get("h") and r.get("l"): B.append((ts(r["candle"]), float(r["px"]), float(r["h"]), float(r["l"])))
    B.sort(); bars[p.stem.upper() + "USDT"] = B

out = []
for sym, d in runs.items():
    B = bars.get(sym)
    if not B: continue
    tt = sorted(t for t in d if d[t] is not None)                 # прогоны «в очереди»
    top = [t for t in tt if d[t] <= 3]
    cur = []
    for t in top + [None]:
        if t is not None and (not cur or t - cur[-1] <= 45 * 60_000):
            cur.append(t); continue
        if len(cur) >= MIN_LEN:
            t0 = cur[0]
            q0 = t0                                                # начало непрерывного пребывания в очереди
            i = bisect_right(tt, t0) - 1
            while i > 0 and tt[i] - tt[i - 1] <= 45 * 60_000: i -= 1
            q0 = tt[i]
            keys = [b[0] for b in B]; j = bisect_right(keys, t0 - 30 * 60_000) - 1
            if j >= 1:
                p0 = B[j][1]; w = [b for b in B if B[j][0] < b[0] <= B[j][0] + 24 * 3600_000]
                if len(w) >= 40:
                    hi = max(b[2] for b in w); tmax = max(w, key=lambda b: b[2])[0]
                    up = (hi / p0 - 1) * 100; dn = (min(b[3] for b in w) / p0 - 1) * 100
                    # ход по сессиям: закрытие к закрытию внутри окна сессии, суммарно по сегментам за 24 ч
                    seg = defaultdict(float); prev = p0
                    for b in w:
                        seg[ses(b[0])] += (b[1] / prev - 1) * 100; prev = b[1]
                    main = max(seg, key=lambda k: seg[k])
                    out.append(dict(sym=sym[:-4], t_q=q0, t_first=t0, t_4=cur[3], n=len(cur), day=datetime.fromtimestamp(t0 / 1000, L).strftime("%d.%m"), ses_first=ses(t0), ses_q=ses(q0),
                                    up=up, dn=dn, tmax=tmax, ses_max=ses(tmax), h_to_max=(tmax - B[j][0]) / 3600_000, seg=dict(seg), main=main, wait_h=(t0 - q0) / 3600_000))
        cur = [t] if t is not None else []
out.sort(key=lambda e: e["t_first"])
went = [e for e in out if e["up"] >= JUMP]
def sh(g, th): return f"{sum(1 for e in g if e['up'] >= th) * 100 // max(1, len(g))}%"
md = [f"# queue_log: монеты в первых 4+ раза подряд ({datetime.now(L):%d.%m %H:%M}, UTC+3)", "",
      f"Серий (≥ {MIN_LEN} прогона подряд на местах 1–3): {len(out)} на {len({e['sym'] for e in out})} монетах, {out[0]['day'] if out else '—'}…{out[-1]['day'] if out else '—'}. «Пошла» — максимум за 24 ч от цены на первом прогоне серии ≥ +{JUMP:g}% (мерка проекта). "
      f"Доли: ≥ +10%: {sh(out, 10)}, ≥ +20%: {sh(out, 20)}, ≥ +{JUMP:g}%: {sh(out, JUMP)}. Не проверено вне выборки.", ""]
md += ["## Когда монета появилась в очереди и когда стала первой (сессии UTC+3)", "", "| сессия | серий | пошли ≥ +40% | в очередь попала в этой сессии | в первые попала в этой сессии |", "|---|---|---|---|---|"]
for n, a, b in SES:
    g1 = [e for e in out if e["ses_first"] == n]; g2 = [e for e in out if e["ses_q"] == n]
    md.append(f"| {n} | {len(g1)} | {sh(g1, JUMP)} | {len(g2)} | {len(g1)} |")
md += ["", "## Пошедшие (≥ +40%): когда появилась в очереди → когда в первых → когда максимум → в какую сессию основной ход", "",
       "| монета | день | в очереди с | в первых с | 4-й раз подряд | серия | максимум 24 ч | когда макс. | сессия макс. | основной ход (по сессиям) | ждала в очереди до первых, ч |", "|---|---|---|---|---|---|---|---|---|---|---|"]
for e in went:
    md.append(f"| {e['sym']} | {e['day']} | {hh(e['t_q'])} ({e['ses_q']}) | {hh(e['t_first'])} ({e['ses_first']}) | {hh(e['t_4'])} | {e['n']} | +{e['up']:.0f}% | {hh(e['tmax'])} ({e['h_to_max']:.0f} ч) | {e['ses_max']} | "
              + ", ".join(f"{k} {v:+.0f}%" for k, v in sorted(e['seg'].items(), key=lambda kv: -kv[1])[:2]) + f" | {e['wait_h']:.1f} |")
md += ["", "## Сводка по пошедшим", ""]
if went:
    c1 = Counter(e["main"] for e in went); c2 = Counter(e["ses_max"] for e in went); c3 = Counter(e["ses_first"] for e in went); c4 = Counter(e["ses_q"] for e in went)
    f = lambda c: ", ".join(f"{k} {v}" for k, v in c.most_common())
    md += [f"- основной ход (сессия с наибольшим набором за 24 ч): {f(c1)}", f"- сессия, в которую пришёлся максимум: {f(c2)}", f"- в первые попали в сессию: {f(c3)}", f"- в очередь попали в сессию: {f(c4)}",
           f"- ждали в очереди до первых (медиана): {st.median(e['wait_h'] for e in went):.1f} ч; от первых до максимума (медиана): {st.median(e['h_to_max'] for e in went):.1f} ч; серия в первых (медиана): {st.median(e['n'] for e in went):.0f} прогонов", ""]
md += ["## Не пошли (< +40%) — для сравнения: те же сессии", ""]
no = [e for e in out if e["up"] < JUMP]
if no:
    c3 = Counter(e["ses_first"] for e in no); c1 = Counter(e["main"] for e in no)
    md += [f"- серий {len(no)}; в первые попали в сессию: " + ", ".join(f"{k} {v}" for k, v in c3.most_common()), f"- ждали в очереди до первых (медиана): {st.median(e['wait_h'] for e in no):.1f} ч; серия (медиана): {st.median(e['n'] for e in no):.0f} прогонов", ""]
md += ["## По дням: сколько серий и сколько пошло", "", "| день | серий | пошли ≥ +40% | какие |", "|---|---|---|---|"]
for dkey in sorted({e["day"] for e in out}, key=lambda x: (x[3:5], x[:2])):
    g = [e for e in out if e["day"] == dkey]; w = [e for e in g if e["up"] >= JUMP]
    md.append(f"| {dkey} | {len(g)} | {len(w)} | {', '.join(e['sym'] + f' +{e['up']:.0f}%' for e in w) or '—'} |")
(HERE / "queue_first_series.md").write_text("\n".join(md) + "\n", encoding="utf-8")
json.dump(out, open(HERE / "queue_first_series.json", "w"), ensure_ascii=False, indent=0)
print("\n".join(md[:60]))
