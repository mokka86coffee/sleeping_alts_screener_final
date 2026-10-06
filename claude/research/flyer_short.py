#!/usr/bin/env python3
"""ИДЕЯ ВЛАДЕЛЬЦА 06.10: «как только что-то улетело — сразу шортить всё, что отросло 2–3 часа» («всё моё попадало не потому что попадало,
а потому что что-то пошло и пошли туда»). Счёт по часовым свечам TradingView (claude/research/tvd/*_60.json), обе стороны и контроль
«те же отросшие монеты в часы без улетевшей». Сделка 500 $, комиссия 0,5 $; цель/стоп 5 %, оба в одной свече — стоп. Binance не запрашивается.
    .venv/bin/python claude/research/flyer_short.py"""
import json, glob, collections, datetime as dt, statistics as st
B = {}
for f in glob.glob('claude/research/tvd/*_60.json'):
    try: d = json.load(open(f))
    except Exception: continue
    s = d['sym'].split(':')[1].replace('USDT.P', '')
    b = {int(x[0]): x for x in d['bars'] if x[4]}
    if len(b) > 200: B[s] = b
hours = sorted({t for b in B.values() for t in b})
t_lo, t_hi = hours[0], hours[-1]
print('монет', len(B), 'часов', len(hours), dt.datetime.fromtimestamp(t_lo).strftime('%d.%m'), '–', dt.datetime.fromtimestamp(t_hi).strftime('%d.%m %H:%M'))
H = 3600
def ret(s, t, k):
    b = B[s]; a, c = b.get(t - k * H), b.get(t)
    return c[4] / a[4] - 1 if a and c else None
def trade(s, t, side, hold, tp=0.05, sl=0.05):
    b = B[s]; p0 = b[t][4]; last = p0
    for i in range(1, hold + 1):
        x = b.get(t + i * H)
        if not x: break
        up, dn = x[2] / p0 - 1, x[3] / p0 - 1
        if side == -1:
            if up >= sl: return -sl * 100
            if dn <= -tp: return tp * 100
        else:
            if dn <= -sl: return -sl * 100
            if up >= tp: return tp * 100
        last = x[4]
    return side * (last / p0 - 1) * 100
def run(A, Bg, hold):
    res = {'fly': [], 'ctl': []}; seen = {}; nev = 0
    for t in hours:
        if t + hold * H > t_hi: break
        r2 = {s: ret(s, t, 2) for s in B}; fl = [s for s, r in r2.items() if r is not None and r >= A]
        new = [s for s in fl if t - seen.get(s, 0) > 12 * H]
        for s in fl: seen[s] = t
        grown = [s for s in B if s not in fl and (ret(s, t, 3) or 0) >= Bg]
        key = 'fly' if new else ('ctl' if not fl else None)
        if key is None: continue
        if new: nev += 1
        for s in grown:
            if t in B[s]: res[key].append((t, s, trade(s, t, -1, hold), trade(s, t, 1, hold)))
    return nev, res
def show(name, v):
    if not v: print(f'   {name}: нет'); return
    sh = [x[2] for x in v]; lo = [x[3] for x in v]; usd = lambda xs: sum(xs) * 5 - 0.5 * len(xs)
    wk = collections.defaultdict(list)
    for t, s, a, b in v: wk[dt.datetime.fromtimestamp(t).strftime('%W')].append(a)
    w = ' · '.join(f'{len(a)} шт {usd(a) / len(a):+.1f}$' for k, a in sorted(wk.items()))
    print(f'   {name}: сделок {len(v)} · ШОРТ в плюс {sum(1 for a in sh if a > 0) * 100 // len(sh)}% {usd(sh) / len(sh):+.1f}$ на сделку (итог {usd(sh):+.0f}$) · лонг там же {usd(lo) / len(lo):+.1f}$ · шорт по неделям: {w}')
for A in (0.15, 0.25, 0.40):
    for Bg in (0.05, 0.08, 0.12):
        for hold in (2, 4, 8):
            nev, res = run(A, Bg, hold)
            print(f'\nулетело ≥ +{A * 100:.0f}% за 2 ч · отросло ≥ +{Bg * 100:.0f}% за 3 ч · держим до {hold} ч · событий {nev}')
            show('после улетевшей', res['fly']); show('контроль (часы без улетевшей)', res['ctl'])
