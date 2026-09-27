#!/usr/bin/env python3
"""РАЗБОР ВСЕХ ЛИДЕРОВ (27.09, владелец: «делай разбор дальше по всем лидерам… по каждому присылай графики и анализ»).
По каждой монете output/leaders.json: Binance 5м за 2 дня (цена, объём, тейкер-покупки → CVD фьючерсов), интерес 5м, фандинг по выплатам,
спот 5м (CVD спота), толпа/топы, стороны ликвидаций из нашего потока cq_v2/liq (OKX+Bybit, с 26.09). Стадия по механике владельца:
  старт — вынос лонгов у минимума 48 ч (или отскок от него) при интересе, растущем за 6 ч; продолжение — цена в верхней трети хода, интерес
  растёт за 24 ч, спот покупает, выносы шортов не рекордные; конец — рекордный вынос шортов / пик минуса фандинга со скачком интереса у максимума
  и интерес за 6 ч падает; сползание — цена ниже максимума ≥ 15%, интерес за 24 ч падает, спот продаёт; иначе — флэт.
Выход: claude/research/leaders_review.html (графики SVG + текст по каждой) и leaders_stages.md (таблица).
"""
from __future__ import annotations
import json, os, sys, time, datetime as dt, statistics as st
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
from core_http import get_json                                   # noqa: E402
L = dt.timezone(dt.timedelta(hours=3))
OUT_H = BASE / "claude/research/leaders_review.html"; OUT_M = BASE / "claude/research/leaders_stages.md"


def liq_by_sym():
    out = {}
    for day in ("2026-09-25", "2026-09-26", "2026-09-27"):
        p = BASE / "cq_v2/liq" / f"{day}.jsonl"
        if not p.exists(): continue
        for line in p.read_text(encoding="utf-8").splitlines():
            try: r = json.loads(line)
            except ValueError: continue
            out.setdefault(r.get("sym"), []).append((int(r["t"]), r.get("side"), float(r.get("usd") or 0)))
    return out


def fetch(sym):
    k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "5m", "limit": 576}, quiet_400=True, weight=5) or []
    if len(k) < 300: return None
    oi = get_json("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": sym, "period": "5m", "limit": 500}, quiet_400=True) or []
    fr = get_json("https://fapi.binance.com/fapi/v1/fundingRate", {"symbol": sym, "limit": 12}, quiet_400=True) or []
    ls = get_json("https://fapi.binance.com/futures/data/globalLongShortAccountRatio", {"symbol": sym, "period": "1h", "limit": 1}, quiet_400=True) or [{}]
    tp = get_json("https://fapi.binance.com/futures/data/topLongShortPositionRatio", {"symbol": sym, "period": "1h", "limit": 1}, quiet_400=True) or [{}]
    sk = get_json("https://api.binance.com/api/v3/klines", {"symbol": sym, "interval": "5m", "limit": 576}, quiet_400=True, weight=5) or []
    return dict(sym=sym, k=k, oi=oi, fr=fr, crowd=float(ls[0].get("longShortRatio") or 0) or None, tops=float(tp[0].get("longShortRatio") or 0) or None, sk=sk if isinstance(sk, list) else [])


def analyse(d, liq):
    k = d["k"]; t = [int(x[0]) for x in k]; c = [float(x[4]) for x in k]; h = [float(x[2]) for x in k]; l = [float(x[3]) for x in k]
    qv = [float(x[7]) for x in k]; tb = [float(x[10]) for x in k]
    cvd = []; a = 0
    for q, b in zip(qv, tb): a += 2 * b - q; cvd.append(a / 1e6)
    ov = [float(x["sumOpenInterestValue"]) / 1e6 for x in d["oi"]]; ot = [int(x["timestamp"]) for x in d["oi"]]
    fv = [float(x["fundingRate"]) * 100 for x in d["fr"]]; ft = [dt.datetime.fromtimestamp(x["fundingTime"] / 1000, L).strftime("%d %H:%M") for x in d["fr"]]
    sc = []; a = 0
    for x in d["sk"]: a += 2 * float(x[10]) - float(x[7]); sc.append(a / 1e6)
    n = len(c); hi = max(h); lo = min(l); ihi = h.index(hi); ilo = l.index(lo)
    px = c[-1]; from_hi = (px / hi - 1) * 100; from_lo = (px / lo - 1) * 100
    oi_now = ov[-1] if ov else None
    oi6 = (ov[-1] / ov[-72] - 1) * 100 if len(ov) >= 72 and ov[-72] else None
    oi24 = (ov[-1] / ov[-288] - 1) * 100 if len(ov) >= 288 and ov[-288] else None
    oi1 = (ov[-1] / ov[-12] - 1) * 100 if len(ov) >= 12 and ov[-12] else None
    buy6 = sum(tb[-72:]) / max(sum(qv[-72:]), 1) * 100; buy1 = sum(tb[-12:]) / max(sum(qv[-12:]), 1) * 100
    spot24 = (sc[-1] - sc[-288]) if len(sc) >= 288 else None; spot6 = (sc[-1] - sc[-72]) if len(sc) >= 72 else None
    fut6 = cvd[-1] - cvd[-72]; fut24 = cvd[-1] - cvd[-288] if n >= 288 else None
    vol1 = sum(qv[-12:]) / (sum(qv[-288:]) / 24) if sum(qv[-288:]) else None
    # ликвидации: по 5-мин корзинам, лонги +, шорты −
    lq = liq.get(d["sym"], []); bins = {}
    for ts, side, usd in lq:
        key = ts // 300_000 * 300_000; bins[key] = bins.get(key, 0) + (usd if side == "long" else -usd)
    lv = [bins.get(tt, 0) / 1e3 for tt in t]
    long_max = max(lv) if lv else 0; short_max = -min(lv) if lv else 0
    i_lmax = lv.index(long_max) if long_max > 0 else None; i_smax = lv.index(-short_max) if short_max > 0 else None
    # стадия
    stage, why = "флэт", []
    f_last = fv[-1] if fv else 0; f_min = min(fv[-6:]) if fv else 0
    recent = n - 72
    if i_smax is not None and i_smax >= recent and ihi >= recent and from_hi > -8 and (oi6 is not None and oi6 < 0):
        stage = "конец"; why.append(f"рекордный вынос шортов {short_max:.0f}K$ у максимума за 6 ч, интерес за 6 ч {oi6:+.1f}%")
    elif f_min <= -0.5 and ihi >= recent and (oi6 is not None and oi6 < -3):
        stage = "конец"; why.append(f"пик минуса фандинга {f_min:+.2f}% у максимума, интерес уходит {oi6:+.1f}% за 6 ч")
    elif i_lmax is not None and i_lmax >= recent and ilo >= recent and from_lo < 12 and (oi6 is not None and oi6 > 0):
        stage = "старт"; why.append(f"вынос лонгов {long_max:.0f}K$ у минимума за 6 ч, интерес за 6 ч {oi6:+.1f}%")
    elif from_hi <= -15 and (oi24 is not None and oi24 < 0) and (spot24 is None or spot24 <= 0):
        stage = "сползание"; why.append(f"{from_hi:+.0f}% от максимума 48 ч, интерес за сутки {oi24:+.0f}%, спот {'продаёт' if spot24 is not None else 'нет'}")
    elif from_hi > -8 and (oi24 is not None and oi24 > 5) and (spot6 is None or spot6 >= 0) and buy6 >= 48:
        stage = "продолжение"; why.append(f"у максимума ({from_hi:+.1f}%), интерес за сутки {oi24:+.0f}%, покупатели 6 ч {buy6:.0f}%")
    elif f_min <= -0.3 and (oi6 is not None and oi6 >= 0) and (spot6 is None or spot6 > 0):
        stage = "лестница на фандинге"; why.append(f"фандинг {f_min:+.2f}%, интерес держится, спот покупает — шаг ждать на возврате фандинга к нулю")
    notes = [f"цена {px:.5g}, {from_hi:+.1f}% от макс 48 ч ({dt.datetime.fromtimestamp(t[ihi]/1000, L):%d %H:%M}), {from_lo:+.1f}% от мин ({dt.datetime.fromtimestamp(t[ilo]/1000, L):%d %H:%M})",
             f"интерес {oi_now:.1f}M$: 1 ч {oi1:+.1f}%, 6 ч {oi6:+.1f}%, 24 ч {oi24:+.1f}%" if oi_now and oi6 is not None and oi24 is not None and oi1 is not None else "интерес: мало данных",
             "фандинг по выплатам: " + ", ".join(f"{a} {b:+.3f}" for a, b in zip(ft[-4:], fv[-4:])),
             f"CVD фьючерсов 6 ч {fut6:+.2f}M$, 24 ч {fut24:+.2f}M$" + (f"; спот 6 ч {spot6:+.2f}M$, 24 ч {spot24:+.2f}M$" if spot24 is not None else "; спота на Binance нет"),
             f"покупатели по рынку 1 ч {buy1:.0f}%, 6 ч {buy6:.0f}%; толпа {d['crowd']}, топы {d['tops']}; объём часа ×{vol1:.1f} к среднему" if vol1 else "",
             (f"ликвидации (поток OKX+Bybit): лонгов макс {long_max:.0f}K$ в {dt.datetime.fromtimestamp(t[i_lmax]/1000, L):%d %H:%M}, шортов макс {short_max:.0f}K$ в {dt.datetime.fromtimestamp(t[i_smax]/1000, L):%d %H:%M}" if (i_lmax is not None and i_smax is not None) else "ликвидации: в потоке пусто")]
    return dict(sym=d["sym"], stage=stage, why=why, notes=[x for x in notes if x], t=t, c=c, qv=qv, cvd=cvd, ov=ov, fv=fv, ft=ft, sc=sc, lv=lv, from_hi=from_hi, oi24=oi24, oi6=oi6, fund=f_last, crowd=d["crowd"], tops=d["tops"], px=px)


W = 1200; PH = [200, 70, 90, 70, 90, 90, 90]
def line(xs, w, h, color, label, fmt=lambda v: f"{v:.4g}"):
    if not xs: return f'<text x="4" y="14" fill="#9aa" font-size="11">{label}: нет</text>'
    lo, hi = min(xs), max(xs); rng = (hi - lo) or 1
    pts = " ".join(f"{60+i/(len(xs)-1)*(w-70):.1f},{10+(hi-y)/rng*(h-20):.1f}" for i, y in enumerate(xs))
    return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.1"/><text x="4" y="14" fill="#9aa" font-size="11">{label}</text><text x="4" y="{h-4}" fill="#667" font-size="10">{fmt(lo)}</text><text x="4" y="26" fill="#667" font-size="10">{fmt(hi)}</text>'
def bars(ys, w, h, label, zero=True, pos="#3fb950", neg="#f85149"):
    if not ys or not any(ys): return f'<text x="4" y="14" fill="#9aa" font-size="11">{label}: нет</text>'
    m = max(abs(y) for y in ys) or 1; y0 = h / 2 if zero else h - 10; bw = max(0.8, (w - 70) / len(ys) - 0.2); o = []
    for i, y in enumerate(ys):
        if not y: continue
        x = 60 + i / len(ys) * (w - 70); hh = abs(y) / m * ((y0 - 10) if zero else (h - 20))
        o.append(f'<rect x="{x:.1f}" y="{(y0-hh if y>=0 else y0):.1f}" width="{bw:.1f}" height="{max(hh,0.5):.1f}" fill="{pos if y>=0 else neg}"/>')
    return "".join(o) + f'<text x="4" y="14" fill="#9aa" font-size="11">{label}</text>' + (f'<line x1="60" y1="{y0}" x2="{w-10}" y2="{y0}" stroke="#444"/>' if zero else "")


def panel(r):
    t = r["t"]; ticks = "".join(f'<text x="{60+i/(len(t)-1)*(W-70):.0f}" y="12" fill="#889" font-size="10">{dt.datetime.fromtimestamp(t[i]/1000, L):%d.%m %H:%M}</text>' for i in range(0, len(t), 96))
    y = 0; s = [f'<svg viewBox="0 0 {W} {sum(PH)+24}" width="100%" style="background:#111">']
    for i, (content) in enumerate([line(r["c"], W, PH[0], "#8fd", "цена, 5м, 2 дня"), bars([q/1e3 for q in r["qv"]], W, PH[1], "объём K$", zero=False, pos="#6b8"),
                                   line(r["ov"], W, PH[2], "#e3b341", "интерес M$"), bars(r["fv"], W, PH[3], "фандинг % по выплатам"),
                                   line(r["cvd"], W, PH[4], "#79c0ff", "CVD фьючерсов M$"), line(r["sc"], W, PH[5], "#d2a8ff", "CVD спота M$"),
                                   bars(r["lv"], W, PH[6], "ликвидации K$ (поток OKX+Bybit): лонги ↑, шорты ↓")]):
        s.append(f'<g transform="translate(0,{y})">{content}</g>'); y += PH[i]
    s.append(f'<g transform="translate(0,{y})">{ticks}</g></svg>'); return "".join(s)


def main():
    ld = json.loads((BASE / "output/leaders.json").read_text(encoding="utf-8")); syms = list(ld.keys()); liq = liq_by_sym()
    t0 = time.time()
    with ThreadPoolExecutor(5) as ex: data = [d for d in ex.map(fetch, syms) if d]
    res = [analyse(d, liq) for d in data]
    order = {"старт": 0, "продолжение": 1, "лестница на фандинге": 2, "конец": 3, "сползание": 4, "флэт": 5}
    res.sort(key=lambda r: (order.get(r["stage"], 9), r["from_hi"]))
    col = {"старт": "#3fb950", "продолжение": "#79c0ff", "лестница на фандинге": "#d2a8ff", "конец": "#f85149", "сползание": "#e3b341", "флэт": "#7d8590"}
    parts = [f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>Лидеры по стадиям</title><style>body{{background:#111;color:#ddd;font:13px/1.4 sans-serif;margin:14px}}a{{color:#79c0ff}}.st{{font-weight:bold}}.nav a{{margin-right:10px}}h2{{margin:22px 0 4px;font-size:16px}}li{{margin:2px 0}}</style></head><body>',
             f'<h1 style="font-size:18px">Лидеры (output/leaders.json, {len(res)} монет) по стадиям · Binance 5м, 2 дня · {dt.datetime.now(L):%d.%m %H:%M} UTC+3</h1>',
             '<div class="nav">' + " ".join(f'<a href="#{k}">{k}: {sum(1 for r in res if r["stage"]==k)}</a>' for k in order) + '</div>']
    cur = None
    for r in res:
        if r["stage"] != cur: cur = r["stage"]; parts.append(f'<h1 id="{cur}" style="font-size:16px;color:{col[cur]};margin-top:26px">— {cur} —</h1>')
        s = r["sym"]
        parts.append(f'<h2 id="{s}">{s[:-4]} · <span class="st" style="color:{col[r["stage"]]}">{r["stage"]}</span> · <a href="https://www.coinglass.com/tv/Binance_{s}">coinglass.com/tv/Binance_{s}</a> · <a href="https://www.coinglass.com/currencies/{s[:-4]}">страница</a></h2>')
        parts.append("<ul>" + "".join(f"<li><b>{w}</b></li>" for w in r["why"]) + "".join(f"<li>{x}</li>" for x in r["notes"]) + "</ul>" + panel(r))
    parts.append("</body></html>"); OUT_H.write_text("".join(parts), encoding="utf-8")
    md = [f"# Лидеры по стадиям · {dt.datetime.now(L):%d.%m %H:%M}\n\n| монета | стадия | от макс 48ч | интерес 6ч | интерес 24ч | фандинг | толпа | топы | почему |\n|---|---|---|---|---|---|---|---|---|"]
    for r in res:
        md.append(f"| {r['sym'][:-4]} | {r['stage']} | {r['from_hi']:+.1f}% | {r['oi6'] if r['oi6'] is None else f'{r['oi6']:+.1f}%'} | {r['oi24'] if r['oi24'] is None else f'{r['oi24']:+.1f}%'} | {r['fund']:+.3f} | {r['crowd']} | {r['tops']} | {'; '.join(r['why'])} |")
    OUT_M.write_text("\n".join(md), encoding="utf-8")
    print(f"монет {len(res)} · {time.time()-t0:.0f} с · " + " · ".join(f"{k} {sum(1 for r in res if r['stage']==k)}" for k in order))
    for k in ("старт", "конец", "продолжение", "лестница на фандинге"):
        print(f"  {k}: " + ", ".join(r["sym"][:-4] for r in res if r["stage"] == k))


if __name__ == "__main__":
    main()
