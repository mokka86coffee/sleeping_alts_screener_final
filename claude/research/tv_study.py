#!/usr/bin/env python3
"""ЧТО БЫЛО ПЕРЕД ХОДОМ ×1.5–×2+ (03.10, владелец: «смотри всех лидеров, что были, и думай, как точнее определять, что пойдёт; любые индикаторы; смотри, кто что использует»).
Данные — TradingView Desktop, дневные бары и индикаторы владельца (tv_collect.py → tvd/*_1D.json): цена, объём, Open Interest, Funding, Liquidations (лонги/шорты), Klinger.
Исход для каждого монето-дня: up50 — максимум за следующие 14 дней ≥ +50 % от закрытия; x2 — максимум за 30 дней ≥ +100 %; dd — худший минимум за 14 дней.
Признаки на день (только прошлое): флэт 7/14 дн, рост и положение в диапазоне 30/90 дн, интерес за 7/14/30 дн, фандинг 7 дн (среднее, доля дней в минусе),
ликвидации 7 дн (доля шортов), объём 3 дн к 20 дн, Klinger выше сигнала, сжатие (ширина Боллинджера 20 к своему минимуму за 60 дн).
Считает: базовую частоту, частоту по квинтилям каждого признака (отдельно первая и вторая половина периода), частоту для готовых «отпечатков», список монет с отпечатком сегодня.
Монеты моложе 180 дней на день сигнала не берём (R48). Только запись; вторая строка CLAUDE.md: закономерность из прошлого — не правило, пока не проверена вне выборки."""
import json, glob, sys, math
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
D = Path(__file__).parent / "tvd"; rows = []; today = []
def roll(a, n, fn):
    out = np.full(len(a), np.nan)
    for i in range(n - 1, len(a)): out[i] = fn(a[i - n + 1:i + 1])
    return out
for f in sorted(glob.glob(str(D / "*_1D.json"))):
    d = json.load(open(f)); b = d["bars"]
    if len(b) < 240: continue
    sym = d["sym"].split(":")[1].replace("USDT.P", ""); t = np.array([x[0] for x in b]); n = len(b)
    o, h, l, c, v = (np.array([x[j] for x in b], float) for j in (1, 2, 3, 4, 5))
    def ser(key, j):
        m = {x[0]: x[j] for x in d.get(key) or [] if len(x) > j and x[j] is not None}
        return np.array([m.get(x, np.nan) for x in t], float)
    oi = ser("oi", 1); fu = ser("fund", 1); lql = np.abs(ser("liq", 1)); lqs = np.abs(ser("liq", 2)); ko = ser("ko", 1); ks = ser("ko", 2)
    hi7 = roll(h, 7, np.max); lo7 = roll(l, 7, np.min); hi14 = roll(h, 14, np.max); lo14 = roll(l, 14, np.min); hi30 = roll(h, 30, np.max); lo30 = roll(l, 30, np.min); hi90 = roll(h, 90, np.max); lo90 = roll(l, 90, np.min)
    sma20 = roll(c, 20, np.mean); sd20 = roll(c, 20, np.std); bbw = sd20 / sma20; bbmin = roll(bbw, 60, np.nanmin)
    v3 = roll(v, 3, np.mean); v20 = roll(v, 20, np.mean); f7 = roll(fu, 7, np.nanmean); fneg = roll((fu < 0).astype(float), 7, np.mean)
    ls7 = roll(np.nan_to_num(lqs), 7, np.sum); ll7 = roll(np.nan_to_num(lql), 7, np.sum)
    for i in range(180, n):
        if not (c[i] > 0 and lo30[i] > 0): continue
        fmax14 = h[i + 1:i + 15].max() / c[i] - 1 if i + 14 < n else np.nan
        fmin14 = l[i + 1:i + 15].min() / c[i] - 1 if i + 14 < n else np.nan
        fmax30 = h[i + 1:i + 31].max() / c[i] - 1 if i + 30 < n else np.nan
        def ch(a, k): return a[i] / a[i - k] - 1 if i >= k and a[i - k] > 0 and not math.isnan(a[i]) and not math.isnan(a[i - k]) else np.nan
        r = dict(sym=sym, t=int(t[i]), c=c[i], flat7=hi7[i] / lo7[i] - 1, flat14=hi14[i] / lo14[i] - 1, grow30=hi30[i] / lo30[i], pos30=c[i] / hi30[i], pos90=(c[i] - lo90[i]) / max(hi90[i] - lo90[i], 1e-12),
                 oi7=ch(oi, 7), oi14=ch(oi, 14), oi30=ch(oi, 30), f7=f7[i], fneg=fneg[i], lsh=ls7[i] / (ls7[i] + ll7[i]) if (ls7[i] + ll7[i]) > 0 else np.nan,
                 volx=v3[i] / v20[i] if v20[i] > 0 else np.nan, ko=float(ko[i] > ks[i]) if not (math.isnan(ko[i]) or math.isnan(ks[i])) else np.nan, sq=bbw[i] / bbmin[i] if bbmin[i] > 0 else np.nan,
                 up=fmax14, dd=fmin14, x30=fmax30, lo7=lo7[i], hi7=hi7[i], age=i)
        (today if i == n - 1 else rows).append(r)
print(f"монет {len({r['sym'] for r in rows})} · монето-дней {len(rows)} · период {datetime.fromtimestamp(min(r['t'] for r in rows), timezone.utc):%d.%m.%Y}–{datetime.fromtimestamp(max(r['t'] for r in rows), timezone.utc):%d.%m.%Y}")
R = [r for r in rows if not math.isnan(r["up"])]; tmid = sorted(r["t"] for r in R)[len(R) // 2]
up = lambda g: sum(1 for r in g if r["up"] >= .5) / max(1, len(g)) * 100
x2 = lambda g: (lambda gg: sum(1 for r in gg if r["x30"] >= 1.0) / max(1, len(gg)) * 100)([r for r in g if not math.isnan(r["x30"])])
print(f"БАЗА: +50 % за 14 дн — {up(R):.2f}% монето-дней · ×2 за 30 дн — {x2(R):.2f}% · (первая половина {up([r for r in R if r['t'] < tmid]):.2f}%, вторая {up([r for r in R if r['t'] >= tmid]):.2f}%)")
print("\nПО КВИНТИЛЯМ ПРИЗНАКА: доля +50 % за 14 дн (в скобках первая/вторая половина периода)")
for k in ("flat7", "flat14", "grow30", "pos30", "pos90", "oi7", "oi14", "oi30", "f7", "fneg", "lsh", "volx", "sq", "ko"):
    g = [r for r in R if not math.isnan(r[k])]
    if len(g) < 1000: print(f"  {k}: мало данных ({len(g)})"); continue
    vals = sorted(r[k] for r in g); qs = [vals[int(len(vals) * q)] for q in (.2, .4, .6, .8)]
    if k in ("ko",): qs = [0.5]
    if k == "fneg": qs = [0.01, 0.3, 0.6, 0.99]
    out = []; lo_ = -1e18
    for q in qs + [1e18]:
        gg = [r for r in g if lo_ < r[k] <= q] if lo_ > -1e17 else [r for r in g if r[k] <= q]
        a = [r for r in gg if r["t"] < tmid]; b2 = [r for r in gg if r["t"] >= tmid]
        out.append(f"≤{q:.3g}: {up(gg):.1f}% ({up(a):.1f}/{up(b2):.1f}) n={len(gg)}" if q < 1e17 else f">{lo_:.3g}: {up(gg):.1f}% ({up(a):.1f}/{up(b2):.1f}) n={len(gg)}"); lo_ = q
    print(f"  {k:7s} " + " · ".join(out))
json.dump(dict(rows=R, today=today, tmid=tmid), open(D / "_study_rows.json", "w"))
print("\nстроки сохранены: tvd/_study_rows.json; монет с данными на сегодня:", len(today))
