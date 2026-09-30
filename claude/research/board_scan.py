#!/usr/bin/env python3
"""ПОИСК ЗАКОНОМЕРНОСТЕЙ ПО ВСЕЙ ДОСКЕ (30.09, владелец: «ты как ИИ, который видит всю картину разом после прогона 150 монет со всеми графиками, движениями, индикаторами, должен был закономерности показать
и отклонения, а разбираешь то, что я пишу из моих же наблюдений»). Гипотез от владельца нет: ищем, что было ПЕРЕД сильными ходами вверх и вниз, и держится ли это в обеих половинах месяца.

Данные: cq_v2/intraday — 30-мин бары 175 монет, 31.08–30.09 (цена, объём, потоки тейкера фьючерсов; интерес и фандинг — только с живой записи, ~1/3 баров).
Метка: «сильный ход вверх» — максимум за следующие 24 ч от цены бара в верхних 10 % по ВСЕЙ выборке (порог = квантиль, не число из головы); «сильное падение» — минимум за 24 ч в нижних 10 %.
Выборка: по одной точке на монету раз в 6 ч (без перекрытия окон). Признаки — по монете относительно её собственной истории и относительно доски (медиана всех монет на тот же момент).
Лифт = доля сильных ходов в группе / доля по всей выборке. Устойчивость: группа в верхнем/нижнем квинтиле признака, лифт считается отдельно для первой (до 16.09) и второй половины.
Результат в claude/research/board_scan.md: только признаки, где лифт одного знака и > 1.25 (или < 0.8) в ОБЕИХ половинах и n ≥ 60 в каждой.
    .venv/bin/python claude/research/board_scan.py"""
import json, glob
from pathlib import Path
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; HERE = Path(__file__).parent
L = timezone(timedelta(hours=3))
rows = []
for p in glob.glob(str(ROOT / "cq_v2" / "intraday" / "*.jsonl")):
    for ln in open(p, encoding="utf-8"):
        try: r = json.loads(ln)
        except ValueError: continue
        if not (r.get("px") and r.get("h") and r.get("l")): continue
        fut = r.get("fut") or {}; kv = r.get("kv") or {}
        rows.append((r["sym"], r["candle"][:16], float(r["px"]), float(r["h"]), float(r["l"]), r.get("oi"), r.get("funding"), fut.get("b"), fut.get("s"), fut.get("d"), fut.get("tk"), kv.get("qv")))
df = pd.DataFrame(rows, columns=["sym", "t", "px", "h", "l", "oi", "fund", "fb", "fs", "fd", "tk", "qv"])
df["t"] = pd.to_datetime(df["t"], format="%Y-%m-%dT%H:%M", utc=True)
df = df.sort_values(["sym", "t"]).drop_duplicates(["sym", "t"]).reset_index(drop=True)
g = df.groupby("sym", sort=False)
B6, B24, B48 = 12, 48, 96
df["r6"] = g["px"].pct_change(B6); df["r24"] = g["px"].pct_change(B24); df["r48"] = g["px"].pct_change(B48)
mx = g["px"].transform(lambda s: s.rolling(B48, min_periods=40).max()); mn = g["px"].transform(lambda s: s.rolling(B48, min_periods=40).min())
df["pos48"] = (df["px"] - mn) / (mx - mn).replace(0, np.nan)                         # положение в 2-суточном диапазоне
df["dd48"] = df["px"] / mx - 1                                                          # от максимума 2 суток
vol = df["fb"].fillna(0) + df["fs"].fillna(0)
df["fd6"] = g["fd"].transform(lambda s: s.rolling(B6, min_periods=6).sum()) / vol.groupby(df["sym"]).transform(lambda s: s.rolling(B6, min_periods=6).sum()).replace(0, np.nan)   # поток тейкера за 6 ч (доля)
df["fd24"] = g["fd"].transform(lambda s: s.rolling(B24, min_periods=24).sum()) / vol.groupby(df["sym"]).transform(lambda s: s.rolling(B24, min_periods=24).sum()).replace(0, np.nan)
med48 = g["qv"].transform(lambda s: s.rolling(B48, min_periods=40).median())
df["vs"] = df["qv"] / med48.replace(0, np.nan)                                          # объём бара к медиане двух суток
df["vs6"] = g["qv"].transform(lambda s: s.rolling(B6, min_periods=6).sum()) / (med48 * B6).replace(0, np.nan)
df["oi6"] = g["oi"].pct_change(B6); df["oi24"] = g["oi"].pct_change(B24)
df["fund_l"] = df["fund"]; df["fund_d"] = df["fund"] - g["fund"].shift(B6)
# доска
for c in ("r6", "r24"):
    df["b_" + c] = df.groupby("t")[c].transform("median")
df["rel24"] = df["r24"] - df["b_r24"]; df["rel6"] = df["r6"] - df["b_r6"]
df["brd_dn_share"] = df.groupby("t")["r24"].transform(lambda s: (s < 0).mean())         # доля монет в минусе за 24 ч
tl = df["t"].dt.tz_convert(L); df["hour"] = tl.dt.hour; df["wd"] = tl.dt.weekday
# метки — вперёд на 24 ч
df["fwd_max"] = g["h"].transform(lambda s: s[::-1].rolling(B24, min_periods=40).max()[::-1].shift(-1)) / df["px"] - 1
df["fwd_min"] = g["l"].transform(lambda s: s[::-1].rolling(B24, min_periods=40).min()[::-1].shift(-1)) / df["px"] - 1
S = df[(df["t"].dt.hour % 6 == 0) & (df["t"].dt.minute == 0)].dropna(subset=["fwd_max", "fwd_min", "r24", "pos48"]).copy()
qu, qd = S["fwd_max"].quantile(0.9), S["fwd_min"].quantile(0.1)
S["up"] = S["fwd_max"] >= qu; S["dn"] = S["fwd_min"] <= qd
mid = pd.Timestamp("2026-09-16", tz="UTC"); S["half"] = np.where(S["t"] < mid, 1, 2)
print(f"точек {len(S)} | монет {S['sym'].nunique()} | 1-я половина {int((S.half == 1).sum())}, 2-я {int((S.half == 2).sum())} | порог сильного хода вверх ≥ {qu * 100:.1f}% за 24 ч, вниз ≤ {qd * 100:.1f}% | базовые доли: вверх {S['up'].mean() * 100:.1f}%, вниз {S['dn'].mean() * 100:.1f}%")
feats = {"r6": "ход цены за 6 ч", "r24": "ход цены за 24 ч", "r48": "ход цены за 48 ч", "pos48": "положение в диапазоне 2 сут (0 низ … 1 верх)", "dd48": "от максимума 2 сут", "fd6": "поток тейкера фьючерсов за 6 ч (покупки−продажи)",
         "fd24": "поток тейкера фьючерсов за 24 ч", "vs": "объём бара к медиане 2 сут", "vs6": "объём 6 ч к медиане 2 сут", "rel24": "ход за 24 ч минус доска", "rel6": "ход за 6 ч минус доска",
         "b_r24": "доска: медиана хода за 24 ч", "b_r6": "доска: медиана хода за 6 ч", "brd_dn_share": "доля монет в минусе за 24 ч", "oi6": "интерес за 6 ч", "oi24": "интерес за 24 ч",
         "fund_l": "фандинг", "fund_d": "изменение фандинга за 6 ч"}
out = []
for f, lab in feats.items():
    X = S.dropna(subset=[f])
    if len(X) < 500: continue
    q = X[f].quantile([0.2, 0.8]).values
    for name, mask in (("нижний квинтиль", X[f] <= q[0]), ("верхний квинтиль", X[f] >= q[1])):
        for target in ("up", "dn"):
            res = []
            for h in (1, 2):
                Y = X[X.half == h]; base = Y[target].mean(); grp = Y[mask.reindex(Y.index, fill_value=False)]
                res.append((len(grp), grp[target].mean() / base if len(grp) else np.nan))
            (n1, l1), (n2, l2) = res
            if n1 >= 60 and n2 >= 60 and ((l1 > 1.25 and l2 > 1.25) or (l1 < 0.8 and l2 < 0.8)):
                grp = X[mask]; out.append(dict(feat=lab, q=name, target="вверх" if target == "up" else "вниз", n=len(grp), l1=l1, l2=l2, rate=grp[target].mean() * 100,
                                                lo=(q[0] if name.startswith("н") else q[1])))
out.sort(key=lambda d: -min(d["l1"], d["l2"]) if d["l1"] > 1 else min(d["l1"], d["l2"]) + 5)
md = [f"# Поиск закономерностей по всей доске ({datetime.now(L):%d.%m %H:%M})", "",
      f"Данные: 175 монет, 30-мин бары 31.08–30.09; {len(S)} точек (по одной на монету раз в 6 ч). Сильный ход — верхние 10% максимума за 24 ч (≥ {qu * 100:.1f}%), сильное падение — нижние 10% минимума (≤ {qd * 100:.1f}%). "
      f"База: вверх {S['up'].mean() * 100:.1f}%, вниз {S['dn'].mean() * 100:.1f}%. Лифт — во сколько раз чаще базы; показаны признаки, где лифт одного знака в ОБЕИХ половинах месяца (до/после 16.09), n ≥ 60 в каждой.", "",
      "| что впереди | признак и квинтиль | порог | n | лифт 1-я половина | лифт 2-я половина | доля |", "|---|---|---|---|---|---|---|"]
for d in out:
    md.append(f"| {d['target']} | {d['feat']} — {d['q']} | {d['lo']:.3g} | {d['n']} | ×{d['l1']:.2f} | ×{d['l2']:.2f} | {d['rate']:.0f}% |")
if not out: md.append("| — | ни один признак не держится в обеих половинах | | | | | |")
# время суток и день недели — тем же методом
md += ["", "## Время суток и день недели (UTC+3), лифт по половинам", "", "| группа | n | вверх 1 | вверх 2 | вниз 1 | вниз 2 |", "|---|---|---|---|---|---|"]
S["hg"] = pd.cut(S["hour"], [-1, 2, 6, 9, 12, 15, 19, 23], labels=["00–03", "03–07", "07–10", "10–13", "13–16", "16–20", "20–24"])
for key, lab in (("hg", "час"), ("wd", "день")):
    for v in sorted(S[key].dropna().unique(), key=lambda x: str(x)):
        cells = []
        for target in ("up", "dn"):
            for h in (1, 2):
                Y = S[S.half == h]; base = Y[target].mean(); grp = Y[Y[key] == v]
                cells.append(f"×{grp[target].mean() / base:.2f}" if len(grp) >= 40 else "—")
        md.append(f"| {lab} {(['пн','вт','ср','чт','пт','сб','вс'][int(v)] if key == 'wd' else v)} | {int((S[key] == v).sum())} | " + " | ".join(cells) + " |")
(HERE / "board_scan.md").write_text("\n".join(md) + "\n", encoding="utf-8")
S.to_pickle(HERE / "board_scan_samples.pkl")
print("\n".join(md[:60]))
