#!/usr/bin/env python3
"""СЛЕЖЕНИЕ ЗА ОДНОЙ МОНЕТОЙ ПО ШЕСТИ ЛИНИЯМ (07.10, владелец: «вот следи за mina» — после разбора DEXE и его слов «mina это продажи на огромных объемах»).
Состояние на последнюю получасовку архива cq_v2/intraday (Coinglass Binance): цена, интерес в монетах и его ход от пика, сделки по рынку на фьючерсе и
на споте за 2 и 12 часов, ликвидации, фандинг. Сравнивается с прошлым запуском (память watch_<SYM>.json) и называет, что изменилось:
интерес поставил новый пик / пошёл от пика вниз / цена обновила минимум / цена держит минимум / спот сменил сторону / фандинг сменил знак.
Ничего не торгует и никуда, кроме вывода, не пишет.
    .venv/bin/python claude/research/watch_coin.py MINA"""
import json, sys, time, datetime as dt
from pathlib import Path
R = Path(__file__).parent; B = R.parents[1]; U = dt.timezone.utc
sym = (sys.argv[1] if len(sys.argv) > 1 else "MINA").upper()
rows = []
for l in open(B / "cq_v2" / "intraday" / f"{sym.lower()}.jsonl"):
    try: x = json.loads(l)
    except ValueError: continue
    if x.get("px") and x.get("oi"): rows.append(x)
r = rows[-144:]; z = r[-1]; oc = [x["oi"] / x["px"] for x in r]
k = max(range(len(oc)), key=lambda i: oc[i])
d = lambda key, n: sum(((x.get(key) or {}).get("d") or 0) for x in r[-n:]) / 1e6
lo = min(x.get("l") or x["px"] for x in r); lo_i = min(range(len(r)), key=lambda i: r[i].get("l") or r[i]["px"])
st = dict(t=z["candle"], px=z["px"], oi=oc[-1], oi_peak=oc[k], peak_t=r[k]["candle"], from_peak=(oc[-1] / oc[k] - 1) * 100, oi2=(oc[-1] / oc[-5] - 1) * 100,
          fut2=d("fut", 4), fut12=d("fut", 24), spot2=d("spot", 4), spot12=d("spot", 24), fund=z.get("funding"), low=lo, low_t=r[lo_i]["candle"],
          bars_since_low=len(r) - 1 - lo_i, liq=z.get("liq24") or {}, oi_type=z.get("oi_type"))
mem = R / f"watch_{sym}.json"
try: prev = json.loads(mem.read_text())
except (OSError, ValueError): prev = None
ev = []
if prev and prev.get("t") != st["t"]:
    if st["oi_peak"] > prev["oi_peak"] * 1.005: ev.append(f"интерес поставил новый пик: {st['oi_peak'] / 1e6:.1f} млн монет (шорты ещё прибывают)" if st["fut12"] < 0 else f"интерес поставил новый пик: {st['oi_peak'] / 1e6:.1f} млн монет")
    if prev["from_peak"] > -5 >= st["from_peak"]: ev.append(f"ИНТЕРЕС РАЗВЕРНУЛСЯ: от пика {st['from_peak']:.0f}% — бьющая сторона выходит")
    if st["low"] < prev["low"] * 0.999: ev.append(f"цена обновила минимум: {st['low']:.6g}")
    if prev["bars_since_low"] < 8 <= st["bars_since_low"]: ev.append(f"цена 4 часа не обновляет минимум {st['low']:.6g}")
    if (prev["spot12"] > 0) != (st["spot12"] > 0): ev.append(f"спот сменил сторону: за 12 ч {st['spot12']:+.2f} млн $")
    if prev.get("fund") is not None and st.get("fund") is not None and (prev["fund"] < 0) != (st["fund"] < 0): ev.append(f"фандинг сменил знак: {st['fund']:+.3f}%")
if not prev or prev.get("t") != st["t"]: mem.write_text(json.dumps(st))
age = (time.time() - dt.datetime.fromisoformat(st["t"].replace("Z", "+00:00")).timestamp()) / 60
print(f"{sym} на {st['t'][11:16]} UTC (данным {age:.0f} мин): цена {st['px']:.6g} · минимум {st['low']:.6g} ({st['bars_since_low'] / 2:.1f} ч назад) · интерес {st['oi'] / 1e6:.1f} млн монет, от пика {st['from_peak']:+.1f}%, за 2 ч {st['oi2']:+.1f}% ({st['oi_type']})")
print(f"  по рынку: фьючерс за 2 ч {st['fut2']:+.2f} млн $, за 12 ч {st['fut12']:+.2f} · спот за 2 ч {st['spot2']:+.2f} млн $, за 12 ч {st['spot12']:+.2f} · фандинг {st['fund'] if st['fund'] is None else format(st['fund'], '+.3f')}% · ликвидации за сутки: лонги {(st['liq'].get('long') or 0) / 1e3:.0f} тыс. $, шорты {(st['liq'].get('short') or 0) / 1e3:.0f} тыс. $")
print("ИЗМЕНЕНИЯ: " + ("; ".join(ev) if ev else ("нет" if prev else "первый запуск")))
