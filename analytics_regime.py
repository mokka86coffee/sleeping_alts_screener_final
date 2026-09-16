#!/usr/bin/env python3
"""МЕРЫ РЕЖИМА ПО ПОЛУЧАСОВКАМ (16.09; владелец: «у тебя есть знания физики, математики — можно ли формулами
считать ход цены, определяя случайности и алгоритмы?»; «внедряй всё сразу в журнал, пока как наблюдения, на
ботов не распространяется»).

Ни одна мера не предсказывает цену. Каждая отвечает на вопрос «это сейчас случайность или чей-то алгоритм и в
каком он режиме». В торговлю не идёт ничего: меры пишутся в журнал наблюдений (junction_log) рядом с исходом,
через неделю проверяются на лидерах с фоном против контроля; не подтвердилась — не идёт никуда.

  • hurst — показатель Хёрста (R/S, из гидрологии): около 0.5 — случайное блуждание; ниже — ход отменяется
    (пила, возврат к среднему, фаза сбора); выше — ход продолжается (память тренда);
  • flow — цена потока (ламбда Кайла, микроструктура рынка): наклон хода бара к дельте тейкеров, % на 1 млн $;
    absorb — доля последних баров, где дельта большая, а цена почти стоит (поглощение, лимитный держит);
    paint — доля баров, где цена прошла много на маленькой дельте (палка на пустом стакане);
  • curve — загиб роста (модели пузырей Сорнетте): квадратичный член логарифма цены на окне; плюс — рост
    быстрее экспоненты (парабола), около нуля — прямая (лестница);
  • pe — энтропия перестановок (Бандт–Помпе): 1 — хаос, ниже — упорядоченный ход, кто-то исполняет план;
  • branch — самовозбуждение выносов (по мотивам процессов Хоукса, модель афтершоков): во сколько раз после
    выноса чаще идёт следующий вынос, чем при случайности; больше 1 — выносы тянут друг друга;
  • lead — кто ведёт: корреляция изменения интереса с ходом СЛЕДУЮЩЕГО бара против обратной; «интерес» —
    плечо ведёт цену, «цена» — плечо догоняет.
Окна в барах — REGIME_* в core_config. Ничего не пишет; вызывается из junction_log.
"""
from __future__ import annotations

import math
import statistics as st

try:
    from core_config import REGIME_HURST_BARS, REGIME_FLOW_BARS, REGIME_CURVE_BARS, REGIME_PE_BARS, REGIME_BRANCH_BARS
except ImportError:
    REGIME_HURST_BARS, REGIME_FLOW_BARS, REGIME_CURVE_BARS, REGIME_PE_BARS, REGIME_BRANCH_BARS = 96, 48, 24, 48, 96


def _rets(closes: list[float]) -> list[float]:
    return [math.log(b / a) for a, b in zip(closes, closes[1:]) if a and b and a > 0 and b > 0]


def _rs_slope(r: list[float]) -> float | None:
    pts = []
    for n in (8, 16, 32, 64):
        if n * 2 > len(r):
            break
        rs = []
        for k in range(0, len(r) - n + 1, n):
            seg = r[k:k + n]
            m = sum(seg) / n
            dev, acc, lo, hi = [x - m for x in seg], 0.0, 0.0, 0.0
            for x in dev:
                acc += x
                lo, hi = min(lo, acc), max(hi, acc)
            sd = (sum(x * x for x in dev) / n) ** .5
            if sd > 0:
                rs.append((hi - lo) / sd)
        if rs:
            pts.append((math.log(n), math.log(sum(rs) / len(rs))))
    if len(pts) < 2:
        return None
    mx, my = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    den = sum((p[0] - mx) ** 2 for p in pts)
    return sum((p[0] - mx) * (p[1] - my) for p in pts) / den if den else None


def hurst(closes: list[float], bars: int = REGIME_HURST_BARS) -> dict:
    """R/S: наклон log(R/S) к log(n) по окнам 8, 16, 32 (и 64). На коротком окне R/S завышен и у случайного ряда
    (около 0.57 на 96 барах), поэтому рядом — тот же расчёт на перемешанных ходах той же монеты (память убита,
    разброс тот же): rel = h − h_перемешанного; около нуля — случайность, выше — ход продолжается, ниже — отменяется"""
    import random as _r
    r = _rets(closes[-(bars + 1):])
    if len(r) < 48:
        return {}
    h = _rs_slope(r)
    if h is None:
        return {}
    rng = _r.Random(len(r))                    # детерминированно: один и тот же ряд — одно и то же число
    base = []
    for _ in range(8):
        sh = list(r)
        rng.shuffle(sh)
        v = _rs_slope(sh)
        if v is not None:
            base.append(v)
    b = st.median(base) if base else None
    return {"h": round(h, 3), "rel": None if b is None else round(h - b, 3)}


def flow(closes: list[float], deltas: list[float], bars: int = REGIME_FLOW_BARS) -> dict:
    """цена потока: % хода бара на 1 млн $ дельты тейкеров; поглощение и палки за последние 8 баров"""
    r = [(b / a - 1) * 100 for a, b in zip(closes, closes[1:]) if a]
    d = deltas[1:len(r) + 1]
    pairs = [(x / 1e6, y) for x, y in zip(d[-bars:], r[-bars:]) if x is not None]
    if len(pairs) < 16:
        return {}
    xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
    mx, my = st.mean(xs), st.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    lam = sum((x - mx) * (y - my) for x, y in pairs) / sxx if sxx else None
    ax = sorted(abs(x) for x in xs)
    ay = sorted(abs(y) for y in ys)
    q = lambda arr, p: arr[min(len(arr) - 1, int(p * len(arr)))]
    big_d, small_d, big_r, small_r = q(ax, .75), q(ax, .25), q(ay, .75), q(ay, .25)
    last = pairs[-8:]
    absorb = sum(1 for x, y in last if abs(x) >= big_d and abs(y) <= small_r) / len(last)
    paint = sum(1 for x, y in last if abs(y) >= big_r and abs(x) <= small_d) / len(last)
    return {"lam": None if lam is None else round(lam, 4), "absorb": round(absorb, 2), "paint": round(paint, 2)}


def curve(closes: list[float], bars: int = REGIME_CURVE_BARS) -> dict:
    """логарифм цены ≈ a + b·x + c·x², x от 0 до 1 на окне; c — загиб, b — наклон"""
    c = [x for x in closes[-bars:] if x and x > 0]
    if len(c) < 12:
        return {}
    n = len(c)
    xs = [i / (n - 1) for i in range(n)]
    ys = [math.log(v) for v in c]
    s = [sum(x ** k for x in xs) for k in range(5)]
    t = [sum((x ** k) * y for x, y in zip(xs, ys)) for k in range(3)]
    m = [[s[0], s[1], s[2]], [s[1], s[2], s[3]], [s[2], s[3], s[4]]]
    det = lambda a: (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
                     + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    d0 = det(m)
    if abs(d0) < 1e-12:
        return {}
    col = lambda k: [[t[i] if j == k else m[i][j] for j in range(3)] for i in range(3)]
    a, b, cc = det(col(0)) / d0, det(col(1)) / d0, det(col(2)) / d0
    fit = [a + b * x + cc * x * x for x in xs]
    ss_res = sum((y - f) ** 2 for y, f in zip(ys, fit))
    my = sum(ys) / n
    ss_tot = sum((y - my) ** 2 for y in ys)
    return {"c": round(cc * 100, 3), "b": round(b * 100, 3), "r2": round(1 - ss_res / ss_tot, 3) if ss_tot else None}


def perm_entropy(closes: list[float], bars: int = REGIME_PE_BARS, order: int = 3) -> float | None:
    """нормированная энтропия порядков соседних закрытий: 1 — хаос, 0 — строгий порядок"""
    c = closes[-bars:]
    if len(c) < order + 10:
        return None
    cnt = {}
    for i in range(len(c) - order + 1):
        w = c[i:i + order]
        key = tuple(sorted(range(order), key=lambda k: (w[k], k)))
        cnt[key] = cnt.get(key, 0) + 1
    tot = sum(cnt.values())
    h = -sum(v / tot * math.log(v / tot) for v in cnt.values())
    return round(max(0.0, h / math.log(math.factorial(order))), 3)


def branch(closes: list[float], bars: int = REGIME_BRANCH_BARS, z: float = 2.0, k: int = 3) -> dict:
    """выносы — бары с |ходом| > z сигм окна; во сколько раз после выноса чаще идёт следующий в k барах"""
    r = _rets(closes[-(bars + 1):])
    if len(r) < 48:
        return {}
    med_r = st.median(r)
    sd = 1.4826 * st.median([abs(x - med_r) for x in r])
    if not sd:
        return {}
    sh = [abs(x - med_r) > z * sd for x in r]
    n_sh = sum(sh)
    if n_sh < 3:
        return {"shocks": n_sh}
    p = n_sh / len(sh)
    base = 1 - (1 - p) ** k
    fol = [any(sh[i + 1:i + 1 + k]) for i, s in enumerate(sh[:-k]) if s]
    if not fol or not base:
        return {"shocks": n_sh}
    return {"shocks": n_sh, "ratio": round((sum(fol) / len(fol)) / base, 2)}


def lead(closes: list[float], ois: list[float | None], bars: int = REGIME_FLOW_BARS) -> dict:
    """corr(Δинтерес_t, ход_{t+1}) против corr(ход_t, Δинтерес_{t+1})"""
    r, o = [], []
    for i in range(1, min(len(closes), len(ois))):
        a, b, oa, ob = closes[i - 1], closes[i], ois[i - 1], ois[i]
        if a and b and oa and ob:
            r.append(b / a - 1)
            o.append(ob / oa - 1)
        else:
            r.append(None)
            o.append(None)
    r, o = r[-bars:], o[-bars:]

    def corr(xs, ys):
        pr = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
        if len(pr) < 16:
            return None
        mx, my = st.mean(p[0] for p in pr), st.mean(p[1] for p in pr)
        sx = sum((p[0] - mx) ** 2 for p in pr) ** .5
        sy = sum((p[1] - my) ** 2 for p in pr) ** .5
        return sum((p[0] - mx) * (p[1] - my) for p in pr) / (sx * sy) if sx and sy else None

    oi_to_px = corr(o[:-1], r[1:])
    px_to_oi = corr(r[:-1], o[1:])
    if oi_to_px is None or px_to_oi is None:
        return {}
    who = "интерес" if abs(oi_to_px) > abs(px_to_oi) + 0.1 else "цена" if abs(px_to_oi) > abs(oi_to_px) + 0.1 else "вровень"
    return {"oi_px": round(oi_to_px, 2), "px_oi": round(px_to_oi, 2), "who": who}


def measures(closes: list[float], deltas: list[float] | None = None, ois: list[float | None] | None = None) -> dict:
    """все меры на последнем баре; ряды выровнены по барам, старые слева"""
    out = {"hurst": hurst(closes), "curve": curve(closes), "pe": perm_entropy(closes), "branch": branch(closes)}
    if deltas:
        out["flow"] = flow(closes, deltas)
    if ois:
        out["lead"] = lead(closes, ois)
    return out
