#!/usr/bin/env python3
"""СИГНАЛ «БЬЮЩАЯ СТОРОНА ВЫДОХЛАСЬ» (07.10, владелец по разбору DEXE: «все эти продажи с другой стороны поглотил маркетмейкер»; на предложение
следить каждые полчаса и писать, когда интерес разворачивается, — «делай»).
Шаг 1 — набор: за последние сутки интерес в монетах вырос от низа окна до своего пика на RISE % и больше, и всё это время по рынку на фьючерсе били
в одну сторону (продажами — толпа в шортах, ММ в лонге; покупками — толпа в лонгах, ММ в шорте).
Шаг 2 — разворот: пик интереса был не раньше PEAK_H часов назад, и от пика интерес упал на DROP % и больше — бьющая сторона выходит;
спот при этом не идёт против (если спот по монете есть).
Сообщение в Телеграм: «где покупать» (выходят шорты) или «где продавать» (выходят лонги), с числами и тем, что ломает картину. Одно на монету и пик.
RISE, DROP, PEAK_H — мерки Claude, вперёд не проверены; каждый сигнал пишется в mm_absorb_log.jsonl для счёта. Сделок не открывает, бота не трогает.
Данные — cq_v2/intraday (Coinglass Binance, шаг 30 минут, запаздывает до часа).
    .venv/bin/python claude/research/mm_absorb_alert.py [--dry]"""
import json, glob, os, sys, time, datetime as dt
from pathlib import Path
R = Path(__file__).parent; B = R.parents[1]; sys.path.insert(0, str(B)); U = dt.timezone.utc
LOG = R / "mm_absorb_log.jsonl"; RISE, DROP, PEAK_H, N = 10.0, 5.0, 6, 48


def scan():
    out, watch = [], []
    try:
        from core_config import STARS_NEW_SKIP as skip                     # акции и сырьё — не сюда
    except ImportError:
        skip = []
    for p in glob.glob(str(B / "cq_v2" / "intraday" / "*.jsonl")):
        if os.path.basename(p)[:-6].upper() in skip: continue
        r = []
        for l in open(p).read().splitlines()[-(N + 6):]:
            try: x = json.loads(l)
            except ValueError: continue
            if x.get("px") and x.get("oi"): r.append(x)
        if len(r) < N * 0.8: continue
        r = r[-N:]; oc = [x["oi"] / x["px"] for x in r]
        ts = dt.datetime.fromisoformat(r[-1]["candle"].replace("Z", "+00:00")).timestamp()
        if time.time() - ts > 3 * 3600: continue
        k = max(range(len(oc)), key=lambda i: oc[i]); lo = min(range(k + 1), key=lambda i: oc[i])
        rise = (oc[k] / oc[lo] - 1) * 100
        if rise < RISE or k - lo < 4: continue
        seg = r[lo:k + 1]
        fb = sum(((x.get("fut") or {}).get("b") or 0) for x in seg); fs = sum(((x.get("fut") or {}).get("s") or 0) for x in seg)
        sb = sum(((x.get("spot") or {}).get("b") or 0) for x in seg); ss = sum(((x.get("spot") or {}).get("s") or 0) for x in seg)
        if fb + fs <= 0 or fb == fs: continue
        side = 1 if fs > fb else -1                                        # 1 — били продажами: толпа в шортах, ждём вверх; −1 — били покупками, ждём вниз
        drop = (oc[-1] / oc[k] - 1) * 100; age = (len(r) - 1 - k) / 2
        pk = dt.datetime.fromisoformat(r[k]["candle"].replace("Z", "+00:00")).timestamp()
        row = dict(sym=os.path.basename(p)[:-6].upper() + "USDT", side=side, t=ts, peak_t=pk, px=r[-1]["px"], px_peak=r[k]["px"], rise=round(rise, 1), drop=round(drop, 1), age_h=age,
                   fut_musd=round((fb - fs) / 1e6, 2), spot_musd=round((sb - ss) / 1e6, 2), fund=r[-1].get("funding"),
                   edge=min(x["px"] for x in r[lo:]) if side == 1 else max(x["px"] for x in r[lo:]))
        spot_against = (sb + ss) > 0 and ((sb - ss) > 0) != (side == 1)     # спот идёт против разворота (на DEXE так было на пробое, не на дне) — не сигнал
        (out if (0 < age <= PEAK_H and drop <= -DROP and not spot_against) else watch).append(row)
    return out, watch


def main():
    dry = "--dry" in sys.argv
    sig, watch = scan()
    seen = set()
    if LOG.exists():
        for l in LOG.read_text(encoding="utf-8").splitlines():
            try: x = json.loads(l); seen.add((x["sym"], round(x["peak_t"])))
            except ValueError: pass
    print(f"{dt.datetime.now(U):%d.%m %H:%M} UTC · в наборе (интерес от +{RISE:g} % и бьют в одну сторону): {len(watch) + len(sig)} · разворот интереса: {len(sig)}")
    top = sorted(watch, key=lambda x: -x["rise"])[:6]
    if top: print("  набирают: " + " · ".join(f"{x['sym'][:-4]} {'шорты' if x['side'] == 1 else 'лонги'} +{x['rise']:.0f}%" for x in top))
    n = 0
    for s in sorted(sig, key=lambda x: -x["rise"]):
        if (s["sym"], round(s["peak_t"])) in seen: continue
        buy = s["side"] == 1; n += 1
        txt = "\n".join([
            f"{'🟢 ГДЕ ПОКУПАТЬ' if buy else '🔻 ГДЕ ПРОДАВАТЬ'} · {s['sym'][:-4]} · {'шорты выходят' if buy else 'лонги выходят'}", "",
            f"💵 цена: {s['px']:.6g}  ·  данные {dt.datetime.fromtimestamp(s['t'], U):%H:%M} UTC",
            f"• интерес в монетах вырос на {s['rise']:.0f}% и от пика уже {s['drop']:.0f}% (пик {s['age_h']:.1f} ч назад)",
            f"• пока он рос, на фьючерсе по рынку {'продали' if buy else 'купили'} на {abs(s['fut_musd']):.2f} млн $ больше — вторую сторону держал маркетмейкер",
            f"• спот за это время: {s['spot_musd']:+.2f} млн $" + (" — согласен" if (s["spot_musd"] > 0) == buy and s["spot_musd"] != 0 else " — данных нет" if s["spot_musd"] == 0 else " — против"),
            f"• фандинг {s['fund']:+.3f}%" if s.get("fund") is not None else "• фандинг —",
            f"✖ ломает: цена {'ниже' if buy else 'выше'} {s['edge']:.6g} или интерес снова растёт",
            "проверка вперёд, сделку не открываю"])
        print(txt + "\n")
        if not dry:
            import cg_shot
            cg_shot.send_text(txt + "\n\n" + cg_shot.links(s["sym"]))
            with LOG.open("a", encoding="utf-8") as f: f.write(json.dumps(dict(s, sent=time.time()), ensure_ascii=False) + "\n")
    print(f"новых сигналов: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
