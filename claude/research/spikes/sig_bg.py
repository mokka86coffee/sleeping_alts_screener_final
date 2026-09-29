#!/usr/bin/env python3
"""ФОН И ИТОГ ПО КАЖДОМУ СИГНАЛУ КАНАЛА (цифры Coinglass Binance: 1D 90 дн, 6h 7 дн, 15m сутки; те же, что trade_facts.py для сделок бота).
Итог сигнала: за 4 ч после бара поста — макс вверх / мин вниз / закрытие и что раньше, +5% или −5%. → sig_bg.json / sig_bg.md"""
import json, statistics as st
from pathlib import Path
from datetime import datetime, timezone, timedelta
H = Path(__file__).parent; CGX = H.parent / "cgx"; L = timezone(timedelta(hours=3))
def cl(v): return v if isinstance(v, (int, float)) and v == v else None
def load(sym, tf):
    f = CGX / f"{sym}_{tf}.json"
    if not f.exists(): return []
    R = [r for r in json.load(open(f))["rows"] if r.get("c")]
    for r in R:
        for k in ("liq_long", "liq_short", "basis", "fund", "cvd_f", "cvd_s", "oi"): r[k] = cl(r.get(k))
    return R
def at(R, t, k):
    v = [r[k] for r in R if r["t"] < t and r.get(k) is not None]
    return v[-1] if v else None
B = []
for f in sorted(H.glob("sig_[0-9]*.json")): B += json.load(open(f))
out = []
for x in B:
    s, t0, e = x["sym"], x["t_in"], x["px_in"]
    M, D, H6 = load(s, "15"), load(s, "1D"), load(s, "360")
    W = [r for r in M if t0 < r["t"] <= t0 + 4 * 3600]
    if len(W) < 8 or not D: continue
    f = dict(tid=f"{s[:-4]}_{datetime.fromtimestamp(t0, L):%H%M}", sym=s[:-4], hhmm=f"{datetime.fromtimestamp(t0, L):%H:%M}", lab=x["label"].replace("СИГНАЛ ", ""), px=e)
    d90 = [r for r in D if t0 - 90 * 86400 <= r["t"] < t0]
    f["x90"] = round(e / min(r["l"] for r in d90), 2); f["hi90"] = round((e / max(r["h"] for r in d90) - 1) * 100, 1)
    d30 = [r for r in D if r["t"] < t0 - 30 * 86400]; f["ch30"] = round((e / d30[-1]["c"] - 1) * 100, 1) if d30 else None
    for k in ("cvd_f", "cvd_s"):
        a, b = at(H6, t0 - 7 * 86400, k), at(H6, t0, k); f[k + "7"] = None if a is None or b is None else (1 if b > a else -1)
    f["up"] = round((max(r["h"] for r in W) / e - 1) * 100, 1); f["dn"] = round((min(r["l"] for r in W) / e - 1) * 100, 1); f["cl"] = round((W[-1]["c"] / e - 1) * 100, 1)
    f["first"] = next(("+5" if r["h"] >= e * 1.05 else "-5" for r in W if r["h"] >= e * 1.05 or r["l"] <= e * 0.95), "нет")
    hs = {}
    for r in M:
        h = int(r["t"] // 3600 * 3600); a = hs.setdefault(h, [0.0, 0.0]); a[0] += r["liq_long"] or 0; a[1] += r["liq_short"] or 0
    h0 = int(t0 // 3600 * 3600); past = [v for h, v in hs.items() if h < h0]
    tl = max((v[0] for v in past), default=0); ts = max((v[1] for v in past), default=0)
    f["short_flush_now"] = bool(ts and hs.get(h0, [0, 0])[1] >= ts)          # на часе поста вынос шортов ≥ крупнейшего часа истории
    f["long_flush_pre"] = bool(tl and max((hs.get(h0 - k * 3600, [0, 0])[0] for k in range(1, 7)), default=0) >= tl)   # за 6 ч до — вынос лонгов ≥ крупнейшего часа
    day = [r for r in M if t0 - 86400 <= r["t"] < t0]
    fu = [r["fund"] for r in day if r.get("fund") is not None]; f["fund"] = round(st.median(fu) * 100, 4) if fu else None
    oi = [r["oi"] for r in M if r["t"] < t0 and r.get("oi")]; f["oi1h"] = round((oi[-1] / oi[-5] - 1) * 100, 1) if len(oi) > 5 else None
    out.append(f)
json.dump(out, open(H / "sig_bg.json", "w"), ensure_ascii=False, indent=0)
print(len(out))
