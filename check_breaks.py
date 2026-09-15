#!/usr/bin/env python3
"""ПРОВЕРКА ПРАВИЛА СЛОМА НА ЭПИЗОДАХ ЛИДЕРОВ (15.09; правило владельца 11.09: индикатор проверяется не по истории
месяца, а на эпизодах лидеров из очереди — от бара, когда монета стала первой, до разворота). Берёт эпизоды
первых мест из queue_log.jsonl (серии place == 1), тянет получасовки через core_binance.get_klines (без дыр),
считает вортекс (VORTEX_N) и клингер TradingView (KLINGER_30M_EMA) и для каждого эпизода отвечает числами:

  • вершина после входа в первые (макс. закрытие за CHECK_BARS баров) и на каком баре она была;
  • первый слом ВНИЗ по разрыву после вершины — через сколько баров после неё (0 — на самом баре вершины);
  • пересечение линий — через сколько баров после вершины (для сравнения: как поздно старый сигнал);
  • сколько баров ход отдал от вершины к бару слома и к бару креста (в %);
  • ложные сломы ДО вершины — сколько «вниз» сработало, пока цена ещё шла вверх;
  • сколько сломов в штиле (диапазон 6 баров < FLAT_PCT) — шум правила при пороге BRK_MIN.

Итог — таблица по эпизодам и сводка: медиана «баров после вершины» для слома и креста, доля ложных.
Запуск: `python3 check_breaks.py --only ARK` (один эпизод), `python3 check_breaks.py --days 14`.
Ничего не пишет, только печатает; в прогон не входит.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
try:
    from core_config import KLINGER_30M_EMA, VORTEX_N
except ImportError:
    KLINGER_30M_EMA, VORTEX_N = (34, 55, 13), 14

CHECK_BARS = 96      # два дня после входа в первые
BRK_MIN_VX = 0.25
BRK_MIN_KL = 0.25
FLAT_PCT = 3.0
EXT = 6


def ema(xs, p):
    o, e, k = [], None, 2 / (p + 1)
    for x in xs:
        e = x if e is None else e + (x - e) * k
        o.append(e)
    return o


def series(bars):
    """bars: (t, h, l, c, vol) → (gap_vx, gap_kl) по барам (None, где не хватает истории)."""
    n = VORTEX_N
    gv = [None] * len(bars)
    for i in range(n, len(bars)):
        vp = vm = tr = 0.0
        for k in range(i - n + 1, i + 1):
            _, h, l, _, _ = bars[k]
            _, ph, pl, pc, _ = bars[k - 1]
            vp += abs(h - pl)
            vm += abs(l - ph)
            tr += max(h - l, abs(h - pc), abs(l - pc))
        gv[i] = (vp - vm) / tr if tr else None
    sv, prev = [], None
    for _, h, l, c, v in bars:
        hlc = (h + l + c) / 3
        sv.append(v if (prev is None or hlc >= prev) else -v)
        prev = hlc
    f1, f2, f3 = KLINGER_30M_EMA
    kvo = [a - b for a, b in zip(ema(sv, f1), ema(sv, f2))]
    sig = ema(kvo, f3)
    gk = [None] * len(bars)
    for i in range(f2, len(bars)):
        gk[i] = kvo[i] - sig[i]
    return gv, gk


def breaks(g, big):
    out = [0] * len(g)
    for i in range(EXT + 1, len(g)):
        if g[i] is None or g[i - 1] is None:
            continue
        w = [x for x in g[i - EXT:i] if x is not None]
        if not w:
            continue
        if g[i] < g[i - 1] and g[i - 1] >= max(w) and g[i - 1] >= big:
            out[i] = -1
        elif g[i] > g[i - 1] and g[i - 1] <= min(w) and g[i - 1] <= -big:
            out[i] = 1
    return out


def crosses(g):
    out = [0] * len(g)
    for i in range(1, len(g)):
        if g[i] is None or g[i - 1] is None:
            continue
        if g[i - 1] > 0 >= g[i]:
            out[i] = -1
        elif g[i - 1] < 0 <= g[i]:
            out[i] = 1
    return out


def episodes(days: int, only: str | None):
    p = BASE_DIR / "output" / "queue_log.jsonl"
    if not p.exists():
        p = BASE_DIR / "queue_log.jsonl"
    recs = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            recs.append(json.loads(line))
        except ValueError:
            continue
    recs.sort(key=lambda r: r["at"])
    since = datetime.now(timezone.utc).timestamp() - days * 86400
    eps, cur = [], {}
    runs = sorted(set(r["at"] for r in recs))
    firsts = {}
    for r in recs:
        if r.get("place") == 1:
            firsts.setdefault(r["at"], set()).add(r["sym"])
    for at in runs:
        now = firsts.get(at, set())
        for s in list(cur):
            if s not in now:
                eps.append(cur.pop(s))
        for s in now:
            if s in cur:
                cur[s]["n"] += 1
            else:
                cur[s] = {"sym": s, "start": at, "n": 1}
    eps += list(cur.values())
    out = []
    for e in eps:
        t = datetime.strptime(e["start"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
        if t < since or e["n"] < 3:      # эпизод — удержание хотя бы три прогона, как звезда
            continue
        if only and e["sym"] != only:
            continue
        out.append(dict(e, t_ms=int(t * 1000)))
    return out


def check(ep, bars):
    idx0 = next((i for i, b in enumerate(bars) if b[0] >= ep["t_ms"]), None)
    if idx0 is None or idx0 + 8 >= len(bars):
        return None
    gv, gk = series(bars)
    bv, bk, cv = breaks(gv, BRK_MIN_VX), None, crosses(gv)
    mxk = max([abs(x) for x in gk if x is not None] + [1e-9])
    bk = breaks(gk, BRK_MIN_KL * mxk)
    end = min(len(bars), idx0 + CHECK_BARS)
    top = max(range(idx0, end), key=lambda i: bars[i][3])
    px_top = bars[top][3]
    def first_after(arr, val, start):
        for i in range(start, end):
            if arr[i] == val:
                return i
        return None
    b_vx = first_after(bv, -1, top)
    b_kl = first_after(bk, -1, top)
    c_vx = first_after(cv, -1, top)
    false_vx = sum(1 for i in range(idx0, top) if bv[i] == -1)
    flat_noise = 0
    for i in range(idx0, end):
        if bv[i] and i >= 6:
            rng = (max(b[3] for b in bars[i - 6:i]) / min(b[3] for b in bars[i - 6:i]) - 1) * 100
            if rng < FLAT_PCT:
                flat_noise += 1
    def gave(i):
        return round((bars[i][3] / px_top - 1) * 100, 1) if i is not None else None
    return {"sym": ep["sym"], "start": ep["start"][5:16], "runs": ep["n"], "top_bar": top - idx0,
            "top_pct": round((px_top / bars[idx0][3] - 1) * 100, 1),
            "vx_after": (b_vx - top) if b_vx is not None else None, "vx_gave": gave(b_vx),
            "kl_after": (b_kl - top) if b_kl is not None else None, "kl_gave": gave(b_kl),
            "cross_after": (c_vx - top) if c_vx is not None else None, "cross_gave": gave(c_vx),
            "false_before_top": false_vx, "flat_noise": flat_noise}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--days", type=int, default=14)
    a = ap.parse_args()
    only = (a.only.upper() + ("" if a.only.upper().endswith("USDT") else "USDT")) if a.only else None
    eps = episodes(a.days, only)
    if not eps:
        print("эпизодов первых (≥3 прогона) за период нет")
        return 0
    import core_binance as cb
    from core_binance import K_HIGH, K_LOW, K_OPEN_TIME, get_klines
    KC, KQ = getattr(cb, "K_CLOSE", 4), getattr(cb, "K_QUOTE_VOLUME", 7)
    rows = []
    for ep in eps:
        ks = get_klines(ep["sym"], "30m", limit=500) or []
        bars = sorted((int(k[K_OPEN_TIME]), float(k[K_HIGH]), float(k[K_LOW]), float(k[KC]), float(k[KQ])) for k in ks)
        r = check(ep, bars)
        if r:
            rows.append(r)
            print(f"{r['sym']:<12} {r['start']} серия {r['runs']:>2} · вершина через {r['top_bar']:>2} бар (+{r['top_pct']}%) · "
                  f"слом вортекса через {r['vx_after']} бар ({r['vx_gave']}%) · клингер {r['kl_after']} ({r['kl_gave']}%) · "
                  f"крест {r['cross_after']} ({r['cross_gave']}%) · ложных до вершины {r['false_before_top']} · в штиле {r['flat_noise']}")
    if rows:
        def med(key):
            v = [r[key] for r in rows if r[key] is not None]
            return statistics.median(v) if v else None
        print(f"\nэпизодов {len(rows)} · медиана: слом вортекса через {med('vx_after')} бар после вершины (отдано {med('vx_gave')}%), "
              f"клингер {med('kl_after')} ({med('kl_gave')}%), крест {med('cross_after')} ({med('cross_gave')}%) · "
              f"ложных до вершины всего {sum(r['false_before_top'] for r in rows)} · сломов в штиле {sum(r['flat_noise'] for r in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
