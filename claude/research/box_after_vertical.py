"""БОКОВИК ПОСЛЕ ВЕРТИКАЛИ — КУДА ВЫЙДЕТ (26.09, по кадру DEXE из видео Щукина: боковик после вертикали при растущем интересе — раздача (шорт) или набор
против толпы (лонг)? Нюанс: на чьей стороне толпа и кто теряет деньги).
Данные: получасовки cq_v2/hist/tops (цена), Binance futures/data за 30 дней: openInterestHist (интерес), globalLongShortAccountRatio (толпа по счетам),
takerlongshortRatio (агрессор), klines (объём в $). Мерки разметки, не правила:
  вертикаль — закрытие получасовки ≥ +15% к прошлому закрытию или ≥ +20% за две;
  боковик — следующие 6 баров (3 ч) закрытия в полосе ±8% от закрытия вертикали;
  исход — в следующие 24 бара (12 ч): «вверх», если закрытие ≥ +10% от вертикали раньше, чем ≤ −8%; «вниз» — наоборот; «стоит» — ни то ни другое.
Разрезы по боковику (бары 1–6 после вертикали): интерес вырос ≥ +5% / нет; толпа по счетам лонг/шорт < 1 (в шортах) / ≥ 1; тейкер (покупки/продажи по рынку)
> 1 / ≤ 1; объём боковика к медиане 48 ч до вертикали.
    .venv/bin/python claude/research/box_after_vertical.py
"""
import json, statistics as st, time, urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; P = ROOT / "cq_v2" / "hist" / "tops"; B = 1800000
def get(u):
    return json.loads(urllib.request.urlopen(u, timeout=20).read())
def series(kind, sym, t0, t1):
    if kind == "kl":
        d = get(f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval=30m&startTime={t0}&endTime={t1}&limit=500")
        return {k[0]: float(k[7]) for k in d}
    ep = {"oi": "openInterestHist", "ls": "globalLongShortAccountRatio", "tk": "takerlongshortRatio"}[kind]
    d = get(f"https://fapi.binance.com/futures/data/{ep}?symbol={sym}&period=30m&startTime={t0}&endTime={t1}&limit=500")
    key = {"oi": "sumOpenInterestValue", "ls": "longShortRatio", "tk": "buySellRatio"}[kind]
    return {int(x["timestamp"]): float(x[key]) for x in d}
L = lambda t: datetime.fromtimestamp(t / 1000 + 3 * 3600, timezone.utc).strftime("%d.%m %H:%M")
events = []
for p in sorted(P.glob("*.json")):
    if p.stem == "BTCUSDT": continue
    kl = json.loads(p.read_text())["kl"]
    for i in range(2, len(kl) - 31):
        c0, c = kl[i - 1][3], kl[i][3]
        if not (c / c0 - 1 >= 0.15 or c / kl[i - 2][3] - 1 >= 0.20): continue
        box = kl[i + 1:i + 7]
        if any(abs(b[3] / c - 1) > 0.08 for b in box): continue
        out = "стоит"
        for b in kl[i + 7:i + 31]:
            if b[3] >= c * 1.10: out = "вверх"; break
            if b[3] <= c * 0.92: out = "вниз"; break
        events.append((p.stem, i, kl, out))
        break_i = i + 40
    # не более одного события на монету в 24 ч: оставляем первое (события ниже переберём с фильтром)
seen = {}; ev2 = []
for sym, i, kl, out in events:
    t = kl[i][0]
    if sym in seen and t - seen[sym] < 48 * B: continue
    seen[sym] = t; ev2.append((sym, i, kl, out))
print(f"вертикалей с боковиком: {len(ev2)} (монет {len(seen)}); исходы: {dict(Counter(e[3] for e in ev2))}\n")
print(f"{'монета':<9}{'вертикаль':<13}{'скачок':>7} | интерес в боксе | толпа L/S | тейкер | объём бокса × | исход")
rows = []
for sym, i, kl, out in ev2:
    t = kl[i][0]; t0, t1 = t - 48 * B, t + 8 * B
    try:
        oi, ls, tk, qv = series("oi", sym, t0, t1), series("ls", sym, t0, t1), series("tk", sym, t0, t1), series("kl", sym, t0, t1)
    except Exception as e:
        print(sym, L(t), "нет данных:", type(e).__name__); continue
    bt = [t + k * B for k in range(1, 7)]
    oi0, oi6 = oi.get(t), oi.get(t + 6 * B)
    oi_chg = (oi6 / oi0 - 1) * 100 if oi0 and oi6 else None
    lsv = [ls[x] for x in bt if x in ls]; tkv = [tk[x] for x in bt if x in tk]
    ls_m = st.median(lsv) if lsv else None; tk_m = st.median(tkv) if tkv else None
    pre = [qv[x] for x in range(t0, t, B) if x in qv]; boxv = [qv[x] for x in bt if x in qv]
    vr = (st.median(boxv) / st.median(pre)) if pre and boxv and st.median(pre) else None
    jump = max(kl[i][3] / kl[i - 1][3] - 1, kl[i][3] / kl[i - 2][3] - 1) * 100
    f = lambda v, w=6, d=1: "   —  " if v is None else f"{v:{w}.{d}f}"
    print(f"{sym[:-4]:<9}{L(t):<13}{jump:+6.0f}% | {f(oi_chg):>14}% | {f(ls_m, 6, 2)} | {f(tk_m, 5, 2)} | {f(vr, 6, 1)} | {out}")
    rows.append(dict(sym=sym, t=t, out=out, oi=oi_chg, ls=ls_m, tk=tk_m, vr=vr))
    time.sleep(0.12)
def grp(name, sel):
    g = [r for r in rows if sel(r)]
    if not g: return
    c = Counter(r["out"] for r in g)
    print(f"  {name:<52} n={len(g):3d} · вверх {c['вверх']:2d} · вниз {c['вниз']:2d} · стоит {c['стоит']:2d} · вверх {c['вверх'] / len(g) * 100:3.0f}%")
print("\nСВОДКА (боковик 3 ч после вертикали; исход за следующие 12 ч):")
grp("все", lambda r: True)
grp("интерес в боксе вырос ≥ +5%", lambda r: r["oi"] is not None and r["oi"] >= 5)
grp("  и толпа в шортах (L/S < 1)", lambda r: r["oi"] is not None and r["oi"] >= 5 and r["ls"] is not None and r["ls"] < 1)
grp("  и толпа в лонгах (L/S ≥ 1)", lambda r: r["oi"] is not None and r["oi"] >= 5 and r["ls"] is not None and r["ls"] >= 1)
grp("интерес в боксе не вырос (< +5%)", lambda r: r["oi"] is not None and r["oi"] < 5)
grp("  и толпа в шортах (L/S < 1)", lambda r: r["oi"] is not None and r["oi"] < 5 and r["ls"] is not None and r["ls"] < 1)
grp("  и толпа в лонгах (L/S ≥ 1)", lambda r: r["oi"] is not None and r["oi"] < 5 and r["ls"] is not None and r["ls"] >= 1)
grp("толпа в шортах (L/S < 1), любой интерес", lambda r: r["ls"] is not None and r["ls"] < 1)
grp("толпа в лонгах (L/S ≥ 1), любой интерес", lambda r: r["ls"] is not None and r["ls"] >= 1)
grp("тейкер в боксе > 1 (покупают по рынку)", lambda r: r["tk"] is not None and r["tk"] > 1)
grp("тейкер в боксе ≤ 1", lambda r: r["tk"] is not None and r["tk"] <= 1)
grp("объём бокса ≥ ×5 к медиане до вертикали", lambda r: r["vr"] is not None and r["vr"] >= 5)
grp("объём бокса < ×5", lambda r: r["vr"] is not None and r["vr"] < 5)
grp("DEXE-контекст: интерес ≥+5% и L/S < 1 и объём ≥ ×5", lambda r: r["oi"] is not None and r["oi"] >= 5 and r["ls"] is not None and r["ls"] < 1 and r["vr"] is not None and r["vr"] >= 5)
