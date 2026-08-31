#!/usr/bin/env python3
"""Экран-поток v7 — вид одобренного стенда (перенос 01.09).

Три окна времени, три линии со смыслами:
  БЕЛАЯ — цена (факт);
  БИРЮЗОВАЯ, главная — «цена по деньгам»: где цена была бы, если бы
    её двигал только перекос покупок к продажам;
  ЯНТАРНАЯ — плечо (открытый интерес).
Зазор белой над бирюзовой — тёплая подушка долга: цена выше своих
денег, ход держат заявками. Рисуется частоколом штрихов, заливок нет.

Объём даётся КАМЕРОЙ, не геометрией (решение владельца 31.08):
ближняя линия режет дальнюю тёмной подложкой цветом фона, слои
отличаются резкостью, крупные расфокусы ложатся ПОВЕРХ линий как
пылинки перед объективом.

Раскладка: «две недели» крупным вверху слева, справа текстовая
колонна, внизу «квартал» и «полгода».
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

# «цена по деньгам»: exp-модель от накопленного ПЕРЕКОСА.
#
# Было: накопленная дельта в ДОЛЛАРАХ, и калибровка Q считалась
# заново в каждом окне так, чтобы размах модели совпал с размахом
# цены этого окна. Из-за этого провал линии равнялся размаху цены ПО
# ПОСТРОЕНИЮ: чем шире окно, тем больше размах, тем глубже уходила
# модель — на полугодии SKR она падала на 74% и утаскивала за собой
# нижнюю границу кадра, прижимая цену к потолку. Зазор «цена выше
# своих денег на N%» при этом не измерялся, а изготавливался
# нормировкой: 49% на двух неделях против 31% на полугодии у одной и
# той же монеты (разбор 31.08, замечание владельца — «деньги уходят
# вниз резко на больших тф»).
#
# Стало. Шаг дня — ПЕРЕКОС К ОБОРОТУ ЭТОГО ЖЕ ДНЯ, величина
# безразмерная и ограниченная: у SKR медиана 2.3%, максимум 15%.
# День с дельтой −$2M при обороте $104M (28.08) теперь весит два
# процента, а не рисует вертикаль, потому что доллары такого дня
# затмевали весь остальной ряд.
#
# Калибровка K — ОДНА на все окна, считается по всему ряду. Именно
# она делает зазор сравнимым между таймфреймами: одно и то же число
# на двух неделях и на полугодии означает одно и то же. Якорь
# остаётся на левом крае окна — окно показывает расхождение,
# накопленное В НЁМ, а не с начала истории.
steps = [(deltas[i] / vols[i] if vols[i] else 0.0)
         for i in range(len(deltas))]
cum = []
c = 0.0
for x in steps:
    c += x
    cum.append(c)
K_MONEY = ((math.log(max(px) / min(px)) or .2)
           / ((max(cum) - min(cum)) or 1.0))


# ── ВИД ПО ОДОБРЕННОМУ СТЕНДУ (перенос 01.09) ───────────────────────
# Стенд flow_ref_stand.py перерисовывал готовый flow_<монета>.html в
# утверждённом языке. Здесь тот же язык, но рисуется сразу из данных —
# промежуточного документа больше нет.
#
# Что утверждено владельцем и не меняется: объём даётся КАМЕРОЙ, не
# геометрией. Работают три приёма — ближняя линия режет дальнюю тёмной
# подложкой цветом фона (подложка тоже растворяется к краям, иначе на
# концах остаются тёмные обрубки), разная резкость слоёв, и крупные
# размытые расфокусы ПОВЕРХ линий как пылинки перед объективом.
# Заливок нет: подушка долга — частокол тонких штрихов.
# Формула экрана: три линии и две-три точки с текстом, остальное —
# атрибутика.
#
# ЧТО НЕ ПЕРЕНОСИТСЯ СО СТЕНДА: денежная линия. Стенд собран до правки
# 31.08 и показывал «цена выше своих денег на 297%» при бирюзовой,
# падающей от края до края, — это старая калибровка, где провал равен
# размаху цены по построению. Здесь линия считается K_MONEY, как выше.
random.seed(23)

VB_W, VB_H = 1920, 1080
C_STEEL, C_TEAL, C_ORNG, C_DARK, TXT = ('#dcecf8', '#3fe4f0', '#ffb054',
                                        '#06192c', '#9fb8cc')
RX = 1296                       # текстовая колонна
N = len(days)

# рамки окон — раскладка владельца: большое сверху слева, два внизу
WINS = [
    ('w2', (150, 168, 1080, 440), 'две недели', 22, max(0, N - 15), N, 4),
    ('qr', (150, 690, 790, 260), 'квартал', 19, max(0, N - 90), N, 2),
    ('hf', (1020, 690, 790, 260), 'полгода', 19, 0, N, 2),
]


def smooth(P):
    """Кривая Катмулла-Рома через точки — та же, что на стенде."""
    if len(P) < 2:
        return f'M{P[0][0]:.1f},{P[0][1]:.1f}' if P else 'M0,0'
    d = f'M{P[0][0]:.1f},{P[0][1]:.1f}'
    for j in range(len(P) - 1):
        p0, p1 = P[max(0, j - 1)], P[j]
        p2, p3 = P[j + 1], P[min(len(P) - 1, j + 2)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += (f' C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} '
              f'{p2[0]:.1f},{p2[1]:.1f}')
    return d


defs = ['''<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
 <stop offset="0" stop-color="#03101f"/>
 <stop offset=".48" stop-color="#0a2a42"/>
 <stop offset="1" stop-color="#041424"/></linearGradient>
<radialGradient id="halo" cx="50%" cy="50%" r="50%">
 <stop offset="0" stop-color="#1a5a7a" stop-opacity=".5"/>
 <stop offset="1" stop-color="#1a5a7a" stop-opacity="0"/></radialGradient>
<radialGradient id="flW" cx="50%" cy="50%" r="50%">
 <stop offset="0" stop-color="#fff8ec" stop-opacity="1"/>
 <stop offset=".3" stop-color="#ffc070" stop-opacity=".6"/>
 <stop offset="1" stop-color="#ffb054" stop-opacity="0"/></radialGradient>
<radialGradient id="flC" cx="50%" cy="50%" r="50%">
 <stop offset="0" stop-color="#f2feff" stop-opacity="1"/>
 <stop offset=".3" stop-color="#5fe8f2" stop-opacity=".6"/>
 <stop offset="1" stop-color="#3fe4f0" stop-opacity="0"/></radialGradient>
<radialGradient id="orbB" cx="50%" cy="50%" r="50%">
 <stop offset="0" stop-color="#8fc4e8" stop-opacity=".42"/>
 <stop offset=".62" stop-color="#8fc4e8" stop-opacity=".2"/>
 <stop offset="1" stop-color="#8fc4e8" stop-opacity="0"/></radialGradient>
<radialGradient id="orbA" cx="50%" cy="50%" r="50%">
 <stop offset="0" stop-color="#ffb35c" stop-opacity=".38"/>
 <stop offset=".62" stop-color="#ffb35c" stop-opacity=".18"/>
 <stop offset="1" stop-color="#ffb35c" stop-opacity="0"/></radialGradient>
<radialGradient id="vig" cx="50%" cy="48%" r="70%">
 <stop offset=".66" stop-color="#000" stop-opacity="0"/>
 <stop offset="1" stop-color="#000" stop-opacity=".62"/></radialGradient>
<linearGradient id="topfade" x1="0" y1="0" x2="0" y2="1">
 <stop offset="0" stop-color="#000" stop-opacity=".34"/>
 <stop offset="1" stop-color="#000" stop-opacity="0"/></linearGradient>
<filter id="f2" x="-80%" y="-80%" width="260%" height="260%">
 <feGaussianBlur stdDeviation="1.8"/></filter>
<filter id="f6" x="-80%" y="-80%" width="260%" height="260%">
 <feGaussianBlur stdDeviation="6"/></filter>
<filter id="f16" x="-90%" y="-90%" width="280%" height="280%">
 <feGaussianBlur stdDeviation="16"/></filter>
<filter id="f34" x="-90%" y="-90%" width="280%" height="280%">
 <feGaussianBlur stdDeviation="34"/></filter>''']
for _k, (_nx, _ny, _nw, _nh), *_r in WINS:
    for _tag, _col in (('s', C_STEEL), ('t', C_TEAL), ('o', C_ORNG),
                       ('d', C_DARK)):
        defs.append(
            f'<linearGradient id="g{_k}{_tag}" gradientUnits="userSpaceOnUse"'
            f' x1="{_nx}" y1="0" x2="{_nx + _nw}" y2="0">'
            f'<stop offset="0" stop-color="{_col}" stop-opacity="0"/>'
            f'<stop offset=".18" stop-color="{_col}" stop-opacity="1"/>'
            f'<stop offset=".82" stop-color="{_col}" stop-opacity="1"/>'
            f'<stop offset="1" stop-color="{_col}" stop-opacity="0"/>'
            f'</linearGradient>')


def draw(key, frame, cap, capsz, i0, i1, nlab):
    """Одно окно: три линии, зазор частоколом, точки с текстом."""
    nx, ny, nw, nh = frame
    n = i1 - i0
    if n < 3:
        return '', ''
    k = nh / 452.0                      # смещения слоёв к высоте окна
    xs = [nx + j * nw / (n - 1) for j in range(n)]

    seg_p = px[i0:i1]
    c0 = cum[i0]
    seg_m = [seg_p[0] * math.exp(K_MONEY * (cum[i0 + j] - c0))
             for j in range(n)]
    seg_o = [oim.get(days[i]) or 0 for i in range(i0, i1)]

    lo = min(min(seg_p), min(seg_m)) * 0.97
    hi = max(max(seg_p), max(seg_m)) * 1.03
    olo = min(seg_o) * 0.9
    ohi = (max(seg_o) * 1.05) or 1.0

    def Y(v):
        return ny + nh - (v - lo) / ((hi - lo) or 1) * nh

    def YO(v):
        return ny + nh - (v - olo) / ((ohi - olo) or 1) * (nh * 0.45)

    # Слои идут от дальнего к ближнему; смещение по вертикали и есть
    # глубина — плечо ниже и мягче, цена выше и резче.
    lay = (('плечо', [YO(v) for v in seg_o], f'g{key}o', 20, 62, 4.4, .26,
            1.1),
           ('деньги', [Y(v) for v in seg_m], f'g{key}t', 0, 8, 6.0, .46, 1.5),
           ('цена', [Y(v) for v in seg_p], f'g{key}s', -16, -44, 4.2, .30,
            1.1))
    art, P = [], {}
    for name, ys, grad, dx, dy, glow, gop, sw in lay:
        pts = [(xs[j] + dx, ys[j] + dy * k) for j in range(n)]
        P[name] = pts
        d = smooth(pts)
        if name != 'плечо':            # ближняя режет дальнюю
            art.append(f'<path d="{d}" class="ln" stroke="url(#g{key}d)" '
                       f'stroke-width="{13 * k + 3:.0f}" opacity=".85" '
                       f'filter="url(#f2)"/>')
        art.append(f'<path d="{d}" class="ln" stroke="url(#{grad})" '
                   f'stroke-width="{glow * 2.6:.1f}" '
                   f'opacity="{gop * .38:.2f}" filter="url(#f16)"/>')
        art.append(f'<path d="{d}" class="ln" stroke="url(#{grad})" '
                   f'stroke-width="{glow:.1f}" opacity="{gop:.2f}" '
                   f'filter="url(#f6)"/>')
        art.append(f'<path d="{d}" class="ln" stroke="url(#{grad})" '
                   f'stroke-width="{sw}" opacity="1"/>')

    # зазор — частокол тонких штрихов, заливок нет
    wh, cy = P['цена'], P['деньги']
    for j in range(0, n, max(1, n // 52)):
        x1, y1 = wh[j]
        y2 = cy[j][1]
        if y1 < y2 - 4:
            art.append(f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x1:.0f}" '
                       f'y2="{y2:.0f}" stroke="{C_ORNG}" stroke-width=".6" '
                       f'opacity=".10"/>')

    # ── события: две-три точки с короткой подписью ──
    ev = []
    for j in range(2, n):
        i = i0 + j
        dpx = seg_p[j] / seg_p[j - 1] - 1 if seg_p[j - 1] else 0
        if deltas[i] < 0 and dpx > 0.04 and abs(deltas[i]) > 3e5:
            ev.append((j, f'+{dpx*100:.0f}% на продажах', 'flW'))
        elif (seg_o[j] and seg_o[j - 1]
                and seg_o[j] / seg_o[j - 1] > 1.28):
            ev.append((j, f'плечо +{(seg_o[j]/seg_o[j-1]-1)*100:.0f}%',
                       'flW'))
    picked, last = [], -99
    for j, txt, fl in ev:
        if j - last >= max(4, n // 6):
            picked.append((j, txt, fl))
            last = j
    pts_svg, words = [], []
    for i_, (j, txt, fl) in enumerate(picked[:nlab]):
        x, y = wh[j]
        ly = y - (118 if i_ == 0 else 78) * max(.62, k)
        pts_svg.append(
            f'<line x1="{x:.0f}" y1="{y:.0f}" x2="{x:.0f}" y2="{ly:.0f}" '
            f'stroke="#d8f0f8" stroke-width=".9" opacity=".28"/>'
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{46 * k:.0f}" '
            f'fill="url(#{fl})" opacity=".55" filter="url(#f6)"/>'
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{17 * k:.0f}" '
            f'fill="url(#{fl})"/>'
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="3" fill="#fff"/>')
        xt = min(max(x, nx + 60), nx + nw - 60)
        words.append(f'<text x="{xt:.0f}" y="{ly - 10:.0f}" '
                     f'text-anchor="middle" class="mark" '
                     f'style="font-size:{capsz}px" opacity=".68">{txt}</text>')

    bx, by = wh[-1]                      # маяк — сегодня
    pts_svg.append(f'<circle cx="{bx:.0f}" cy="{by:.0f}" r="{40 * k:.0f}" '
                   f'fill="url(#flC)" opacity=".55" filter="url(#f6)"/>'
                   f'<circle cx="{bx:.0f}" cy="{by:.0f}" r="{15 * k:.0f}" '
                   f'fill="url(#flC)"/>'
                   f'<circle cx="{bx:.0f}" cy="{by:.0f}" r="3" fill="#fff"/>')
    label = (f'<text x="{nx}" y="{ny - 22}" class="mark" '
             f'style="font-size:{capsz - 2}px" opacity=".38">{cap}</text>')
    return ''.join(art) + ''.join(pts_svg), ''.join(words) + label


scene, over = '', ''
for _w in WINS:
    _a, _b = draw(*_w)
    scene += _a
    over += _b

# ── вердикт от главной линии ────────────────────────────────────────
i0v = max(0, N - 15)
c0 = cum[i0v]
mv = px[i0v] * math.exp(K_MONEY * (cum[-1] - c0))
gap_now = px[-1] / mv - 1
verdict = ('ЖДАТЬ' if gap_now > 0.10 else
           'СМОТРЕТЬ ВХОД' if gap_now < -0.10 else 'ДЕРЖАТЬ')
vcol = C_ORNG if verdict == 'ЖДАТЬ' else C_TEAL
reason = (f'за две недели цена выше своих денег на {gap_now*100:.0f}% — '
          f'ход держат заявками, не покупками' if gap_now > 0.10 else
          f'деньги выше цены на {abs(gap_now)*100:.0f}%' if gap_now < -0.10
          else 'цена и деньги идут вровень')

# ── воздух: гало, орбы, пыль ───────────────────────────────────────
air = ['<ellipse cx="700" cy="380" rx="820" ry="300" fill="url(#halo)" '
       'filter="url(#f34)"/>',
       '<ellipse cx="1100" cy="880" rx="900" ry="260" fill="url(#halo)" '
       'opacity=".7" filter="url(#f34)"/>']
for _cx, _cy, _r, _g in ((286, 246, 36, 'orbB'), (1704, 900, 42, 'orbB'),
                         (1560, 190, 26, 'orbB'), (640, 606, 32, 'orbA'),
                         (1420, 640, 24, 'orbA'), (120, 880, 28, 'orbB')):
    air.append(f'<circle cx="{_cx}" cy="{_cy}" r="{_r}" fill="url(#{_g})" '
               f'filter="url(#f6)"/>')
for _ in range(160):
    _x, _y = random.uniform(0, VB_W), random.uniform(40, VB_H - 20)
    _c = '#ffc76a' if random.random() < .48 else '#55d8e8'
    air.append(f'<circle cx="{_x:.0f}" cy="{_y:.0f}" '
               f'r="{random.uniform(.5, 1.3):.1f}" fill="{_c}" '
               f'opacity="{random.uniform(.10, .38):.2f}"/>')

# ── передний план: расфокус перед объективом, ПОВЕРХ линий ─────────
fg = []
for _cx, _cy, _r, _g, _op in ((372, 470, 112, 'orbA', .45),
                              (1180, 300, 92, 'orbB', .4),
                              (860, 860, 128, 'orbB', .34),
                              (1660, 780, 84, 'orbA', .38),
                              (196, 760, 74, 'orbB', .3)):
    fg.append(f'<circle cx="{_cx}" cy="{_cy}" r="{_r}" fill="url(#{_g})" '
              f'opacity="{_op}" filter="url(#f34)"/>')
for _ in range(24):
    _x, _y = random.uniform(60, VB_W - 60), random.uniform(150, VB_H - 80)
    _c = '#ffc76a' if random.random() < .45 else '#8fd8f0'
    fg.append(f'<circle cx="{_x:.0f}" cy="{_y:.0f}" '
              f'r="{random.uniform(5, 15):.0f}" fill="{_c}" '
              f'opacity="{random.uniform(.10, .20):.2f}" '
              f'filter="url(#f16)"/>')

TICK = A.coin.upper()
column = f'''
<text x="{RX}" y="272" class="tickGlow" filter="url(#f6)">{TICK}</text>
<text x="{RX}" y="272" class="tick">{TICK}</text>
<text x="{RX}" y="352" class="verd" fill="{vcol}">{verdict}</text>
<foreignObject x="{RX - 3}" y="376" width="556" height="130">
 <div xmlns="http://www.w3.org/1999/xhtml" class="why">{reason}</div>
</foreignObject>
<text x="{RX}" y="556" class="leg"><tspan fill="{C_STEEL}">— цена</tspan>
<tspan dx="16" fill="{C_TEAL}">— цена по деньгам</tspan>
<tspan dx="16" fill="{C_ORNG}">— плечо</tspan></text>
<text x="{RX}" y="586" class="leg" fill="#7f9bb0">тёплая подушка — цена выше денег</text>
<text x="{RX}" y="610" class="leg" fill="#7f9bb0">точки — конфликты хода · маяк — сегодня</text>'''

svg = f'''<svg viewBox="0 0 {VB_W} {VB_H}" xmlns="http://www.w3.org/2000/svg">
<defs>{''.join(defs)}</defs>
<rect width="{VB_W}" height="{VB_H}" fill="url(#bg)"/>
{''.join(air)}
{scene}
{''.join(fg)}
{over}
{column}
<rect width="{VB_W}" height="150" fill="url(#topfade)"/>
<rect width="{VB_W}" height="{VB_H}" fill="url(#vig)"/>
</svg>'''

html = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{TICK} \u00b7 поток</title><style>
*{{box-sizing:border-box;margin:0}}
html,body{{height:100%}}
body{{background:#03101f;overflow:hidden}}
svg{{display:block;width:100vw;height:100vh}}
.ln{{fill:none;stroke-linecap:round;stroke-linejoin:round}}
.mark{{font-family:Arial,Helvetica,sans-serif;font-weight:800;
  fill:{TXT};letter-spacing:.05em}}
.tick{{font:800 62px Arial;fill:#eef6fb;letter-spacing:.02em}}
.tickGlow{{font:800 62px Arial;fill:{C_TEAL};letter-spacing:.02em;
  opacity:.45}}
.verd{{font:800 36px Arial;letter-spacing:.06em}}
.why{{font:italic 16px Georgia,serif;color:#a8c4d4;line-height:1.55}}
.leg{{font:700 12px Arial;letter-spacing:.06em}}
.back{{position:fixed;left:18px;top:16px;z-index:9;
  font:700 11px Arial;letter-spacing:.14em;color:#5fe0ea;
  text-decoration:none;border:1px solid rgba(95,224,234,.35);
  border-radius:8px;padding:5px 11px;opacity:.55}}
.back:hover{{opacity:1}}
</style></head><body><a class="back" href="podium.html">\u2190 зал</a>
{svg}</body></html>'''

_out = Path(A.out) if getattr(A, 'out', None) else Path(f'flow_{A.coin}.html')
_out.write_text(html, encoding='utf-8')
print(f'{A.coin}: поток собран,', len(html), 'байт · зазор сейчас',
      f'{gap_now*100:+.0f}% · вердикт {verdict}')
