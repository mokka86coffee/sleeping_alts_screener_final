#!/usr/bin/env python3
"""Экран-поток v10 — три горизонта планами в глубину (перенос 01.09).

Одна сцена, три горизонта тремя планами: полгода далеко, мелко и
тускло; квартал в середине; две недели близко, крупно и резко.
Ближний план ниже и правее — взгляд скользит от общего к
сегодняшнему.

ГЛАВНОЕ ПРАВИЛО: горизонт тем ярче и резче, чем он ближе к «сейчас».
Один множитель глубины тянет за собой всё — толщину линий, плотность
свечей, размер узлов, силу свечения. Это не украшение: глаз сразу
понимает, куда смотреть первым.

Приёмы, утверждённые владельцем по референсам:
  ЛИНИЯ-ТРУБКА — тень снизу отрывает её от фона, широкое гало даёт
    свет, узкий блик сверху читается круглым боком. Без тени линия
    лежит плоско, сколько ни добавляй свечения.
  СВЕЧИ из настоящих OHLC — тело от открытия к закрытию, тень от
    низа к верху; ярче линии, потому что событие важнее фона.
  ТРИ ГЛАВНЫЕ СВЕЧИ — дни с самым сильным перекосом покупок к
    продажам. Только на ближнем плане: на дальнем это был бы шум.
  ГЛУБИНА РЕЗКОСТИ — та же сцена, размытая, видна только по краям
    через маску. Резкость в середине, углы в расфокусе.
  ГРАФ под графиком — узлы на линии денег и ветви между ними.
  СПИРАЛЬ на фоне — водяной знак: логарифмический рост, то есть то
    же, чем занят экран.

Денежная линия считается перекосом к обороту дня с одной калибровкой
на весь ряд (правка 31.08), а не накопленными долларами.

Раскладка «плиткой» осталась под --layout a: она пригодится, если
понадобится сравнить, но по умолчанию собирается планами.

Данные: cq_v2/<монета>.json. Зовётся из patch_run_flow_all.py.
"""
import argparse
import json
import math
import random
from pathlib import Path

W, H = 1920, 1140
AP = argparse.ArgumentParser()
AP.add_argument('--coin', default='skr')
AP.add_argument('--layout', default='b', choices=('a', 'b'))
AP.add_argument('--out', default=None)
A = AP.parse_args()

for c in (Path('cq_v2') / f'{A.coin}.json', Path(f'{A.coin}.json')):
    if c.exists():
        D = json.loads(c.read_text(encoding='utf-8'))
        break
else:
    raise SystemExit(f'нет данных: cq_v2/{A.coin}.json')

for k in D:
    D[k] = list(reversed(D[k]))
closes = {r['datetime'][:10]: r['close'] for r in D['ohlcv']}
ohlc = {r['datetime'][:10]: (r.get('open'), r.get('high'), r.get('low'),
                             r.get('close')) for r in D['ohlcv']}
oimap = {r['datetime'][:10]: r.get('open_interest') or 0
         for r in D.get('oi', [])}
tr = [t for t in D['trade'] if closes.get(t['datetime'][:10])]
days = [t['datetime'][:10] for t in tr]
px = [closes[d] for d in days]
vols = [t['quote_volume'] for t in tr]
dl = [t['quote_buy_volume'] - t['quote_sell_volume'] for t in tr]
oi = [oimap.get(d) or 0 for d in days]
_last = 0.0
for i in range(len(oi)):
    if oi[i] > 0:
        _last = oi[i]
    else:
        oi[i] = _last
N = len(px)

steps = [(dl[i] / vols[i] if vols[i] else 0.0) for i in range(N)]
cum, c = [], 0.0
for x in steps:
    c += x
    cum.append(c)
K = (math.log(max(px) / min(px)) or .2) / ((max(cum) - min(cum)) or 1.0)
money = [px[0] * math.exp(K * v) for v in cum]
MX = max(abs(x) for x in steps) or 1.0
# ── СЮЖЕТ МОНЕТЫ (01.09) ───────────────────────────────────────────
# Прогноз строится в reputation_cq и до экрана потока не доходил
# вовсе: человек видел линии, но не видел, ЧТО система по ним
# прочла. Читаем готовую карту — своих расчётов здесь нет.
PLOT = PLOT_WHY = PLOT_GUARD = ""
for _rp in (Path("output/reputation.json"), Path("reputation.json")):
    if not _rp.exists():
        continue
    try:
        _e = (json.loads(_rp.read_text(encoding="utf-8"))
              .get(A.coin.upper() + "USDT") or {})
    except ValueError:
        _e = {}
    _pl = str(_e.get("plot") or "")
    if _pl:
        PLOT = _pl.split(":")[0].replace(" (шаблон", "|").split("|")[0]
        PLOT = PLOT.split("(")[0].strip()
        _rest = _pl.split(":", 1)[1] if ":" in _pl else ""
        _parts = [x.strip() for x in _rest.split(";") if x.strip()]
        PLOT_WHY = _parts[0] if _parts else ""
        PLOT_GUARD = _parts[-1] if len(_parts) > 1 else ""
    break

random.seed(11)

DEFS = '''
<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
 <stop offset="0" stop-color="#000306"/><stop offset=".5" stop-color="#030d16"/>
 <stop offset="1" stop-color="#000205"/></linearGradient>
<radialGradient id="glowA" cx="50%" cy="50%" r="50%">
 <stop offset="0" stop-color="#ffb44a" stop-opacity=".9"/>
 <stop offset="1" stop-color="#ff7a1a" stop-opacity="0"/></radialGradient>
<radialGradient id="glowC" cx="50%" cy="50%" r="50%">
 <stop offset="0" stop-color="#8fe8ff" stop-opacity=".9"/>
 <stop offset="1" stop-color="#2fd8ff" stop-opacity="0"/></radialGradient>
<radialGradient id="vig" cx="50%" cy="50%" r="74%">
 <stop offset=".62" stop-color="#000" stop-opacity="0"/>
 <stop offset="1" stop-color="#000" stop-opacity=".70"/></radialGradient>
<radialGradient id="dofg" cx="48%" cy="54%" r="64%">
 <stop offset="0" stop-color="#000"/><stop offset=".44" stop-color="#000"/>
 <stop offset=".80" stop-color="#999"/><stop offset="1" stop-color="#fff"/>
</radialGradient>
<mask id="dof"><rect width="1920" height="1140" fill="url(#dofg)"/></mask>
<filter id="b3" x="-70%" y="-70%" width="240%" height="240%">
 <feGaussianBlur stdDeviation="3"/></filter>
<filter id="b9" x="-70%" y="-70%" width="240%" height="240%">
 <feGaussianBlur stdDeviation="9"/></filter>
<filter id="b26" x="-90%" y="-90%" width="280%" height="280%">
 <feGaussianBlur stdDeviation="26"/></filter>
<filter id="b60" x="-90%" y="-90%" width="280%" height="280%">
 <feGaussianBlur stdDeviation="60"/></filter>'''

GR = []                      # градиенты линий: свои на каждое окно


def grads(tag, x0, x1):
    """Линия гаснет к обоим краям своего окна — иначе обрубки."""
    for nm, stops in (
            ('hot', (('#ff7a1a', 0), ('#ff9a2e', 1), ('#ffb44a', 1),
                     ('#ffd07a', 1), ('#ffd07a', 0))),
            ('cyn', (('#2fd8ff', 0), ('#2fd8ff', .9), ('#7fe8ff', .9),
                     ('#7fe8ff', .9), ('#7fe8ff', 0))),
            ('pale', (('#9fc0d8', 0), ('#9fc0d8', .55), ('#c8dcea', .55),
                      ('#c8dcea', .55), ('#c8dcea', 0)))):
        offs = (0, .12, .55, .88, 1)
        body = ''.join(
            f'<stop offset="{o}" stop-color="{col}" stop-opacity="{op}"/>'
            for o, (col, op) in zip(offs, stops))
        GR.append(f'<linearGradient id="{nm}{tag}" '
                  f'gradientUnits="userSpaceOnUse" x1="{x0}" y1="0" '
                  f'x2="{x1}" y2="0">{body}</linearGradient>')


def window(tag, i0, i1, frame, depth, cap):
    """Одно окно: те же приёмы, сила — по глубине плана.

    depth: 1.0 — ближний план (крупно, ярко, резко), 0.25 — дальний.
    Все размеры и плотности умножаются на него, поэтому дальний
    горизонт сам собой уходит в фон, а ближний выступает вперёд.
    """
    x0, y0, w, h = frame
    n = i1 - i0
    if n < 3:
        return '', ''
    grads(tag, x0, x0 + w)
    xs = [x0 + j * w / (n - 1) for j in range(n)]
    sp = px[i0:i1]
    # ЯКОРЬ ДЕНЕГ — НА НАЧАЛО ОКНА (правка 01.09, случай AIO). Раньше
    # окно брало кусок глобальной денежной линии, якоренной на начало
    # ВСЕГО ряда. В коротком окне деньги оказывались привязаны к цене
    # полугодовой давности, висели далеко от текущей, шкала
    # растягивалась на обе линии — и движение денег сжималось в черту.
    # У AIO деньги занимали 10% высоты кадра вместо 46, и цена теряла
    # с 95 до 86. В одиночной сцене окно было одно и якорь совпадал с
    # началом ряда, поэтому при переносе на три плана ошибка проехала.
    _c0 = cum[i0]
    sm = [sp[0] * math.exp(K * (cum[i0 + j] - _c0)) for j in range(n)]
    so = oi[i0:i1]
    lo = min(min(sp), min(sm)) * .96
    hi = max(max(sp), max(sm)) * 1.04
    olo, ohi = ((min(so) * .9, (max(so) * 1.06) or 1.0) if any(so)
                else (0.0, 1.0))

    def Y(v):
        return y0 + h - (v - lo) / ((hi - lo) or 1) * h

    def YO(v):
        # ПЛЕЧО ЖИВЁТ В ТОМ ЖЕ КАДРЕ (правка 01.09). Я увёл его на 26
        # пикселей НИЖЕ края окна и урезал полосу с 45% до 34% — и
        # пересечения плеча с ценой стали невозможны в принципе. А они
        # содержательные: плечо выше цены значит толпа зашла, ниже —
        # ход идёт без неё. Возвращаю прежнюю полосу: нижние 45% того
        # же кадра, без отступа.
        return y0 + h - (v - olo) / ((ohi - olo) or 1) * h * .45

    def poly(ys, dx=0.0, dy=0.0):
        return ' '.join(f'{xs[i]+dx:.1f},{ys[i]+dy:.1f}'
                        for i in range(n))

    def tube(ys, grad, hi_col, base):
        w_ = base * depth
        return (
            f'<polyline points="{poly(ys, 2.2*depth, 4.0*depth)}" fill="none" '
            f'stroke="#000306" stroke-width="{w_*2.6:.1f}" opacity=".75" '
            f'filter="url(#b3)"/>'
            f'<polyline points="{poly(ys)}" fill="none" stroke="url(#{grad})" '
            f'stroke-width="{w_*19:.0f}" opacity="{.13*depth:.2f}" '
            f'filter="url(#b60)"/>'
            f'<polyline points="{poly(ys)}" fill="none" stroke="url(#{grad})" '
            f'stroke-width="{w_*6.5:.1f}" opacity="{.34*depth:.2f}" '
            f'filter="url(#b26)"/>'
            f'<polyline points="{poly(ys)}" fill="none" stroke="url(#{grad})" '
            f'stroke-width="{w_*2.1:.1f}" opacity="{.78*depth:.2f}" '
            f'filter="url(#b9)"/>'
            f'<polyline points="{poly(ys)}" fill="none" stroke="url(#{grad})" '
            f'stroke-width="{max(.8, w_):.1f}" opacity="{.55+.45*depth:.2f}"/>'
            f'<polyline points="{poly(ys, 0, -w_*.42)}" fill="none" '
            f'stroke="{hi_col}" stroke-width="{max(.5, w_*.34):.1f}" '
            f'opacity="{.85*depth:.2f}"/>')

    yp = [Y(v) for v in sp]
    ym = [Y(v) for v in sm]
    yo = [YO(v) for v in so] if any(so) else []

    # свечи из настоящих OHLC
    BW = max(1.6, w / n * .62)
    cnd = []
    for j in range(n):
        o, hg, lw, cl = ohlc.get(days[i0 + j], (None, None, None, None))
        if not (o and hg and lw and cl):
            continue
        up = cl >= o
        col = '#ffb44a' if up else '#ff6a2a'
        ya, yb2 = Y(o), Y(cl)
        yt, yb = min(ya, yb2), max(ya, yb2)
        if yb - yt < 1.2:
            yt, yb = yt - .6, yb + .6
        op = (.5 + abs(steps[i0 + j]) / MX * .45) * (.35 + .65 * depth)
        cnd.append(
            f'<line x1="{xs[j]:.1f}" y1="{Y(hg):.1f}" x2="{xs[j]:.1f}" '
            f'y2="{Y(lw):.1f}" stroke="{col}" stroke-width=".8" '
            f'opacity="{op*.75:.2f}"/>'
            f'<rect x="{xs[j]-BW/2:.1f}" y="{yt:.1f}" width="{BW:.1f}" '
            f'height="{yb-yt:.1f}" fill="{col}" opacity="{op*.5:.2f}" '
            f'filter="url(#b9)"/>'
            f'<rect x="{xs[j]-BW/2:.1f}" y="{yt:.1f}" width="{BW:.1f}" '
            f'height="{yb-yt:.1f}" fill="{col}" opacity="{op:.2f}"/>')

    # три главные свечи — только на ближнем плане, иначе шум
    hero = []
    if depth >= .7:
        for j in sorted(range(n), key=lambda q: -abs(steps[i0 + q]))[:3]:
            o, hg, lw, cl = ohlc.get(days[i0 + j], (None,)*4)
            if not (o and hg and lw and cl):
                continue
            col = '#ffd07a' if cl >= o else '#ff8a3a'
            ya, yb2 = Y(o), Y(cl)
            yt, yb = min(ya, yb2), max(ya, yb2)
            if yb - yt < 3:
                yt, yb = yt - 1.5, yb + 1.5
            bw = BW * 2.2
            hero.append(
                f'<line x1="{xs[j]:.1f}" y1="{Y(hg):.1f}" x2="{xs[j]:.1f}" '
                f'y2="{Y(lw):.1f}" stroke="{col}" stroke-width="6" '
                f'opacity=".28" filter="url(#b9)"/>'
                f'<line x1="{xs[j]:.1f}" y1="{Y(hg):.1f}" x2="{xs[j]:.1f}" '
                f'y2="{Y(lw):.1f}" stroke="#fff6e4" stroke-width="1.4" '
                f'opacity=".95"/>'
                f'<rect x="{xs[j]-bw/2-3:.1f}" y="{yt-3:.1f}" '
                f'width="{bw+6:.1f}" height="{yb-yt+6:.1f}" '
                f'fill="url(#glowA)" opacity=".7" filter="url(#b9)"/>'
                f'<rect x="{xs[j]-bw/2:.1f}" y="{yt:.1f}" width="{bw:.1f}" '
                f'height="{yb-yt:.1f}" fill="{col}" opacity="1"/>'
                f'<rect x="{xs[j]-bw/2:.1f}" y="{yt:.1f}" width="{bw:.1f}" '
                f'height="{yb-yt:.1f}" fill="none" stroke="#fffaf0" '
                f'stroke-width="1.1" opacity=".9"/>')

    # узлы на деньгах и ветви графа
    mn, gp = [], []
    st = max(4, n // 14)
    prev = None
    for j in range(st, n - 2, st):
        mn.append(f'<circle cx="{xs[j]:.1f}" cy="{ym[j]:.1f}" '
                  f'r="{9*depth:.1f}" fill="url(#glowC)" opacity=".5" '
                  f'filter="url(#b9)"/>'
                  f'<circle cx="{xs[j]:.1f}" cy="{ym[j]:.1f}" '
                  f'r="{max(1.2, 2.2*depth):.1f}" fill="#e8fbff"/>')
        if prev:
            bx = (prev[0] + xs[j]) / 2
            by = max(prev[1], ym[j]) + random.uniform(26, 90) * depth
            gp.append(f'<path d="M{prev[0]:.0f},{prev[1]:.0f} '
                      f'L{bx:.0f},{by:.0f} L{xs[j]:.0f},{ym[j]:.0f}" '
                      f'fill="none" stroke="#5f9ec0" stroke-width=".7" '
                      f'opacity="{.16*depth:.2f}"/>')
        prev = (xs[j], ym[j])

    body = (''.join(gp)
            + (tube(yo, f'pale{tag}', '#dcecf8', 1.3) if yo else '')
            + tube(ym, f'cyn{tag}', '#dffaff', 2.0)
            + ''.join(cnd)
            + tube(yp, f'hot{tag}', '#fff6e4', 2.8)
            + ''.join(mn) + ''.join(hero))
    # ── ПОДПИСИ СОБЫТИЙ (возвращены 01.09) ─────────────────────────
    # При переписывании экрана я их потерял целиком, и человек видел
    # линии без единого объяснения, что на них смотреть. Два вида, оба
    # были в прежней версии и оба считаются из данных:
    #   цена растёт на ПРОДАЖАХ — ход держат лимитными заявками;
    #   плечо влилось за день — толпу завели.
    # На дальнем плане подписей нет: там они были бы шумом.
    ev = []
    if depth >= .6:
        for j in range(2, n):
            i = i0 + j
            dpx = sp[j] / sp[j-1] - 1 if sp[j-1] else 0
            if dl[i] < 0 and dpx > .04 and abs(dl[i]) > 3e5:
                ev.append((j, f'цена +{dpx*100:.0f}% при продажах '
                              f'${abs(dl[i])/1e6:.1f}M — держат заявками'))
            elif (so[j] and so[j-1] and so[j] / so[j-1] > 1.28):
                ev.append((j, f'плечо влилось +'
                              f'{(so[j]/so[j-1]-1)*100:.0f}% за день'))
    picked, last = [], -99
    for j, txt in ev:
        if j - last >= max(4, n // 5):
            picked.append((j, txt)); last = j
    pins = []
    for k_, (j, txt) in enumerate(picked[:3 if depth >= .9 else 2]):
        px_, py_ = xs[j], yp[j]
        ly = py_ - (52 + k_ * 26) * max(.7, depth)
        xt = min(max(px_, x0 + 120), x0 + w - 120)
        pins.append(
            f'<line x1="{px_:.0f}" y1="{py_:.0f}" x2="{px_:.0f}" '
            f'y2="{ly:.0f}" stroke="#d8f0f8" stroke-width=".8" '
            f'opacity=".26"/>'
            f'<circle cx="{px_:.0f}" cy="{py_:.0f}" r="{16*depth:.0f}" '
            f'fill="url(#glowA)" opacity=".55" filter="url(#b9)"/>'
            f'<circle cx="{px_:.0f}" cy="{py_:.0f}" r="2.6" fill="#fff6e4"/>'
            f'<text x="{xt:.0f}" y="{ly-8:.0f}" text-anchor="middle" '
            f'font-family="Arial" font-weight="700" '
            f'font-size="{10 + 3*depth:.0f}" fill="#cfe0ec" '
            f'opacity="{.45 + .35*depth:.2f}" '
            f'letter-spacing=".04em">{txt}</text>')

    lab = (f'<text x="{x0}" y="{y0 - 16}" font-family="Arial" '
           f'font-weight="800" font-size="{13 + 5*depth:.0f}" '
           f'fill="#9fb8cc" opacity="{.30 + .28*depth:.2f}" '
           f'letter-spacing=".26em">{cap}</text>')
    return body + ''.join(pins), lab


# ── РАСКЛАДКИ ──────────────────────────────────────────────────────
if A.layout == 'a':
    WINS = [('w2', max(0, N-15), N, (150, 180, 1080, 400), 1.00, 'две недели'),
            ('qr', max(0, N-90), N, (150, 700, 780, 300), .70, 'квартал'),
            ('hf', 0, N, (1030, 700, 780, 300), .55, 'полгода')]
else:
    WINS = [('hf', 0, N, (70, 210, 1180, 230), .38, 'полгода'),
            ('qr', max(0, N-90), N, (300, 430, 1330, 270), .68, 'квартал'),
            ('w2', max(0, N-15), N, (560, 700, 1290, 280), 1.00, 'две недели')]

scene, over = '', ''
for w in WINS:
    b_, l_ = window(*w)
    scene += b_
    over += l_


def backdrop(cx, cy, R):
    out = []
    for k, rr in enumerate((R*.42, R*.68, R*1.0)):
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{rr:.0f}" fill="none" '
                   f'stroke="#1b4462" stroke-width="1" '
                   f'opacity="{.16-k*.035:.2f}"/>')
    for i in range(24):
        a_ = i * math.pi / 12
        f_ = 1.02 if i % 3 == 0 else .74
        out.append(f'<line x1="{cx+math.cos(a_)*R*.30:.0f}" '
                   f'y1="{cy+math.sin(a_)*R*.30:.0f}" '
                   f'x2="{cx+math.cos(a_)*R*f_:.0f}" '
                   f'y2="{cy+math.sin(a_)*R*f_:.0f}" stroke="#1b4462" '
                   f'stroke-width=".8" '
                   f'opacity="{.13 if i%3==0 else .07:.2f}"/>')
    for turn, (op, wd, col) in enumerate(((.20, 1.3, '#24587c'),
                                          (.10, .8, '#1b4462'))):
        pts, th = [], 0.0
        while th < math.pi * 6.2:
            r = R * .085 * math.exp(.148 * th)
            if r > R * 1.16:
                break
            ang = th + turn * .55
            pts.append(f'{cx+math.cos(ang)*r:.0f},{cy+math.sin(ang)*r:.0f}')
            th += .085
        out.append(f'<polyline points="{" ".join(pts)}" fill="none" '
                   f'stroke="{col}" stroke-width="{wd}" opacity="{op}"/>')
    return ''.join(out)


noise = []
for _ in range(80):
    x, y = random.uniform(60, W-60), random.uniform(120, H-80)
    noise.append(f'<rect x="{x:.0f}" y="{y:.0f}" '
                 f'width="{random.uniform(14,54):.0f}" height="2" '
                 f'fill="{"#ffb44a" if random.random()<.5 else "#4aa8d8"}" '
                 f'opacity="{random.uniform(.05,.18):.2f}"/>')
for cx, cy, cols, rows, st_, col, op in ((520, 300, 14, 8, 12, '#ffb44a', .20),
                                         (1180, 640, 12, 9, 11, '#4aa8d8', .16)):
    for r in range(rows):
        for c2 in range(cols):
            if random.random() < (c2/cols)*.6:
                continue
            noise.append(f'<circle cx="{cx+c2*st_}" cy="{cy+r*st_}" r="1.5" '
                         f'fill="{col}" opacity="{op:.2f}"/>')

bok = []
for _ in range(30):
    x, y, r = random.uniform(0, W), random.uniform(80, H), random.uniform(8, 52)
    warm = random.random() < .72
    col = '#ff9a2e' if warm else '#4ad8ff'
    op = random.uniform(.10, .32)
    bok.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.0f}" fill="{col}" '
               f'opacity="{op*.45:.2f}" filter="url(#b9)"/>'
               f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.0f}" fill="none" '
               f'stroke="{col}" stroke-width="1.4" opacity="{op:.2f}"/>')

spark = ''.join(
    f'<circle cx="{random.uniform(0,W):.0f}" cy="{random.uniform(60,H):.0f}" '
    f'r="{random.uniform(.7,2.0):.1f}" '
    f'fill="{"#ffc76a" if random.random()<.74 else "#7fe8ff"}" '
    f'opacity="{random.uniform(.20,.75):.2f}"/>' for _ in range(280))

i0v = max(0, N - 15)
mv = px[i0v] * math.exp(K * (cum[-1] - cum[i0v]))
gap = px[-1] / mv - 1
verdict = ('ЖДАТЬ' if gap > .10 else
           'СМОТРЕТЬ ВХОД' if gap < -.10 else 'ДЕРЖАТЬ')
why = (f'за две недели цена выше своих денег на {gap*100:.0f}% — '
       f'ход держат заявками, не покупками' if gap > .10 else
       f'деньги выше цены на {abs(gap)*100:.0f}%' if gap < -.10
       else 'цена и деньги идут вровень')
TILT = ('rotate(-5.5 960 560) scale(1.03) translate(-30,-18)'
        if A.layout == 'a' else
        'rotate(-7.5 960 560) scale(1.05) translate(-44,-26)')

svg = f'''<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">
<defs>{DEFS}{''.join(GR)}</defs>
<rect width="{W}" height="{H}" fill="url(#bg)"/>
<ellipse cx="1500" cy="240" rx="520" ry="300" fill="url(#glowC)"
  opacity=".13" filter="url(#b60)"/>
<ellipse cx="300" cy="900" rx="520" ry="280" fill="url(#glowA)"
  opacity=".16" filter="url(#b60)"/>
{backdrop(1560, 290, 600)}
{''.join(noise)}
{spark}
<g id="scene" transform="{TILT}">{scene}{over}</g>
<use href="#scene" filter="url(#b9)" mask="url(#dof)" opacity=".95"/>
<use href="#scene" filter="url(#b26)" mask="url(#dof)" opacity=".45"/>
{''.join(bok)}
<text x="118" y="962" font-family="Arial" font-weight="800" font-size="58"
  fill="#fff6e4" letter-spacing=".02em">{A.coin.upper()}</text>
<text x="118" y="1012" font-family="Arial" font-weight="800" font-size="26"
  fill="#ffb44a" letter-spacing=".10em">{verdict}</text>
<!-- КАК СТРОИТСЯ ПРОГНОЗ: имя сюжета крупно, под ним основание и
     сторож. Раньше это жило только в зале, и на потоке человек видел
     линии, не зная, что система по ним прочла. -->
{'' if not PLOT else f'''
<text x="118" y="1056" font-family="Arial" font-weight="800" font-size="21"
  fill="#7fe8ff" letter-spacing=".03em">{PLOT}</text>
<text x="118" y="1082" font-family="Georgia,serif" font-style="italic"
  font-size="15" fill="#a8c4d4" opacity=".85">{PLOT_WHY[:96]}</text>'''}
<text x="118" y="{1050 if not PLOT else 1108}" font-family="Georgia,serif"
  font-style="italic" font-size="15" fill="#8fa8bc" opacity=".7">{why}</text>
<text x="1800" y="1044" font-family="Arial" font-weight="700" font-size="11"
  fill="#7f9bb0" letter-spacing=".10em" text-anchor="end">
  <tspan fill="#ffb44a">— цена</tspan><tspan dx="14" fill="#7fe8ff">— деньги</tspan><tspan dx="14" fill="#c8dcea">— плечо</tspan></text>
<text x="1800" y="1064" font-family="Arial" font-weight="700" font-size="10"
  fill="#5f7a90" letter-spacing=".10em" text-anchor="end">свечи — дни; ближний план ярче, дальний тусклее</text>
<rect width="{W}" height="{H}" fill="url(#vig)"/>
</svg>'''

html = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{A.coin.upper()} · поток · раскладка {A.layout.upper()}</title><style>
*{{box-sizing:border-box;margin:0}}html,body{{height:100%}}
body{{background:#000306;overflow:hidden}}
svg{{display:block;width:100vw;height:100vh}}
.back{{position:fixed;left:18px;top:16px;z-index:9;font:700 11px Arial;
letter-spacing:.14em;color:#ffb44a;text-decoration:none;
border:1px solid rgba(255,180,74,.35);border-radius:8px;padding:5px 11px;
opacity:.55}}.back:hover{{opacity:1}}
</style></head><body><a class="back" href="podium.html">\u2190 зал</a>
{svg}</body></html>'''

out = Path(A.out) if A.out else Path(f'flow_{A.coin}.html')
out.write_text(html, encoding='utf-8')
print(f'{A.coin}: поток собран, {len(html)} байт · дней {N} · '
      f'зазор {gap*100:+.0f}% · вердикт {verdict}')
