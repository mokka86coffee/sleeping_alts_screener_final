#!/usr/bin/env python3
"""КОГО СЕЙЧАС ПОГЛОЩАЕТ МАРКЕТМЕЙКЕР (07.10, владелец прислал разбор DEXE на Coinglass: на пробое интерес растёт, фьючерс и спот бьют продажами,
ликвидации — «это значит, что все эти продажи с другой стороны поглотил маркетмейкер»; потом разворот вверх).
Чтение: интерес растёт — значит, открываются новые позиции; если при этом по рынку бьют в одну сторону, то вторую сторону этих сделок держит тот,
кто стоит заявками, — маркетмейкер. Бьют продажами и интерес растёт → толпа в шортах, ММ набирает лонг. Бьют покупками и интерес растёт → толпа в лонгах, ММ в шорте.
Здесь это смотрится на эту минуту по всем монетам архива (cq_v2/intraday, шаг 30 минут, Coinglass Binance): за 24 часа — рост интереса в монетах,
перекос сделок по рынку на фьючерсе и отдельно на споте, цена, фандинг. Это не сигнал входа: момент — когда бьющая сторона выдыхается (интерес перестаёт расти).
    .venv/bin/python claude/research/mm_absorb.py [часов=24]"""
import json, glob, os, sys
H = int(sys.argv[1]) if len(sys.argv) > 1 else 24; N = H * 2
rows = []
for p in glob.glob(os.path.join(os.path.dirname(__file__), "..", "..", "cq_v2", "intraday", "*.jsonl")):
    L = open(p).read().splitlines()[-(N + 6):]; r = []
    for l in L:
        try: x = json.loads(l)
        except ValueError: continue
        if x.get("px") and x.get("oi"): r.append(x)
    if len(r) < N * 0.8: continue
    r = r[-N:]; a, z = r[0], r[-1]
    fb = sum(((x.get("fut") or {}).get("b") or 0) for x in r); fs = sum(((x.get("fut") or {}).get("s") or 0) for x in r)
    sb = sum(((x.get("spot") or {}).get("b") or 0) for x in r); ss = sum(((x.get("spot") or {}).get("s") or 0) for x in r)
    if fb + fs <= 0: continue
    oi = (z["oi"] / z["px"]) / (a["oi"] / a["px"]) - 1
    # последние 4 часа: интерес ещё растёт или уже нет
    q = r[-8:]; oi4 = (q[-1]["oi"] / q[-1]["px"]) / (q[0]["oi"] / q[0]["px"]) - 1
    rows.append(dict(sym=os.path.basename(p)[:-6].upper(), px=(z["px"] / a["px"] - 1) * 100, oi=oi * 100, oi4=oi4 * 100, fut=(fb - fs) / (fb + fs) * 100, futusd=(fb - fs) / 1e6,
                     spot=(sb - ss) / (sb + ss) * 100 if sb + ss > 0 else None, spotusd=(sb - ss) / 1e6, fund=z.get("funding"), t=z["candle"][5:16].replace("T", " ")))
g = lambda v, p=1: "—" if v is None else f"{v:+.{p}f}"
def show(title, sel, key):
    print(title)
    for x in sorted([r for r in rows if sel(r)], key=key)[:8]:
        print(f"  {x['sym']:9s} цена {g(x['px'], 0)}% · интерес {g(x['oi'], 0)}% (за последние 4 ч {g(x['oi4'], 0)}%) · фьючерс по рынку {g(x['fut'])}% ({g(x['futusd'], 2)} млн $) · спот {g(x['spot'])}% ({g(x['spotusd'], 2)} млн $) · фандинг {g(x['fund'], 3)}")
print(f"монет {len(rows)} · окно {H} ч · данные до {max(r['t'] for r in rows)} UTC")
show("\nБЬЮТ ПРОДАЖАМИ, ИНТЕРЕС РАСТЁТ → толпа набирает шорты, вторую сторону держит ММ (он в лонге):", lambda r: r["oi"] >= 10 and r["fut"] < 0, lambda r: r["oi"] * r["fut"])
show("\nБЬЮТ ПОКУПКАМИ, ИНТЕРЕС РАСТЁТ → толпа набирает лонги, ММ в шорте:", lambda r: r["oi"] >= 10 and r["fut"] > 0, lambda r: -r["oi"] * r["fut"])
