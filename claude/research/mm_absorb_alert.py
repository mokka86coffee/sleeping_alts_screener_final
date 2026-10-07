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
FLAT_W, JUMP_W, BACK, LEFT, FLAT_PX, FLAT_NEAR = 32, 8, 240, 3.0, 3.0, 0.9   # две вершины (07.10): флэт 16 ч, скачок 4 ч, вершина — максимум 5 дней, уход интереса 3 % от пика


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


def tops(logrows=(), cut=0):
    """ДВЕ ВЕРШИНЫ (07.10, владелец прислал снимки Coinglass UAI и Q; на «поставить в получасовой сторож обе вершины — флэт UAI и скачок Q
    с фандингом в плюсе?» — «поставь»).
    flat — флэт у вершины (UAI): за FLAT_W получасов интерес в монетах вырос на RISE % и больше, на фьючерсе по рынку покупают, вершина пяти дней
      внутри окна, а цена за окно не ушла (не больше +FLAT_PX %) и стоит не ниже FLAT_NEAR от вершины; фандинг не в минусе. Покупки лонгистов кто-то
      принимает лимитными продажами. pierce — верх такого флэта проколот (на 02–06.10 у 7 из 15 сначала прокол, потом падение).
    jump — скачок на вершине (Q): интерес в монетах +RISE % за JUMP_W получасов, цена за это время выросла, вершина пяти дней тут же, фандинг в плюсе
      на фьючерсе за эти часы по рынку покупали, и цена ещё не ниже FLAT_NEAR от вершины (зашли лонги; при фандинге в минусе это шорты-топливо — не эта картина). left — после скачка интерес ушёл от пика на LEFT %: «где продавать».
    FLAT_W, JUMP_W, BACK, LEFT, FLAT_PX, FLAT_NEAR и RISE — мерки Claude, вперёд не проверены. cut — отрезать последние cut строк (проверка на прошлом).
    → список событий dict(kind, sym, side=-1, t, peak_t, px, top, ...)"""
    try:
        from core_config import STARS_NEW_SKIP as skip
    except ImportError:
        skip = []
    ts_of = lambda x: dt.datetime.fromisoformat(x["candle"].replace("Z", "+00:00")).timestamp()
    flats = {}                                                             # последний флэт монеты из журнала — для прокола верха
    for x in logrows:
        if x.get("kind") == "flat": flats[x["sym"]] = x
        elif x.get("kind") == "pierce": flats.pop(x["sym"], None)
    out = []
    for p in glob.glob(str(B / "cq_v2" / "intraday" / "*.jsonl")):
        base = os.path.basename(p)[:-6].upper()
        if base in skip: continue
        r = []
        for l in open(p).read().splitlines()[-(BACK + N + 12 + cut):]:
            try: x = json.loads(l)
            except ValueError: continue
            if x.get("px") and x.get("oi"): r.append(x)
        if cut: r = r[:-cut]
        n = len(r)
        if n < BACK + FLAT_W: continue
        ts = ts_of(r[-1])
        if not cut and time.time() - ts > 3 * 3600: continue
        sym = base + "USDT"; oc = [x["oi"] / x["px"] for x in r]; px = [x["px"] for x in r]; hi = [x.get("h") or x["px"] for x in r]
        fund = lambda i: r[i].get("funding")
        net = lambda a, i, k: sum(((x.get(k) or {}).get("b") or 0) - ((x.get(k) or {}).get("s") or 0) for x in r[a:i + 1]) / 1e6
        # флэт у вершины
        i = n - 1; a = i - FLAT_W; top = max(hi[a:i + 1]); doi = (oc[i] / oc[a] - 1) * 100; dpx = (px[i] / px[a] - 1) * 100
        if (doi >= RISE and net(a, i, "fut") > 0 and top >= max(hi[i - BACK:i + 1]) and dpx <= FLAT_PX and px[i] >= top * FLAT_NEAR
                and not ((fund(i) or 0) < 0)):
            out.append(dict(kind="flat", sym=sym, side=-1, t=ts, peak_t=ts, px=px[i], top=top, rise=round(doi, 1), dpx=round(dpx, 1),
                            fut_musd=round(net(a, i, "fut"), 2), spot_musd=round(net(a, i, "spot"), 2), fund=fund(i)))
        # прокол верха флэта, о котором уже писали (не старше двух суток)
        f = flats.get(sym)
        if f and ts - f["t"] <= 48 * 3600:
            after = [hi[j] for j in range(n) if ts_of(r[j]) > f["t"]]
            if after and max(after) > f["top"]:
                out.append(dict(kind="pierce", sym=sym, side=-1, t=ts, peak_t=f["t"], px=px[-1], top=f["top"], hi=max(after), fund=fund(n - 1)))
        # скачок на вершине и уход интереса после него
        ev = None; i = max(BACK, n - N)
        while i < n:
            if ((oc[i] / oc[i - JUMP_W] - 1) * 100 >= RISE and px[i] > px[i - JUMP_W] and (fund(i) or 0) > 0
                    and net(i - JUMP_W, i, "fut") > 0                      # 07.10 21:45 UTC: DRIFT получил сразу «покупать» и «продавать» — скачок считаем лонгами, только если по рынку покупали
                    and max(hi[i - JUMP_W:i + 1]) >= max(hi[i - BACK:i + 1]) and px[i] >= max(hi[i - JUMP_W:i + 1]) * FLAT_NEAR):
                k = i; t = None
                for j in range(i + 1, n):
                    if oc[j] > oc[k]: k = j
                    elif oc[j] <= oc[k] * (1 - LEFT / 100): t = j; break
                ev = (i, k, t)
                if t is None: break
                i = t + 1
            else:
                i += 1
        if ev:
            i, k, t = ev; a = i - JUMP_W; top = max(hi[a:(t or n - 1) + 1])
            row = dict(sym=sym, side=-1, peak_t=ts_of(r[i]), top=top, rise=round((oc[i] / oc[a] - 1) * 100, 1), dpx=round((px[i] / px[a] - 1) * 100, 1),
                       fut_musd=round(net(a, i, "fut"), 2), spot_musd=round(net(a, i, "spot"), 2), fund=fund(i))
            if t is None and n - 1 - i <= 4:                              # только свежее: сторож ходит каждые полчаса, старое не досылаем
                out.append(dict(row, kind="jump", t=ts, px=px[-1]))
            elif t is not None and n - 1 - t <= 2:
                out.append(dict(row, kind="left", t=ts_of(r[t]), px=px[t], drop=round((oc[t] / oc[k] - 1) * 100, 1), from_top=round((px[t] / top - 1) * 100, 1)))
    return out


def tops_text(s):
    c = s["sym"][:-4]; fu = f"фандинг {s['fund']:+.3f}%" if s.get("fund") is not None else "фандинга в данных нет"
    tail = "проверка вперёд, сделку не открываю"
    if s["kind"] == "flat":
        return "\n".join([f"🟠 ВЕРШИНА ГРУЗИТСЯ · {c} · лонги во флэте (картина UAI)", "",
            f"💵 цена: {s['px']:.6g}  ·  верх флэта {s['top']:.6g}  ·  данные {dt.datetime.fromtimestamp(s['t'], U):%H:%M} UTC",
            f"• за {FLAT_W // 2} ч интерес в монетах {s['rise']:+.0f}%, на фьючерсе по рынку купили на {s['fut_musd']:.2f} млн $ больше, а цена {s['dpx']:+.1f}%",
            f"• спот за это время: {s['spot_musd']:+.2f} млн $  ·  {fu}",
            "• 02–06.10 таких было 15: дальше (до двух суток) ниже 13, но у 7 сначала прокололи верх флэта",
            "✖ ломает: фандинг уходит в минус (это уже шорты-топливо)", tail])
    if s["kind"] == "pierce":
        return "\n".join([f"⚡ ВЕРХ ФЛЭТА ПРОКОЛОТ · {c}", "",
            f"💵 цена: {s['px']:.6g}  ·  верх флэта был {s['top']:.6g}, прокол до {s['hi']:.6g}  ·  {fu}",
            "• о флэте писал " + f"{dt.datetime.fromtimestamp(s['peak_t'], U):%d.%m %H:%M} UTC" + "; 02–06.10 прокол был у 7 из 15, дальше ниже флэта 5 из 7, но STRK и BAND сначала дали ещё +15…+17 %", tail])
    if s["kind"] == "jump":
        return "\n".join([f"🟠 СКАЧОК ЛОНГОВ НА ВЕРШИНЕ · {c} · картина Q", "",
            f"💵 цена: {s['px']:.6g}  ·  вершина {s['top']:.6g}  ·  скачок {dt.datetime.fromtimestamp(s['peak_t'], U):%H:%M} UTC",
            f"• за {JUMP_W // 2} ч интерес в монетах {s['rise']:+.0f}%, цена {s['dpx']:+.1f}%, {fu} — зашли лонги",
            f"• фьючерс по рынку {s['fut_musd']:+.2f} млн $  ·  спот {s['spot_musd']:+.2f} млн $",
            f"• жду ухода интереса от пика на {LEFT:g}% — тогда напишу «где продавать»",
            "✖ ломает: фандинг уходит в минус", tail])
    return "\n".join([f"🔻 ГДЕ ПРОДАВАТЬ · {c} · после скачка лонгов интерес уходит (картина Q)", "",
        f"💵 цена: {s['px']:.6g}  ·  уже {s['from_top']:+.1f}% от вершины {s['top']:.6g}  ·  данные {dt.datetime.fromtimestamp(s['t'], U):%H:%M} UTC",
        f"• скачок {dt.datetime.fromtimestamp(s['peak_t'], U):%d.%m %H:%M} UTC: интерес {s['rise']:+.0f}% за {JUMP_W // 2} ч, {fu}; от пика интерес уже {s['drop']:.1f}%",
        "• 04–07.10 при фандинге в плюсе таких было 14: к вершине не вернулись 8",
        f"✖ ломает: цена выше {s['top']:.6g} или интерес снова растёт", tail])


def main():
    dry = "--dry" in sys.argv
    sig, watch = scan()
    seen = set(); logrows = []
    if LOG.exists():
        for l in LOG.read_text(encoding="utf-8").splitlines():
            try: x = json.loads(l)
            except ValueError: continue
            logrows.append(x)
            if not x.get("kind"): seen.add((x["sym"], round(x["peak_t"])))
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
    tp = tops(logrows)
    if tp: print("  вершины: " + " · ".join(f"{x['sym'][:-4]} {dict(flat='флэт', pierce='прокол', jump='скачок', left='интерес ушёл')[x['kind']]}" for x in tp))
    for s in tp:
        if s["kind"] == "pierce": dup = False                            # прокол пишется один раз: после него флэт из журнала снят
        else: dup = any(x.get("kind") == s["kind"] and x["sym"] == s["sym"] and s["t"] - x["t"] < 24 * 3600 for x in logrows)
        if dup: continue
        n += 1; txt = tops_text(s)
        print(txt + "\n")
        if not dry:
            import cg_shot
            cg_shot.send_text(txt + "\n\n" + cg_shot.links(s["sym"]))
            with LOG.open("a", encoding="utf-8") as f: f.write(json.dumps(dict(s, sent=time.time()), ensure_ascii=False) + "\n")
    print(f"новых сигналов: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
