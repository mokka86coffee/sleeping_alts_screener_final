#!/usr/bin/env python3
"""КТО СТАНОВИТСЯ ЛИДЕРОМ: отбор внутри доски, без влияния общего рынка (03.10, владелец: «смотри всех лидеров, что были, и думай, как точнее определять, что пойдёт»).
Проблема прошлых счётов: всё решал режим рынка (первая половина периода — любой лонг в минус, вторая — в плюс). Здесь на каждый день все монеты ранжируются между собой.
Для каждого признака: берём десятую часть доски с самым высоким (и самым низким) значением в этот день и считаем, насколько её будущий ход отличается от медианы доски в ТОТ ЖЕ день:
  ex14 — разница медианного хода закрытия за 14 дн; ld — доля монет, давших +50 % по максимуму за 14 дн (в скобках такая же доля по всей доске).
Отдельно первая и вторая половина периода: признак годен, только если знак совпадает в обеих. Данные TradingView (tvd/*_1D.json). Только запись."""
import json, math, sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from tv_rules import load, roll, ch, D
def feats(F, i, B):
    c, h, l, v, oi = F["c"], F["h"], F["l"], F["v"], F["oi"]; t = int(F["t"][i]); n = lambda x: float("nan") if x is None else x
    r = {}
    r["mom7"] = ch(c, i, 7); r["mom30"] = ch(c, i, 30); r["mom90"] = ch(c, i, 90)
    r["rs7"] = r["mom7"] - B.get((t, 7), float("nan")); r["rs30"] = r["mom30"] - B.get((t, 30), float("nan"))
    r["flat7"] = F["hi7"][i] / F["lo7"][i] - 1; r["flat14"] = F["hi14"][i] / F["lo14"][i] - 1
    r["pos30"] = c[i] / F["hi30"][i]; r["pos90"] = c[i] / F["hi90"][i]; r["up_from_lo90"] = c[i] / F["lo90"][i] - 1
    r["grow30"] = F["hi30"][i] / F["lo30"][i]
    r["oi7"] = ch(oi, i, 7); r["oi14"] = ch(oi, i, 14); r["oi30"] = ch(oi, i, 30)
    r["oi_minus_px14"] = r["oi14"] - ch(c, i, 14)                       # интерес растёт быстрее цены
    r["f7"] = F["f7"][i]; r["f3"] = F["f3"][i]; r["fneg7"] = F["fneg7"][i]
    s = F["ls7"][i] + F["ll7"][i]; r["liq_short_share7"] = F["ls7"][i] / s if s > 0 else float("nan")
    r["liq_to_oi7"] = s / (oi[i]) if oi[i] > 0 else float("nan")        # сколько вынесли за неделю относительно интереса (в монетах/монетах или $/монеты — только ранг)
    r["vol3_20"] = np.mean(v[i - 2:i + 1]) / F["v20"][i] if F["v20"][i] > 0 else float("nan")
    r["vol_day"] = v[i] / F["v20"][i - 1] if F["v20"][i - 1] > 0 else float("nan")
    r["turn"] = np.mean(v[i - 6:i + 1]) / oi[i] if oi[i] > 0 else float("nan")   # оборот к интересу
    r["sq"] = F["bbw"][i] / F["bbmin"][i] if F["bbmin"][i] > 0 else float("nan"); r["atr"] = F["atr"][i]
    r["ko_gap"] = (F["ko"][i] - F["ks"][i]) / (abs(F["ks"][i]) + 1e-12); r["ko_up7"] = float(F["ko"][i] > F["ko"][i - 7])
    r["day"] = c[i] / c[i - 1] - 1
    return r
def main():
    C = load(); days = defaultdict(list)
    # ход доски: медиана по монетам
    allt = sorted({int(t) for F in C.values() for t in F["t"]}); B = {}
    for k in (7, 30):
        acc = defaultdict(list)
        for F in C.values():
            for i in range(k, F["n"]):
                if F["c"][i - k] > 0: acc[int(F["t"][i])].append(F["c"][i] / F["c"][i - k] - 1)
        for t, a in acc.items(): B[(t, k)] = float(np.median(a))
    rows = []; today = []
    for sym, F in C.items():
        n = F["n"]
        for i in range(180, n):
            r = feats(F, i, B); r["sym"] = sym; r["t"] = int(F["t"][i]); r["c"] = float(F["c"][i])
            if i + 14 < n:
                r["fw"] = F["c"][i + 14] / F["c"][i] - 1; r["fmax"] = F["h"][i + 1:i + 15].max() / F["c"][i] - 1; r["fmin"] = F["l"][i + 1:i + 15].min() / F["c"][i] - 1
                rows.append(r)
            elif i == n - 1: today.append(r)
    byd = defaultdict(list)
    for r in rows: byd[r["t"]].append(r)
    ds = sorted(d for d in byd if len(byd[d]) >= 100); tmid = ds[len(ds) // 2]
    print(f"монет {len(C)} · дней {len(ds)} · {datetime.fromtimestamp(ds[0], timezone.utc):%d.%m.%Y}–{datetime.fromtimestamp(ds[-1], timezone.utc):%d.%m.%Y} · середина {datetime.fromtimestamp(tmid, timezone.utc):%d.%m.%Y}")
    keys = [k for k in rows[0] if k not in ("sym", "t", "c", "fw", "fmax", "fmin")]
    res = {}
    for k in keys:
        out = {}
        for part, sel in (("1", lambda d: d < tmid), ("2", lambda d: d >= tmid)):
            for end in ("hi", "lo"):
                ex = []; ld = []; bl = []
                for d in ds:
                    if not sel(d): continue
                    g = [r for r in byd[d] if not math.isnan(r[k])]
                    if len(g) < 100: continue
                    g.sort(key=lambda r: r[k]); m = len(g) // 10; top = g[-m:] if end == "hi" else g[:m]
                    med = np.median([r["fw"] for r in g]); ex.append(np.median([r["fw"] for r in top]) - med)
                    ld.append(sum(1 for r in top if r["fmax"] >= .5) / m); bl.append(sum(1 for r in g if r["fmax"] >= .5) / len(g))
                out[part + end] = (np.mean(ex) * 100 if ex else float("nan"), np.mean(ld) * 100 if ld else float("nan"), np.mean(bl) * 100 if bl else float("nan"))
        res[k] = out
    print("\nПРИЗНАК · верхняя десятая: ex14 1-я/2-я половина, доля +50% (доска) 1-я/2-я || нижняя десятая: то же")
    for k in sorted(keys, key=lambda k: -(min(res[k]["1hi"][1] / max(res[k]["1hi"][2], 1e-9), res[k]["2hi"][1] / max(res[k]["2hi"][2], 1e-9)))):
        o = res[k]
        print(f"  {k:17s} верх: ex {o['1hi'][0]:+5.1f}/{o['2hi'][0]:+5.1f} · +50%: {o['1hi'][1]:4.1f} ({o['1hi'][2]:.1f}) / {o['2hi'][1]:4.1f} ({o['2hi'][2]:.1f})  ||  низ: ex {o['1lo'][0]:+5.1f}/{o['2lo'][0]:+5.1f} · +50%: {o['1lo'][1]:4.1f} / {o['2lo'][1]:4.1f}")
    json.dump(dict(rows=rows, today=today, tmid=tmid), open(D / "_leaders_rows.json", "w"))
if __name__ == "__main__": main()
