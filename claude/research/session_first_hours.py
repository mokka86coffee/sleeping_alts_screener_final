#!/usr/bin/env python3
"""«ПОДОЖДАЛИ ЧАС-ДВА — ПОДТВЕРДИЛОСЬ — БЕРЁМ» (06.10, владелец: «начало — подождали час — окей подтвердилось то или другое идем брать, ничего не
подтвердилось вообще сделки не открываем», «первые час-два»). Каждая сессия каждого дня метится по своим первым W часам: ход цены по рынку (медиана по
монетам пульса) и объём часа к норме; дальше считаются сделки бота из журнала, взятые ПОСЛЕ этих W часов. Лонги — только на всплеске. Время UTC.
    .venv/bin/python claude/research/session_first_hours.py"""
import json, gzip, glob, datetime as dt, collections, statistics as st
from pathlib import Path
B = Path(__file__).resolve().parents[2]; U = dt.timezone.utc
H = collections.defaultdict(list)
def add(r, s=None):
    s = s or r.get("sym")
    if r.get("price") and r.get("oi_usd"): H[s].append((r["t"], r["price"], r.get("rvol_1h")))
for f in sorted(glob.glob(str(B / "pulse_archive/2026-09-2[6-9].jsonl.gz")) + glob.glob(str(B / "pulse_archive/2026-09-30.jsonl.gz")) + glob.glob(str(B / "pulse_archive/2026-10-*.jsonl.gz"))):
    for l in gzip.open(f, "rt"): add(json.loads(l))
for s, rs in json.load(open(B / "pulse.json")).items():
    if s != "_meta":
        for r in rs: add(r, s)
for s in H: H[s] = sorted(set(H[s]))
SES = {"Токио": (0, 7), "Лондон": (7, 13), "Нью-Йорк": (13, 21)}
ent, ex = {}, []
for fn in ("output/paper_fast3.jsonl", "output/paper_wake.jsonl"):
    for l in open(B / fn, encoding="utf-8"):
        try: e = json.loads(l)
        except ValueError: continue
        if e.get("kind") == "entry": ent[(e["sym"], round(float(e["at"])))] = e
        elif str(e.get("kind", "")).startswith("exit"): ex.append(e)
TR, seen = [], set()
for e in ex:
    en = ent.get((e["sym"], round(float(e["opened_at"])))) or {}
    r = str(en.get("rule") or e.get("rule") or "")
    if e["side"] == 1 and ("всплеск" not in r or any(z in r for z in ("R52", "R59", "флэт", "переворот"))): continue
    k = (e["sym"], int(e["opened_at"] // 180), e["side"])
    if k in seen: continue
    seen.add(k); TR.append((e["opened_at"], e["side"], e["result_pct"]))


def head(t0, W):
    rv, dp = [], []
    for s, rs in H.items():
        a = [x for x in rs if t0 - 2400 <= x[0] <= t0 + 900]; b = [x for x in rs if t0 + W * 3600 - 900 <= x[0] <= t0 + W * 3600 + 2400]
        if not a or not b: continue
        dp.append(b[0][1] / a[-1][1] - 1)
        v = [x[2] for x in rs if t0 + 2700 <= x[0] <= t0 + W * 3600 + 2400 and x[2] is not None]
        if v: rv.append(st.mean(v))
    return (st.median(rv), st.median(dp) * 100) if len(rv) >= 15 else None


def run(W):
    pts = []
    days = sorted({dt.datetime.fromtimestamp(t, U).date() for t, _, _ in TR})
    for d in days:
        for s, (a, b) in SES.items():
            t0 = dt.datetime(d.year, d.month, d.day, a, tzinfo=U).timestamp(); t1 = t0 + (b - a) * 3600
            m = head(t0, W)
            g = [x for x in TR if t0 + W * 3600 <= x[0] < t1]
            if m and g: pts.append((m, [x[2] for x in g if x[1] == 1], [x[2] for x in g if x[1] == -1], f"{d:%d.%m} {s}"))
    rv = sorted(p[0][0] for p in pts); hi = rv[2 * len(rv) // 3]
    print(f"\n═══ смотрим первые {W} ч · сессий со сделками после них: {len(pts)} · объём «высокий» — верхняя треть, от ×{hi:.2f} нормы")
    w = lambda q: f"{100 * sum(1 for x in q if x > 0) // max(1, len(q))}%"
    for vn, vs in (("объём не высокий", lambda m: m[0] < hi), ("объём высокий", lambda m: m[0] >= hi)):
        for pn, ps in (("цена вверх", lambda m: m[1] >= 0), ("цена вниз", lambda m: m[1] < 0)):
            g = [p for p in pts if vs(p[0]) and ps(p[0])]
            L = [x for p in g for x in p[1]]; S = [x for p in g for x in p[2]]
            print(f"  {vn}, {pn}: сессий {len(g)} · лонги {len(L):3d} сд., в плюс {w(L)}, {sum(L):+5.0f}% (сессий в плюс {sum(1 for p in g if p[1] and sum(p[1]) > 0)} из {sum(1 for p in g if p[1])})"
                  f" · шорты {len(S):3d} сд., в плюс {w(S)}, {sum(S):+5.0f}% (сессий в плюс {sum(1 for p in g if p[2] and sum(p[2]) > 0)} из {sum(1 for p in g if p[2])})")
            if vn == "объём не высокий" and pn == "цена вверх":
                print("     сессии: " + " · ".join(f"{p[3]} шорты {len(p[2])}/{sum(p[2]):+.0f}%" for p in g))
for W in (1, 2):
    run(W)


def dynamic(min_h=1.0):
    """«как ведёт себя рынок дальше» (владелец: «1 час не всегда показателен»): режим считается на минуту входа — ход цены по рынку и объём от открытия
    сессии до последнего показания пульса перед входом; сделки раньше min_h часов от открытия не берутся"""
    out = []
    for t, side, res in TR:
        d = dt.datetime.fromtimestamp(t, U); s = next((n for n, (a, b) in SES.items() if a <= d.hour < b), None)
        if not s: continue
        t0 = dt.datetime(d.year, d.month, d.day, SES[s][0], tzinfo=U).timestamp()
        if t - t0 < min_h * 3600: continue
        rv, dp = [], []
        for sy, rs in H.items():
            a = [x for x in rs if t0 - 2400 <= x[0] <= t0 + 900]; b = [x for x in rs if t - 3000 <= x[0] <= t]
            if not a or not b: continue
            dp.append(b[-1][1] / a[-1][1] - 1)
            v = [x[2] for x in rs if t0 + 2700 <= x[0] <= t and x[2] is not None]
            if v: rv.append(st.mean(v))
        if len(rv) >= 15: out.append((st.median(rv), st.median(dp) * 100, side, res, f"{d:%d.%m} {s}"))
    rv = sorted(x[0] for x in out); hi = rv[2 * len(rv) // 3]
    print(f"\n═══ режим на минуту входа (с открытия сессии до входа), сделки не раньше {min_h:g} ч от открытия · сделок {len(out)} · объём «высокий» — верхняя треть, от ×{hi:.2f}")
    w = lambda q: f"{100 * sum(1 for x in q if x > 0) // max(1, len(q))}%"
    for vn, vs in (("объём не высокий", lambda x: x[0] < hi), ("объём высокий", lambda x: x[0] >= hi)):
        for pn, ps in (("рынок с открытия вверх", lambda x: x[1] >= 0), ("рынок с открытия вниз", lambda x: x[1] < 0)):
            g = [x for x in out if vs(x) and ps(x)]
            for sd, nm in ((1, "лонги"), (-1, "шорты")):
                q = [x for x in g if x[2] == sd]; ses = collections.defaultdict(float)
                for x in q: ses[x[4]] += x[3]
                print(f"  {vn}, {pn} · {nm}: {len(q):3d} сд., в плюс {w([x[3] for x in q])}, {sum(x[3] for x in q):+5.0f}% · сессий в плюс {sum(1 for v in ses.values() if v > 0)} из {len(ses)}")
for mh in (1.0, 2.0):
    dynamic(mh)


def fine():
    """06.10 владелец: «разбивай до самого момента вплоть до часа, важно качество не количество сделок». Режим на минуту входа, только сессии без объёма
    (ниже верхней трети): сделка «против хода сессии» — шорт, когда рынок с открытия вверх, лонг на всплеске, когда вниз. По сессиям и по часу сессии."""
    rows = []
    for t, side, res in TR:
        d = dt.datetime.fromtimestamp(t, U); s = next((n for n, (a, b) in SES.items() if a <= d.hour < b), None)
        if not s: continue
        t0 = dt.datetime(d.year, d.month, d.day, SES[s][0], tzinfo=U).timestamp()
        rv, dp = [], []
        for sy, rs in H.items():
            a = [x for x in rs if t0 - 2400 <= x[0] <= t0 + 900]; b = [x for x in rs if t - 3000 <= x[0] <= t]
            if not a or not b: continue
            dp.append(b[-1][1] / a[-1][1] - 1)
            v = [x[2] for x in rs if t0 + 2700 <= x[0] <= t and x[2] is not None]
            if v: rv.append(st.mean(v))
        if len(dp) >= 15: rows.append(dict(rv=st.median(rv) if len(rv) >= 15 else None, dp=st.median(dp) * 100, side=side, res=res, ses=s, day=f"{d:%d.%m}", h=int((t - t0) // 3600) + 1))
    rvs = sorted(r["rv"] for r in rows if r["rv"] is not None); hi = rvs[2 * len(rvs) // 3]
    w = lambda q: f"{100 * sum(1 for x in q if x['res'] > 0) // max(1, len(q))}%"
    def line(nm, q):
        dd = collections.defaultdict(float)
        for x in q: dd[x["day"]] += x["res"]
        return f"{nm}: {len(q):3d} сд., в плюс {w(q)}, {sum(x['res'] for x in q):+5.0f}%, дней в плюс {sum(1 for v in dd.values() if v > 0)} из {len(dd)}"
    print(f"\n═══ ПО ЧАСУ СЕССИИ · сессии без объёма (объём с открытия ниже ×{hi:.2f}; в первый час объём ещё не известен — он идёт отдельной строкой)")
    for s in SES:
        print(f"\n{s}:")
        for h in range(1, SES[s][1] - SES[s][0] + 1):
            q = [r for r in rows if r["ses"] == s and r["h"] == h and (r["rv"] is None or r["rv"] < hi)]
            if not q: continue
            su = [r for r in q if r["side"] == -1 and r["dp"] >= 0]; sdn = [r for r in q if r["side"] == -1 and r["dp"] < 0]
            lu = [r for r in q if r["side"] == 1 and r["dp"] >= 0]; ld = [r for r in q if r["side"] == 1 and r["dp"] < 0]
            print(f"  {h}-й час | " + " | ".join(line(n, g) for n, g in (("шорт при рынке вверх", su), ("шорт при рынке вниз", sdn), ("лонг при рынке вверх", lu), ("лонг при рынке вниз", ld)) if g))
    print("\nпо размеру хода рынка с открытия сессии (без объёма, со второго часа):")
    q = [r for r in rows if r["h"] >= 2 and r["rv"] is not None and r["rv"] < hi]
    for nm, cond in (("рынок вверх больше +0,5 %", lambda r: r["dp"] >= 0.5), ("вверх до +0,5 %", lambda r: 0 <= r["dp"] < 0.5), ("вниз до −0,5 %", lambda r: -0.5 < r["dp"] < 0), ("вниз больше −0,5 %", lambda r: r["dp"] <= -0.5)):
        g = [r for r in q if cond(r)]
        print(f"  {nm:26s} | " + line("шорты", [r for r in g if r["side"] == -1]) + " | " + line("лонги", [r for r in g if r["side"] == 1]))
fine()
