#!/usr/bin/env python3
"""ГДЕ, НА ЧЁМ И ПОЧЕМУ ЗАТУХАЮТ ПАМПЫ — ПО ОДНОМУ, СО ВСЕМИ ДАННЫМИ СРАЗУ (07.10, владелец: «надо искать что работает а что нет… важно понять где затухают
на чем и почему и найти связи»; до этого: «ты долбишься в лоб»). Не правило по всем монетам, а досье на вершину каждого пампа последних дней:
  когда (сессия, час), где (к прежним максимумам месяца), что с шортами и лонгами (интерес в монетах до, на вершине и после; фандинг; контракт к споту),
  кто пришёл (объём к норме), что делал остальной рынок в эти же часы, что показали кластеры в вершинной свече.
Источники: кластеры с графика владельца (tvd/*_fp30.json), пульс скринера (pulse.json), дневные свечи BingX (movers_bingx_1d.json). Время UTC.
    .venv/bin/python claude/research/pump_fade.py"""
import json, glob, statistics as st, datetime as dt
from pathlib import Path
R = Path(__file__).parent; B = R.parents[1]; U = dt.timezone.utc
f = lambda t: dt.datetime.fromtimestamp(t, U).strftime("%d.%m %H:%M")
P = json.load(open(B / "pulse.json")); D1 = json.load(open(R / "movers_bingx_1d.json"))
SES = (("Токио", 0, 7), ("Лондон", 7, 13), ("Нью-Йорк", 13, 21), ("Сидней", 21, 24)); WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
PUMPS = "LONGXIA AIN CT MOVR RLC US MAGMA SAND VELVET NIGHT COLLECT BTW GRIFFAIN ORCA".split()


def near(rs, t, tol=3000):
    q = [r for r in rs if abs(r["t"] - t) <= tol and r.get("price")]
    return min(q, key=lambda r: abs(r["t"] - t)) if q else None


def board(t0, t1):
    v = []
    for s, rs in P.items():
        if s == "_meta": continue
        a, z = near(rs, t0), near(rs, t1)
        if a and z: v.append(z["price"] / a["price"] - 1)
    return st.median(v) * 100 if len(v) >= 30 else None


g = lambda v, p=1, s="": "—" if v is None else f"{v:+.{p}f}{s}"
for sym in PUMPS:
    try: d = json.load(open(R / "tvd" / f"{sym}_fp30.json"))
    except OSError: continue
    b = d["bars"]; fp = {x["i"]: x for x in d["fp"]}; n = len(b)
    T = max(range(n), key=lambda i: b[i][2]); S = min(range(max(0, T - 96), T + 1), key=lambda i: b[i][3])
    tT, tS = b[T][0] + 900, b[S][0]; hi, lo = b[T][2], b[S][3]
    dtT = dt.datetime.fromtimestamp(b[T][0], U); hh = dtT.hour + dtT.minute / 60
    ses = next(x for x in SES if x[1] <= hh < x[2])
    rs = P.get(sym + "USDT") or []
    oc = lambda r: r["oi_usd"] / r["price"] if r and r.get("oi_usd") else None
    r0, rT, r2, r8 = near(rs, tS), near(rs, tT), near(rs, tT + 7200), near(rs, tT + 8 * 3600)
    rb = near(rs, tT - 7200)
    o0, oT, o2, o8, ob = oc(r0), oc(rT), oc(r2), oc(r8), oc(rb)
    k = D1.get(sym) or []
    prev = [x[2] for x in k if x[0] < tS - 86400 and x[0] >= tS - 31 * 86400]
    ph = max(prev) if prev else None
    rng = (b[T][2] - b[T][3]) or 1e-12
    print(f"\n{sym}: ×{hi / lo:.2f} · вершина {f(b[T][0])} UTC · {WD[dtT.weekday()]} · {ses[0]}, {hh - ses[1] + 1:.0f}-й час из {ses[2] - ses[1]}" + (" · за час до смены сессии" if ses[2] - hh <= 1 else " · первый час сессии" if hh - ses[1] < 1 else ""))
    print(f"  где: к максимуму прошлых 30 дней {g((hi / ph - 1) * 100 if ph else None, 0, '%')}" + (" (вершина у прежнего максимума)" if ph and abs(hi / ph - 1) <= 0.05 else " (выше прежнего максимума)" if ph and hi > ph else " (ниже прежнего максимума)" if ph else ""))
    print(f"  интерес в монетах: за подъём ×{g(oT / o0 if oT and o0 else None, 2)[1:] if oT and o0 else '—'} · за последние 2 ч до вершины {g((oT / ob - 1) * 100 if oT and ob else None, 0, '%')} · через 2 ч после {g((o2 / oT - 1) * 100 if o2 and oT else None, 0, '%')} · через 8 ч {g((o8 / oT - 1) * 100 if o8 and oT else None, 0, '%')}")
    print(f"  фандинг: в начале {g(r0.get('funding') if r0 else None, 3)} · на вершине {g(rT.get('funding') if rT else None, 3)} · через 2 ч {g(r2.get('funding') if r2 else None, 3)} | контракт к споту на вершине {g(rT.get('basis') if rT else None, 2, '%')} | доля спота {g((rT.get('spot_share') or 0) * 100 if rT else None, 0, '%')[1:] if rT else '—'}")
    print(f"  объём часа к норме: за 2 ч до вершины ×{g(rb.get('rvol_1h') if rb else None, 1)[1:] if rb and rb.get('rvol_1h') is not None else '—'} · на вершине ×{g(rT.get('rvol_1h') if rT else None, 1)[1:] if rT and rT.get('rvol_1h') is not None else '—'} · через 2 ч ×{g(r2.get('rvol_1h') if r2 else None, 1)[1:] if r2 and r2.get('rvol_1h') is not None else '—'}")
    print(f"  рынок (медиана монет): 2 ч до вершины {g(board(tT - 7200, tT), 2, '%')} · 2 ч после {g(board(tT, tT + 7200), 2, '%')}")
    print(f"  вершинная свеча: хвост {100 * (b[T][2] - max(b[T][1], b[T][4])) / rng:.0f}% · объём на {100 * (fp[T]['poc'] - b[T][3]) / rng:.0f}% высоты · дельта {100 * (fp[T]['buy'] - fp[T]['sell']) / (b[T][5] or 1):+.0f}% · после: 2 ч {(b[min(n - 1, T + 4)][4] / hi - 1) * 100:+.0f}%, 8 ч {(b[min(n - 1, T + 16)][4] / hi - 1) * 100:+.0f}%")
