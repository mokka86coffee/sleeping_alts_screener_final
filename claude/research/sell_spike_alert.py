#!/usr/bin/env python3
"""СИГНАЛ «ГДЕ ПРОДАВАТЬ»: БРОСОК ВВЕРХ С ВОЗВРАТОМ (07.10, владелец: «мне главное чтобы ты нашел где покупать а где продавать», «2 месяца уже этого жду»).
Монета выросла от низа за 48 ч на 30 % и больше; закрытая 30-минутная свеча ставит новый максимум за 48 ч, хвост сверху — от 60 % свечи, главный объём
(POC кластера) — в нижней трети свечи. Шорт по закрытию, стоп над вершиной свечи, держать 8 часов. Счёт 07.10 на 17 монетах за 6 суток
(pump_ends.py и проверка в чате): 7 сигналов, 5 в плюс, 1 стоп, +100 % без плеча; без условия по объёму внутри свечи — 15 сигналов, 8 стопов.
Зеркальный сигнал на покупку не работает (5 сигналов, 4 стопа) — его здесь нет. Вперёд не проверено: каждый сигнал пишется в sell_spike_log.jsonl.
Кандидаты — из пульса скринера (цена к минимуму 48 ч); кластеры — с графика владельца в TradingView (режим Volume footprint), как tv_footprint.py.
Сообщение уходит в Телеграм (cg_shot.send_text). Бота и его правила не трогает, сделок не открывает.
    .venv/bin/python claude/research/sell_spike_alert.py [--dry]"""
import asyncio, json, sys, time, datetime as dt
from pathlib import Path
B = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(B)); sys.path.insert(0, str(Path(__file__).parent))
import tv_footprint as tvf
U = dt.timezone.utc; LOG = Path(__file__).parent / "sell_spike_log.jsonl"
RISE, WICK, POC_MAX, HOLD_H = 1.3, 0.6, 0.35, 8


def candidates(now):
    p = json.loads((B / "pulse.json").read_text(encoding="utf-8")); out = []
    for s, rs in p.items():
        if s == "_meta": continue
        w = [r["price"] for r in rs if r.get("price") and now - r["t"] <= 48 * 3600]
        if len(w) >= 20 and now - rs[-1]["t"] < 3 * 3600 and w[-1] / min(w) >= RISE * 0.9 and w[-1] >= max(w) * 0.85:
            out.append(s.replace("USDT", ""))
    return out


async def scan(syms):
    found = []; _lk = tvf.tv_lock()
    async with tvf.websockets.connect(tvf.page(), max_size=None) as ws:
        was = json.loads(await tvf.ev(ws, "JSON.stringify([window.TradingViewApi.activeChart().symbol(), window.TradingViewApi.activeChart().resolution()])"))
        try:
            for s in syms:
                v = await tvf.ev(ws, tvf.JS % (json.dumps(f"BINANCE:{s}USDT.P"), json.dumps("30")))
                try: d = json.loads(v)
                except (TypeError, ValueError): continue
                if d.get("err"):
                    print(f"{s}: {d['err']}")
                    if "footprint" in d["err"]: return found, d["err"]
                    continue
                b = d["bars"]; fp = {x["i"]: x for x in d["fp"]}; i = len(b) - 2                # последняя ЗАКРЫТАЯ свеча
                if i < 96 or i not in fp or time.time() - b[i][0] > 3900: continue
                hi48 = max(x[2] for x in b[i - 96:i]); lo48 = min(x[3] for x in b[i - 96:i]); rng = b[i][2] - b[i][3]
                if rng <= 0 or b[i][2] <= hi48 or b[i][2] / lo48 < RISE: continue
                wick = (b[i][2] - max(b[i][1], b[i][4])) / rng; poc = (fp[i]["poc"] - b[i][3]) / rng
                if wick >= WICK and poc <= POC_MAX:
                    found.append(dict(sym=s + "USDT", t=b[i][0], entry=b[i][4], stop=b[i][2], rise=round(b[i][2] / lo48, 2), wick=round(wick * 100), poc=round(poc * 100),
                                      delta=round((fp[i]["buy"] - fp[i]["sell"]) / (b[i][5] or 1) * 100, 1)))
        finally:
            await tvf.ev(ws, tvf.JS % (json.dumps(was[0]), json.dumps(was[1])))
    return found, None


def main():
    dry = "--dry" in sys.argv; now = time.time()
    c = candidates(now); print(f"{dt.datetime.fromtimestamp(now, U):%d.%m %H:%M} UTC · монет с ростом от 30 % за 48 ч у максимума: {len(c)}" + (": " + ", ".join(c) if c else ""))
    if not c: return 0
    found, err = asyncio.run(scan(c))
    if err: print("СТОП:", err); return 2
    seen = set()
    if LOG.exists():
        for l in LOG.read_text(encoding="utf-8").splitlines():
            try: r = json.loads(l); seen.add((r["sym"], r["t"]))
            except ValueError: pass
    for s in found:
        if (s["sym"], s["t"]) in seen: continue
        e, st_ = s["entry"], s["stop"]; tt = dt.datetime.fromtimestamp(s["t"] + 1800, U)
        txt = "\n".join([f"🔻 ГДЕ ПРОДАВАТЬ · {s['sym'][:-4]} · бросок вверх с возвратом", "",
                         f"💵 шорт от: {e:.6g}  ·  свеча закрылась {tt:%H:%M} UTC", f"🛑 стоп:    {st_:.6g}  (+{(st_ / e - 1) * 100:.1f}%) — над вершиной свечи", f"⏳ держать: {HOLD_H} ч", "",
                         f"• рост от низа за 48 ч ×{s['rise']}", f"• хвост сверху {s['wick']}% свечи, главный объём на {s['poc']}% её высоты", f"• дельта свечи {s['delta']:+.1f}% объёма",
                         "• проверка вперёд: 7 случаев за 6 суток, 5 в плюс; сделку не открываю"])
        print(txt)
        if not dry:
            import cg_shot
            cg_shot.send_text(txt + "\n\n" + cg_shot.links(s["sym"]))
            with LOG.open("a", encoding="utf-8") as f: f.write(json.dumps(dict(s, sent=now), ensure_ascii=False) + "\n")
    print(f"сигналов: {len(found)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
