#!/usr/bin/env python3
"""РУКА ММ ПО ИСТОРИИ (30.09, владелец: «индикаторы показывают ИСТОРИЮ, они не скажут, где брать; по ним надо смотреть, почему рука ММ, которая тянет монету, действует именно так и на что смотрит,
где ходы — конец тренда, а где просто слив плечей»). Не поиск сигнала входа, а разбор устройства хода: что происходило с ПОЗИЦИЯМИ (интерес в контрактах) во время хода и что было накоплено ДО него.

По всем сильным падениям и ростам доски за месяц (30-мин бары 175 монет, 31.08–30.09): падение — цена ушла от максимума за 24 ч на ≤ порога, рост — от минимума за 24 ч на ≥ порога (пороги — верхние 10 % ходов по
всей выборке, не числа из головы). По каждому ходу: интерес Binance (контракты, шаг 2 ч) на вершине/низе, во время хода и через сутки, фандинг за сутки до хода, перекос счетов (лонги/шорты) до хода;
исход: какую долю хода цена вернула за следующие 24 ч. Типы не заданы заранее — смотрим, как связаны «что стало с позициями во время хода» и «что цена сделала потом».
    .venv/bin/python claude/research/mm_hand.py     → mm_hand.md, mm_hand.pkl"""
import json, glob, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
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
        if r.get("px") and r.get("h") and r.get("l"): rows.append((r["sym"], r["candle"][:16], float(r["px"]), float(r["h"]), float(r["l"])))
df = pd.DataFrame(rows, columns=["sym", "t", "px", "h", "l"]); df["t"] = pd.to_datetime(df["t"], format="%Y-%m-%dT%H:%M", utc=True)
df = df.sort_values(["sym", "t"]).drop_duplicates(["sym", "t"]).reset_index(drop=True)
B24 = 48
g = df.groupby("sym", sort=False)
df["mx24"] = g["h"].transform(lambda s: s.rolling(B24, min_periods=24).max()); df["mn24"] = g["l"].transform(lambda s: s.rolling(B24, min_periods=24).min())
df["dd"] = df["l"] / df["mx24"] - 1; df["ru"] = df["h"] / df["mn24"] - 1
qd, qu = df["dd"].quantile(0.02), df["ru"].quantile(0.98)                # 2 % баров с самым сильным ходом внутри окна 24 ч (эпизоды ниже — по одному на ход)
print(f"порог падения от максимума 24 ч: {qd * 100:.1f}% | порог роста от минимума 24 ч: {qu * 100:.1f}%")
def episodes(kind):
    out = []
    for sym, d in df.groupby("sym"):
        d = d.reset_index(drop=True)
        hit = d.index[(d["dd"] <= qd) if kind == "dn" else (d["ru"] >= qu)].tolist()
        last = -999
        for i in hit:
            if i - last < 48: continue                                  # один эпизод на монету раз в сутки
            last = i
            w = d.iloc[max(0, i - 48):i + 1]
            if kind == "dn":
                ip = w["h"].idxmax(); pk = d.loc[ip, "h"]; tr = d.loc[i, "l"]; it = i
            else:
                ip = w["l"].idxmin(); pk = d.loc[ip, "l"]; tr = d.loc[i, "h"]; it = i
            after = d.iloc[i + 1:i + 49]
            if len(after) < 40: continue
            rec = ((after["h"].max() - tr) / (pk - tr)) if kind == "dn" else ((tr - after["l"].min()) / (tr - pk))       # доля хода, которую цена вернула за следующие 24 ч
            out.append(dict(sym=sym, kind=kind, t_start=d.loc[ip, "t"], t_end=d.loc[it, "t"], p0=pk, p1=tr, move=(tr / pk - 1) * 100, ret=rec, close24=(after["px"].iloc[-1] / tr - 1) * 100))
    return pd.DataFrame(out)
E = pd.concat([episodes("dn"), episodes("up")], ignore_index=True)
print("эпизодов:", len(E), E.groupby("kind").size().to_dict(), "монет:", E["sym"].nunique())

def get(url):
    for _ in range(3):
        try: return json.load(urllib.request.urlopen(url, timeout=20))
        except Exception: time.sleep(1)
    return None
def series(sym):
    oi = get(f"https://fapi.binance.com/futures/data/openInterestHist?symbol={sym}&period=2h&limit=500") or []
    fr = get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&limit=200") or []
    lsr = get(f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={sym}&period=4h&limit=200") or []
    return sym, dict(oi=[(int(x["timestamp"]), float(x["sumOpenInterest"])) for x in oi], fr=[(int(x["fundingTime"]), float(x["fundingRate"])) for x in fr],
                     lsr=[(int(x["timestamp"]), float(x["longShortRatio"])) for x in lsr])
syms = sorted(E["sym"].unique())
with ThreadPoolExecutor(8) as ex: SER = dict(ex.map(series, syms))
def near(lst, t, side=0):
    """значение ряда ближе всего к моменту t (мс)"""
    if not lst: return None
    k = min(range(len(lst)), key=lambda j: abs(lst[j][0] - t))
    return lst[k][1] if abs(lst[k][0] - t) <= 5 * 3600_000 else None
res = []
for _, e in E.iterrows():
    s = SER.get(e["sym"]);
    if not s or not s["oi"]: res.append({}); continue
    t0 = int(e["t_start"].timestamp() * 1000); t1 = int(e["t_end"].timestamp() * 1000)
    o0, o1, o_pre, o_post = near(s["oi"], t0), near(s["oi"], t1), near(s["oi"], t0 - 24 * 3600_000), near(s["oi"], t1 + 24 * 3600_000)
    f = [v for t, v in s["fr"] if t0 - 24 * 3600_000 <= t <= t0]
    lr = near(s["lsr"], t0)
    res.append(dict(oi_move=None if not (o0 and o1) else (o1 / o0 - 1) * 100, oi_pre=None if not (o0 and o_pre) else (o0 / o_pre - 1) * 100,
                    oi_after=None if not (o1 and o_post) else (o_post / o1 - 1) * 100, fund_pre=None if not f else float(np.mean(f)) * 100, lsr_pre=lr))
E = pd.concat([E, pd.DataFrame(res)], axis=1)
E.to_pickle(HERE / "mm_hand.pkl")
E = E.dropna(subset=["oi_move"])
print("эпизодов с интересом:", len(E))
md = [f"# Рука ММ по истории: что стало с позициями во время хода ({datetime.now(L):%d.%m %H:%M})", "",
      f"Эпизодов с данными интереса: {len(E)} (падений {int((E.kind == 'dn').sum())}, ростов {int((E.kind == 'up').sum())}), 174 монеты, 31.08–30.09. Падение — от максимума 24 ч на ≤ {qd * 100:.1f}%, рост — от минимума на ≥ +{qu * 100:.1f}% (2 % самых сильных баров, один эпизод на монету в сутки). "
      "«Вернула» — какая доля хода отыграна за следующие 24 ч (1.0 — всё, 0 — ничего). Интерес — в контрактах (без цены).", ""]
def table(kind, title):
    D = E[E.kind == kind].copy()
    md.append(f"## {title} ({len(D)})"); md.append("")
    D["g"] = pd.qcut(D["oi_move"], 3, labels=["позиции сильно закрылись", "средне", "позиции остались/выросли"] if kind == "dn" else ["позиции закрылись", "средне", "позиции выросли"])
    md += ["| что стало с интересом во время хода | эпизодов | интерес во время хода | вернула за 24 ч (медиана) | закрытие через 24 ч от низа/верха хода | фандинг за сутки до | перекос счетов лонг/шорт до | интерес за сутки ДО хода |", "|---|---|---|---|---|---|---|---|"]
    for k, x in D.groupby("g", observed=True):
        md.append(f"| {k} | {len(x)} | {x['oi_move'].median():+.1f}% | {x['ret'].median():.2f} | {x['close24'].median():+.1f}% | {x['fund_pre'].median():+.3f}% | {x['lsr_pre'].median():.2f} | {x['oi_pre'].median():+.1f}% |")
    md.append("")
    c = D[["oi_move", "ret"]].corr(method="spearman").iloc[0, 1]
    md.append(f"Связь «интерес во время хода → доля возврата» (ранговая корреляция): {c:+.2f}"); md.append("")
    return D
Dd = table("dn", "Сильные падения"); Du = table("up", "Сильные росты")
(HERE / "mm_hand.md").write_text("\n".join(md) + "\n", encoding="utf-8"); print("\n".join(md))
