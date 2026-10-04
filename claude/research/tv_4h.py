#!/usr/bin/env python3
"""4-ЧАСОВЫЕ ПРИЗНАКИ ПЕРЕД ХОДОМ (03.10; владелец: «думай, как точнее определять, что пойдёт»). Данные TradingView tvd/*_240.json, ~107 дней, все перпы (≥ 180 дней, без своего ММ).
Раз в сутки (бар 00:00 UTC) для каждой монеты: признаки за последние 24/72 ч и место на доске; исход — максимум за следующие 7 дней ≥ +30 % от закрытия (лидер недели) и медианный ход закрытия за 7 дней относительно доски.
Верхняя и нижняя десятая доски по каждому признаку, отдельно первая и вторая половина периода. Только запись."""
import json, glob, math, sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import numpy as np
D = Path(__file__).parent / "tvd"; ROOT = Path(__file__).resolve().parents[2]
try: OWN = {s for s in json.load(open(ROOT / "output" / "own_mm.json"))["coins"]}
except Exception: OWN = set()
rows = []
for f in sorted(glob.glob(str(D / "*_240.json"))):
    d = json.load(open(f)); sym = d["sym"].split(":")[1].replace(".P", ""); b = d["bars"]
    if sym in OWN or len(b) < 200: continue
    try:
        if len(json.load(open(D / Path(f).name.replace("_240.json", "_1D.json")))["bars"]) < 180: continue
    except Exception: continue
    t = [x[0] for x in b]; h = np.array([x[2] for x in b]); l = np.array([x[3] for x in b]); c = np.array([x[4] for x in b]); v = np.array([x[5] or 0 for x in b]); n = len(b)
    def ser(key, j):
        m = {x[0]: x[j] for x in d.get(key) or [] if len(x) > j and x[j] is not None}; return np.array([m.get(x, np.nan) for x in t], float)
    oi = ser("oi", 1); fu = ser("fund", 1); ll = np.nan_to_num(np.abs(ser("liq", 1))); ls = np.nan_to_num(np.abs(ser("liq", 2))); ko = ser("ko", 1); ks = ser("ko", 2)
    for i in range(84, n - 42):
        if t[i] % 86400: continue
        r = dict(sym=sym, t=t[i])
        g = lambda a, k: (a[i] / a[i - k] - 1) if a[i - k] > 0 and not (math.isnan(a[i]) or math.isnan(a[i - k])) else float("nan")
        r["mom24"] = g(c, 6); r["mom72"] = g(c, 18); r["mom7d"] = g(c, 42); r["oi24"] = g(oi, 6); r["oi72"] = g(oi, 18); r["oi7d"] = g(oi, 42)
        r["oi_px72"] = r["oi72"] - r["mom72"]; r["fund"] = fu[i]; r["fund72"] = float(np.nanmean(fu[i - 17:i + 1])) if not np.all(np.isnan(fu[i - 17:i + 1])) else float("nan")
        s24 = ls[i - 5:i + 1].sum(); l24 = ll[i - 5:i + 1].sum(); r["liq_short_share24"] = s24 / (s24 + l24) if s24 + l24 > 0 else float("nan")
        r["liq24_to_7d"] = (s24 + l24) / max(1e-9, (ls[i - 41:i + 1].sum() + ll[i - 41:i + 1].sum()) / 7)
        r["liq_short24_to_7d"] = s24 / max(1e-9, ls[i - 41:i + 1].sum() / 7) if ls[i - 41:i + 1].sum() > 0 else float("nan")
        r["liq_long24_to_7d"] = l24 / max(1e-9, ll[i - 41:i + 1].sum() / 7) if ll[i - 41:i + 1].sum() > 0 else float("nan")
        r["vol24_to_7d"] = v[i - 5:i + 1].sum() / max(1e-9, v[i - 41:i + 1].sum() / 7)
        r["range72"] = h[i - 17:i + 1].max() / l[i - 17:i + 1].min() - 1; r["range7d"] = h[i - 41:i + 1].max() / l[i - 41:i + 1].min() - 1
        r["squeeze"] = r["range72"] / r["range7d"] if r["range7d"] > 0 else float("nan"); r["pos14d"] = c[i] / h[i - 83:i + 1].max()
        r["ko_gap"] = (ko[i] - ks[i]) / (abs(ks[i]) + 1e-12) if not (math.isnan(ko[i]) or math.isnan(ks[i])) else float("nan")
        r["fw"] = c[i + 42] / c[i] - 1; r["fmax"] = h[i + 1:i + 43].max() / c[i] - 1; r["fmin"] = l[i + 1:i + 43].min() / c[i] - 1
        rows.append(r)
byd = defaultdict(list)
for r in rows: byd[r["t"]].append(r)
ds = sorted(d for d in byd if len(byd[d]) >= 200); tmid = ds[len(ds) // 2]; keys = [k for k in rows[0] if k not in ("sym", "t", "fw", "fmax", "fmin")]
print(f"монет {len({r['sym'] for r in rows})} · дней {len(ds)} · {datetime.fromtimestamp(ds[0], timezone.utc):%d.%m}–{datetime.fromtimestamp(ds[-1], timezone.utc):%d.%m} · середина {datetime.fromtimestamp(tmid, timezone.utc):%d.%m}")
res = {}
for k in keys:
    o = {}
    for part, sel in (("1", lambda d: d < tmid), ("2", lambda d: d >= tmid)):
        for end in ("hi", "lo"):
            ex = []; ld = []; bl = []; tr = []
            for d in ds:
                if not sel(d): continue
                g = [r for r in byd[d] if not math.isnan(r[k])]
                if len(g) < 100: continue
                g.sort(key=lambda r: r[k]); m = len(g) // 10; top = g[-m:] if end == "hi" else g[:m]; med = np.median([r["fw"] for r in g])
                ex.append(np.median([r["fw"] for r in top]) - med); ld.append(sum(1 for r in top if r["fmax"] >= .3) / m); bl.append(sum(1 for r in g if r["fmax"] >= .3) / len(g))
            o[part + end] = (np.mean(ex) * 100, np.mean(ld) * 100, np.mean(bl) * 100)
    res[k] = o
print("ПРИЗНАК · верхняя десятая: медианный ход 7 дн к доске 1-я/2-я половина · доля +30% за 7 дн (доска) || нижняя десятая")
for k in sorted(keys, key=lambda k: -(res[k]["1hi"][0] + res[k]["2hi"][0])):
    o = res[k]; print(f"  {k:18s} верх: {o['1hi'][0]:+5.1f}/{o['2hi'][0]:+5.1f} · +30%: {o['1hi'][1]:4.1f} ({o['1hi'][2]:.1f}) / {o['2hi'][1]:4.1f} ({o['2hi'][2]:.1f})  ||  низ: {o['1lo'][0]:+5.1f}/{o['2lo'][0]:+5.1f} · +30%: {o['1lo'][1]:4.1f} / {o['2lo'][1]:4.1f}")
