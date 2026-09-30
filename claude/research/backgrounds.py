#!/usr/bin/env python3
"""ФОНЫ ПО ВСЕМ ЗАКРЫТЫМ СДЕЛКАМ (30.09, владелец: «правило не убиваем и не меняем — УВЕЛИЧИВАЕМ ТОЧНОСТЬ: если 20 сделок из 100 сработали, правило есть; берём ВСЕ известные фоны
(недельный ТФ монеты: вынос, пила, флэт; лидер; выходные, сессия, биткоин, медиана доски, risk on/off) и смотрим, где правило работает; нет фона — пишем, что в этот день/время не работает»).

Только запись: правила и ворота бота не трогаются. Каждая сделка (обе книги, без двойников по монете+минуте входа) × фоны на момент входа:
  монета (дневки/часовки Coinglass-выгрузки cgx): интерес за 3 и 7 дн, цена за 7 дн и 24 ч, положение в диапазоне 30 дн, вынос лонгов/шортов за 7 дн (один из 3 крупнейших дней за 30 дн — по своей истории монеты),
      «флэт с падающим интересом» (движение за 7 дн меньше медианы по всем сделкам и интерес за 3 дн падает), фандинг на входе;
  доска и лидер: запись бота на входе (board24, board6, ход лидера за 48 ч), пачка/BTC (с 30.09 18:03);
  BTC: ход за 24 ч и за 1 ч на входе (часовки Binance);
  время: день недели, сессия (UTC+3).
Группы n < 10 — «мало». Устойчивость: доля в плюсе в первой и второй половине сделок по времени. Результат: backgrounds.md. Не проверено вне выборки.
    .venv/bin/python claude/research/backgrounds.py"""
import json, urllib.request, statistics as st
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]; R = Path(__file__).parent
L = timezone(timedelta(hours=3))
WD = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
SES = (("Сидней", 0, 3), ("Токио", 3, 10), ("Лондон", 10, 16), ("Нью-Йорк", 16, 24))
tr = json.load(open(R / "cgr" / "trades.json"))
seen = set(); T = []
for t in sorted(tr, key=lambda t: t["t_in"]):
    k = (t["sym"], round(t["t_in"] / 300))
    if k in seen: continue
    seen.add(k); T.append(t)
# запись входа бота: fon, pack, btc
ent = []
for f in ("paper_fast3", "paper_wake"):
    for l in open(ROOT / "output" / f"{f}.jsonl", encoding="utf-8"):
        try: r = json.loads(l)
        except ValueError: continue
        if r.get("kind") == "entry": ent.append(r)
def fon_of(t):
    for e in ent:
        if e["sym"] == t["sym"] and abs(e["at"] - t["t_in"]) < 300: return e.get("fon") or {}, e
    return {}, {}
# BTC часовки
def get(u):
    for _ in range(3):
        try: return json.load(urllib.request.urlopen(u, timeout=25))
        except Exception: pass
    return []
t0 = min(t["t_in"] for t in T) - 30 * 3600
bk = get(f"https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1h&startTime={int(t0 * 1000)}&limit=1000")
btc = [(int(x[0]) / 1000, float(x[4])) for x in bk]
def btc_ch(t, h):
    a = [p for s, p in btc if s + 3600 <= t]
    return None if len(a) <= h else (a[-1] / a[-1 - h] - 1) * 100
cache = {}
def rows(sym, f):
    k = (sym, f)
    if k not in cache:
        try: cache[k] = json.load(open(R / "cgx" / f"{sym}_{f}.json"))["rows"]
        except Exception: cache[k] = None
    return cache[k]
X = []
for t in T:
    s = t["sym"]; d1 = rows(s, "1D"); h1 = rows(s, "60")
    if not d1: continue
    D = [r for r in d1 if r["t"] + 86400 <= t["t_in"]]
    if len(D) < 32: continue
    o = [r["oi"] for r in D]; c = [r["c"] for r in D]
    fo, e = fon_of(t)
    x = dict(sym=s[:-4], side=t["side"], book=t["book"], usd=t["res"] * 10, res=t["res"], tin=t["t_in"])
    x["oi3"] = (o[-1] / o[-4] - 1) * 100 if o[-4] else None; x["oi7"] = (o[-1] / o[-8] - 1) * 100 if o[-8] else None
    x["r7"] = (c[-1] / c[-8] - 1) * 100; x["r24"] = (c[-1] / c[-2] - 1) * 100
    hi = max(r["h"] for r in D[-30:]); lo = min(r["l"] for r in D[-30:]); x["pos30"] = (c[-1] - lo) / (hi - lo) if hi > lo else None
    for side, key in (("л", "liq_long"), ("ш", "liq_short")):
        v = [r[key] for r in D[-30:] if r[key] == r[key]]
        if len(v) >= 20:
            top3 = sorted(v, reverse=True)[:3]; last7 = [r[key] for r in D[-7:] if r[key] == r[key]]
            x["flush_" + side] = bool(last7) and max(last7) >= top3[-1]
    hh = [r for r in (h1 or []) if r["t"] + 3600 <= t["t_in"]]
    x["fund"] = hh[-1]["fund"] if hh and hh[-1]["fund"] == hh[-1]["fund"] else None
    x["board24"] = fo.get("board24"); x["board6"] = fo.get("board6"); x["lead"] = fo.get("leader_run48")
    x["btc24"] = btc_ch(t["t_in"], 24); x["btc1"] = btc_ch(t["t_in"], 1)
    d = datetime.fromtimestamp(t["t_in"], L); x["wd"] = WD[d.weekday()]; x["ses"] = next(n for n, a, b in SES if a <= d.hour < b)
    X.append(x)
med7 = st.median(abs(x["r7"]) for x in X)
for x in X: x["flat"] = (abs(x["r7"]) < med7 and x["oi3"] is not None and x["oi3"] < 0)
print(len(T), "сделок,", len(X), "с историей монеты")
mid = sorted(x["tin"] for x in X)[len(X) // 2]
def cell(g):
    if len(g) < 10: return f"n={len(g)} — мало"
    a = [x for x in g if x["tin"] < mid]; b = [x for x in g if x["tin"] >= mid]
    hf = lambda z: "—" if len(z) < 5 else f"{sum(1 for x in z if x['usd'] > 0) * 100 // len(z)}%"
    return f"n={len(g)} · плюс {sum(1 for x in g if x['usd'] > 0) * 100 // len(g)}% · ≥+4.5%: {sum(1 for x in g if x['res'] >= 4.5)} · сумма {sum(x['usd'] for x in g):.0f} $ · половины {hf(a)}/{hf(b)}"
def split(feat, cuts=None, labels=None):
    out = []
    vals = [x[feat] for x in X if x.get(feat) is not None]
    if cuts is None and vals and not isinstance(vals[0], (bool, str)):
        q = st.quantiles(vals, n=3); cuts = q; labels = ["нижняя треть", "средняя треть", "верхняя треть"]
        out = [(labels[0] + f" (<{q[0]:.3g})", [x for x in X if x.get(feat) is not None and x[feat] < q[0]]),
               (labels[1], [x for x in X if x.get(feat) is not None and q[0] <= x[feat] < q[1]]),
               (labels[2] + f" (≥{q[1]:.3g})", [x for x in X if x.get(feat) is not None and x[feat] >= q[1]])]
    else:
        for v in sorted({x.get(feat) for x in X if x.get(feat) is not None}, key=str): out.append((str(v), [x for x in X if x.get(feat) == v]))
    return out
names = [("oi3", "интерес монеты за 3 дн"), ("oi7", "интерес монеты за 7 дн"), ("r7", "цена монеты за 7 дн"), ("r24", "цена монеты за сутки (дневка до входа)"), ("pos30", "положение в диапазоне 30 дн"),
         ("flush_л", "за 7 дн был вынос лонгов (топ-3 дня из 30)"), ("flush_ш", "за 7 дн был вынос шортов (топ-3 дня из 30)"), ("flat", "флэт с падающим интересом"), ("fund", "фандинг на входе"),
         ("board24", "доска: медиана за 24 ч"), ("board6", "доска: медиана за 6 ч"), ("lead", "ход лидера за 48 ч"), ("btc24", "BTC за 24 ч"), ("btc1", "BTC за 1 ч"), ("wd", "день недели"), ("ses", "сессия")]
md = [f"# Фоны по всем закрытым сделкам ({datetime.now(L):%d.%m %H:%M})", "",
      f"Сделок {len(X)} (27.09–30.09, обе книги, без двойников). Правило (вход по всплеску) НЕ меняется; таблица — где оно работало и где нет. «Половины» — доля в плюсе по времени, первая/вторая. n < 10 — мало. Не проверено вне выборки.", ""]
for side, nm in ((1, "ЛОНГИ"), (-1, "ШОРТЫ")):
    S = [x for x in X if x["side"] == side]
    md += [f"## {nm}: {cell(S)}", ""]
    X_all = X; X = S
    for feat, lab in names:
        md.append(f"**{lab}**"); md.append("")
        for k, g in split(feat): md.append(f"- {k}: {cell(g)}")
        md.append("")
    X = X_all
(R / "backgrounds.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print("\n".join(md[:80]))
