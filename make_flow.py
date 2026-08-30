#!/usr/bin/env python3
"""Экран-поток v6 (творение по референсу владельца, ночь 30.08).

Три окна времени, линии со смыслами, конфликты геометрией:
  БЕЛАЯ — цена (факт);
  БИРЮЗОВАЯ, главная и самая светящаяся — «цена по деньгам»:
    где цена была бы, если бы её двигали только реальные
    покупки-продажи (накопленная дельта тейкеров, модель);
  ЯНТАРНАЯ — плечо (открытый интерес).
Зазор белой над бирюзовой — тёплая подушка «долга»: цена выше
своих денег, ход держат заявками. Подписи всплывают на точках
конфликтов (лучи вверх, как в референсе). Боке — ликвидации:
янтарные под линией — снятые лонги, бирюзовые над — шорты.
Вердикт справа — от главной линии. Данные: живой bless.json.
"""
import argparse
import json
import math
import random
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--coin", default="bless")
ap.add_argument("--archive", default="cq_v2")
ap.add_argument("--out", default="flow.html")
A = ap.parse_args()
src = Path(A.archive) / f"{A.coin.lower()}.json"
if not src.exists() and Path(f"{A.coin.lower()}.json").exists():
    src = Path(f"{A.coin.lower()}.json")
d = json.load(open(src))
for k in d:
    d[k] = list(reversed(d[k]))
tr, oh, oi, lq = d['trade'], d['ohlcv'], d['oi'], d['liq']
days = [t['datetime'][:10] for t in tr]
close = {r['datetime'][:10]: r['close'] for r in oh}
oim = {r['datetime'][:10]: r['open_interest'] for r in oi}
lqm = {r['datetime'][:10]: r for r in lq}
# ряды разной глубины (trade старше ohlcv) — живём по дням с ценой
keep = [i for i, dt in enumerate(days) if close.get(dt)]
days = [days[i] for i in keep]
tr = [tr[i] for i in keep]
px = [close[dt] for dt in days]
deltas = [t['quote_buy_volume'] - t['quote_sell_volume'] for t in tr]
vols = [t['quote_volume'] for t in tr]

# «цена по деньгам»: exp-модель от накопленной дельты; Q калиброван
# так, чтобы лог-размах линии совпадал с размахом цены за полгода
cum = []
c = 0.0
for x in deltas:
    c += x
    cum.append(c)
# калибровка: лог-размах модельной линии = лог-размаху цены,
# а старт совмещён так, чтобы СРЕДНИЕ лог-уровни совпали — тогда
# линии живут в одном коридоре, и зазор читается как конфликт


W, PAD = 1520, 56
def _waves():
    out = []
    for bundle in range(3):                     # три пучка глубины
        base_y = 830 + bundle * 55
        amp = 46 - bundle * 9
        blur = ('', ' filter="url(#b2)"', ' filter="url(#b4)"')[bundle]
        for k in range(9):
            ph = random.uniform(0, 6.28)
            yo = base_y + k * 6 + random.uniform(-4, 4)
            pts = []
            for xx in range(-40, W + 41, 24):
                yy = (yo + amp * math.sin(xx / 210 + ph)
                      + 14 * math.sin(xx / 87 + ph * 1.7))
                pts.append(f'{xx},{yy:.0f}')
            col = random.choice(('#2a7a8a', '#3a9aae', '#4ab8c8', '#57d8e8'))
            op = .10 + bundle * .05 + random.uniform(0, .08)
            out.append(f'<polyline points="{" ".join(pts)}" fill="none" '
                       f'stroke="{col}" stroke-width="1" '
                       f'opacity="{op:.2f}"{blur}/>')
    return ''.join(out)

seawaves = _waves()
random.seed(7)


def window(x0, y0, w, h, i0, i1, title, big=False):
    """Одно окно: линии, зазор, боке, события."""
    n = i1 - i0
    xs = [x0 + j * w / (n - 1) for j in range(n)]
    seg_p = px[i0:i1]
    # модель окна: из старта окна, размах лога = размаху лога цены
    c0 = cum[i0]
    reach = max(abs(cum[i] - c0) for i in range(i0, i1)) or 1.0
    spanw = math.log(max(seg_p) / min(seg_p)) or .2
    Qw = reach / spanw
    seg_m = [seg_p[0] * math.exp((cum[i0 + j] - c0) / Qw)
             for j in range(n)]
    seg_o = [oim.get(days[i]) or 0 for i in range(i0, i1)]
    lo = min(min(seg_p), min(seg_m)) * 0.97
    hi = max(max(seg_p), max(seg_m)) * 1.03
    olo, ohi = min(seg_o) * 0.9, max(seg_o) * 1.05 or 1

    def Y(v):  return y0 + h - (v - lo) / (hi - lo) * h
    def YO(v): return y0 + h - (v - olo) / (ohi - olo) * (h * 0.45)

    def path(vals, yf):
        P = [(xs[j], yf(v)) for j, v in enumerate(vals)]
        if len(P) < 3:
            return 'M' + ' L'.join(f'{x:.1f},{y:.1f}' for x, y in P)
        d = f'M{P[0][0]:.1f},{P[0][1]:.1f}'
        for j in range(len(P) - 1):
            p0 = P[max(0, j - 1)]
            p1, p2 = P[j], P[j + 1]
            p3 = P[min(len(P) - 1, j + 2)]
            c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
            c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
            d += (f' C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} '
                  f'{p2[0]:.1f},{p2[1]:.1f}')
        return d

    p_white = path(seg_p, Y)
    p_cyan = path(seg_m, Y)
    p_amber = path(seg_o, YO)

    # подушка долга: сегментно, только где белая НАД бирюзовой
    debt_polys = []
    seg = []
    for j in range(n):
        if seg_p[j] > seg_m[j]:
            seg.append(j)
        elif seg:
            debt_polys.append(seg)
            seg = []
    if seg:
        debt_polys.append(seg)
    debt_svg = ''
    for sg in debt_polys:
        if len(sg) < 2:
            continue
        pts = [f'{xs[j]:.1f},{Y(seg_p[j]):.1f}' for j in sg]
        pts += [f'{xs[j]:.1f},{Y(seg_m[j]):.1f}' for j in reversed(sg)]
        debt_svg += (f'<polygon points="{" ".join(pts)}" '
                     f'fill="url(#debt)" opacity=".9" filter="url(#b2)"/>')

    # боке-ликвидации
    bokeh = []
    for j in range(n):
        l = lqm.get(days[i0 + j])
        if not l:
            continue
        for usd, col, side in ((l['long_liquidations_usd'], '#f0b356', 1),
                               (l['short_liquidations_usd'], '#55d8e8', -1)):
            if usd < 15000:
                continue
            r = min(11, 2 + math.sqrt(usd) / 110)
            yy = Y(seg_p[j]) + side * (14 + r * 2)
            bokeh.append(f'<circle cx="{xs[j]:.0f}" cy="{yy:.0f}" r="{r:.1f}" '
                         f'fill="{col}" opacity=".20" filter="url(#b4)"/>')

    # события: конфликты для подписей
    ev = []
    for j in range(2, n):
        i = i0 + j
        dpx = seg_p[j] / seg_p[j - 1] - 1
        if deltas[i] < 0 and dpx > 0.04 and abs(deltas[i]) > 3e5:
            ev.append((j, -1, f"цена +{dpx*100:.0f}% при продажах "
                              f"${abs(deltas[i])/1e6:.1f}M — держат заявками"))
        if seg_o[j] and seg_o[j - 1] and seg_o[j]/seg_o[j-1] > 1.28:
            ev.append((j, 1, "плечо влилось "
                             f"+{(seg_o[j]/seg_o[j-1]-1)*100:.0f}% за день"))
        if seg_o[j] and seg_o[j-1] and seg_o[j]/seg_o[j-1] < 0.86 \
                and abs(dpx) < 0.03:
            ev.append((j, 1, "плечо вышло, цена устояла"))
    # прорядить: не чаще раза в n/5
    picked, last = [], -99
    for j, s_, txt in sorted(ev, key=lambda e: e[0]):
        if j - last >= max(4, n // 6):
            picked.append((j, s_, txt))
            last = j
    labels = []
    show_n = 4 if big else (0 if n > 120 else 2)
    for k_, (j, s_, txt) in enumerate(picked[:show_n]):
        ax, ay = xs[j], Y(seg_p[j])
        ly = y0 + (18 + (k_ % 2) * 26 if s_ < 0 else h - 14 - (k_ % 2) * 24)
        anch = 'start' if xs[j] < x0 + w * 0.6 else 'end'
        labels.append(
            f'<line x1="{ax:.0f}" y1="{ay:.0f}" x2="{ax:.0f}" y2="{ly:.0f}" '
            f'stroke="#a8dce8" stroke-width=".6" opacity=".5"/>'
            f'<circle cx="{ax:.0f}" cy="{ay:.0f}" r="3.2" fill="#e8f4f8" '
            f'filter="url(#b2)"/>'
            f'<text x="{ax:.0f}" y="{ly - 4 if s_ < 0 else ly + 11:.0f}" '
            f'text-anchor="{anch}" class="lbl">{txt}</text>')

    # флажки эпизодов на большом трендовом окне
    flags = []
    if not big and n > 120:
        med = sorted(vols[max(0, i0-30):i0] or vols[:30])[len(vols[:30])//2]
        j = 0
        while j < n:
            i = i0 + j
            if i < 30:
                j += 1
                continue
            m30 = sorted(vols[i-30:i])
            base = m30[len(m30)//2]
            if base and vols[i] >= 4 * base:
                j2 = j
                while j2+1 < n and vols[i0+j2+1] >= 2*base:
                    j2 += 1
                pk = max(range(j, j2+1), key=lambda q: vols[i0+q])
                r7 = (seg_p[pk+7]/seg_p[pk]-1) if pk+7 < n else None
                v = ('зреет' if r7 is None else
                     'слили' if r7 <= -.25 else
                     'устояли' if r7 >= -.10 else 'отдали часть')
                col = {'слили': '#f0b356', 'устояли': '#55d8e8',
                       'зреет': '#a8dce8', 'отдали часть': '#ffd98c'}[v]
                mult = vols[i0+pk]/base
                tier = len(flags) % 3
                fy = y0 + 8 + tier * 13
                flags.append(
                    f'<line x1="{xs[pk]:.0f}" y1="{Y(seg_p[pk]):.0f}" '
                    f'x2="{xs[pk]:.0f}" y2="{fy+3}" stroke="{col}" '
                    f'stroke-width=".7" opacity=".5"/>'
                    f'<text x="{xs[pk]:.0f}" y="{fy}" text-anchor="middle" '
                    f'class="flg" fill="{col}">×{mult:.0f} · {v}</text>')
                j = j2 + 8
            else:
                j += 1

    # искры: локальные экстремумы белой и бирюзовой
    sparks = ''
    rays = ''
    for j in range(2, n - 2):
        for vals, colr in ((seg_p, '#ffffff'), (seg_m, '#7ae0ea'),
                           (seg_o, '#ffcf7a')):
            v = vals[j]
            if not v:
                continue
            if (v > vals[j-1] and v > vals[j+1]) or \
               (v < vals[j-1] and v < vals[j+1]):
                if random.random() > (.5 if big else .3):
                    continue
                yv = Y(v) if vals is not seg_o else YO(v)
                sparks += (f'<circle cx="{xs[j]:.0f}" cy="{yv:.0f}" r="1.6" '
                           f'fill="{colr}"/>'
                           f'<circle cx="{xs[j]:.0f}" cy="{yv:.0f}" r="4.5" '
                           f'fill="{colr}" opacity=".5" filter="url(#b2)"/>'
                           f'<circle cx="{xs[j]:.0f}" cy="{yv:.0f}" r="9" '
                           f'fill="{colr}" opacity=".18" filter="url(#b6)"/>')
                if random.random() < .22:
                    rays += (f'<line x1="{xs[j]:.0f}" y1="{yv:.0f}" '
                             f'x2="{xs[j]:.0f}" '
                             f'y2="{max(y0-30, yv-random.uniform(60,150)):.0f}" '
                             f'stroke="#b8d8e8" stroke-width=".6" '
                             f'opacity=".22"/>')
    # растровые пятна точек — у дней с крупными ликвидациями
    lq_days = sorted(range(n), key=lambda q: -(
        (lqm.get(days[i0+q]) or {}).get('total_liquidations_usd', 0)))[:3]
    for q in lq_days:
        gx, gy = xs[q], Y(seg_p[q]) + random.choice((-1, 1)) * 46
        sparks += ''.join(
            f'<circle cx="{gx + a*7 - 24:.0f}" cy="{gy + b*7 - 14:.0f}" '
            f'r=".9" fill="#7ab8d8" opacity=".3"/>'
            for a in range(8) for b in range(5))
    beads = ''.join(
        f'<circle cx="{xs[j] + random.uniform(-4, 4):.0f}" '
        f'cy="{Y(seg_m[j]) + random.uniform(-5, 5):.0f}" '
        f'r="{random.uniform(1.2, 3.4):.1f}" fill="#7ae0ea" '
        f'opacity="{random.uniform(.25, .6):.2f}" filter="url(#b2)"/>'
        for j in range(0, n, max(2, n // 26)))
    sw_main = 3.2 if big else 2.2
    return f'''
  <g>
    <text x="{x0}" y="{y0 - 8}" class="ttl">{title}</text>
    {''.join(bokeh)}
    {debt_svg}
    <path d="{p_amber}" class="ln" stroke="#f0b356" stroke-width="1.3"
          opacity=".55" filter="url(#b2)"/>
    <path d="{p_amber}" class="ln" stroke="#ffcf7a" stroke-width=".9"
          opacity=".9"/>
    {rays}
    <path d="{p_cyan}" class="ln" stroke="#3fb0c8"
          stroke-width="3" opacity=".28" filter="url(#b6)"/>
    <path d="{p_cyan}" class="ln" stroke="#7ae0ea"
          stroke-width="1.4"/>
    {beads}
    <path d="{p_white}" class="ln" stroke="#e8f4f8" stroke-width="1.1"
          opacity=".95"/>
    {sparks}
    <circle cx="{xs[-1]:.0f}" cy="{Y(seg_p[-1]):.0f}" r="4.6"
          fill="#fff" filter="url(#b2)"/>
    <circle cx="{xs[-1]:.0f}" cy="{Y(seg_p[-1]):.0f}" r="10"
          fill="#57d8e8" opacity=".25" filter="url(#b6)"/>
    {''.join(flags)}
    {''.join(labels)}
  </g>'''


N = len(days)
i0v = N - 15
c0 = cum[i0v]
reach = max(abs(cum[i] - c0) for i in range(i0v, N)) or 1.0
spanv = math.log(max(px[i0v:]) / min(px[i0v:])) or .2
mv = px[i0v] * math.exp((cum[-1] - c0) / (reach / spanv))
gap_now = px[-1] / mv - 1
verdict = ('ЖДАТЬ' if gap_now > 0.10 else
           'СМОТРЕТЬ ВХОД' if gap_now < -0.10 else 'ДЕРЖАТЬ')
vcol = '#f0b356' if verdict == 'ЖДАТЬ' else '#55d8e8'
reason = (f'за две недели цена выше своих денег на {gap_now*100:.0f}% — '
          f'ход держат заявками, не покупками' if gap_now > 0.10 else
          f'деньги выше цены на {abs(gap_now)*100:.0f}%' if gap_now < -0.10
          else 'цена и деньги идут вровень')

def _edge_orbs(k):
    out = []
    for _ in range(k):
        # края и низ кадра — как в референсе
        if random.random() < .6:
            x, y = random.uniform(0, W), random.uniform(760, 1000)
        else:
            x = random.choice((random.uniform(0, 130),
                               random.uniform(W - 130, W)))
            y = random.uniform(80, 1000)
        r = random.uniform(9, 30)
        col = random.choice(('#7ab8d8', '#a8d4e8', '#ffcf7a'))
        out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.1f}" '
                   f'fill="{col}" opacity="{random.uniform(.10, .26):.2f}" '
                   f'filter="url(#b12)"/>')
    return ''.join(out)

dust = (_edge_orbs(26)
        + ''.join(f'<circle cx="{random.uniform(0, W):.0f}" '
                  f'cy="{random.uniform(60, 990):.0f}" '
                  f'r="{random.uniform(.6, 1.8):.1f}" fill="#a8dce8" '
                  f'opacity="{random.uniform(.08, .25):.2f}"/>'
                  for _ in range(160)))  # пыль

svg = f'''<svg viewBox="0 0 {W} 1010" xmlns="http://www.w3.org/2000/svg">
<rect width="{W}" height="1010" fill="url(#bgGrad)"/>
{seawaves}
<rect width="{W}" height="1010" fill="url(#vign)" opacity=".7"/>
<defs>
  <filter id="b2" x="-80%" y="-80%" width="260%" height="260%">
    <feGaussianBlur stdDeviation="2"/></filter>
  <filter id="b4" x="-80%" y="-80%" width="260%" height="260%">
    <feGaussianBlur stdDeviation="4"/></filter>
  <filter id="b6" x="-80%" y="-80%" width="260%" height="260%">
    <feGaussianBlur stdDeviation="6"/></filter>
  <linearGradient id="bgGrad" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#04101e"/>
    <stop offset=".62" stop-color="#071826"/>
    <stop offset="1" stop-color="#0a2430"/>
  </linearGradient>
  <radialGradient id="vign" cx="50%" cy="45%" r="75%">
    <stop offset=".62" stop-color="#000" stop-opacity="0"/>
    <stop offset="1" stop-color="#000" stop-opacity=".55"/>
  </radialGradient>
  <filter id="b12" x="-90%" y="-90%" width="280%" height="280%">
    <feGaussianBlur stdDeviation="12"/></filter>
  <filter id="b40" x="-90%" y="-90%" width="280%" height="280%">
    <feGaussianBlur stdDeviation="40"/></filter>
  <linearGradient id="debt" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#f0b356" stop-opacity=".22"/>
    <stop offset="1" stop-color="#f0b356" stop-opacity=".04"/>
  </linearGradient>
</defs>
{dust}
{window(PAD, 96, W - 460, 380, N - 15, N, 'ДВЕ НЕДЕЛИ · ЧАСЫ ПОДКЛЮЧАТСЯ HOURLY-ВЫГРУЗКОЙ', big=True)}
{window(PAD, 560, (W - PAD*3)//2, 340, N - 90, N, 'КВАРТАЛ')}
{window(PAD*2 + (W - PAD*3)//2, 560, (W - PAD*3)//2, 340, 0, N, 'ПОЛГОДА · ФЛАЖКИ — ИСХОДЫ ВСПЛЕСКОВ')}
<text x="{W-390}" y="158" class="tickGlow"
  filter="url(#b6)">{A.coin.upper()}</text>
<text x="{W-390}" y="158" class="tick">{A.coin.upper()}</text>
<text x="{W-390}" y="216" class="verd" fill="{vcol}">{verdict}</text>
<foreignObject x="{W-392}" y="234" width="330" height="120">
  <div xmlns="http://www.w3.org/1999/xhtml" class="why">{reason}</div>
</foreignObject>
<text x="{W-390}" y="368" class="leg"><tspan fill="#e8f4f8">— цена</tspan>
<tspan dx="12" fill="#55d8e8">— цена по деньгам</tspan>
<tspan dx="12" fill="#ffcf7a">— плечо</tspan></text>
<text x="{W-390}" y="390" class="leg" fill="#7a93a8">тёплая подушка — цена выше денег</text>
<text x="{W-390}" y="408" class="leg" fill="#7a93a8">боке: янтарь — сняты лонги · бирюза — шорты</text>
</svg>'''

html = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{A.coin.upper()} · поток</title><style>
body{{margin:0;background:#04080f;display:flex;justify-content:center}}
svg{{width:100%;max-width:1600px;height:auto}}
.ln{{fill:none;stroke-linecap:round;stroke-linejoin:round}}
.ttl{{font:600 9px Arial;fill:#57708a;letter-spacing:.28em}}
.lbl{{font:italic 10.5px Georgia;fill:#c9dce8}}
.flg{{font:700 8px Arial;letter-spacing:.04em}}
.tick{{font:800 44px Arial;fill:#e8f4f8;letter-spacing:.02em}}
.verd{{font:800 30px Arial;letter-spacing:.06em}}
.why{{font:italic 13px Georgia;color:#a8c4d4;line-height:1.5}}
.leg{{font:600 10px Arial;letter-spacing:.04em}}
.tickGlow{{font:800 58px Arial;fill:#57d8e8;
  letter-spacing:.02em;opacity:.5}}
.back{{position:fixed;left:18px;top:16px;z-index:9;
  font:700 11px Arial;letter-spacing:.14em;color:#57d8e8;
  text-decoration:none;border:1px solid rgba(87,216,232,.5);
  border-radius:8px;padding:5px 11px;opacity:.75}}
.back:hover{{opacity:1;border-color:#7ae0ea}}
</style></head><body><a class="back" href="podium.html">\u2190 \u0437\u0430\u043b</a>{svg}</body></html>'''
open(A.out, 'w').write(html)
print(f'{A.coin}: поток собран,', len(html), 'байт · зазор сейчас',
      f'{gap_now*100:+.0f}% · вердикт {verdict}')
