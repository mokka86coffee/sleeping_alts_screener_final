"""Быстрый вихрь на получасовках (11.09).

Что было не так со старым «вортекс 4ч вверх» (владелец, 11.09): одно слово на
любой разрыв. Нет величины разрыва, нет его направления, нет ПЕРЕГРЕВА — где
значение стоит относительно своих исторических крайних, — нет дивергенции.
Здесь считаются все четыре, по истории САМОЙ монеты, а не по общему порогу.

Чистая математика без сети: на вход свечи Binance (списки списков), на выход
словарь. Сеть — только в read_symbol через core_binance.klines_30m.

Формула — как у TradingView «Vortex Indicator» (VI, период 14): суммы размахов
вверх |high − low[1]| и вниз |low − high[1]| к сумме истинного диапазона.
Числа должны совпадать с графиком владельца бар в бар.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
from datetime import datetime, timezone

from core_config import (
    OUTPUT_DIR,
    VORTEX_DIV_EPS,
    VORTEX_DIV_MIN_GAP,
    VORTEX_DIV_WINDOW,
    VORTEX_EXTREME_PCT,
    VORTEX_HORIZONS,
    VORTEX_HTML,
    VORTEX_N,
    VORTEX_SLOPE_BARS,
    VORTEX_TURN_MIN_BARS,
)


# ─────────────────────────────────────────────────────────────
# Линии
# ─────────────────────────────────────────────────────────────
def vortex_lines(highs: list[float], lows: list[float], closes: list[float],
                 n: int = VORTEX_N) -> tuple[list, list]:
    """VI+ и VI− по барам. Первые n баров — None: сумме не из чего набраться."""
    m = len(closes)
    if m < n + 1:
        return [None] * m, [None] * m
    vm_p = [0.0] * m
    vm_m = [0.0] * m
    tr = [0.0] * m
    for i in range(1, m):
        vm_p[i] = abs(highs[i] - lows[i - 1])
        vm_m[i] = abs(lows[i] - highs[i - 1])
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    vi_p: list = [None] * m
    vi_m: list = [None] * m
    s_p = sum(vm_p[1:n + 1])
    s_m = sum(vm_m[1:n + 1])
    s_t = sum(tr[1:n + 1])
    for i in range(n, m):
        if i > n:
            s_p += vm_p[i] - vm_p[i - n]
            s_m += vm_m[i] - vm_m[i - n]
            s_t += tr[i] - tr[i - n]
        if s_t > 0:
            vi_p[i] = s_p / s_t
            vi_m[i] = s_m / s_t
    return vi_p, vi_m


def gap_direction(gap: list, bars: int = VORTEX_SLOPE_BARS) -> tuple[str, float | None]:
    """Разрыв растёт, сужается или стоит — по сравнению с тем, что был bars назад.
    Сужение считается ПО МОДУЛЮ: разрыв +0.40 → +0.20 сужается так же, как −0.40 → −0.20."""
    vals = [g for g in gap if g is not None]
    if len(vals) < bars + 1:
        return "нет данных", None
    cur, prev = vals[-1], vals[-1 - bars]
    d = abs(cur) - abs(prev)
    if abs(d) < VORTEX_DIV_EPS:
        return "стоит", round(d, 3)
    return ("растёт" if d > 0 else "сужается"), round(d, 3)


# ─────────────────────────────────────────────────────────────
# Перегрев: где значение относительно своей истории
# ─────────────────────────────────────────────────────────────
def percentile_rank(history: list[float], value: float) -> float | None:
    """Доля истории НИЖЕ значения, в процентах. 95 — выше было в пяти процентах баров."""
    vals = [v for v in history if v is not None]
    if not vals:
        return None
    below = sum(1 for v in vals if v < value)
    return round(100.0 * below / len(vals), 1)


def _quantile(vals: list[float], q: float) -> float:
    s = sorted(vals)
    if not s:
        return 0.0
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def after_extremes(values: list, closes: list[float], pct: int = VORTEX_EXTREME_PCT,
                   horizons: tuple = VORTEX_HORIZONS) -> dict:
    """Что делала цена после крайних значений ряда — по эпизодам, не по барам.

    Эпизод — первый бар, вошедший в зону (сосед слева ещё вне зоны); иначе десять
    баров подряд в перегреве считались бы десятью случаями одного и того же.
    Для каждого горизонта: сколько эпизодов, доля с ходом вверх, медиана хода.
    """
    vals = [v for v in values if v is not None]
    if len(vals) < 50:
        return {}
    hi_thr = _quantile(vals, 1 - pct / 100.0)
    lo_thr = _quantile(vals, pct / 100.0)
    out = {"hi_thr": round(hi_thr, 3), "lo_thr": round(lo_thr, 3), "hi": {}, "lo": {}}
    for tag, cond in (("hi", lambda v: v >= hi_thr), ("lo", lambda v: v <= lo_thr)):
        idx = []
        prev_in = False
        for i, v in enumerate(values):
            now_in = v is not None and cond(v)
            if now_in and not prev_in:
                idx.append(i)
            prev_in = now_in
        for h in horizons:
            moves = [(closes[i + h] / closes[i] - 1) * 100 for i in idx if i + h < len(closes) and closes[i]]
            if not moves:
                continue
            out[tag][h] = {"n": len(moves), "up_share": round(100 * sum(m > 0 for m in moves) / len(moves)),
                           "median": round(st.median(moves), 2)}
        out[tag]["episodes"] = len(idx)
    return out


# ─────────────────────────────────────────────────────────────
# Дивергенция (владелец, 11.09)
# ─────────────────────────────────────────────────────────────
def _swing_lows(vals: list, start: int, wing: int = 3) -> list[int]:
    """Локальные минимумы ряда: ниже всех соседей в wing барах с каждой стороны."""
    out = []
    for i in range(max(start, wing), len(vals) - wing):
        v = vals[i]
        if v is None:
            continue
        neigh = [vals[j] for j in range(i - wing, i + wing + 1) if j != i and vals[j] is not None]
        if neigh and all(v <= x for x in neigh) and any(v < x for x in neigh):
            out.append(i)
    return out


def _line_near(line: list, i: int, wing: int = 2, lowest: bool = True) -> float | None:
    seg = [v for v in line[max(0, i - wing): i + wing + 1] if v is not None]
    if not seg:
        return None
    return min(seg) if lowest else max(seg)


def divergence(vi_line: list, price_ext: list[float], window: int = VORTEX_DIV_WINDOW,
               min_gap: int = VORTEX_DIV_MIN_GAP, eps: float = VORTEX_DIV_EPS,
               price_falls: bool = True) -> dict | None:
    """Дивергенция по определению владельца (11.09, график IOST): «следующий лой покупок по
    вортексу выше предыдущего при сползающей цене».

    ЯКОРЬ — ЦЕНА, НЕ ЛИНИЯ (правка 11.09 после первого прогона на живых данных): первая
    версия брала два последних лоя ЛИНИИ, и на IOST взяла две мелкие впадины, между которыми
    цена подскочила, — дивергенции «не нашла», хотя на той же картинке она видна глазами.
    Теперь: находим последний свинг-лой цены (b) и предыдущий свинг-лой выше него (a) — цена
    сделала более низкий лой; берём лой линии рядом с каждым (±2 бара) и проверяем, что
    второй лой линии ВЫШЕ первого на eps. Для зеркала продавцов — свинг-максимумы цены и
    более высокий максимум при более низком максимуме линии.
    """
    n = len(vi_line)
    start = max(0, n - window)
    sign = 1.0 if price_falls else -1.0
    ext = [sign * v for v in price_ext]                # для зеркала ищем максимумы как минимумы
    lows = _swing_lows(ext, start)
    if len(lows) < 2:
        return None
    b = lows[-1]
    a = None
    for i in reversed(lows[:-1]):
        if b - i < min_gap:
            continue
        if ext[i] > ext[b]:                            # предыдущий лой цены ВЫШЕ — цена сползла
            a = i
            break
    if a is None:
        return None
    la = _line_near(vi_line, a, lowest=price_falls)
    lb = _line_near(vi_line, b, lowest=price_falls)
    if la is None or lb is None:
        return None
    diff = (lb - la) if price_falls else (la - lb)     # покупатели: лой выше; продавцы: пик ниже
    if diff < eps:
        return None
    return {"bar_a": a, "bar_b": b, "line_a": round(la, 3), "line_b": round(lb, 3),
            "price_a": price_ext[a], "price_b": price_ext[b], "bars_ago": n - 1 - b}


# ─────────────────────────────────────────────────────────────
# Серии по каждой линии (владелец, 11.09: «каждая следующая получасовая свеча
# поднимает лой продаж» — направление читается по линии, не по разрыву)
# ─────────────────────────────────────────────────────────────
def line_streak(line: list) -> dict:
    """Сколько закрытых баров подряд линия идёт в одну сторону, считая от последнего.
    Разрыв между линиями слеп к тому, КТО двигается; серия по каждой линии — нет."""
    vals = [v for v in line if v is not None]
    if len(vals) < 2:
        return {"dir": "стоит", "n": 0}
    d0 = vals[-1] - vals[-2]
    if d0 == 0:
        return {"dir": "стоит", "n": 0}
    n = 1
    for i in range(len(vals) - 2, 0, -1):
        d = vals[i] - vals[i - 1]
        if (d > 0) == (d0 > 0) and d != 0:
            n += 1
        else:
            break
    return {"dir": "поднимает" if d0 > 0 else "опускает", "n": n}


def divergence_run(line: list, closes: list[float], line_up: bool = True, price_up: bool = False) -> int:
    """Дивергенция бар за баром: сколько закрытых баров подряд линия идёт в одну сторону,
    а цена — в другую. Покупатели: линия вверх при цене вниз (line_up, не price_up).
    Продавцы: линия вверх при цене вверх — продавцы набирают, пока цена ещё растёт.
    Это счётчик, на котором копится статистика дивергенций; свинговый поиск выше — её
    «крупная» форма, как её рисуют на графике."""
    vals = [(v, c) for v, c in zip(line, closes) if v is not None]
    n = 0
    for i in range(len(vals) - 1, 0, -1):
        dl = vals[i][0] - vals[i - 1][0]
        dp = vals[i][1] - vals[i - 1][1]
        if dl == 0 or dp == 0:
            break
        if ((dl > 0) == line_up) and ((dp > 0) == price_up):
            n += 1
        else:
            break
    return n


def turn_state(vi_p: list, vi_m: list, min_bars: int = VORTEX_TURN_MIN_BARS) -> dict | None:
    """«Сторона сменилась»: одна линия поднимается, другая опускается, обе не короче min_bars.
    side — кто взял: «продавцы» (их линия вверх, покупатели вниз) или «покупатели».
    ago — сколько баров назад обе пошли вместе (короткая из двух серий)."""
    sp, sm = line_streak(vi_p), line_streak(vi_m)
    if sm["dir"] == "поднимает" and sp["dir"] == "опускает" and min(sm["n"], sp["n"]) >= min_bars:
        return {"side": "продавцы", "ago": min(sm["n"], sp["n"])}
    if sp["dir"] == "поднимает" and sm["dir"] == "опускает" and min(sm["n"], sp["n"]) >= min_bars:
        return {"side": "покупатели", "ago": min(sm["n"], sp["n"])}
    return None


def turn_events(vi_p: list, vi_m: list, closes: list[float], min_bars: int = VORTEX_TURN_MIN_BARS,
                horizons: tuple = VORTEX_HORIZONS) -> list[dict]:
    """Все бары истории, где событие «сторона сменилась» ВПЕРВЫЕ стало истинным, и ход цены после.
    Это проверка на дубль с силой: в какой бар сказал вихрь. Событие считается по линиям,
    известным на тот бар, — без заглядывания вперёд."""
    out = []
    prev = None
    for i in range(min_bars + 1, len(closes)):
        st = turn_state(vi_p[:i + 1], vi_m[:i + 1], min_bars)
        cur = st["side"] if st else None
        if cur and cur != prev and st["ago"] == min_bars:      # первый бар, где серии дотянулись
            ev = {"bar": i, "side": cur, "close": closes[i]}
            for h in horizons:
                ev[f"h{h}"] = round((closes[i + h] / closes[i] - 1) * 100, 2) if i + h < len(closes) else None
            out.append(ev)
        prev = cur
    return out


# ─────────────────────────────────────────────────────────────
# Полное чтение по свечам
# ─────────────────────────────────────────────────────────────
def read_klines(klines: list[list], n: int = VORTEX_N) -> dict:
    """Всё чтение вихря по списку свечей Binance. Пусто — если свечей мало."""
    from core_binance import K_CLOSE, K_HIGH, K_LOW, K_OPEN_TIME, series
    highs = series(klines, K_HIGH)
    lows = series(klines, K_LOW)
    closes = series(klines, K_CLOSE)
    times = [int(k[K_OPEN_TIME]) for k in klines]
    if len(closes) < n + 2:
        return {}
    vi_p, vi_m = vortex_lines(highs, lows, closes, n)
    gap = [None if (p is None or q is None) else p - q for p, q in zip(vi_p, vi_m)]
    cur_p, cur_m, cur_g = vi_p[-1], vi_m[-1], gap[-1]
    if cur_p is None:
        return {}
    direction, slope = gap_direction(gap)
    out = {
        "n": n, "bars": len(closes), "at": times[-1],
        "vi_plus": round(cur_p, 4), "vi_minus": round(cur_m, 4), "gap": round(cur_g, 4),
        "side": "покупатели" if cur_g > 0 else ("продавцы" if cur_g < 0 else "поровну"),
        "gap_dir": direction, "gap_slope": slope,
        # серии по линиям и дивергенция бар за баром
        "streak_plus": line_streak(vi_p), "streak_minus": line_streak(vi_m),
        "div_run_buy": divergence_run(vi_p, closes, line_up=True, price_up=False),
        "div_run_sell": divergence_run(vi_m, closes, line_up=True, price_up=True),
        "turn": turn_state(vi_p, vi_m),
        # перегрев — доля истории ниже текущего значения
        "pct_plus": percentile_rank(vi_p, cur_p),
        "pct_minus": percentile_rank(vi_m, cur_m),
        "pct_gap": percentile_rank(gap, cur_g),
        "after_gap": after_extremes(gap, closes),
        "after_plus": after_extremes(vi_p, closes),
        "div_buy": divergence(vi_p, lows, price_falls=True),
        "div_sell": divergence(vi_m, highs, price_falls=False),
        # хвосты для картинки
        "tail": {"t": times[-VORTEX_DIV_WINDOW:], "c": closes[-VORTEX_DIV_WINDOW:],
                 "p": vi_p[-VORTEX_DIV_WINDOW:], "m": vi_m[-VORTEX_DIV_WINDOW:]},
    }
    hot = VORTEX_EXTREME_PCT
    out["heat"] = ("перегрет вверх" if (out["pct_gap"] or 0) >= 100 - hot
                   else "перегрет вниз" if (out["pct_gap"] or 100) <= hot
                   else "в норме")
    return out


def compact(r: dict) -> dict | None:
    """Короткая форма для near_move.json и queue_log — без хвостов и таблиц."""
    if not r:
        return None
    t = r.get("turn") or {}
    return {"side": r["side"], "gap": r["gap"], "gap_dir": r["gap_dir"],
            "plus": r["vi_plus"], "minus": r["vi_minus"],
            "streak_plus": r["streak_plus"], "streak_minus": r["streak_minus"],
            "div_run_buy": r["div_run_buy"], "div_run_sell": r["div_run_sell"],
            "heat": r["heat"], "pct_gap": r["pct_gap"],
            "turn_side": t.get("side"), "turn_ago": t.get("ago")}


def read_symbol(symbol: str) -> dict:
    """Чтение по живым получасовкам биржи. Сеть — через core_binance."""
    from core_binance import klines_30m
    kl = klines_30m(symbol)
    r = read_klines(kl) if kl else {}
    if r:
        r["symbol"] = symbol
    return r


def say(r: dict) -> str:
    """Одна строка для подписи карточки: разрыв, направление, перегрев, дивергенция."""
    if not r:
        return "вихрь: мало баров"
    sp, sm = r["streak_plus"], r["streak_minus"]
    bits = [f"вихрь 30м {r['side']} · разрыв {r['gap']:+.2f} {r['gap_dir']}",
            f"покупатели {sp['dir']} {sp['n']} бар. · продавцы {sm['dir']} {sm['n']} бар.",
            f"{r['heat']} ({r['pct_gap']:.0f}% истории ниже)"]
    if r.get("turn"):
        bits.append(f"сторона сменилась: {r['turn']['side']} {r['turn']['ago']} бар. назад")
    if r.get("div_run_buy"):
        bits.append(f"покупатели вверх при цене вниз {r['div_run_buy']} бар. подряд")
    if r.get("div_run_sell"):
        bits.append(f"продавцы вверх при цене вверх {r['div_run_sell']} бар. подряд")
    if r.get("div_buy"):
        d = r["div_buy"]
        bits.append(f"дивергенция покупателей: лой линии {d['line_a']:.2f}→{d['line_b']:.2f} "
                    f"при цене ниже, {d['bars_ago']} бар. назад")
    if r.get("div_sell"):
        d = r["div_sell"]
        bits.append(f"зеркало продавцов: {d['line_a']:.2f}→{d['line_b']:.2f} при цене выше")
    return " · ".join(bits)


# ─────────────────────────────────────────────────────────────
# HTML из кода — чтобы проверить глазами по одной монете
# ─────────────────────────────────────────────────────────────
def render_html(r: dict) -> str:
    sym = r.get("symbol", "").replace("USDT", "")
    tail = r["tail"]
    W, H, PAD = 900, 220, 24
    n = len(tail["c"])

    def x(i: int) -> float:
        return PAD + (W - 2 * PAD) * i / max(n - 1, 1)

    def poly(vals: list, lo: float, hi: float, y0: float, h: float) -> str:
        pts = []
        for i, v in enumerate(vals):
            if v is None:
                continue
            y = y0 + h - (h * (v - lo) / (hi - lo) if hi > lo else h / 2)
            pts.append(f"{x(i):.1f},{y:.1f}")
        return " ".join(pts)

    cl = [v for v in tail["c"] if v is not None]
    lines = [v for v in tail["p"] + tail["m"] if v is not None]
    price_poly = poly(tail["c"], min(cl), max(cl), PAD, H - 2 * PAD)
    lo_l, hi_l = min(lines), max(lines)
    p_poly = poly(tail["p"], lo_l, hi_l, PAD, H - 2 * PAD)
    m_poly = poly(tail["m"], lo_l, hi_l, PAD, H - 2 * PAD)
    marks = ""
    d = r.get("div_buy")
    if d:
        ia, ib = d["bar_a"] - (r["bars"] - n), d["bar_b"] - (r["bars"] - n)
        if 0 <= ia < n and 0 <= ib < n:
            ya = PAD + (H - 2 * PAD) - (H - 2 * PAD) * (d["line_a"] - lo_l) / (hi_l - lo_l)
            yb = PAD + (H - 2 * PAD) - (H - 2 * PAD) * (d["line_b"] - lo_l) / (hi_l - lo_l)
            marks = (f'<line x1="{x(ia):.1f}" y1="{ya:.1f}" x2="{x(ib):.1f}" y2="{yb:.1f}" '
                     f'stroke="#f0a04b" stroke-width="3" stroke-linecap="round" opacity=".9"/>')

    def table(title: str, a: dict) -> str:
        if not a:
            return f"<div class='blk'><div class='t'>{title}</div><div class='dim'>истории мало</div></div>"
        rows = ""
        for tag, lbl in (("hi", f"верхние {VORTEX_EXTREME_PCT}% · порог {a['hi_thr']:+.2f}"),
                         ("lo", f"нижние {VORTEX_EXTREME_PCT}% · порог {a['lo_thr']:+.2f}")):
            cells = "".join(
                f"<td>{a[tag][h]['up_share']}% вверх · медиана {a[tag][h]['median']:+.1f}%</td>"
                if h in a[tag] else "<td class='dim'>—</td>" for h in VORTEX_HORIZONS)
            rows += f"<tr><th>{lbl}<br><span class='dim'>эпизодов {a[tag].get('episodes', 0)}</span></th>{cells}</tr>"
        heads = "".join(f"<td class='dim'>через {h} бар.</td>" for h in VORTEX_HORIZONS)
        return f"<div class='blk'><div class='t'>{title}</div><table><tr><th></th>{heads}</tr>{rows}</table></div>"

    at = datetime.fromtimestamp(r["at"] / 1000, tz=timezone.utc).strftime("%d.%m %H:%M UTC")
    div_txt = ""
    if d:
        div_txt = (f"<div class='blk hot'><div class='t'>дивергенция покупателей</div>"
                   f"лой линии {d['line_a']:.3f} → {d['line_b']:.3f}, лой цены {d['price_a']:g} → {d['price_b']:g}, "
                   f"второй лой {d['bars_ago']} баров назад</div>")
    ds = r.get("div_sell")
    if ds:
        div_txt += (f"<div class='blk'><div class='t'>зеркало продавцов (не проверено)</div>"
                    f"лой линии {ds['line_a']:.3f} → {ds['line_b']:.3f} при цене {ds['price_a']:g} → {ds['price_b']:g}</div>")
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>вихрь {sym}</title>
<style>
body{{margin:0;background:radial-gradient(1200px 600px at 30% -10%,#1b2433,#0b0f16 60%);color:#dfe6f0;font:15px/1.45 -apple-system,Inter,system-ui,sans-serif;padding:28px}}
h1{{font-weight:300;font-size:30px;letter-spacing:.02em;margin:0 0 4px}} .sub{{color:#8b97a8;margin-bottom:22px}}
.big{{display:flex;align-items:baseline;margin:6px 0 18px;flex-wrap:wrap}} .big>div{{margin:0 44px 10px 0}} .big b{{font-weight:200;font-size:56px;letter-spacing:-.02em}} .big b.h{{font-size:30px;font-weight:300}}
.big .p{{color:#6fb7ff}} .big .m{{color:#ff7a7a}} .big .g{{color:#f0a04b}} .lbl{{color:#8b97a8;font-size:13px;text-transform:uppercase;letter-spacing:.12em}}
svg{{display:block;width:100%;max-width:{W}px;background:linear-gradient(#0f1520,#0a0e15);border:1px solid #1f2a3a;border-radius:14px;box-shadow:0 20px 50px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.04)}}
.blk{{margin-top:18px;padding:14px 16px;border:1px solid #1f2a3a;border-radius:12px;background:rgba(255,255,255,.02)}}
.blk .t{{color:#8b97a8;font-size:12px;text-transform:uppercase;letter-spacing:.12em;margin-bottom:8px}}
.hot{{border-color:#f0a04b66;box-shadow:0 0 0 1px #f0a04b22,0 0 30px #f0a04b18}}
table{{border-collapse:collapse;width:100%}} td,th{{padding:6px 10px;text-align:left;border-top:1px solid #1a2331;font-weight:400;vertical-align:top}} .dim{{color:#6d7887}}
</style></head><body>
<h1>{sym} · вихрь 30м</h1>
<div class="sub">{at} · {r['bars']} баров истории · период {r['n']}</div>
<div class="big"><div><div class="lbl">покупатели</div><b class="p">{r['vi_plus']:.3f}</b><div class="dim">{r['streak_plus']['dir']} {r['streak_plus']['n']} бар.</div></div>
<div><div class="lbl">продавцы</div><b class="m">{r['vi_minus']:.3f}</b><div class="dim">{r['streak_minus']['dir']} {r['streak_minus']['n']} бар.</div></div>
<div><div class="lbl">разрыв · {r['gap_dir']}</div><b class="g">{r['gap']:+.3f}</b></div>
<div><div class="lbl">перегрев</div><b class="h">{r['heat']}</b><div class="dim">разрыв выше, чем в {r['pct_gap']:.0f}% истории · покупатели {r['pct_plus']:.0f}% · продавцы {r['pct_minus']:.0f}%</div></div></div>
<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">
<polyline points="{price_poly}" fill="none" stroke="#9aa6b8" stroke-width="1.2" opacity=".55"/>
<polyline points="{p_poly}" fill="none" stroke="#6fb7ff" stroke-width="1.8"/>
<polyline points="{m_poly}" fill="none" stroke="#ff7a7a" stroke-width="1.8"/>
{marks}
<text x="{PAD}" y="{H - 8}" fill="#6d7887" font-size="11">последние {n} баров · серая — цена, синяя — покупатели, красная — продавцы, оранжевая — дивергенция</text>
</svg>
{div_txt}
{table("что бывало после крайних значений РАЗРЫВА", r['after_gap'])}
{table("что бывало после крайних значений линии ПОКУПАТЕЛЕЙ", r['after_plus'])}
<div class="blk dim">{say(r)}</div>
</body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Быстрый вихрь по одной монете — чтение и картинка из кода")
    ap.add_argument("--only", required=True, help="символ, например IOSTUSDT")
    ap.add_argument("--json", action="store_true", help="напечатать чтение целиком")
    ap.add_argument("--div", action="store_true",
                    help="разбор поиска дивергенции: какие свинг-лои цены найдены и почему пара отвергнута")
    ap.add_argument("--events", action="store_true",
                    help="все бары месяца, где сторона сменилась, и ход цены после — проверка на дубль с силой")
    ap.add_argument("--tail", type=int, default=0,
                    help="напечатать последние N баров: время, low, close, VI+, VI− — для сверки с графиком "
                         "и для настройки дивергенции на живом ряде")
    a = ap.parse_args()
    sym = a.only.upper()
    if not sym.endswith("USDT"):
        sym += "USDT"
    r = read_symbol(sym)
    if not r:
        print(f"{sym}: свечей нет или мало")
        return
    print(say(r))
    if a.events:
        from core_binance import K_CLOSE, K_HIGH, K_LOW, K_OPEN_TIME, klines_30m, series
        kl = klines_30m(sym)
        hi, lo, cl = series(kl, K_HIGH), series(kl, K_LOW), series(kl, K_CLOSE)
        vp, vm = vortex_lines(hi, lo, cl)
        evs = turn_events(vp, vm, cl)
        print(f"событий «сторона сменилась» за {len(cl)} баров: {len(evs)}")
        for e in evs:
            t = datetime.fromtimestamp(int(kl[e['bar']][K_OPEN_TIME]) / 1000, tz=timezone.utc).strftime("%d.%m %H:%M")
            hs = " · ".join(f"{h}б {e[f'h{h}']:+.1f}%" if e[f'h{h}'] is not None else f"{h}б —" for h in VORTEX_HORIZONS)
            print(f"  {t} UTC  {e['side']:<10} цена {e['close']:g} · после: {hs}")
        for side in ("продавцы", "покупатели"):
            sub = [e for e in evs if e["side"] == side]
            for h in VORTEX_HORIZONS:
                v = [e[f"h{h}"] for e in sub if e[f"h{h}"] is not None]
                if v:
                    print(f"  итог {side}: через {h} бар. n={len(v)} · вверх {100 * sum(x > 0 for x in v) / len(v):.0f}% · медиана {st.median(v):+.2f}%")
    if a.div:
        from core_binance import K_CLOSE, K_HIGH, K_LOW, K_OPEN_TIME, klines_30m, series
        kl = klines_30m(sym)
        hi, lo, cl = series(kl, K_HIGH), series(kl, K_LOW), series(kl, K_CLOSE)
        vp, _ = vortex_lines(hi, lo, cl)
        n_ = len(cl)
        start = max(0, n_ - VORTEX_DIV_WINDOW)
        for lbl, ext in (("по МИНИМУМАМ баров", lo), ("по ЗАКРЫТИЯМ", cl)):
            sw = _swing_lows(ext, start)
            print(f"свинг-лои цены в окне {VORTEX_DIV_WINDOW} баров, {lbl}:")
            for i in sw:
                t = datetime.fromtimestamp(int(kl[i][K_OPEN_TIME]) / 1000, tz=timezone.utc).strftime("%d.%m %H:%M")
                ln = _line_near(vp, i)
                print(f"  бар {n_ - 1 - i:>2} назад · {t} · цена {ext[i]:g} · лой линии рядом {'—' if ln is None else f'{ln:.3f}'}")
            print("  результат:", divergence(vp, ext, price_falls=True))
    if a.tail:
        from core_binance import K_CLOSE, K_HIGH, K_LOW, K_OPEN_TIME, klines_30m, series
        kl = klines_30m(sym)
        hi, lo, cl = series(kl, K_HIGH), series(kl, K_LOW), series(kl, K_CLOSE)
        vp, vm = vortex_lines(hi, lo, cl)
        print("свеча UTC        low        high       close      VI+     VI-")
        for i in range(max(0, len(cl) - a.tail), len(cl)):
            t = datetime.fromtimestamp(int(kl[i][K_OPEN_TIME]) / 1000, tz=timezone.utc).strftime("%d.%m %H:%M")
            p_, m_ = vp[i], vm[i]
            print(f"{t}  {lo[i]:<10g} {hi[i]:<10g} {cl[i]:<10g} "
                  f"{'—' if p_ is None else f'{p_:.4f}'}  {'—' if m_ is None else f'{m_:.4f}'}")
    if a.json:
        slim = {k: v for k, v in r.items() if k != "tail"}
        print(json.dumps(slim, ensure_ascii=False, indent=1))
    from sources_storage import write_atomic  # запись через общий атомарный писатель
    path = OUTPUT_DIR / VORTEX_HTML.name.format(sym=sym.replace("USDT", "").lower())
    write_atomic(path, render_html(r))
    print(f"картинка: {path}")


if __name__ == "__main__":
    main()
