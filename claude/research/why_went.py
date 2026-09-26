"""ПОЧЕМУ ПОШЛА И ПОЧЕМУ НЕ УВИДЕЛИ (26.09): разбор одной монеты за последние 72 ч по внутридневному архиву и Binance — какие наши признаки были до хода
(R34 интерес +15%/3 ч, R1 интерес растёт при стоящей цене, R6/R23 покупки по рынку, фандинг R20, спот R19, объём), что говорил near_move (балл, признаки,
группа), была ли в очереди/звёздах/книгах. Печатает хронологию и вывод. Мерки — из реестра.
    .venv/bin/python claude/research/why_went.py RARE
"""
import json, sys, urllib.request, statistics as st
from datetime import datetime, timezone, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
L = timezone(timedelta(hours=3)); B = 1800000
sym = sys.argv[1].upper(); sym = sym if sym.endswith("USDT") else sym + "USDT"
def g(u): return json.loads(urllib.request.urlopen(u, timeout=20).read())
k = g(f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval=30m&limit=150")
T = [int(x[0]) for x in k]; C = [float(x[4]) for x in k]; H = [float(x[2]) for x in k]; QV = [float(x[7]) for x in k]; TB = [float(x[10]) for x in k]
oi = g(f"https://fapi.binance.com/futures/data/openInterestHist?symbol={sym}&period=30m&limit=150"); OI = {int(x["timestamp"]): float(x["sumOpenInterestValue"]) for x in oi}
tk = g(f"https://fapi.binance.com/futures/data/takerlongshortRatio?symbol={sym}&period=30m&limit=150"); TK = {int(x["timestamp"]): float(x["buySellRatio"]) for x in tk}
fr = g(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&limit=12")
ls = g(f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={sym}&period=1h&limit=1")
imx = max(range(len(H)), key=lambda i: H[i]); lo = min(C[:imx + 1] or C); ilo = C.index(lo)
print(f"{sym[:-4]}: минимум {lo} ({datetime.fromtimestamp(T[ilo]/1000, L).strftime('%d.%m %H:%M')}) → максимум {H[imx]} ({datetime.fromtimestamp(T[imx]/1000, L).strftime('%d.%m %H:%M')}) = +{(H[imx]/lo-1)*100:.0f}% · сейчас {C[-1]} ({(C[-1]/H[imx]-1)*100:+.0f}% от максимума)")
print(f"фандинг последние 12 выплат: {[round(float(x['fundingRate'])*100,3) for x in fr]} · толпа L/S {float(ls[-1]['longShortRatio']):.2f}")
print("хронология (местное): бар · цена · ход 48 ч · интерес 3 ч · тейкер · объём × к медиане 48 · метки")
med48 = lambda i: (sorted(QV[max(0, i-48):i])[max(0, i-48 if i>=48 else i)//2] if i > 4 else 1) or 1
first = {}
for i in range(len(k)):
    t = T[i]; c = C[i]
    o3 = (OI[t] / OI[t - 6 * B] - 1) * 100 if t in OI and (t - 6 * B) in OI and OI[t - 6 * B] else None
    r48 = (c / C[i - 96] - 1) * 100 if i >= 96 else None
    tkv = TK.get(t); vx = QV[i] / (st.median(QV[max(0, i-48):i]) or 1) if i >= 8 else None
    tags = []
    if o3 is not None and o3 >= 15: tags.append("R34 интерес+15%/3ч")
    if tkv is not None and tkv >= 1.4: tags.append("R23 покупки по рынку")
    if vx is not None and vx >= 5: tags.append("объём ×5")
    if r48 is not None and r48 >= 40: tags.append("В ХОДУ ≥40%")
    for tg in tags:
        first.setdefault(tg, datetime.fromtimestamp(t/1000, L).strftime('%d.%m %H:%M'))
    if tags or i >= len(k) - 4 or i % 8 == 0:
        print(f"  {datetime.fromtimestamp(t/1000, L).strftime('%d.%m %H:%M')} · {c:.6g} · {('%+.0f%%' % r48) if r48 is not None else '—':>5} · {('%+.0f%%' % o3) if o3 is not None else '—':>6} · {('%.2f' % tkv) if tkv is not None else '—':>5} · {('×%.1f' % vx) if vx is not None else '—':>6} · {' '.join(tags)}")
print("первые срабатывания:", first)
# что говорил экран
nm = {}
try: nm = json.loads((ROOT / "output" / "near_move.json").read_text()).get("coins") or {}
except Exception: pass
c = nm.get(sym) or {}
print(f"near_move сейчас: балл {c.get('score')} · группа {c.get('group')} · признаки: {c.get('why')}")
q = [json.loads(l) for l in (ROOT / "output" / "queue_log.jsonl").read_text().splitlines()[-40000:] if f'"sym": "{sym}"' in l]
places = [(r["candle"][5:16], r.get("place")) for r in q if r.get("place")]
print(f"очередь за последние прогоны: мест {len(places)}: {places[:6]}{' …' if len(places) > 6 else ''}")
for f in ("paper_first3", "paper_sight", "paper_interest", "paper_second", "paper_crowd", "paper_end"):
    p = ROOT / "output" / f"{f}.jsonl"
    if p.exists():
        n = sum(1 for l in p.read_text().splitlines()[-3000:] if f'"sym": "{sym}"' in l and '"kind": "entry"' in l)
        if n: print(f"книга {f}: входов {n}")
inh = first.get("В ХОДУ ≥40%"); r34 = first.get("R34 интерес+15%/3ч"); r23 = first.get("R23 покупки по рынку")
print("ВЫВОД:", f"R34 сработал {r34}" if r34 else "R34 не срабатывал", "·", f"покупки по рынку {r23}" if r23 else "покупок по рынку ≥1.4 не было", "·", f"в ходу с {inh}" if inh else "порог +40% не взят")
